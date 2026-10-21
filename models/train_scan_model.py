"""Train the wound-photo model used by the app's Scan feature.

Pipeline: CLIP ViT-B/32 image embeddings (ONNX, via fastembed -- no PyTorch needed) ->
logistic regression heads. Data: data/images/wound_hf (huggingface.co/datasets/rupeshsah/wound,
Apache-2.0, 1,564 images).

What the labels are worth, and how this script treats them:
  * `type` comes from the image collection (pressure / diabetic / venous / ...) -> trained and reported.
  * `severity` and `description` look machine-generated (e.g. a "venous" wound described with
    "charred tissue"), so severity is only kept if it beats a baseline that guesses severity from
    the TRUE wound type alone. If it does not, the model is just re-learning the type.
  * There are no infection or healing-time labels in this data, so nothing here predicts them.

Evaluation is grouped: near-duplicate images (scraped datasets are full of them) are clustered and
kept on one side of each split, otherwise accuracy is inflated by memorised copies.
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from fastembed import ImageEmbedding
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "images" / "wound_hf"
CACHE = ROOT / "data" / "images" / "clip_b32_embeddings.npy"
OUT = ROOT / "models" / "scan"
EMBED_MODEL = "Qdrant/clip-ViT-B-32-vision"
DUP_SIM = 0.97  # cosine similarity above which two images are treated as the same photo


def load_rows():
    with open(DATA / "metadata.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def embed_all(paths):
    if CACHE.exists():
        e = np.load(CACHE)
        if len(e) == len(paths):
            return e
    model = ImageEmbedding(EMBED_MODEL)
    vecs = []
    for i, v in enumerate(model.embed([str(p) for p in paths], batch_size=32)):
        vecs.append(v)
        if (i + 1) % 200 == 0:
            print(f"  embedded {i + 1}/{len(paths)}", flush=True)
    e = np.vstack(vecs).astype("float32")
    np.save(CACHE, e)
    return e


def duplicate_groups(x):
    """Union-find over pairs with cosine similarity >= DUP_SIM. x must be L2-normalised."""
    n = len(x)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    sims = x @ x.T
    np.fill_diagonal(sims, 0)
    ii, jj = np.where(np.triu(sims) >= DUP_SIM)
    for a, b in zip(ii, jj):
        parent[find(a)] = find(b)
    groups = np.array([find(i) for i in range(n)])
    return groups, int(len(ii))


def make_clf(c):
    return LogisticRegression(C=c, max_iter=3000, class_weight="balanced")


def cv_eval(x, y, groups, c, folds=5, seed=0):
    """Out-of-fold predictions + the nearest-training-image similarity of each held-out image."""
    pred = np.empty(len(y), dtype=object)
    nn_sim = np.zeros(len(y))
    for tr, te in StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed).split(x, y, groups):
        clf = make_clf(c).fit(x[tr], y[tr])
        pred[te] = clf.predict(x[te])
        nn_sim[te] = (x[te] @ x[tr].T).max(axis=1)
    return pred, nn_sim


def main():
    rows = load_rows()
    paths = [DATA / "images" / r["img_path"] for r in rows]
    types = np.array([r["type"] for r in rows])
    sev = np.array([r["severity"] for r in rows])

    print(f"{len(rows)} images; embedding with {EMBED_MODEL} ...", flush=True)
    x = embed_all(paths)
    x = x / np.linalg.norm(x, axis=1, keepdims=True)

    groups, dup_pairs = duplicate_groups(x)
    n_groups = len(set(groups))
    print(f"near-duplicate pairs (cos >= {DUP_SIM}): {dup_pairs}; independent groups: {n_groups}/{len(rows)}")

    # pick C by grouped CV on wound type (small grid)
    best_c, best_f1, results = None, -1, {}
    for c in (0.5, 2.0, 8.0):
        pred, _ = cv_eval(x, types, groups, c)
        f1 = f1_score(types, pred, average="macro")
        results[c] = round(float(f1), 3)
        if f1 > best_f1:
            best_c, best_f1 = c, f1
    print("type macro-F1 by C:", results, "-> C =", best_c)

    type_pred, nn_sim = cv_eval(x, types, groups, best_c)
    classes = sorted(set(types))
    type_acc = accuracy_score(types, type_pred)
    type_f1 = f1_score(types, type_pred, average="macro")
    type_cm = confusion_matrix(types, type_pred, labels=classes)
    per_class = {c: round(float((type_pred[types == c] == c).mean()), 3) for c in classes}
    majority = max(set(types), key=list(types).count)
    print(f"TYPE: acc {type_acc:.3f}  macro-F1 {type_f1:.3f}  (majority-class baseline "
          f"{(types == majority).mean():.3f})")
    print("per-class recall:", per_class)

    # severity: image model vs. a baseline that knows the TRUE wound type but ignores the image
    sev_pred, _ = cv_eval(x, sev, groups, best_c)
    sev_acc = accuracy_score(sev, sev_pred)
    sev_f1 = f1_score(sev, sev_pred, average="macro")
    base_pred = np.empty(len(rows), dtype=object)
    for tr, te in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(x, types, groups):
        for t in set(types[te]):
            tr_t = tr[types[tr] == t]
            vals, cnt = np.unique(sev[tr_t], return_counts=True)
            base_pred[te[types[te] == t]] = vals[cnt.argmax()]
    base_acc = accuracy_score(sev, base_pred)
    base_f1 = f1_score(sev, base_pred, average="macro")
    print(f"SEVERITY: image model acc {sev_acc:.3f} F1 {sev_f1:.3f} | type-only baseline acc {base_acc:.3f} F1 {base_f1:.3f}")
    severity_adds_signal = bool(sev_f1 > base_f1 + 0.03)
    print("severity kept:", severity_adds_signal)

    # out-of-distribution threshold: photos far from anything seen in training
    ood_threshold = float(np.percentile(nn_sim, 5))
    print(f"nearest-neighbour similarity of held-out images: median {np.median(nn_sim):.3f}, "
          f"5th pct {ood_threshold:.3f}")

    # final models on all data
    OUT.mkdir(exist_ok=True)
    type_clf = make_clf(best_c).fit(x, types)
    joblib.dump(type_clf, OUT / "type_model.pkl")
    if severity_adds_signal:
        joblib.dump(make_clf(best_c).fit(x, sev), OUT / "severity_model.pkl")
    np.save(OUT / "train_embeddings.npy", x.astype("float16"))

    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "embedding_model": EMBED_MODEL,
        "dataset": "huggingface.co/datasets/rupeshsah/wound (Apache-2.0)",
        "images": len(rows),
        "near_duplicate_pairs": dup_pairs,
        "independent_groups": n_groups,
        "type": {
            "classes": classes,
            "cv_accuracy": round(float(type_acc), 3),
            "cv_macro_f1": round(float(type_f1), 3),
            "majority_baseline": round(float((types == majority).mean()), 3),
            "per_class_recall": per_class,
            "confusion_matrix": type_cm.tolist(),
        },
        "severity": {
            "kept": severity_adds_signal,
            "cv_accuracy": round(float(sev_acc), 3),
            "cv_macro_f1": round(float(sev_f1), 3),
            "type_only_baseline_macro_f1": round(float(base_f1), 3),
            "note": "Labels look machine-generated; kept only if it beats guessing from the true type.",
        },
        "ood_similarity_threshold": round(ood_threshold, 4),
        "caveats": [
            "Wound-type labels come from an image collection; severity/description text looks machine-generated.",
            "No infection or healing-time labels exist in this data; the model predicts neither.",
            "Images are web-collected at 350x350, not clinical photos taken with a standard protocol.",
            "Cross-validated, duplicate-grouped accuracy; not clinical validation.",
        ],
    }
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2))
    print("saved", OUT)


if __name__ == "__main__":
    main()
