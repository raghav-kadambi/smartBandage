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
    <div style="margin-top:10px; font-size:12px; color:var(--text-soft);">
      <span class="legend-dot" style="background:var(--text);"></span>real
      &nbsp;&nbsp;
      <span class="legend-dot" style="background:var(--text-faint);"></span>synthetic
    </div>
  `;

  // ---- classifier metrics ----
  document.getElementById("accAll").textContent = fmtPct(cond.accuracy_holdout_all);
  document.getElementById("accReal").textContent =
    cond.accuracy_holdout_real_only !== null
      ? `${fmtPct(cond.accuracy_holdout_real_only)} (n=${cond.real_only_test_n})`
      : "n/a — no real rows in test split";

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