"""
Generate the WoundSense TRAINING set for the 4 bandage signals:
    temperature (degC, core-equivalent), humidity (% RH under the dressing),
    heart_rate (bpm), systolic_bp / diastolic_bp (mmHg)

There is no public dataset with these signals recorded from a wound dressing and labelled
healthy / wound_healing / infected, so the training set is *knowledge-based*: each class is
sampled from distributions whose centres and spreads are set from the published clinical
criteria below. The models are then tested on real ICU patients (PhysioNet 2019) that were
never used here -- see validation/validate_physionet2019.py.

Where the numbers come from (all in data/literature_data.py, verifiable on PubMed):
  * SIRS vital-sign criteria: temp > 38 or < 36 degC, HR > 90 bpm  (Bone 1992, PMID 1303622)
  * qSOFA blood-pressure criterion: SBP <= 100 mmHg                (Singer 2016 / Seymour 2016)
  * Moist wound bed heals faster; dry beds scab, saturated beds macerate
                                                                   (Winter 1962; Junker 2013; Cutting 2002)
  * Hypertension (mean SBP 150 vs 120) slows wound drying, OR 1.65 (Ahmed 2011, PMID 21853091)
  * Local infection = warmth + increased drainage                  (Fierheller 2010; Woo 2009; Lipsky 2012)
Adult resting reference ranges (HR 60-100, BP ~120/80, temp ~36.5-37.5) are standard physiology.

healing_days is a transparent HEURISTIC (there is no real outcome data); see healing_days().

Usage:  python data/generate_training_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "wound_data_train.csv"

FEATURES = ["temperature", "humidity", "heart_rate", "systolic_bp", "diastolic_bp"]
LIMITS = {
    "temperature": (34.0, 42.0),
    "humidity": (10.0, 100.0),
    "heart_rate": (35.0, 180.0),
    "systolic_bp": (70.0, 200.0),
    "diastolic_bp": (35.0, 120.0),
}
N_PER_CLASS = 6000
HYPERTENSIVE_FRACTION = 0.2  # share of each class with sustained hypertension (Ahmed 2011 subgroup)

# Each class may have sub-profiles: (weight, {feature: (mean, sd)})
PROFILES = {
    "healthy": [
        (1.0, {"temperature": (36.8, 0.30), "humidity": (52, 9), "heart_rate": (74, 9),
               "systolic_bp": (118, 10), "diastolic_bp": (76, 7)}),
    ],
    "wound_healing": [
        # moist, balanced bed (65-85% RH); vitals normal, mild local inflammation
        (1.0, {"temperature": (37.0, 0.35), "humidity": (75, 6), "heart_rate": (80, 10),
               "systolic_bp": (122, 12), "diastolic_bp": (78, 8)}),
    ],
    "infected": [
        # local infection: warmth, wetter dressing from drainage, borderline tachycardia
        (0.55, {"temperature": (37.7, 0.45), "humidity": (88, 5), "heart_rate": (92, 11),
                "systolic_bp": (124, 14), "diastolic_bp": (78, 9)}),
        # spreading / systemic: SIRS fever + tachycardia, falling BP toward qSOFA range
        (0.35, {"temperature": (38.6, 0.50), "humidity": (87, 6), "heart_rate": (108, 13),
                "systolic_bp": (104, 14), "diastolic_bp": (62, 9)}),
        # systemic with hypothermia (the < 36 degC SIRS arm)
        (0.10, {"temperature": (35.7, 0.40), "humidity": (86, 6), "heart_rate": (106, 13),
                "systolic_bp": (100, 14), "diastolic_bp": (60, 9)}),
    ],
}


def sample_class(rng, label, n):
    profiles = PROFILES[label]
    weights = np.array([w for w, _ in profiles])
    which = rng.choice(len(profiles), size=n, p=weights / weights.sum())
    rows = np.zeros((n, len(FEATURES)))
    for k, (_, spec) in enumerate(profiles):
        idx = np.where(which == k)[0]
        m = len(idx)
        sbp_mu, sbp_sd = spec["systolic_bp"]
        dbp_mu, dbp_sd = spec["diastolic_bp"]
        sbp = rng.normal(sbp_mu, sbp_sd, m)
        # diastolic tracks systolic (r ~ 0.6 in adults), plus its own noise
        dbp = dbp_mu + 0.45 * (sbp - sbp_mu) + rng.normal(0, dbp_sd * 0.8, m)
        rows[idx, 0] = rng.normal(*spec["temperature"], m)
        rows[idx, 1] = rng.normal(*spec["humidity"], m)
        rows[idx, 2] = rng.normal(*spec["heart_rate"], m)
        rows[idx, 3] = sbp
        rows[idx, 4] = dbp

    # sustained hypertension sub-group, present in every class
    hyp = rng.random(n) < HYPERTENSIVE_FRACTION
    rows[hyp, 3] += rng.normal(28, 8, hyp.sum())
    rows[hyp, 4] += rng.normal(12, 5, hyp.sum())

    df = pd.DataFrame(rows, columns=FEATURES)
    for f, (lo, hi) in LIMITS.items():
        df[f] = df[f].clip(lo, hi)
    df["condition"] = label
    return df


def healing_days(df, rng):
    """Heuristic days-to-heal. NOT learned from real outcomes.
    Base window per class, stretched by a severity score built from published risk signals:
    fever/hypothermia, tachycardia, hypotension (sepsis criteria), hypertension (slower drying,
    Ahmed 2011) and distance of humidity from the moist optimum (~75% RH)."""
    temp_dev = np.clip(np.abs(df["temperature"] - 37.0) / 2.0, 0, 1)
    tachy = np.clip((df["heart_rate"] - 80) / 40.0, 0, 1)
    hypo = np.clip((110 - df["systolic_bp"]) / 30.0, 0, 1)
    hyper = np.clip((df["systolic_bp"] - 130) / 40.0, 0, 1)
    moist = np.clip(np.abs(df["humidity"] - 75) / 30.0, 0, 1)
    severity = 0.25 * temp_dev + 0.2 * tachy + 0.2 * hypo + 0.15 * hyper + 0.2 * moist

    windows = {"healthy": (0, 3), "wound_healing": (7, 21), "infected": (21, 42)}
    days = np.zeros(len(df))
    for cond, (lo, hi) in windows.items():
        m = (df["condition"] == cond).values
        days[m] = lo + severity[m] * (hi - lo) * 1.6
    days += rng.normal(0, 1.5, len(df))
    return np.clip(days, 0, 60).round(1)


def main(seed=42):
    rng = np.random.default_rng(seed)
    df = pd.concat([sample_class(rng, c, N_PER_CLASS) for c in PROFILES], ignore_index=True)
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    df[FEATURES] = df[FEATURES].round(1)
    df["healing_days"] = healing_days(df, rng)
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df)} rows -> {OUT}")
    print(df.groupby("condition")[FEATURES + ["healing_days"]].mean().round(1))


if __name__ == "__main__":
    main()
