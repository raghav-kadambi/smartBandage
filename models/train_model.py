"""
Train the two WoundSense Random Forest models on the 4 bandage signals
(temperature, humidity, heart rate, blood pressure as systolic + diastolic):

1. condition_model -> classifies a reading as healthy / wound_healing / infected
2. healing_model   -> regresses estimated days-to-heal

Training data: data/wound_data_train.csv, the knowledge-based set produced by
data/generate_training_data.py (class distributions set from published clinical criteria).
Internal metrics below are on a held-out split of that set. The *external* test on real
patients (PhysioNet 2019, never used for training) is validation/validate_physionet2019.py.

Usage:  python models/train_model.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    precision_recall_fscore_support,
    r2_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import LabelEncoder

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "wound_data_train.csv"
OUT_DIR = ROOT / "models"

FEATURES = ["temperature", "humidity", "heart_rate", "systolic_bp", "diastolic_bp"]
FEATURE_RANGES = {
    "temperature": (34.0, 42.0),
    "humidity": (10.0, 100.0),
    "heart_rate": (35.0, 180.0),
    "systolic_bp": (70.0, 200.0),
    "diastolic_bp": (35.0, 120.0),
}

CLF_PARAMS = dict(n_estimators=300, max_depth=12, min_samples_leaf=5, random_state=42, n_jobs=-1)
REG_PARAMS = dict(n_estimators=300, max_depth=12, min_samples_leaf=5, random_state=42, n_jobs=-1)


def load_data():
    df = pd.read_csv(DATA_PATH)
    missing = set(FEATURES + ["condition", "healing_days"]) - set(df.columns)
    if missing:
        raise ValueError(f"{DATA_PATH.name} is missing columns {missing}; run data/generate_training_data.py")
    return df


def main():
    df = load_data()
    counts = df["condition"].value_counts().to_dict()
    print(f"Training rows: {len(df)} -> {counts}")

    X = df[FEATURES].values
    le = LabelEncoder()
    y_class = le.fit_transform(df["condition"].values)
    y_days = df["healing_days"].values
    class_names = list(le.classes_)

    X_train, X_test, yc_train, yc_test, yd_train, yd_test = train_test_split(
        X, y_class, y_days, test_size=0.2, random_state=42, stratify=y_class
    )

    # ---- condition classifier ----
    clf = RandomForestClassifier(**CLF_PARAMS)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_acc = cross_val_score(RandomForestClassifier(**CLF_PARAMS), X_train, yc_train, cv=cv, scoring="accuracy")
    clf.fit(X_train, yc_train)
    yc_pred = clf.predict(X_test)
    acc = accuracy_score(yc_test, yc_pred)
    macro_f1 = f1_score(yc_test, yc_pred, average="macro")
    precision, recall, f1, support = precision_recall_fscore_support(
        yc_test, yc_pred, labels=range(len(class_names)), zero_division=0
    )
    cm = confusion_matrix(yc_test, yc_pred, labels=range(len(class_names)))
    print(f"Classifier: held-out accuracy {acc:.3f}, macro-F1 {macro_f1:.3f}, "
          f"5-fold CV accuracy {cv_acc.mean():.3f} +/- {cv_acc.std():.3f}")

    # ---- healing-days regressor ----
    reg = RandomForestRegressor(**REG_PARAMS)
    reg.fit(X_train, yd_train)
    yd_pred = reg.predict(X_test)
    mae = mean_absolute_error(yd_test, yd_pred)
    r2 = r2_score(yd_test, yd_pred)
    print(f"Regressor: held-out MAE {mae:.2f} days | R^2 {r2:.3f}")

    OUT_DIR.mkdir(exist_ok=True)
    joblib.dump(clf, OUT_DIR / "condition_model.pkl", compress=3)
    joblib.dump(reg, OUT_DIR / "healing_model.pkl", compress=3)
    joblib.dump(le, OUT_DIR / "label_encoder.pkl")

    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data_source_file": DATA_PATH.name,
        "features": FEATURES,
        "feature_ranges": FEATURE_RANGES,
        "classes": class_names,
        "data_quality": {
            "training_rows_total": int(len(df)),
            "training_class_distribution": {k: int(v) for k, v in counts.items()},
            "training_data_source": (
                "Knowledge-based: no public dataset records these signals from a wound dressing with "
                "healthy/healing/infected labels, so each class is sampled from distributions set by "
                "published criteria (SIRS, Sepsis-3/qSOFA, moist-healing and hypertension studies). "
                "See data/generate_training_data.py."
            ),
            "healing_days_source": (
                "Heuristic severity score (fever, tachycardia, hypotension, hypertension, humidity away "
                "from the moist optimum), NOT learned from real patient outcomes."
            ),
            "external_test_set": "PhysioNet/CinC Challenge 2019 -- used for testing only, never for training.",
        },
        "condition_model": {
            "algorithm": "RandomForestClassifier",
            "params": {k: v for k, v in CLF_PARAMS.items() if k != "n_jobs"},
            "accuracy_holdout": round(float(acc), 3),
            "macro_f1_holdout": round(float(macro_f1), 3),
            "cv5_accuracy_mean": round(float(cv_acc.mean()), 3),
            "cv5_accuracy_std": round(float(cv_acc.std()), 3),
            "holdout_n": int(len(yc_test)),
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
            "feature_importance": {f: round(float(v), 3) for f, v in zip(FEATURES, clf.feature_importances_)},
        },
        "healing_model": {
            "algorithm": "RandomForestRegressor",
            "params": {k: v for k, v in REG_PARAMS.items() if k != "n_jobs"},
            "mae_days_holdout": round(float(mae), 2),
            "r2_holdout": round(float(r2), 3),
            "feature_importance": {f: round(float(v), 3) for f, v in zip(FEATURES, reg.feature_importances_)},
        },
    }
    (OUT_DIR / "metadata.json").write_text(json.dumps(meta, indent=2))
    print("Saved condition_model.pkl, healing_model.pkl, label_encoder.pkl, metadata.json")


if __name__ == "__main__":
    main()
