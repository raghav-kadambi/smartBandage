const SLIDER_RANGES = JSON.parse(document.getElementById("slider-ranges-data").textContent);

const FEATURE_LABELS = {
  pH: "pH",
  temperature: "Temperature (°C)",
  humidity: "Humidity (%)",
  exudate_level: "Exudate level",
  oxygen_saturation: "Oxygen saturation (%)",
};

const CLASS_LABELS = {
  healthy: "Healthy",
  wound_healing: "Wound healing",
  infected: "Infected",
};

// Rough centroids matching how the training script defines each class band —
// good enough to instantly demo all three scenarios without dragging every slider.
const PRESETS = {
  healthy: { pH: 7.15, temperature: 31.5, humidity: 45, exudate_level: 1.8, oxygen_saturation: 88 },
  wound_healing: { pH: 7.7, temperature: 33, humidity: 60, exudate_level: 5, oxygen_saturation: 78 },
  infected: { pH: 8.7, temperature: 37.5, humidity: 82, exudate_level: 8.5, oxygen_saturation: 55 },
};

const slidersEl = document.getElementById("sliders");
const values = {};
const sliderInputs = {};

Object.entries(SLIDER_RANGES).forEach(([key, cfg]) => {
  values[key] = cfg.default;

  const row = document.createElement("div");
  row.className = "slider-row";
  row.innerHTML = `
    <div class="slider-top">
      <span class="label">${FEATURE_LABELS[key]}</span>
      <span class="value" id="val-${key}">${cfg.default}</span>
    </div>
    <input type="range" id="slider-${key}" min="${cfg.min}" max="${cfg.max}" step="${cfg.step}" value="${cfg.default}" />
  `;
  slidersEl.appendChild(row);

  const input = row.querySelector("input");
  sliderInputs[key] = input;
  const valLabel = row.querySelector(`#val-${key}`);
  input.addEventListener("input", () => {
    values[key] = parseFloat(input.value);
    valLabel.textContent = input.value;
    debouncedPredict();
  });
});

document.querySelectorAll(".preset-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const preset = PRESETS[btn.dataset.preset];
    Object.entries(preset).forEach(([key, val]) => {
      values[key] = val;
      sliderInputs[key].value = val;
      document.getElementById(`val-${key}`).textContent =
        Number.isInteger(val) ? val : val.toFixed(2);
    });
    predict();
  });
});

let debounceTimer = null;
function debouncedPredict() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(predict, 180);
}

async function predict() {
  const res = await fetch("/api/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(values),
  });
  if (!res.ok) return;
  const data = await res.json();
  renderPrediction(data);
  loadHistory();
  if (data.reading_count) {
    document.getElementById("readingCountMeta").textContent =
      `${data.reading_count} reading${data.reading_count === 1 ? "" : "s"} recorded this session`;
  }
}

function renderPrediction(data) {
  const badge = document.getElementById("conditionBadge");
  badge.className = `result-condition ${data.condition}`;
  document.getElementById("conditionLabel").textContent = CLASS_LABELS[data.condition] || data.condition;
  document.getElementById("confidenceVal").textContent = `${Math.round(data.confidence * 100)}%`;
  document.getElementById("healingDaysVal").textContent =
    data.healing_days <= 1 ? "Nearly healed" : `${data.healing_days} days`;

  const probBars = document.getElementById("probBars");
  probBars.innerHTML = "";
  Object.entries(data.class_probs)
    .sort((a, b) => b[1] - a[1])
    .forEach(([cls, p]) => {
      const row = document.createElement("div");
      row.className = "prob-bar-row";
      row.innerHTML = `
        <div class="top"><span>${CLASS_LABELS[cls] || cls}</span><span>${Math.round(p * 100)}%</span></div>
        <div class="prob-bar-track"><div class="prob-bar-fill" style="width:${p * 100}%"></div></div>
      `;
      probBars.appendChild(row);
    });
}

async function loadHistory() {
  const res = await fetch("/api/readings-history");
  if (!res.ok) return;
  const data = await res.json();
  const el = document.getElementById("historyTable");
  if (!data.readings || data.readings.length === 0) {
    el.innerHTML = `<div style="color:var(--text-faint); font-size:12.5px;">No readings yet — move a slider to generate one.</div>`;
    return;
  }
  const rows = data.readings
    .map((r) => {
      const time = new Date(r.created_at + "Z").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      return `
        <tr>
          <td>${time}</td>
          <td>${CLASS_LABELS[r.condition] || r.condition}</td>
          <td>${Math.round(r.confidence * 100)}%</td>
          <td>${r.healing_days.toFixed(1)} days</td>
          <td>${r.ph.toFixed(2)}</td>
          <td>${r.temperature.toFixed(1)}°C</td>
          <td>${r.humidity.toFixed(0)}%</td>
          <td>${r.exudate_level.toFixed(1)}</td>
          <td>${r.oxygen_saturation.toFixed(0)}%</td>
        </tr>`;
    })
    .join("");
  el.innerHTML = `
    <table class="data-table">
      <thead>
        <tr><th>Time</th><th>Condition</th><th>Conf.</th><th>Healing est.</th><th>pH</th><th>Temp</th><th>Humidity</th><th>Exudate</th><th>O2 sat</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

predict();
loadHistory();