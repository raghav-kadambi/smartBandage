"""
Train two models for the Smart Wound-Care Bandage demo, and record honest, detailed
quality metrics so the app's "Model insights" page can show the reviewer exactly how
good (or not) the models are, and how much of the training data is real vs synthetic.

1. condition_model  -> classifies sensor readings into healthy / wound_healing / infected
2. healing_model    -> regresses estimated days-to-heal from sensor readings

Change DATA_PATH below to point at whatever labelled CSV you currently have
(pH, temperature, humidity, exudate_level, oxygen_saturation, condition columns).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    mean_absolute_error,
    r2_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.preprocessing import LabelEncoder
import joblib

ROOT = Path(__file__).resolve().parent.parent

# ---- point this at your current labelled CSV ----
DATA_PATH = ROOT / "data" / "wound_data_train.csv"

OUT_DIR = ROOT / "models"

FEATURES = ["pH", "temperature", "humidity", "exudate_level", "oxygen_saturation"]
RNG = np.random.default_rng(42)

FEATURE_RANGES = {
    "pH": (4.0, 10.0),
    "temperature": (25.0, 40.0),
    "humidity": (10.0, 100.0),
    "exudate_level": (0.0, 10.0),
    "oxygen_saturation": (30.0, 100.0),
}

AUGMENT_TARGET_PER_CLASS = 250


def load_seed_data():
    df = pd.read_csv(DATA_PATH)
    missing = set(FEATURES + ["condition"]) - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")
    bad_labels = set(df["condition"].unique()) - {"healthy", "wound_healing", "infected"}
    if bad_labels:
        raise ValueError(
            f"Unexpected condition labels found: {bad_labels}. "
            "Expected only healthy / wound_healing / infected."
        )
    return df


def augment_gaussian(df, target_per_class=AUGMENT_TARGET_PER_CLASS):
    """Fit a per-class Gaussian to real rows and sample synthetic rows from it, ONLY
    topping a class up to `target_per_class` -- classes with enough real data already
    are left alone (or barely touched). Every row is tagged is_synthetic so the app
    can report the real-vs-synthetic mix honestly."""
    df = df.copy()
    df["is_synthetic"] = False
    frames = [df]

    for cond, group in df.groupby("condition"):
        n_real = len(group)
        n_needed = max(0, target_per_class - n_real)
        if n_needed == 0:
            continue
        X = group[FEATURES].values
        mean = X.mean(axis=0)
        cov = np.cov(X, rowvar=False) + np.eye(len(FEATURES)) * 1e-2 if n_real > 1 else np.eye(len(FEATURES)) * 0.5
        samples = RNG.multivariate_normal(mean, cov, size=n_needed)
        for i, feat in enumerate(FEATURES):
            lo, hi = FEATURE_RANGES[feat]
            samples[:, i] = np.clip(samples[:, i], lo, hi)
        synth = pd.DataFrame(samples, columns=FEATURES)
        synth["condition"] = cond
        synth["is_synthetic"] = True
        frames.append(synth)

    full = pd.concat(frames, ignore_index=True)
    return full


def synthesize_healing_days(df):
    """Transparent heuristic -> days-to-heal. Not learned from real outcomes -- there is
    no real longitudinal healing-time dataset yet. Replace this once you have one."""
    healthy_centroid = {
        "pH": 7.15, "temperature": 31.5, "humidity": 47.0,
        "exudate_level": 1.8, "oxygen_saturation": 88.0,
    }
    spans = {k: (FEATURE_RANGES[k][1] - FEATURE_RANGES[k][0]) for k in FEATURES}

    severity = np.zeros(len(df))
    for feat in FEATURES:
        direction = -1 if feat == "oxygen_saturation" else 1
        delta = (df[feat] - healthy_centroid[feat]) / spans[feat]
        severity += np.clip(direction * delta, 0, None)
    severity = severity / severity.max() if severity.max() > 0 else severity

    base_days = {"healthy": (0, 3), "wound_healing": (5, 16), "infected": (14, 30)}
    days = np.zeros(len(df))
    for cond, (lo, hi) in base_days.items():
        mask = df["condition"] == cond
        days[mask] = lo + severity[mask] * (hi - lo)

    noise = RNG.normal(0, 1.2, size=len(df))
    return np.clip(days + noise, 0, 35)


def main():
    seed = load_seed_data()
    seed_counts = seed["condition"].value_counts().to_dict()
    print(f"Real (seed) rows: {len(seed)} -> {seed_counts}")

    augmented = augment_gaussian(seed)
    aug_counts = augmented["condition"].value_counts().to_dict()
    real_count = int((~augmented["is_synthetic"]).sum())
    synthetic_count = int(augmented["is_synthetic"].sum())
    print(f"Training rows after augmentation: {len(augmented)} "
          f"(real: {real_count}, synthetic: {synthetic_count}) -> {aug_counts}")

    augmented["healing_days"] = synthesize_healing_days(augmented)

    X = augmented[FEATURES].values
    y_class_raw = augmented["condition"].values
    y_days = augmented["healing_days"].values
    is_synth = augmented["is_synthetic"].values

    le = LabelEncoder()
    y_class = le.fit_transform(y_class_raw)
    class_names = list(le.classes_)

    (X_train, X_test, yc_train, yc_test, yd_train, yd_test,
     synth_train, synth_test) = train_test_split(
        X, y_class, y_days, is_synth, test_size=0.2, random_state=42, stratify=y_class
    )

    # ---- condition classifier ----
    clf = RandomForestClassifier(n_estimators=300, max_depth=8, random_state=42)
    clf.fit(X_train, yc_train)
    yc_pred = clf.predict(X_test)
    acc = accuracy_score(yc_test, yc_pred)
    precision, recall, f1, support = precision_recall_fscore_support(
        yc_test, yc_pred, labels=range(len(class_names)), zero_division=0
    )
    cm = confusion_matrix(yc_test, yc_pred, labels=range(len(class_names)))
    feat_importance_clf = dict(zip(FEATURES, clf.feature_importances_.tolist()))

    # accuracy measured only on real (non-synthetic) held-out rows, if there are any
    real_test_mask = synth_test == False  # noqa: E712
    if real_test_mask.sum() > 0:
        acc_real_only = accuracy_score(yc_test[real_test_mask], clf.predict(X_test[real_test_mask]))
    else:
        acc_real_only = None

    print(f"Condition classifier accuracy (held-out, incl. synthetic): {acc:.3f}")
    if acc_real_only is not None:
        print(f"Condition classifier accuracy (held-out, REAL rows only, n={int(real_test_mask.sum())}): {acc_real_only:.3f}")

    # ---- healing-days regressor ----
    reg = RandomForestRegressor(n_estimators=300, max_depth=8, random_state=42)
    reg.fit(X_train, yd_train)
    yd_pred = reg.predict(X_test)
    mae = mean_absolute_error(yd_test, yd_pred)
    r2 = r2_score(yd_test, yd_pred)
    feat_importance_reg = dict(zip(FEATURES, reg.feature_importances_.tolist()))
    print(f"Healing-days regressor MAE: {mae:.2f} days | R^2: {r2:.3f}")

    OUT_DIR.mkdir(exist_ok=True)
    joblib.dump(clf, OUT_DIR / "condition_model.pkl")
    joblib.dump(reg, OUT_DIR / "healing_model.pkl")
    joblib.dump(le, OUT_DIR / "label_encoder.pkl")

    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_source_file": DATA_PATH.name,
        "features": FEATURES,
        "feature_ranges": FEATURE_RANGES,
        "classes": class_names,

        "data_quality": {
            "seed_rows_total": int(len(seed)),
            "seed_class_distribution": {k: int(v) for k, v in seed_counts.items()},
            "training_rows_total": int(len(augmented)),
            "training_rows_real": real_count,
            "training_rows_synthetic": synthetic_count,
            "synthetic_pct": round(100 * synthetic_count / len(augmented), 1),
            "training_class_distribution": {k: int(v) for k, v in aug_counts.items()},
            "augmentation_method": (
                "Per-class Gaussian (mean+covariance) fit to real rows, sampled and "
                "clipped to plausible sensor ranges, only topping classes up to "
                f"{AUGMENT_TARGET_PER_CLASS} rows."
            ),
            "healing_days_source": (
                "Heuristic severity score (distance from a healthy centroid), NOT learned "
                "from real patient outcomes -- no real healing-time dataset exists yet."
            ),
        },

        "condition_model": {
            "algorithm": "RandomForestClassifier",
            "accuracy_holdout_all": round(float(acc), 3),
            "accuracy_holdout_real_only": round(float(acc_real_only), 3) if acc_real_only is not None else None,
            "real_only_test_n": int(real_test_mask.sum()),
            "per_class": [
                {
                    "class": class_names[i],
                    "precision": round(float(precision[i]), 3),
                    "recall": round(float(recall[i]), 3),
                    "f1": round(float(f1[i]), 3),
                    "support": int(support[i]),
                }
                for i in range(len(class_names))
            ],
            "confusion_matrix": cm.tolist(),
            "confusion_matrix_labels": class_names,
            "feature_importance": {k: round(v, 3) for k, v in feat_importance_clf.items()},
        },

        "healing_model": {
            "algorithm": "RandomForestRegressor",
            "mae_days_holdout": round(float(mae), 2),
            "r2_holdout": round(float(r2), 3),
            "feature_importance": {k: round(v, 3) for k, v in feat_importance_reg.items()},
        },
    }

    with open(OUT_DIR / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)

    augmented.to_csv(ROOT / "data" / "augmented_training_data.csv", index=False)
    print("Saved condition_model.pkl, healing_model.pkl, label_encoder.pkl, metadata.json")


if __name__ == "__main__":
    main()