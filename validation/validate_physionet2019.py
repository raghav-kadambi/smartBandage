"""
External validation of the WoundSense Random Forest models on the official
PhysioNet/Computing in Cardiology Challenge 2019 dataset (40,336 real ICU patients,
two US hospital systems, Sepsis-3 labels). TEST ONLY -- nothing here is used for training.

Reyna MA et al. Crit Care Med 2020;48(2):210-217. doi:10.1097/CCM.0000000000004145
Data: https://physionet.org/content/challenge-2019/1.0.0/ (CC-BY 4.0)

What can and cannot be tested
-----------------------------
* PhysioNet records HR, Temp, SBP, DBP (and MAP) every hour -> 4 of our 5 inputs.
  It has no under-dressing humidity, so for the deployed model we MARGINALISE humidity:
  P(infected | vitals) = mean over a grid of humidity values drawn from the training
  distribution. A vitals-only Random Forest (same synthetic training data, humidity
  dropped) is reported alongside as a sensitivity check.
* Label: SepsisLabel (1 from 6 h before Sepsis-3 onset). Sepsis is *systemic* infection,
  the closest real, officially-labelled proxy for the "infected" class -- it is not local
  wound infection, and the report says so.
* The regressor's days-to-heal has no ground truth anywhere, so it is checked for
  construct validity: does predicted recovery time rise with sepsis, and rise as sepsis
  onset approaches?
* Clinical baselines on the same rows: SIRS vital-sign criteria (temp, HR) and the qSOFA
  blood-pressure criterion (SBP <= 100) -- the published scores our signals can compute.

Usage:
    python validation/download_physionet2019.py      # once
    python validation/validate_physionet2019.py
Outputs: models/external_validation.json and model_outputs/1x_*.png
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.patches  # noqa: F401  (used via matplotlib.patches)
import matplotlib.pyplot as plt
import matplotlib.ticker  # noqa: F401
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_CSV = ROOT / "data" / "physionet_2019" / "physionet2019_vitals.csv"
TRAIN_CSV = ROOT / "data" / "wound_data_train.csv"
MODELS = ROOT / "models"
FIG_DIR = ROOT / "model_outputs"
OUT_JSON = MODELS / "external_validation.json"

FEATURES = ["temperature", "humidity", "heart_rate", "systolic_bp", "diastolic_bp"]
VITALS = ["temperature", "heart_rate", "systolic_bp", "diastolic_bp"]
FFILL_LIMIT_H = 6       # carry a vital forward at most 6 hours
N_HUMIDITY_GRID = 9     # quantiles of training humidity used to marginalise it
N_BOOT = 1000
RNG = np.random.default_rng(42)

# Reference palette (dataviz skill, light mode)
C_MODEL, C_VITALS, C_SIRS, C_QSOFA = "#2a78d6", "#6250d6", "#eb6834", "#1baf7a"
C_INK, C_MUTED, C_GRID = "#0b0b0b", "#52514e", "#e4e3df"


# ---------------------------------------------------------------- data
def load_physionet():
    if not DATA_CSV.exists():
        raise SystemExit(f"{DATA_CSV} not found -- run validation/download_physionet2019.py first")
    df = pd.read_csv(DATA_CSV)
    df = df.rename(columns={"HR": "heart_rate", "Temp": "temperature", "SBP": "systolic_bp", "DBP": "diastolic_bp"})
    df = df.sort_values(["patient_id", "ICULOS"])
    # Derive DBP from MAP when DBP is missing: MAP ~ (SBP + 2*DBP) / 3
    derived = (3 * df["MAP"] - df["systolic_bp"]) / 2
    df["diastolic_bp"] = df["diastolic_bp"].fillna(derived)
    g = df.groupby("patient_id")
    for c in VITALS:
        df[c] = g[c].ffill(limit=FFILL_LIMIT_H)
    n_rows_raw, n_pat_raw = len(df), df["patient_id"].nunique()
    df = df.dropna(subset=VITALS)
    plausible = (
        df["heart_rate"].between(20, 250) & df["temperature"].between(30, 43)
        & df["systolic_bp"].between(50, 260) & df["diastolic_bp"].between(15, 160)
        & (df["diastolic_bp"] < df["systolic_bp"])
    )
    df = df[plausible].reset_index(drop=True)
    info = {
        "rows_raw": int(n_rows_raw), "patients_raw": int(n_pat_raw),
        "rows_evaluated": int(len(df)), "patients_evaluated": int(df["patient_id"].nunique()),
        "sepsis_rows": int(df["SepsisLabel"].sum()),
        "sepsis_row_prevalence": round(float(df["SepsisLabel"].mean()), 4),
        "sepsis_patients": int(df.groupby("patient_id")["SepsisLabel"].max().sum()),
        "preprocessing": (
            f"Hourly rows; vitals forward-filled within patient for up to {FFILL_LIMIT_H} h; DBP derived from "
            "MAP and SBP where missing; rows still missing a vital or physiologically implausible were dropped."
        ),
    }
    return df, info


# ---------------------------------------------------------------- scoring
def predict_marginal(model, vitals_df, humidity_grid, class_idx=None, proba=True):
    """Average model output over humidity values (humidity is not recorded in PhysioNet).
    Deduplicates identical vital-sign rows first -- ICU vitals repeat a lot."""
    uniq, inverse = np.unique(vitals_df[VITALS].round(1).values, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    out = np.zeros(len(uniq))
    for h in humidity_grid:
        X = np.column_stack([uniq[:, 0], np.full(len(uniq), h), uniq[:, 1], uniq[:, 2], uniq[:, 3]])
        if proba:
            out += model.predict_proba(X)[:, class_idx]
        else:
            out += model.predict(X)
    return (out / len(humidity_grid))[inverse]


def predict_marginal_classes(model, vitals_df, humidity_grid):
    uniq, inverse = np.unique(vitals_df[VITALS].round(1).values, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    probs = np.zeros((len(uniq), len(model.classes_)))
    for h in humidity_grid:
        X = np.column_stack([uniq[:, 0], np.full(len(uniq), h), uniq[:, 1], uniq[:, 2], uniq[:, 3]])
        probs += model.predict_proba(X)
    return (probs / len(humidity_grid))[inverse]


def sirs_vitals(df):
    return ((df["temperature"] > 38) | (df["temperature"] < 36)).astype(int) + (df["heart_rate"] > 90).astype(int)


def qsofa_bp(df):
    return (df["systolic_bp"] <= 100).astype(int)


# ---------------------------------------------------------------- metrics
def binary_report(y, score, pred):
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    sens = tp / (tp + fn) if tp + fn else 0.0
    spec = tn / (tn + fp) if tn + fp else 0.0
    ppv = tp / (tp + fp) if tp + fp else 0.0
    npv = tn / (tn + fn) if tn + fn else 0.0
    f1 = 2 * ppv * sens / (ppv + sens) if ppv + sens else 0.0
    return {
        "auroc": round(float(roc_auc_score(y, score)), 4),
        "auprc": round(float(average_precision_score(y, score)), 4),
        "auprc_chance": round(float(np.mean(y)), 4),
        "accuracy": round(float((tp + tn) / len(y)), 4),
        "balanced_accuracy": round(float((sens + spec) / 2), 4),
        "sensitivity": round(float(sens), 4),
        "specificity": round(float(spec), 4),
        "ppv": round(float(ppv), 4),
        "npv": round(float(npv), 4),
        "f1": round(float(f1), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "n": int(len(y)),
    }


def boot_auc_ci(y, score):
    y, score = np.asarray(y), np.asarray(score)
    aucs = []
    for _ in range(N_BOOT):
        idx = RNG.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        aucs.append(roc_auc_score(y[idx], score[idx]))
    lo, hi = np.percentile(aucs, [2.5, 97.5])
    return [round(float(lo), 4), round(float(hi), 4)]


def sens_at_spec(y, score, target_spec=0.80):
    fpr, tpr, thr = roc_curve(y, score)
    ok = np.where(1 - fpr >= target_spec)[0]
    i = ok[np.argmax(tpr[ok])]
    return {"specificity": round(float(1 - fpr[i]), 4), "sensitivity": round(float(tpr[i]), 4), "threshold": round(float(thr[i]), 4)}


# ---------------------------------------------------------------- figures
def style_axes(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(C_MUTED)
    ax.tick_params(colors=C_MUTED, labelsize=9)
    ax.grid(color=C_GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plot_roc(curves, title, path):
    fig, ax = plt.subplots(figsize=(5.6, 5.2), dpi=150)
    ax.plot([0, 1], [0, 1], color=C_MUTED, lw=1, ls="--", label="Chance (AUROC 0.50)")
    for name, (y, s, color) in curves.items():
        fpr, tpr, _ = roc_curve(y, s)
        ax.plot(fpr, tpr, color=color, lw=2, label=f"{name} (AUROC {roc_auc_score(y, s):.3f})")
    ax.set_xlabel("False positive rate (1 - specificity)", color=C_INK)
    ax.set_ylabel("True positive rate (sensitivity)", color=C_INK)
    ax.set_title(title, color=C_INK, fontsize=11, loc="left")
    style_axes(ax)
    ax.legend(frameon=False, fontsize=8.5, loc="lower right", labelcolor=C_INK)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_pr(curves, prevalence, title, path):
    fig, ax = plt.subplots(figsize=(5.6, 5.2), dpi=150)
    ax.axhline(prevalence, color=C_MUTED, lw=1, ls="--", label=f"Chance (prevalence {prevalence:.3f})")
    for name, (y, s, color) in curves.items():
        p, r, _ = precision_recall_curve(y, s)
        ax.plot(r, p, color=color, lw=2, label=f"{name} (AUPRC {average_precision_score(y, s):.3f})")
    ax.set_xlabel("Recall (sensitivity)", color=C_INK)
    ax.set_ylabel("Precision (PPV)", color=C_INK)
    ax.set_title(title, color=C_INK, fontsize=11, loc="left")
    style_axes(ax)
    ax.legend(frameon=False, fontsize=8.5, loc="upper right", labelcolor=C_INK)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_class_mix(table, path):
    """Share of hours predicted healthy / healing / infected, split by true sepsis label."""
    labels = ["No sepsis", "Sepsis (Sepsis-3)"]
    order = [("healthy", "#1baf7a"), ("wound_healing", "#2a78d6"), ("infected", "#e34948")]
    fig, ax = plt.subplots(figsize=(6.4, 2.8), dpi=150)
    for row, key in enumerate(["no_sepsis", "sepsis"]):
        left = 0.0
        for cls, color in order:
            v = table[key][cls]
            ax.barh(row, v, left=left, color=color, edgecolor="white", linewidth=2, height=0.55)
            if v > 0.07:
                ax.text(left + v / 2, row, f"{v:.0%}", ha="center", va="center", color="white", fontsize=9, fontweight="bold")
            left += v
    ax.set_yticks([0, 1], labels)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_title("Predicted class by true label (hourly rows)", color=C_INK, fontsize=11, loc="left")
    handles = [matplotlib.patches.Patch(color=c, label=n.replace("_", " ")) for n, c in order]
    ax.legend(handles=handles, frameon=False, fontsize=8.5, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.18), labelcolor=C_INK)
    style_axes(ax)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_regressor_trend(trend, baseline, path):
    fig, ax = plt.subplots(figsize=(6.4, 4.0), dpi=150)
    ax.axhline(baseline, color=C_MUTED, lw=1, ls="--", label=f"Non-sepsis patients (mean {baseline:.1f} d)")
    ax.plot(trend["hours"], trend["mean_days"], color=C_MODEL, lw=2, label="Sepsis patients")
    ax.fill_between(trend["hours"], trend["lo"], trend["hi"], color=C_MODEL, alpha=0.15, linewidth=0)
    ax.axvline(0, color=C_INK, lw=1)
    ax.text(0.5, ax.get_ylim()[1], " Sepsis-3 onset", va="top", fontsize=8.5, color=C_INK)
    ax.set_xlabel("Hours relative to sepsis onset", color=C_INK)
    ax.set_ylabel("Predicted days to heal (regressor)", color=C_INK)
    ax.set_title("Regressor output around sepsis onset (mean, 95% CI)", color=C_INK, fontsize=11, loc="left")
    style_axes(ax)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", labelcolor=C_INK)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    df, data_info = load_physionet()
    print(f"Evaluating {data_info['rows_evaluated']:,} hourly rows from {data_info['patients_evaluated']:,} patients "
          f"({data_info['sepsis_patients']:,} with sepsis)")

    clf = joblib.load(MODELS / "condition_model.pkl")
    reg = joblib.load(MODELS / "healing_model.pkl")
    le = joblib.load(MODELS / "label_encoder.pkl")
    classes = list(le.classes_)
    inf_idx = classes.index("infected")

    train = pd.read_csv(TRAIN_CSV)
    humidity_grid = np.quantile(train["humidity"], np.linspace(0.05, 0.95, N_HUMIDITY_GRID))

    # Deployed model, humidity marginalised
    probs = predict_marginal_classes(clf, df, humidity_grid)
    df["p_infected"] = probs[:, inf_idx]
    df["pred_class"] = np.array(classes)[probs.argmax(axis=1)]
    df["pred_days"] = predict_marginal(reg, df, humidity_grid, proba=False)

    # Sensitivity check: vitals-only RF trained on the same synthetic training data
    vit_cols = ["temperature", "heart_rate", "systolic_bp", "diastolic_bp"]
    clf_v = RandomForestClassifier(n_estimators=300, max_depth=12, min_samples_leaf=5, random_state=42, n_jobs=-1)
    clf_v.fit(train[vit_cols].values, le.transform(train["condition"]))
    uniq, inv = np.unique(df[vit_cols].round(1).values, axis=0, return_inverse=True)
    df["p_infected_vitals_only"] = clf_v.predict_proba(uniq)[:, inf_idx][inv.ravel()]

    df["sirs_vitals"] = sirs_vitals(df)
    df["qsofa_bp"] = qsofa_bp(df)
    df["sirs_plus_bp"] = df["sirs_vitals"] + df["qsofa_bp"]

    y = df["SepsisLabel"].values

    # ---- hourly (row-level) ----
    row = {
        "deployed_model": binary_report(y, df["p_infected"], (df["pred_class"] == "infected").astype(int)),
        "vitals_only_model": binary_report(y, df["p_infected_vitals_only"], (df["p_infected_vitals_only"] >= 0.5).astype(int)),
        "baseline_sirs_vitals_ge1": binary_report(y, df["sirs_vitals"], (df["sirs_vitals"] >= 1).astype(int)),
        "baseline_sirs_vitals_eq2": binary_report(y, df["sirs_vitals"], (df["sirs_vitals"] >= 2).astype(int)),
        "baseline_qsofa_sbp_le100": binary_report(y, df["qsofa_bp"], df["qsofa_bp"]),
        "baseline_sirs_plus_bp_ge2": binary_report(y, df["sirs_plus_bp"], (df["sirs_plus_bp"] >= 2).astype(int)),
    }
    row["deployed_model"]["sensitivity_at_80pct_specificity"] = sens_at_spec(y, df["p_infected"])

    # ---- patient-level: highest risk over the stay vs ever-septic ----
    pat = df.groupby("patient_id").agg(
        y=("SepsisLabel", "max"), p=("p_infected", "max"), pv=("p_infected_vitals_only", "max"),
        sirs=("sirs_vitals", "max"), sbp=("qsofa_bp", "max"), sirsbp=("sirs_plus_bp", "max"),
        pred_inf=("pred_class", lambda s: int((s == "infected").any())),
        days_mean=("pred_days", "mean"), days_max=("pred_days", "max"),
        los=("ICULOS", "max"), source=("source_set", "first"),
    )
    patient = {
        "deployed_model": binary_report(pat["y"], pat["p"], pat["pred_inf"]),
        "vitals_only_model": binary_report(pat["y"], pat["pv"], (pat["pv"] >= 0.5).astype(int)),
        "baseline_sirs_vitals_eq2": binary_report(pat["y"], pat["sirs"], (pat["sirs"] >= 2).astype(int)),
        "baseline_qsofa_sbp_le100": binary_report(pat["y"], pat["sbp"], pat["sbp"]),
        "baseline_sirs_plus_bp_ge2": binary_report(pat["y"], pat["sirsbp"], (pat["sirsbp"] >= 2).astype(int)),
    }
    patient["deployed_model"]["auroc_95ci"] = boot_auc_ci(pat["y"].values, pat["p"].values)
    patient["deployed_model"]["sensitivity_at_80pct_specificity"] = sens_at_spec(pat["y"], pat["p"])

    per_hospital = {}
    for src, g in pat.groupby("source"):
        per_hospital[src] = {
            "patients": int(len(g)), "sepsis_patients": int(g["y"].sum()),
            "auroc_deployed": round(float(roc_auc_score(g["y"], g["p"])), 4),
            "auroc_sirs_vitals": round(float(roc_auc_score(g["y"], g["sirs"])), 4),
        }

    # 3-class prediction mix by true label
    mix = {}
    for key, mask in (("no_sepsis", y == 0), ("sepsis", y == 1)):
        vc = df.loc[mask, "pred_class"].value_counts(normalize=True)
        mix[key] = {c: round(float(vc.get(c, 0.0)), 4) for c in ["healthy", "wound_healing", "infected"]}

    # ---- regressor construct validity ----
    onset = df[df["SepsisLabel"] == 1].groupby("patient_id")["ICULOS"].min() + 6  # label starts 6 h before onset
    sep = df[df["patient_id"].isin(onset.index)].copy()
    sep["rel_h"] = sep["ICULOS"] - sep["patient_id"].map(onset)
    win = sep[sep["rel_h"].between(-48, 24)]
    rho_onset, p_onset = spearmanr(win["rel_h"], win["pred_days"])
    trend_g = win.groupby("rel_h")["pred_days"]
    trend = pd.DataFrame({"mean_days": trend_g.mean(), "sd": trend_g.std(), "n": trend_g.size()}).reset_index()
    trend["lo"] = trend["mean_days"] - 1.96 * trend["sd"] / np.sqrt(trend["n"])
    trend["hi"] = trend["mean_days"] + 1.96 * trend["sd"] / np.sqrt(trend["n"])
    trend = trend.rename(columns={"rel_h": "hours"})
    non = pat[pat["y"] == 0]
    rho_los, p_los = spearmanr(non["days_mean"], non["los"])
    regressor = {
        "note": (
            "No dataset records wound days-to-heal, so the regressor is checked for construct validity: "
            "predicted recovery time should be longer during sepsis and should rise as sepsis onset approaches."
        ),
        "auroc_pred_days_vs_sepsis_hourly": round(float(roc_auc_score(y, df["pred_days"])), 4),
        "auroc_pred_days_vs_sepsis_patient": round(float(roc_auc_score(pat["y"], pat["days_max"])), 4),
        "mean_pred_days_no_sepsis_hours": round(float(df.loc[y == 0, "pred_days"].mean()), 2),
        "mean_pred_days_sepsis_hours": round(float(df.loc[y == 1, "pred_days"].mean()), 2),
        "spearman_hours_to_onset_vs_pred_days": {"rho": round(float(rho_onset), 4), "p_value": float(p_onset), "window_h": [-48, 24]},
        "spearman_pred_days_vs_icu_length_of_stay_non_sepsis": {"rho": round(float(rho_los), 4), "p_value": float(p_los)},
    }

    # ---- figures ----
    FIG_DIR.mkdir(exist_ok=True)
    plot_roc({
        "WoundSense RF (deployed)": (pat["y"], pat["p"], C_MODEL),
        "RF, vitals only": (pat["y"], pat["pv"], C_VITALS),
        "SIRS vitals (temp + HR)": (pat["y"], pat["sirs"], C_SIRS),
        "SIRS vitals + SBP<=100": (pat["y"], pat["sirsbp"], C_QSOFA),
    }, "PhysioNet 2019 - patient-level ROC", FIG_DIR / "10_physionet_roc_patient.png")
    plot_roc({
        "WoundSense RF (deployed)": (y, df["p_infected"], C_MODEL),
        "RF, vitals only": (y, df["p_infected_vitals_only"], C_VITALS),
        "SIRS vitals (temp + HR)": (y, df["sirs_vitals"], C_SIRS),
        "SIRS vitals + SBP<=100": (y, df["sirs_plus_bp"], C_QSOFA),
    }, "PhysioNet 2019 - hourly ROC", FIG_DIR / "11_physionet_roc_hourly.png")
    plot_pr({
        "WoundSense RF (deployed)": (pat["y"], pat["p"], C_MODEL),
        "SIRS vitals + SBP<=100": (pat["y"], pat["sirsbp"], C_QSOFA),
    }, float(pat["y"].mean()), "PhysioNet 2019 - patient-level precision/recall", FIG_DIR / "12_physionet_pr_patient.png")
    plot_class_mix(mix, FIG_DIR / "13_physionet_predicted_class_mix.png")
    plot_regressor_trend(trend, regressor["mean_pred_days_no_sepsis_hours"], FIG_DIR / "14_physionet_regressor_onset_trend.png")

    result = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "name": "PhysioNet/Computing in Cardiology Challenge 2019: Early Prediction of Sepsis from Clinical Data",
            "version": "1.0.0",
            "url": "https://physionet.org/content/challenge-2019/1.0.0/",
            "citation": "Reyna MA et al. Crit Care Med. 2020;48(2):210-217. doi:10.1097/CCM.0000000000004145",
            "license": "CC-BY 4.0",
            "used_for_training": False,
            "label": "SepsisLabel (Sepsis-3; positive from 6 h before onset)",
            "label_caveat": "Sepsis is systemic infection in ICU patients -- a proxy for the bandage's 'infected' class, not local wound infection.",
            "missing_feature": "humidity (not recorded in PhysioNet) -- marginalised over the training distribution",
            **data_info,
        },
        "humidity_grid": [round(float(h), 1) for h in humidity_grid],
        "classifier_hourly": row,
        "classifier_patient": patient,
        "classifier_per_hospital": per_hospital,
        "predicted_class_mix": mix,
        "regressor": regressor,
        "regressor_onset_trend": trend[["hours", "mean_days", "lo", "hi", "n"]].round(3).to_dict(orient="list"),
        "figures": sorted(p.name for p in FIG_DIR.glob("1[0-4]_physionet_*.png")),
    }
    OUT_JSON.write_text(json.dumps(result, indent=2))

    d, s = patient["deployed_model"], patient["baseline_sirs_plus_bp_ge2"]
    print(f"Patient-level AUROC: WoundSense RF {d['auroc']} (95% CI {d['auroc_95ci']}) | SIRS+SBP {s['auroc']}")
    print(f"Hourly AUROC: WoundSense RF {row['deployed_model']['auroc']} | vitals-only RF {row['vitals_only_model']['auroc']}")
    print(f"Regressor: Spearman(hours-to-onset, days) = {regressor['spearman_hours_to_onset_vs_pred_days']['rho']}")
    print(f"Wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
