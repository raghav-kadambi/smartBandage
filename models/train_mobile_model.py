"""Train the reduced-feature model used by the mobile app.

The web app's model needs pH, exudate and oxygen saturation. The hardware available
today only gives temperature, humidity and a moisture reading, so this trains a separate
RandomForest on just those three columns and saves it under models/mobile/ -- the web
app's models/*.pkl are not touched.

Assumption (stated, not proven): the bandage's moisture sensor reading is scaled to the
same 0-10 range as the dataset's `exudate_level` column and treated as a proxy for it.
Labels and healing days come from the same CSV as the web app. Its provenance should be
confirmed (near-perfect class separation suggests generated data), so the accuracy here is
not evidence of clinical performance.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "augmented_training_data.csv"
OUT = ROOT / "models" / "mobile"

# model feature name -> column in the CSV
COLUMN_FOR = {"temperature": "temperature", "humidity": "humidity", "moisture": "exudate_level"}
FEATURES = list(COLUMN_FOR)


def main():
    df = pd.read_csv(DATA)
    X = df[[COLUMN_FOR[f] for f in FEATURES]].values
    y = df["condition"].values
    days = df["healing_days"].values

    Xtr, Xte, ytr, yte, dtr, dte = train_test_split(
        X, y, days, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(n_estimators=300, max_depth=10, random_state=42, n_jobs=-1)
    clf.fit(Xtr, ytr)
    acc = accuracy_score(yte, clf.predict(Xte))

    reg = RandomForestRegressor(n_estimators=300, max_depth=10, random_state=42, n_jobs=-1)
    reg.fit(Xtr, dtr)
    pred = reg.predict(Xte)
    mae, r2 = mean_absolute_error(dte, pred), r2_score(dte, pred)

    OUT.mkdir(exist_ok=True)
    joblib.dump(clf, OUT / "condition_model.pkl")
    joblib.dump(reg, OUT / "healing_model.pkl")

    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "features": FEATURES,
        "classes": [str(c) for c in clf.classes_],
        "training_rows": int(len(df)),
        "synthetic_rows": int(df["is_synthetic"].sum()) if "is_synthetic" in df else None,
        "condition_accuracy_holdout": round(float(acc), 3),
        "healing_mae_days_holdout": round(float(mae), 2),
        "healing_r2_holdout": round(float(r2), 3),
        "feature_importance": {f: round(float(v), 3) for f, v in zip(FEATURES, clf.feature_importances_)},
        "caveats": [
            "Source CSV is flagged as non-synthetic but is almost perfectly separable; confirm "
            "where it came from. Holdout accuracy is not clinical validation either way.",
            "Healing days come from a severity heuristic, not real patient outcomes.",
            "The moisture sensor is assumed to map onto the dataset's exudate_level (0-10).",
        ],
    }
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
