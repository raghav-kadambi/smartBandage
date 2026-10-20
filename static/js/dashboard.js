const SLIDER_RANGES = JSON.parse(document.getElementById("slider-ranges-data").textContent);
const INPUT_MODE = JSON.parse(document.getElementById("input-mode-data").textContent);

const FEATURE_LABELS = {
  temperature: "Body temperature (°C)",
  humidity: "Humidity under dressing (%)",
  heart_rate: "Heart rate (bpm)",
  systolic_bp: "Systolic blood pressure (mmHg)",
  diastolic_bp: "Diastolic blood pressure (mmHg)",
};

const CLASS_LABELS = {
  healthy: "Healthy",
  wound_healing: "Wound healing",
  infected: "Infected",
};

// Typical readings for each class in the training data (see data/generate_training_data.py)
// -- enough to demo all three scenarios without dragging every slider.
const PRESETS = {
  healthy: { temperature: 36.8, humidity: 52, heart_rate: 74, systolic_bp: 118, diastolic_bp: 76 },
  wound_healing: { temperature: 37.0, humidity: 75, heart_rate: 80, systolic_bp: 122, diastolic_bp: 78 },
  infected: { temperature: 38.6, humidity: 88, heart_rate: 108, systolic_bp: 104, diastolic_bp: 62 },
};

// ---------------- simulate mode ----------------

const values = {};
const sliderInputs = {};

function setupSliders() {
  const slidersEl = document.getElementById("sliders");
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
        document.getElementById(`val-${key}`).textContent = Number.isInteger(val) ? val : val.toFixed(1);
      });
      predict();
    });
  });
}

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
  const data = await res.json();
  if (!res.ok) {
    document.getElementById("readingCountMeta").textContent = data.error || "Prediction failed";
    return;
  }
  renderPrediction(data);
  loadHistory();
  if (data.reading_count) {
    document.getElementById("readingCountMeta").textContent =
      `${data.reading_count} reading${data.reading_count === 1 ? "" : "s"} recorded`;
  }
}

// ---------------- ESP32 mode ----------------

const LIVE_STALE_MS = 30000;
let lastShownReadingId = null;

function setupDevice() {
  document.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const text = document.getElementById(btn.dataset.copy).textContent;
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = "Copied";
        setTimeout(() => (btn.textContent = "Copy"), 1200);
      } catch (e) {
        /* clipboard blocked -- the value is still selectable */
      }
    });
  });

  document.getElementById("btnRegenToken").addEventListener("click", async () => {
    if (!confirm("Create a new token? The ESP32 must be re-flashed with it.")) return;
    const res = await fetch("/api/device/regenerate", { method: "POST" });
    if (res.ok) document.getElementById("deviceToken").textContent = (await res.json()).token;
  });

  pollDevice();
  setInterval(pollDevice, 3000);
}

async function pollDevice() {
  const res = await fetch("/api/device/status");
  if (!res.ok) return;
  const d = await res.json();
  document.getElementById("deviceEndpoint").textContent = d.endpoint;
  document.getElementById("deviceToken").textContent = d.token;

  const statusEl = document.getElementById("deviceStatus");
  const statusText = document.getElementById("deviceStatusText");
  const lastSeen = d.last_seen ? new Date(d.last_seen + "Z") : null;
  const online = lastSeen && Date.now() - lastSeen.getTime() < LIVE_STALE_MS;
  statusEl.className = `device-status ${online ? "online" : "offline"}`;
  statusText.textContent = online
    ? `Connected · last reading ${lastSeen.toLocaleTimeString()}`
    : lastSeen
      ? `Offline · last reading ${lastSeen.toLocaleString()}`
      : "Not connected yet — waiting for the first reading";

  const r = d.latest;
  if (!r) return;
  renderLiveTiles(r);
  if (r.id !== lastShownReadingId) {
    lastShownReadingId = r.id;
    renderPrediction(r);
    loadHistory();
  }
}

function renderLiveTiles(r) {
  const tiles = [
    ["Temperature", r.temperature.toFixed(1), "°C"],
    ["Humidity", r.humidity.toFixed(0), "%"],
    ["Heart rate", r.heart_rate.toFixed(0), "bpm"],
    ["Blood pressure", `${r.systolic_bp.toFixed(0)}/${r.diastolic_bp.toFixed(0)}`, "mmHg"],
  ];
  document.getElementById("liveTiles").innerHTML = tiles
    .map(([k, v, u]) => `<div class="live-tile"><div class="k">${k}</div><div class="v">${v}<span class="u">${u}</span></div></div>`)
    .join("");
}

// ---------------- shared rendering ----------------

function renderPrediction(data) {
  const badge = document.getElementById("conditionBadge");
  badge.className = `result-condition ${data.condition}`;
  document.getElementById("conditionLabel").textContent = CLASS_LABELS[data.condition] || data.condition;
  document.getElementById("confidenceVal").textContent = `${Math.round(data.confidence * 100)}%`;
  const days = Number(data.healing_days);
  document.getElementById("healingDaysVal").textContent = days <= 1 ? "Nearly healed" : `${days.toFixed(1)} days`;

  const probBars = document.getElementById("probBars");
  probBars.innerHTML = "";
  if (!data.class_probs) return;
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
    el.innerHTML = `<div style="color:var(--text-faint); font-size:12.5px;">No readings yet.</div>`;
    return;
  }
  const rows = data.readings
    .map((r) => {
      const time = new Date(r.created_at + "Z").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      return `
        <tr>
          <td>${time}</td>
          <td>${r.source === "esp32" ? "ESP32" : "Simulated"}</td>
          <td>${CLASS_LABELS[r.condition] || r.condition}</td>
          <td>${Math.round(r.confidence * 100)}%</td>
          <td>${r.healing_days.toFixed(1)} days</td>
          <td>${r.temperature.toFixed(1)}°C</td>
          <td>${r.humidity.toFixed(0)}%</td>
          <td>${r.heart_rate.toFixed(0)} bpm</td>
          <td>${r.systolic_bp.toFixed(0)}/${r.diastolic_bp.toFixed(0)}</td>
        </tr>`;
    })
    .join("");
  el.innerHTML = `
    <div style="overflow-x:auto;">
    <table class="data-table">
      <thead>
        <tr><th>Time</th><th>Source</th><th>Condition</th><th>Conf.</th><th>Healing est.</th><th>Temp</th><th>Humidity</th><th>Heart rate</th><th>BP</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    </div>
  `;
}

if (INPUT_MODE === "simulate") {
  setupSliders();
  predict();
} else {
  setupDevice();
}
loadHistory();
