const CLASS_LABELS = {
  healthy: "Healthy",
  wound_healing: "Wound healing",
  infected: "Infected",
};

function fmtPct(x) {
  return `${Math.round(x * 100)}%`;
}

async function load() {
  const res = await fetch("/api/model-metrics");
  if (!res.ok) {
    document.getElementById("qualityBanner").textContent =
      "No trained model metadata found yet — run models/train_model.py first.";
    return;
  }
  const m = await res.json();
  render(m);
}

function render(m) {
  const dq = m.data_quality;
  const cond = m.condition_model;
  const heal = m.healing_model;

  document.getElementById("trainedAt").textContent = m.trained_at
    ? `Last trained ${new Date(m.trained_at).toLocaleString()} on ${m.data_source_file}`
    : "";

  // // ---- quality banner ----
  // const banner = document.getElementById("qualityBanner");
  // banner.innerHTML = `
  //   <strong>${dq.training_rows_real} real rows</strong> and
  //   <strong>${dq.training_rows_synthetic} synthetic rows</strong>
  //   (${dq.synthetic_pct}% of training data is synthetic) went into this model.
  //   ${dq.augmentation_method}
  //   <br/><br/>
  //   <strong>Days-to-heal is not learned from real outcomes.</strong> ${dq.healing_days_source}
  // `;

  // ---- data composition ----
// ---- data composition ----
const comp = document.getElementById("dataComposition");
comp.innerHTML = "";

Object.entries(dq.training_class_distribution).forEach(([cls, total]) => {
  const row = document.createElement("div");
  row.className = "dist-bar-row";

  row.innerHTML = `
    <div class="top">
      <span>${CLASS_LABELS[cls] || cls}</span>
      <span>${total} rows</span>
    </div>

    <div class="dist-bar-track">
      <div class="dist-bar-real" style="width:100%"></div>
    </div>
  `;

  comp.appendChild(row);
});

  comp.innerHTML += `
    <p class="validation-note" style="margin-top:12px;">${escapeHtml(dq.training_data_source || "")}</p>
  `;

  // ---- classifier metrics ----
  document.getElementById("accAll").textContent = `${fmtPct(cond.accuracy_holdout)} (n=${cond.holdout_n})`;
  document.getElementById("accReal").textContent = `${fmtPct(cond.cv5_accuracy_mean)} ± ${fmtPct(cond.cv5_accuracy_std)}`;

  const perClassTable = document.getElementById("perClassTable");
  let rows = cond.per_class
    .map(
      (c) => `
    <tr>
      <td>${CLASS_LABELS[c.class] || c.class}</td>
      <td>${fmtPct(c.precision)}</td>
      <td>${fmtPct(c.recall)}</td>
      <td>${fmtPct(c.f1)}</td>
      <td>${c.support}</td>
    </tr>`
    )
    .join("");
  perClassTable.innerHTML = `
    <table class="data-table">
      <thead><tr><th>Class</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  // ---- confusion matrix ----
  const labels = cond.confusion_matrix_labels;
  const cmDiv = document.getElementById("confusionMatrix");
  let header = `<th></th>` + labels.map((l) => `<th>${CLASS_LABELS[l] || l}</th>`).join("");
  let body = cond.confusion_matrix
    .map((row, i) => {
      const cells = row
        .map((val, j) => `<td class="${i === j ? "diag" : ""}">${val}</td>`)
        .join("");
      return `<tr><th>${CLASS_LABELS[labels[i]] || labels[i]}</th>${cells}</tr>`;
    })
    .join("");
  cmDiv.innerHTML = `
    <table class="cm-table">
      <thead><tr>${header}</tr></thead>
      <tbody>${body}</tbody>
    </table>
    <div style="font-size:11.5px; color:var(--text-faint); margin-top:8px;">Rows = actual, columns = predicted</div>
  `;

  // ---- regressor metrics ----
  document.getElementById("maeVal").textContent = `${heal.mae_days_holdout}`;
  document.getElementById("r2Val").textContent = `${heal.r2_holdout}`;

  // ---- feature importance ----
  renderImportance("featImportanceClf", cond.feature_importance);
  renderImportance("featImportanceReg", heal.feature_importance);

  document.getElementById("hlAcc").textContent = fmtPct(cond.accuracy_holdout);
  document.getElementById("hlCv").textContent = `${fmtPct(cond.cv5_accuracy_mean)} ± ${fmtPct(cond.cv5_accuracy_std)}`;
  document.getElementById("hlR2").textContent = Number(heal.r2_holdout).toFixed(2);

  if (m.external_validation) {
    const pat = m.external_validation.classifier_patient;
    document.getElementById("hlExt").textContent = fmt3(pat.deployed_model.auroc);
    document.getElementById("hlExtLabel").textContent =
      `External AUROC on real ICU patients (PhysioNet 2019), vs ${fmt3(pat.baseline_sirs_plus_bp_ge2.auroc)} for the standard clinical score`;
    renderExternal(m.external_validation);
  }
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const fmt3 = (x) => (x === undefined || x === null ? "—" : Number(x).toFixed(3));

function renderExternal(ev) {
  const ds = ev.dataset;
  const pat = ev.classifier_patient;
  const hr = ev.classifier_hourly;
  const reg = ev.regressor;
  const dep = pat.deployed_model;

  const rows = [
    ["WoundSense Random Forest (deployed, humidity marginalised)", pat.deployed_model, hr.deployed_model, true],
    ["Random Forest, vitals only (same training data)", pat.vitals_only_model, hr.vitals_only_model],
    ["Baseline: SIRS vitals ≥ 2 (temp + HR)", pat.baseline_sirs_vitals_eq2, hr.baseline_sirs_vitals_eq2],
    ["Baseline: qSOFA systolic BP ≤ 100", pat.baseline_qsofa_sbp_le100, hr.baseline_qsofa_sbp_le100],
    ["Baseline: SIRS vitals + SBP ≤ 100, score ≥ 2", pat.baseline_sirs_plus_bp_ge2, hr.baseline_sirs_plus_bp_ge2],
  ]
    .map(([name, p, h, bold]) => `
      <tr${bold ? ' style="font-weight:600;"' : ""}>
        <td>${name}</td>
        <td>${fmt3(p.auroc)}</td><td>${fmt3(p.auprc)}</td>
        <td>${fmtPct(p.sensitivity)}</td><td>${fmtPct(p.specificity)}</td><td>${fmtPct(p.balanced_accuracy)}</td>
        <td>${fmt3(h.auroc)}</td>
      </tr>`)
    .join("");

  const hosp = Object.entries(ev.classifier_per_hospital)
    .map(([k, v]) => `${k.replace("training_set", "Hospital ")}: AUROC ${fmt3(v.auroc_deployed)} (SIRS ${fmt3(v.auroc_sirs_vitals)}, n=${v.patients.toLocaleString()})`)
    .join(" · ");

  const figs = (ev.figures || [])
    .map((f) => `<img src="/model-outputs/${encodeURIComponent(f)}" alt="${escapeHtml(f.replace(/_/g, " ").replace(".png", ""))}" loading="lazy" />`)
    .join("");

  document.getElementById("externalBody").innerHTML = `
    <p class="validation-note">
      Tested on <strong>${ds.patients_evaluated.toLocaleString()} real ICU patients</strong>
      (${ds.rows_evaluated.toLocaleString()} hourly readings, ${ds.sepsis_patients.toLocaleString()} with sepsis) from the
      <a href="${ds.url}" target="_blank" rel="noopener">${escapeHtml(ds.name)}</a>, ${escapeHtml(ds.citation)}.
      None of this data was used for training. Label: ${escapeHtml(ds.label)}.
      ${escapeHtml(ds.label_caveat)} Missing input: ${escapeHtml(ds.missing_feature)}.
    </p>
    <div class="metric-pair" style="margin-bottom:14px;">
      <div><div class="metric-big">${fmt3(dep.auroc)}</div><div class="metric-label">Patient-level AUROC (95% CI ${fmt3(dep.auroc_95ci[0])}–${fmt3(dep.auroc_95ci[1])})</div></div>
      <div><div class="metric-big">${fmtPct(dep.sensitivity_at_80pct_specificity.sensitivity)}</div><div class="metric-label">Sensitivity at 80% specificity (patient level)</div></div>
    </div>
    <div style="overflow-x:auto;">
      <table class="data-table">
        <thead><tr><th>Model / score</th><th>AUROC (patient)</th><th>AUPRC (patient, chance ${fmt3(dep.auprc_chance)})</th><th>Sensitivity</th><th>Specificity</th><th>Balanced acc.</th><th>AUROC (hourly)</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="validation-note" style="margin-top:10px;">Per hospital system: ${hosp}</p>
    <p class="validation-note"><strong>Days-to-heal regressor (construct validity, no ground truth exists):</strong>
      mean predicted ${reg.mean_pred_days_sepsis_hours} days during sepsis hours vs ${reg.mean_pred_days_no_sepsis_hours} otherwise;
      AUROC of predicted days for sepsis ${fmt3(reg.auroc_pred_days_vs_sepsis_patient)} (patient level);
      Spearman ρ vs hours to onset ${fmt3(reg.spearman_hours_to_onset_vs_pred_days.rho)}.</p>
    <div class="validation-figs">${figs}</div>
  `;
}

function renderImportance(elId, importanceObj) {
  const el = document.getElementById(elId);
  el.innerHTML = "";
  const entries = Object.entries(importanceObj).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...entries.map((e) => e[1]), 0.001);
  entries.forEach(([feat, val]) => {
    const row = document.createElement("div");
    row.className = "prob-bar-row";
    row.innerHTML = `
      <div class="top"><span>${feat}</span><span>${val}</span></div>
      <div class="prob-bar-track"><div class="prob-bar-fill" style="width:${(val / max) * 100}%"></div></div>
    `;
    el.appendChild(row);
  });
}

load();