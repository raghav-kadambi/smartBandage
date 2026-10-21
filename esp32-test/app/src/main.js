import { api, prefs, ApiError, setAuthExpiredHandler, streamChat, DEFAULT_SERVER } from "./api.js";
import {
  live, onLive, connectBandage, disconnectBandage, measureOnWatch, finishWatchSession, startDemo, stopDemo,
} from "./ble.js";
import { lineChart, sparkline } from "./charts.js";

// ---------- helpers ----------

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const pct = (x, d = 0) => `${(x * 100).toFixed(d)}%`;
const fmtInt = (n) => Number(n).toLocaleString();
const when = (iso) =>
  new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

function ago(ms) {
  if (!ms) return "No data yet";
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 20) return "Just now";
  if (s < 3600) return `${Math.round(s / 60) || 1} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

async function openLink(url) {
  if (!url) return;
  try {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(url);
  } catch {
    window.open(url, "_blank", "noopener");
  }
}

function toast(text) {
  document.querySelector(".toast")?.remove();
  const t = document.createElement("div");
  t.className = "toast";
  t.setAttribute("role", "status");
  t.textContent = text;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}

// Lucide-style 24px stroke icons
const ICON = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"/>',
  trends: '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 6-6"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  camera: '<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.5"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  chev: '<path d="m9 18 6-6-6-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
  temp: '<path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/>',
  drop: '<path d="M12 2.7s6 6.3 6 11.3a6 6 0 0 1-12 0c0-5 6-11.3 6-11.3z"/>',
  waves: '<path d="M2 6c2-2 4 2 6 0s4 2 6 0 4 2 6 0M2 12c2-2 4 2 6 0s4 2 6 0 4 2 6 0M2 18c2-2 4 2 6 0s4 2 6 0 4 2 6 0"/>',
  heart: '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7z"/>',
  pulse: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  bandage: '<rect x="2.5" y="7.5" width="19" height="9" rx="4.5" transform="rotate(-45 12 12)"/><path d="M10 10h.01M14 14h.01M10 14h.01M14 10h.01"/>',
  watch: '<rect x="6" y="6" width="12" height="12" rx="3"/><path d="M9 6V3h6v3M9 18v3h6v-3M12 10v2l1.5 1.5"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  activity: '<path d="M12 6v6l4 2"/><circle cx="12" cy="12" r="10"/>',
  up: '<path d="m18 15-6-6-6 6"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  flat: '<path d="M5 12h14"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5V21h16"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
  external: '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  server: '<rect x="2" y="3" width="20" height="8" rx="2"/><rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 7h.01M6 17h.01"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  focus: '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="3"/>',
  ruler: '<path d="M21.3 15.3 8.7 2.7a1 1 0 0 0-1.4 0L2.7 7.3a1 1 0 0 0 0 1.4l12.6 12.6a1 1 0 0 0 1.4 0l4.6-4.6a1 1 0 0 0 0-1.4z"/><path d="m7.5 10.5 2-2M10.5 13.5l2-2M13.5 16.5l2-2"/>',
  sparkle: '<path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4z"/><path d="M19 17v4M17 19h4"/>',
  stethoscope: '<path d="M6 3v6a4 4 0 0 0 8 0V3"/><path d="M10 13v3a5 5 0 0 0 10 0v-2"/><circle cx="20" cy="12" r="2"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
};
const icon = (n, cls = "") =>
  `<svg class="ic ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[n] || ""}</svg>`;

const METRICS = {
  temperature: { title: "Temperature", unit: "°C", cls: "c-temp", color: "var(--m-temp)", icon: "temp", fields: ["temperature"], dec: 1, device: "Bandage", model: true },
  humidity: { title: "Humidity", unit: "%", cls: "c-hum", color: "var(--m-hum)", icon: "drop", fields: ["humidity"], dec: 0, device: "Bandage", model: true },
  heart_rate: { title: "Heart rate", unit: "bpm", cls: "c-hr", color: "var(--m-hr)", icon: "heart", fields: ["bpm"], dec: 0, device: "Watch", model: true },
  blood_pressure: { title: "Blood pressure", unit: "mmHg", cls: "c-bp", color: "var(--m-bp)", icon: "pulse", fields: ["systolic", "diastolic"], dec: 0, device: "Watch", model: true },
  moisture: { title: "Dressing moisture", unit: "/ 10", cls: "c-moist", color: "var(--m-moist)", icon: "waves", fields: ["moisture"], dec: 1, device: "Bandage", model: false },
};
const HEAL = { title: "Days to heal", unit: "days", cls: "c-heal", color: "var(--m-heal)", icon: "activity", fields: ["healing_days"], dec: 1 };
const TILE_ORDER = ["temperature", "humidity", "heart_rate", "blood_pressure", "moisture"];

const STATUS = {
  healthy: { cls: "good", label: "On track", icon: "check", blurb: "Readings look like a wound that is healing well." },
  wound_healing: { cls: "warn", label: "Healing", icon: "activity", blurb: "Readings fit an active healing phase. Keep monitoring." },
  infected: { cls: "crit", label: "Needs attention", icon: "alert", blurb: "Readings match the pattern linked with infection. Consider contacting your clinician." },
};
const INPUT_NAMES = {
  temperature: ["Temperature", "bandage"], humidity: ["Humidity", "bandage"],
  heart_rate: ["Heart rate", "watch"], systolic_bp: ["Blood pressure", "watch"], diastolic_bp: ["Blood pressure", "watch"],
};
const TYPE_NAME = {
  Pressure: "Pressure injury", Diabetic: "Diabetic ulcer", Venous: "Venous leg ulcer", Surgical: "Surgical wound",
  Bruises: "Bruise", Burn: "Burn", Abrasion: "Abrasion", Laceration: "Laceration", Normal: "Normal skin", Cut: "Cut",
};
const TIPS = [
  { icon: "drop", title: "Keep it moist, not soaked", id: "junker_2013",
    body: "Moist wound treatment promotes re-epithelialisation and reduces scarring compared with letting a wound dry out." },
  { icon: "temp", title: "Watch the temperature trend", id: "fierheller_2010",
    body: "In chronic leg ulcers, a warmer area around the wound was significantly linked with infection. A steady settle toward normal is what you want." },
  { icon: "heart", title: "Rest and keep stress low", id: "gouin_2011",
    body: "Experimental studies show psychological stress measurably slows wound repair." },
  { icon: "pulse", title: "Mind your blood pressure", id: "ahmed_2011",
    body: "After hip replacement, patients with high blood pressure took about 3.8 days to reach a dry wound, versus 2.0 days for others." },
];
const demoQS = () => (live.demo ? "1" : "0");

function citeName(p) {
  if (!p) return "";
  const authors = p.authors.split(",").map((a) => a.trim()).filter(Boolean);
  const last = (a) => a.split(" ")[0];
  const who = authors.length > 2 ? `${last(authors[0])} et al.` : authors.length === 2 ? `${last(authors[0])} & ${last(authors[1])}` : last(authors[0] || "Anon");
  return `${who}, ${p.year}`;
}

function currentValue(metric, status) {
  // live (this session) wins; otherwise the newest value the server has
  const out = [];
  let at = 0;
  for (const f of metric.fields) {
    let v = live.values[f];
    let t = live.at[f];
    if (v === undefined && status?.latest?.[f]) {
      v = status.latest[f].value;
      t = Date.parse(status.latest[f].at);
    }
    if (v === undefined || v === null) return { text: "––", at: 0 };
    out.push(Number(v).toFixed(metric.dec));
    at = Math.max(at, t || 0);
  }
  return { text: out.join("/"), at };
}

// ---------- shell / router ----------

const app = $("#app");
let cleanup = null;
let infoCache = null;
let modelCache = null;

setAuthExpiredHandler(() => {
  prefs.token = null;
  location.hash = "#/auth";
});

function shell(html, { nav = true, cls = "" } = {}) {
  app.innerHTML = `<main id="view" class="view ${nav ? "with-nav" : ""} ${cls}">${html}</main>${nav ? navHtml() : ""}`;
  window.scrollTo(0, 0);
  return $("#view");
}

function navHtml() {
  const raw = location.hash.split("/")[1] || "home";
  const cur = { wound: "profile", devices: "profile", model: "profile", library: "profile", metric: "trends" }[raw] || raw;
  const item = (id, ic, label) =>
    `<a href="#/${id}" class="nav-item ${cur === id ? "active" : ""}" ${cur === id ? 'aria-current="page"' : ""}><span class="pill">${icon(ic)}</span>${label}</a>`;
  return `<nav class="nav" aria-label="Main">${item("home", "home", "Home")}${item("trends", "trends", "Trends")}
    <a href="#/scan" class="nav-fab" aria-label="Scan wound">${icon("camera", "lg")}</a>
    ${item("chat", "chat", "Assistant")}${item("profile", "user", "Profile")}</nav>`;
}

function appbar(title, { back = null, eyebrow = "", action = "" } = {}) {
  if (back) {
    return `<header class="appbar sub"><a href="${back}" class="icon-btn" aria-label="Back">${icon("back")}</a>
      <div class="titles"><h1>${esc(title)}</h1></div>${action || '<span style="width:40px"></span>'}</header>`;
  }
  return `<header class="appbar"><div class="titles">${eyebrow ? `<p class="eyebrow">${esc(eyebrow)}</p>` : ""}<h1>${esc(title)}</h1></div>${action}</header>`;
}

const errorBox = (e) => `<div class="notice error" role="alert">${icon("alert", "sm")}<span>${esc(e.message || e)}</span></div>`;

async function loadInfo() {
  if (!infoCache) infoCache = await api("/wound-info");
  return infoCache;
}
async function loadModel() {
  if (!modelCache) modelCache = await api("/model");
  return modelCache;
}

function bindLinks(root) {
  $$("[data-url]", root).forEach((a) => {
    a.onclick = (e) => {
      e.preventDefault();
      openLink(a.dataset.url);
    };
  });
}

async function route() {
  if (cleanup) {
    cleanup();
    cleanup = null;
  }
  const [, name = "home", arg] = location.hash.split("/");
  if (!prefs.token) return renderAuth();
  const views = {
    home: renderHome, metric: renderMetric, wound: renderWound, trends: renderTrends, scan: renderScan, chat: renderChat,
    devices: renderDevices, profile: renderProfile, model: renderModel, library: renderLibrary, auth: renderHome,
  };
  cleanup = (await (views[name] || renderHome)(arg)) || null;
}
window.addEventListener("hashchange", route);

// ---------- auth ----------

function renderAuth() {
  let mode = "login";
  const draw = (err = "") => {
    const signup = mode === "signup";
    shell(
      `<div class="auth">
        <div class="brand"><div class="logo">${icon("bandage")}</div><h1>WoundSense</h1>
          <p>${signup ? "Create your account to start monitoring." : "Smart-bandage monitoring, backed by clinical research."}</p></div>
        <form id="f" class="card stack" novalidate>
          ${signup ? `<label class="field"><span>Full name</span><input class="input" name="name" autocomplete="name" required /></label>` : ""}
          <label class="field"><span>Email</span><input class="input" name="email" type="email" inputmode="email" autocomplete="email" required /></label>
          <label class="field"><span>Password${signup ? ' <span class="hint">· at least 6 characters</span>' : ""}</span>
            <div class="input-wrap"><input class="input" id="pw" name="password" type="password" autocomplete="${signup ? "new-password" : "current-password"}" required />
            <button type="button" class="icon-btn ghost reveal" id="reveal" aria-label="Show password">${icon("eye")}</button></div></label>
          ${err ? errorBox(err) : ""}
          <button class="btn primary block" id="go">${signup ? "Create account" : "Sign in"}</button>
        </form>
        <p class="auth-switch">${signup ? "Already have an account?" : "New to WoundSense?"}
          <button class="link-btn" id="switch">${signup ? "Sign in" : "Create an account"}</button></p>
        <details class="server"><summary>${icon("server", "sm")} Server settings</summary>
          <label class="field"><span>Server address</span><input class="input" id="server" value="${esc(prefs.server)}" placeholder="${DEFAULT_SERVER}" inputmode="url" autocapitalize="off" />
          <span class="hint">The computer running <code>mobile_server.py</code>, on the same network as this phone.</span></label>
        </details>
        <p class="disclaimer">For information only. Not a medical device and not a diagnosis.</p>
      </div>`,
      { nav: false },
    );
    $("#switch").onclick = () => ((mode = signup ? "login" : "signup"), draw());
    $("#reveal").onclick = () => {
      const pw = $("#pw");
      pw.type = pw.type === "password" ? "text" : "password";
      $("#reveal").setAttribute("aria-label", pw.type === "password" ? "Show password" : "Hide password");
    };
    $("#f").onsubmit = async (e) => {
      e.preventDefault();
      const fd = Object.fromEntries(new FormData(e.target));
      prefs.server = $("#server").value || DEFAULT_SERVER;
      const go = $("#go");
      go.disabled = true;
      go.innerHTML = `<span class="spinner"></span> ${signup ? "Creating account" : "Signing in"}`;
      try {
        const r = await api(signup ? "/auth/signup" : "/auth/login", { method: "POST", body: fd });
        prefs.token = r.token;
        prefs.user = r.user;
        infoCache = modelCache = null;
        location.hash = "#/home";
        route();
      } catch (er) {
        draw(er.message);
      }
    };
  };
  draw();
}

// ---------- home ----------

function probBar(probs) {
  if (!probs) return "";
  const order = [["healthy", "good", "On track"], ["wound_healing", "warn", "Healing"], ["infected", "crit", "Needs attention"]];
  return `<div><div class="probbar" role="img" aria-label="Model probabilities: ${order.map(([k, , l]) => `${l} ${pct(probs[k] || 0)}`).join(", ")}">
      ${order.map(([k, c]) => (probs[k] > 0.005 ? `<i class="${c}" style="width:${(probs[k] * 100).toFixed(1)}%"></i>` : "")).join("")}</div>
    <div class="problegend">${order.map(([k, c, l]) => `<span><i style="background:var(--${c})"></i>${l} <b>${pct(probs[k] || 0)}</b></span>`).join("")}</div></div>`;
}

function inputChecklist(missing) {
  const seen = new Set();
  const rows = Object.keys(INPUT_NAMES).filter((k) => {
    const name = INPUT_NAMES[k][0];
    if (seen.has(name)) return false;
    seen.add(name);
    return true;
  });
  return `<div class="checklist">${rows.map((k) => {
    const [name, dev] = INPUT_NAMES[k];
    const ok = !missing.some((m) => INPUT_NAMES[m][0] === name);
    return `<div class="check ${ok ? "ok" : "no"}"><span class="mark">${ok ? icon("check", "xs") : ""}</span>
      <span class="grow">${name}</span><span class="subtle xsmall">${ok ? "Fresh" : `Needs ${dev}`}</span></div>`;
  }).join("")}</div>`;
}

async function renderHome() {
  const name = (prefs.user?.name || "").split(" ")[0];
  const hr = new Date().getHours();
  const greet = hr < 12 ? "Good morning" : hr < 18 ? "Good afternoon" : "Good evening";
  const view = shell(`
    ${appbar(name ? `${greet}, ${name}` : greet, {
      eyebrow: new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }),
      action: `<a href="#/profile" class="avatar" aria-label="Profile">${esc((prefs.user?.name || "?")[0].toUpperCase())}</a>`,
    })}
    <div class="row"><a class="chip" id="conn" href="#/devices"></a><span class="grow"></span>
      <a href="#/model" class="chip">${icon("shield", "xs")} Validated model</a></div>
    <section id="status" class="card status-card" aria-live="polite">
      <div class="skel" style="height:30px;width:40%"></div><div class="skel" style="height:56px;width:60%"></div><div class="skel" style="height:10px"></div>
    </section>
    <section id="overall"></section>
    <div class="section-head"><h2>Vitals</h2><a href="#/trends">See trends</a></div>
    <section id="tiles" class="vitals"></section>
    <a class="card action-card" href="#/scan" id="scan-tile"></a>
    <div class="section-head"><h2>Evidence-based tip</h2><a href="#/library">Library</a></div>
    <section id="tip" class="card"></section>
    <p class="disclaimer">For information only, not a diagnosis. Contact a clinician about any concern.</p>`);

  let status = null;
  const hist = {};

  const connLabel = () => {
    const c = $("#conn");
    if (!c) return;
    const on = live.esp === "connected";
    c.className = `chip ${live.demo ? "demo" : on ? "live" : ""}`;
    c.innerHTML = `<span class="dot"></span>${live.demo ? "Demo data" : on ? "Bandage live" : "Bandage offline"}`;
  };

  async function drawTip() {
    const t = TIPS[Math.floor(Date.now() / 864e5) % TIPS.length];
    let cite = "";
    try {
      const info = await loadInfo();
      const p = info.papers.find((x) => x.id === t.id);
      if (p) cite = `<a href="#" data-url="${esc(p.url)}" class="cite-link">${icon("book", "xs")} ${esc(citeName(p))} · PubMed</a>`;
    } catch {
      /* the tip still reads fine without its citation */
    }
    const el = $("#tip");
    if (!el) return;
    el.innerHTML = `<div class="insight"><span class="art">${icon(t.icon)}</span><div><b>${esc(t.title)}</b><p>${esc(t.body)}</p>${cite}</div></div>`;
    bindLinks(el);
  }

  function drawStatus() {
    const el = $("#status");
    if (!el) return;
    const w = status?.wound;
    const missing = status?.missing || [];
    if (!w) {
      el.innerHTML = `<div class="status-top"><span class="tag primary">Wound assessment</span></div>
        <div><h3 style="font-size:20px">Get your first assessment</h3>
          <p class="muted small" style="margin-top:4px">The model needs fresh readings from your bandage and watch.</p></div>
        ${inputChecklist(missing)}
        <div class="btn-row"><a class="btn primary" href="#/devices">${icon("bandage", "sm")} Connect devices</a></div>`;
      return;
    }
    const s = STATUS[w.condition] || STATUS.wound_healing;
    const tr = { improving: ["up", "Improving"], stable: ["flat", "Stable"], worsening: ["down", "Worsening"], new: ["sparkle", "First assessment"] }[w.trend];
    const stale = missing.length > 0;
    el.innerHTML = `
      <div class="status-top"><span class="status-badge ${s.cls}">${icon(s.icon, "sm")}${s.label}</span>
        <span class="trend">${icon(tr[0], "sm")}${tr[1]}</span></div>
      <a class="hero-metric" href="#/metric/healing_days">
        <div><p class="label">Estimated time to heal</p><p class="value">${Math.round(w.healing_days)}<small>${Math.round(w.healing_days) === 1 ? "day" : "days"}</small></p></div>
        <div class="conf"><span class="subtle xsmall">Confidence</span><b>${pct(w.confidence)}</b></div></a>
      ${probBar(w.probs)}
      <p class="small muted">${s.blurb}</p>
      ${stale ? `<div class="notice warn">${icon("info", "sm")}<span>This assessment is from ${ago(Date.parse(w.at)).toLowerCase()}. Fresh ${[...new Set(missing.map((m) => INPUT_NAMES[m][0].toLowerCase()))].join(" and ")} readings will update it.</span></div>` : ""}
      <div class="status-foot"><span>Updated ${ago(Date.parse(w.at)).toLowerCase()}</span><a class="link-btn small" href="#/model">How this works</a></div>`;
  }

  function drawExtras() {
    const o = status?.overall;
    const ov = $("#overall");
    if (ov) {
      const meta = { ok: ["check", "Looking steady"], watch: ["info", "Keep an eye on it"], alert: ["alert", "Needs attention"] };
      ov.innerHTML = o && o.level !== "ok"
        ? `<div class="alert-card ${o.level}" role="status">${icon(meta[o.level][0])}<div><b>${meta[o.level][1]}</b>
             <ul>${o.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div></div>`
        : "";
    }
    const t = $("#scan-tile");
    if (t) {
      const s = status?.scan;
      t.innerHTML = `<span class="art">${icon("camera", "lg")}</span>
        <div class="grow"><b>Scan your wound</b><span>${
          s ? `Last: ${esc(TYPE_NAME[s.type.label] || s.type.label)} · ${ago(Date.parse(s.created_at)).toLowerCase()}` : "Photo check for wound type and appearance"
        }</span></div>${icon("chev", "chev")}`;
    }
  }

  function drawTiles() {
    const el = $("#tiles");
    if (!el) return;
    el.innerHTML = TILE_ORDER.map((id) => {
      const m = METRICS[id];
      const v = currentValue(m, status);
      const series = (hist[id] || []).map((p) => p[m.fields[0]]).filter((x) => x != null);
      return `<a class="vital ${m.cls} ${id === "moisture" ? "wide" : ""}" href="#/metric/${id}">
        <div class="vital-head"><span class="vital-ic">${icon(m.icon)}</span>${m.title}
          ${m.model ? "" : '<span class="tag role">Context</span>'}</div>
        <div class="vital-val"><b data-val="${id}">${v.text}</b><small>${m.unit}</small></div>
        <div class="vital-foot"><span data-age="${id}">${ago(v.at)}</span>${sparkline(series, m.color, id === "moisture" ? 140 : 64, 28)}</div></a>`;
    }).join("");
  }

  function updateLive() {
    connLabel();
    for (const id of TILE_ORDER) {
      const v = currentValue(METRICS[id], status);
      const b = view.querySelector(`[data-val="${id}"]`);
      const a = view.querySelector(`[data-age="${id}"]`);
      if (b) b.textContent = v.text;
      if (a) a.textContent = ago(v.at);
    }
  }

  async function refresh() {
    try {
      const d = demoQS();
      status = await api(`/status?demo=${d}`);
      await Promise.all(
        TILE_ORDER.map(async (id) => {
          hist[id] = (await api(`/history?metric=${id}&hours=24&demo=${d}`)).points;
        }),
      );
      drawStatus();
      drawExtras();
      drawTiles();
    } catch (e) {
      const el = $("#status");
      if (el) {
        el.innerHTML = `<h3>Can't load your data</h3>${errorBox(e)}<a class="btn sm" href="#/profile">Check server settings</a>`;
      }
      drawTiles();
    }
  }

  connLabel();
  drawTiles();
  drawExtras();
  drawTip();
  refresh();
  const poll = setInterval(refresh, 20000);
  const tick = setInterval(updateLive, 1000);
  const off = onLive(updateLive);
  return () => {
    clearInterval(poll);
    clearInterval(tick);
    off();
  };
}

// ---------- metric detail ----------

const RANGES = [["6H", 6], ["24H", 24], ["7D", 168], ["30D", 720]];

async function renderMetric(id) {
  const isHeal = id === "healing_days";
  const m = isHeal ? HEAL : METRICS[id];
  if (!m) {
    location.hash = "#/home";
    return;
  }
  let hours = 24;
  const view = shell(
    `${appbar(m.title, { back: isHeal ? "#/home" : "#/trends" })}
     <section class="card ${m.cls}">
       <div class="readout"><div><p class="big"><span id="big">––</span><small>${m.unit}</small></p>
         <p class="subtle small" id="when">Latest reading</p></div>
         ${m.device ? `<span class="tag">${m.device}</span>` : '<span class="tag primary">Model output</span>'}</div>
       ${id === "blood_pressure" ? `<div class="legend" style="margin-top:8px"><span><i style="background:var(--m-bp)"></i>Systolic</span><span><i style="background:var(--text-3)"></i>Diastolic</span></div>` : ""}
       <div id="chart" class="chart-wrap"></div>
       <div class="seg" role="tablist" aria-label="Time range">${RANGES.map(([l, h]) => `<button role="tab" data-h="${h}" class="${h === hours ? "on" : ""}">${l}</button>`).join("")}</div>
     </section>
     <section class="stats" id="stats"></section>
     <section id="guide" class="stack"></section>`,
  );
  const series = m.fields.map((f, i) => ({ key: f, color: i === 0 ? m.color : "var(--text-3)", dash: i > 0 }));

  async function draw() {
    try {
      const h = await api(`/history?metric=${id}&hours=${hours}&demo=${demoQS()}`);
      const last = h.points[h.points.length - 1];
      const fmt = (p) => m.fields.map((f) => (p?.[f] == null ? "––" : Number(p[f]).toFixed(m.dec))).join("/");
      $("#big").textContent = last ? fmt(last) : "––";
      $("#when").textContent = last ? `Latest · ${when(last.t)}` : "No readings in this range";
      lineChart($("#chart"), {
        points: h.points,
        series,
        decimals: m.dec,
        onScrub: (p) => {
          $("#big").textContent = fmt(p || last);
          $("#when").textContent = p ? when(p.t) : last ? `Latest · ${when(last.t)}` : "";
        },
      });
      const s = h.stats;
      $("#stats").innerHTML = s
        ? [["Low", s.min], ["Average", s.avg], ["High", s.max]].map(([k, v]) => `<div class="stat"><span>${k}</span><b>${v.toFixed(m.dec)}</b></div>`).join("") +
          `<div class="stat"><span>Readings</span><b>${fmtInt(s.count)}</b></div>`
        : "";
    } catch (e) {
      $("#chart").innerHTML = errorBox(e);
    }
  }
  $$(".seg button", view).forEach((b) => {
    b.onclick = () => {
      hours = Number(b.dataset.h);
      $$(".seg button", view).forEach((x) => x.classList.toggle("on", x === b));
      draw();
    };
  });
  draw();

  if (isHeal) {
    $("#guide").innerHTML = `<div class="card"><h3>How this is estimated</h3>
      <p class="muted small" style="margin-top:6px">A Random Forest regressor estimates days to heal from temperature, humidity, heart rate and blood pressure.
      Humidity carries most of the weight. Its targets come from a published-criteria severity score, not real patient outcomes, so read it as a trend, not a date.</p>
      <a class="btn tonal sm" style="margin-top:12px" href="#/model">${icon("shield", "sm")} Model & validation</a></div>`;
    return;
  }
  try {
    const info = await loadInfo();
    const g = info.guides[id];
    const papers = g.papers.map((pid) => info.papers.find((p) => p.id === pid)).filter(Boolean);
    $("#guide").innerHTML = `<div class="card"><h3>About this measurement</h3>
        <p class="muted small" style="margin-top:6px">${esc(g.what)}</p><p class="small" style="margin-top:8px">${esc(g.evidence)}</p>
        <div class="callout"><b>Good to know:</b> ${esc(g.tip)}</div></div>
      <div class="section-head"><h2>Research</h2><span class="subtle small">${papers.length} studies</span></div>
      <div class="list">${papers.map(paperCard).join("")}</div>`;
    bindLinks(view);
  } catch {
    /* evidence is optional; the chart is the point of this screen */
  }
}

function paperCard(p) {
  return `<article class="paper"><h4>${esc(p.title)}</h4>
    <p class="meta">${esc(citeName(p))} · ${esc(p.journal)}</p>
    <p>${esc(p.key_findings)}</p>
    <div class="foot">${(p.sensors || []).map((s) => `<span class="tag">${esc(s.replace("_", " "))}</span>`).join("")}
      <span class="grow"></span><a href="#" data-url="${esc(p.url)}" class="cite-link">${p.pmid ? `PMID ${esc(p.pmid)}` : "Source"} ${icon("external", "xs")}</a></div></article>`;
}

// ---------- trends ----------

async function renderTrends() {
  let hours = 24;
  const view = shell(`
    ${appbar("Trends", { eyebrow: "Your progress over time" })}
    <div class="seg" role="tablist" aria-label="Time range">${[["24H", 24], ["7D", 168], ["30D", 720]].map(([l, h]) => `<button role="tab" data-h="${h}" class="${h === hours ? "on" : ""}">${l}</button>`).join("")}</div>
    <a class="card c-heal" href="#/metric/healing_days">
      <div class="readout"><div><p class="subtle small">Estimated days to heal</p><p class="big"><span id="th-val">––</span><small>days</small></p></div>
        <span class="tag primary">Model output</span></div>
      <div id="th-chart" class="chart-wrap"></div></a>
    <div class="section-head"><h2>Vitals</h2></div>
    <div id="cards" class="list"></div>`);

  async function draw() {
    const d = demoQS();
    try {
      const [heal, ...rest] = await Promise.all([
        api(`/history?metric=healing_days&hours=${hours}&demo=${d}`),
        ...TILE_ORDER.map((id) => api(`/history?metric=${id}&hours=${hours}&demo=${d}`)),
      ]);
      const last = heal.points[heal.points.length - 1];
      const show = (p) => ($("#th-val").textContent = p ? Number(p.healing_days).toFixed(0) : "––");
      show(last);
      lineChart($("#th-chart"), { points: heal.points, series: [{ key: "healing_days", color: "var(--m-heal)" }], decimals: 0, onScrub: (p) => show(p || last) });
      $("#cards").innerHTML = TILE_ORDER.map((id, i) => {
        const m = METRICS[id];
        const h = rest[i];
        const vals = h.points.map((p) => p[m.fields[0]]).filter((x) => x != null);
        const s = h.stats;
        const change = vals.length > 1 ? vals[vals.length - 1] - vals[0] : null;
        const dir = change == null ? null : Math.abs(change) < 10 ** -m.dec ? "flat" : change > 0 ? "up" : "down";
        return `<a class="lr ${m.cls}" href="#/metric/${id}"><span class="lr-ic">${icon(m.icon)}</span>
          <div class="grow"><b>${m.title}</b><span>${s ? `Range ${s.min.toFixed(m.dec)}–${s.max.toFixed(m.dec)} ${m.unit}` : "No data in this range"}</span></div>
          ${sparkline(vals, m.color, 64, 28)}
          <div class="end"><b>${s ? s.avg.toFixed(m.dec) : "––"}</b>${dir ? `<span class="trend">${icon(dir, "xs")}${Math.abs(change).toFixed(m.dec)}</span>` : "avg"}</div></a>`;
      }).join("");
    } catch (e) {
      $("#cards").innerHTML = `<div style="padding:16px">${errorBox(e)}</div>`;
    }
  }
  $$(".seg button", view).forEach((b) => {
    b.onclick = () => {
      hours = Number(b.dataset.h);
      $$(".seg button", view).forEach((x) => x.classList.toggle("on", x === b));
      draw();
    };
  });
  draw();
}

// ---------- scan wound (photo) ----------

function downscale(file, max = 768) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * k);
      c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.88));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Could not open that image."));
    };
    img.src = url;
  });
}

function scanResultHtml(r) {
  const bars = r.type.top.slice(0, 3).map((t, i) =>
    `<div class="hbar ${i === 0 ? "ours" : ""}"><div class="hb-top"><span>${esc(TYPE_NAME[t.label] || t.label)}</span><b>${pct(t.p)}</b></div>
      <div class="track"><div class="fill" style="--w:${(t.p * 100).toFixed(1)}%"></div></div></div>`).join("");
  return `<div class="card stack">
    <div class="result-head"><div><p class="subtle small">Looks most like</p><h3>${esc(TYPE_NAME[r.type.label] || r.type.label)}</h3></div>
      ${r.severity ? `<span class="tag">${esc(r.severity.label)} appearance</span>` : ""}</div>
    ${r.quality.map((w) => `<div class="notice warn">${icon("info", "sm")}<span>${esc(w)}</span></div>`).join("")}
    ${r.notes.map((w) => `<div class="notice">${icon("info", "sm")}<span>${esc(w)}</span></div>`).join("")}
    <div class="hbars">${bars}</div>
    <p class="subtle xsmall">Wound type from a CLIP image model (77.6% cross-validated accuracy on 1,564 public photos). It does not detect infection or predict healing time.</p>
  </div>`;
}

async function renderScan() {
  const view = shell(
    `${appbar("Scan wound", { eyebrow: "Photo check" })}
    <section class="card stack">
      <div id="preview" class="dropzone"><div class="ph">${icon("image")}<b>Add a photo of the wound</b><span class="small">JPEG or PNG · nothing else in frame</span></div></div>
      <div class="guidelines"><span>${icon("sun", "sm")}Good, even light</span><span>${icon("focus", "sm")}Centred and in focus</span>
        <span>${icon("ruler", "sm")}15–20 cm away</span><span>${icon("shield", "sm")}No faces or IDs</span></div>
      <div class="btn-row">
        <label class="btn primary">${icon("camera", "sm")} Take photo<input id="cam" type="file" accept="image/*" capture="environment" hidden /></label>
        <label class="btn">${icon("image", "sm")} Upload<input id="gal" type="file" accept="image/*" hidden /></label>
      </div>
    </section>
    <div id="result"></div>
    <div class="section-head"><h2>Previous scans</h2></div>
    <div id="history" class="list"><div class="scan-row"><div class="thumb-ph skel"></div><div class="grow"><div class="skel" style="height:14px;width:50%"></div></div></div></div>`,
  );

  async function loadHistory() {
    try {
      const h = await api("/scans");
      $("#history").innerHTML = h.scans.length
        ? h.scans.map((s) => `<div class="scan-row"><img src="${s.thumb}" alt="" /><div class="grow"><b>${esc(TYPE_NAME[s.type.label] || s.type.label)}</b>
            <p class="subtle small">${when(s.created_at)}${s.severity ? ` · ${esc(s.severity.label)}` : ""}</p></div>
            ${s.reliable ? `<span class="small muted">${pct(s.type.confidence)}</span>` : '<span class="tag">Retake</span>'}</div>`).join("")
        : `<div class="scan-row"><span class="subtle small">No scans yet. Your photo history appears here.</span></div>`;
    } catch (e) {
      $("#history").innerHTML = `<div style="padding:16px">${errorBox(e)}</div>`;
    }
  }

  async function handle(file) {
    if (!file) return;
    $("#result").innerHTML = `<div class="card row"><span class="spinner" style="color:var(--primary)"></span><span class="muted">Analysing photo…</span></div>`;
    try {
      const dataUrl = await downscale(file);
      $("#preview").innerHTML = `<img src="${dataUrl}" alt="Your photo" />`;
      const r = await api("/scan", { method: "POST", body: { image: dataUrl }, timeout: 60000 });
      $("#result").innerHTML = scanResultHtml(r);
      loadHistory();
    } catch (e) {
      $("#result").innerHTML = errorBox(e);
    }
  }
  $("#cam", view).onchange = (e) => handle(e.target.files[0]);
  $("#gal", view).onchange = (e) => handle(e.target.files[0]);
  loadHistory();
}

// ---------- chat ----------

function renderMarkdown(text) {
  const clean = text
    .replace(/[\u200b\u200c\u200d\u2060]/g, "")
    .replace(/\u3010/g, "[").replace(/\u3011/g, "]")
    .replace(/[ \t]+([.,;:])/g, "$1"); // tidy the gap left where an unverified citation was removed
  const inline = (raw) => {
    let h = esc(raw);
    h = h.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|\s)\*(?!\s)(.+?)\*(?=\s|$|[.,;])/g, "$1<i>$2</i>");
    return h.replace(/\[([A-Z][^[\]]{1,60}?,\s?\d{4}[a-z]?)\]/g, '<span class="cite">$1</span>');
  };
  const cells = (ln) => ln.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  const lines = clean.split("\n");
  let out = "";
  let list = false;
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    if (list && !/^\s*[-*•]\s+/.test(ln)) (out += "</ul>"), (list = false);
    if (/^\s*\|/.test(ln) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const head = cells(ln);
      let rows = "";
      i += 2;
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows += `<tr>${cells(lines[i++]).map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`;
      i--;
      out += `<div class="table-wrap"><table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;
      continue;
    }
    const heading = ln.match(/^\s{0,3}#{1,6}\s+(.*)/);
    if (heading) {
      out += `<h4 class="md-h">${inline(heading[1])}</h4>`;
      continue;
    }
    const bullet = ln.match(/^\s*[-*•]\s+(.*)/);
    if (bullet) {
      if (!list) (out += "<ul>"), (list = true);
      out += `<li>${inline(bullet[1])}</li>`;
      continue;
    }
    if (/^\s*---+\s*$/.test(ln)) continue;
    out += ln.trim() ? `<p>${inline(ln)}</p>` : "";
  }
  return out + (list ? "</ul>" : "");
}

// The conversation lives in memory only: it survives switching tabs but is gone when the app restarts.
let chatLog = [];

async function renderChat() {
  const view = shell(`
    ${appbar("Assistant", { eyebrow: "Grounded in your data and PubMed", action: `<button class="icon-btn" id="newchat" aria-label="New conversation">${icon("edit")}</button>` })}
    <div id="thread" class="thread" aria-live="polite"></div>
    <form id="cf" class="composer"><input id="msg" class="input" placeholder="Ask about your wound…" autocomplete="off" aria-label="Message" />
      <button class="send" id="send" aria-label="Send">${icon("send")}</button></form>`, { cls: "chat-view" });
  const thread = $("#thread");
  const sugg = [
    ["temp", "What does my temperature mean?"],
    ["alert", "Are there signs of infection?"],
    ["drop", "Is my dressing too wet?"],
    ["heart", "How does stress affect healing?"],
  ];
  const scrollEnd = () => window.scrollTo({ top: document.body.scrollHeight });

  const empty = () => {
    thread.innerHTML = `<div class="chat-empty"><div class="logo">${icon("sparkle")}</div><h2>How can I help?</h2>
      <p class="muted small">I explain your readings using 28 PubMed studies and cite every claim. I'm not a doctor and will point you to a clinician for anything concerning.</p></div>
      <div class="suggestions">${sugg.map(([ic, s]) => `<button type="button" class="suggestion">${icon(ic, "sm")}${esc(s)}</button>`).join("")}</div>`;
    $$(".suggestion", thread).forEach((b) => (b.onclick = () => send(b.textContent)));
  };

  const add = (role, html = "") => {
    $(".chat-empty", thread)?.remove();
    $(".suggestions", thread)?.remove();
    const d = document.createElement("div");
    d.className = `msg ${role}`;
    d.innerHTML = role === "bot" ? `<span class="bot-av">${icon("sparkle")}</span><div class="body">${html}</div>` : html;
    thread.appendChild(d);
    scrollEnd();
    return role === "bot" ? $(".body", d) : d;
  };

  const sourcesHtml = (list) =>
    `<div class="sources"><span>Sources</span>${list.map((c) => `<a href="#" class="source" data-url="${esc(c.url)}">${icon("book", "sm")}
      <span><b>${esc(c.tag.replace(/[[\]]/g, ""))}</b> · ${esc(c.title)} <i class="subtle">${esc(c.journal)}</i></span></a>`).join("")}</div>`;

  if (chatLog.length) {
    chatLog.forEach((t) => {
      if (t.role === "user") add("me", esc(t.content));
      else {
        const b = add("bot", renderMarkdown(t.content));
        if (t.cites?.length) b.insertAdjacentHTML("beforeend", sourcesHtml(t.cites));
        bindLinks(b);
      }
    });
  } else empty();

  let busy = false;
  async function send(text) {
    text = text.trim();
    if (!text || busy) return;
    busy = true;
    $("#send").disabled = true;
    $("#msg").value = "";
    add("me", esc(text));
    const bot = add("bot", '<span class="typing" aria-label="Assistant is typing"><i></i><i></i><i></i></span>');
    const history = chatLog.slice(-8).map(({ role, content }) => ({ role, content }));
    try {
      const full = await streamChat(text, live.demo, history, (t) => {
        bot.innerHTML = renderMarkdown(t.split("\n\n__CITATIONS__:")[0]) || bot.innerHTML;
        scrollEnd();
      });
      const [body, cites] = full.split("\n\n__CITATIONS__:");
      bot.innerHTML = renderMarkdown(body);
      const list = cites ? JSON.parse(cites) : [];
      chatLog.push({ role: "user", content: text }, { role: "assistant", content: body, cites: list });
      if (list.length) {
        bot.insertAdjacentHTML("beforeend", sourcesHtml(list));
        bindLinks(bot);
      }
    } catch (e) {
      bot.innerHTML = errorBox(e);
    }
    busy = false;
    $("#send").disabled = false;
    scrollEnd();
  }
  $("#cf").onsubmit = (e) => (e.preventDefault(), send($("#msg").value));
  $("#newchat").onclick = () => {
    if (busy) return;
    chatLog = [];
    empty();
  };
}

// ---------- my wound ----------

async function renderWound() {
  const view = shell(`
    ${appbar("My wound", { back: "#/profile", action: `<a href="#/scan" class="icon-btn" aria-label="Scan wound">${icon("camera")}</a>` })}
    <section id="summary" class="card"><div class="wound-head"><div class="thumb-ph skel"></div><div class="grow"><div class="skel" style="height:18px;width:60%"></div></div></div></section>
    <div class="seg" role="tablist"><button data-t="overview" class="on">Overview</button><button data-t="details">Details</button><button data-t="learn">Learn</button></div>
    <div id="tab"></div>`);
  let info;
  let scans = [];
  try {
    [info, { scans }] = await Promise.all([loadInfo(), api("/scans")]);
  } catch (e) {
    $("#tab").innerHTML = errorBox(e);
    return;
  }
  const c = info.context || {};
  const last = scans[0];
  const created = c.created_at ? Date.parse(c.created_at + (/[zZ]|[+-]\d\d:\d\d$/.test(c.created_at) ? "" : "Z")) : null;
  const dayN = created ? Math.max(0, Math.floor((Date.now() - created) / 864e5)) + (c.days_since_onset || 0) + 1 : null;

  $("#summary").innerHTML = `<div class="wound-head">
      ${last ? `<img src="${last.thumb}" alt="Latest wound photo" />` : `<div class="thumb-ph">${icon("bandage", "lg")}</div>`}
      <div class="grow"><p class="subtle small">${last ? `Latest scan · ${ago(Date.parse(last.created_at)).toLowerCase()}` : "No scan yet"}</p>
        <h2>${esc(last ? TYPE_NAME[last.type.label] || last.type.label : c.cause || "Tell us about your wound")}</h2>
        <div class="chips">${dayN ? `<span class="chip">Day ${dayN}</span>` : ""}${c.pain_level != null ? `<span class="chip">Pain ${c.pain_level}/10</span>` : ""}${
          c.itching_level != null ? `<span class="chip">Itch ${c.itching_level}/10</span>` : ""}</div></div></div>`;

  const paper = (id) => info.papers.find((x) => x.id === id);
  const tabs = {
    overview: () => `<div class="stack">
      <div class="section-head"><h2>Care guidance</h2></div>
      ${TIPS.map((t) => {
        const p = paper(t.id);
        return `<div class="card insight"><span class="art">${icon(t.icon)}</span><div><b>${esc(t.title)}</b><p>${esc(t.body)}</p>
          ${p ? `<a href="#" data-url="${esc(p.url)}" class="cite-link">${icon("book", "xs")} ${esc(citeName(p))}</a>` : ""}</div></div>`;
      }).join("")}
      <div class="notice">${icon("stethoscope", "sm")}<span>Spreading redness, pus, fever, a bad smell or pain that keeps rising deserve a prompt check by a clinician, whatever the app shows.</span></div></div>`,
    details: () => {
      const causes = ["Burn", "Cut or laceration", "Surgical wound", "Pressure injury", "Diabetic foot ulcer", "Venous leg ulcer", "Other"];
      const sev = ["Mild", "Moderate", "Severe"];
      const opt = (list, cur) => list.map((x) => `<option ${x === cur ? "selected" : ""}>${x}</option>`).join("");
      return `<form id="ctx" class="card stack">
        <div class="grid2">
          <label class="field"><span>Cause</span><select class="input" name="cause"><option value="">Select</option>${opt(causes, c.cause)}</select></label>
          <label class="field"><span>Severity</span><select class="input" name="severity"><option value="">Select</option>${opt(sev, c.severity)}</select></label>
        </div>
        <label class="field"><div class="range-head"><span>Pain</span><b id="pv">${c.pain_level ?? 0} / 10</b></div><input type="range" name="pain_level" min="0" max="10" value="${c.pain_level ?? 0}" /></label>
        <label class="field"><div class="range-head"><span>Itching</span><b id="iv">${c.itching_level ?? 0} / 10</b></div><input type="range" name="itching_level" min="0" max="10" value="${c.itching_level ?? 0}" /></label>
        <label class="field"><span>Days since the wound happened</span><input class="input" type="number" inputmode="numeric" name="days_since_onset" min="0" value="${c.days_since_onset ?? 0}" /></label>
        <label class="field"><span>Notes</span><textarea class="input" name="notes" rows="3" placeholder="Anything your care team or the assistant should know">${esc(c.notes || "")}</textarea></label>
        <button class="btn primary block" id="save">Save details</button></form>`;
    },
    learn: () => `<div class="stack">
      <div class="section-head"><h2>Your sensors</h2></div>
      ${["temperature", "humidity", "heart_rate", "blood_pressure", "moisture"].map((k) => {
        const g = info.guides[k];
        const m = METRICS[k];
        return `<details class="card fold"><summary><span class="row ${m.cls}"><span class="lr-ic">${icon(m.icon, "sm")}</span>${esc(g.title)}</span>${icon("chev")}</summary>
          <p class="muted small">${esc(g.what)}</p><p class="small" style="margin-top:8px">${esc(g.evidence)}</p>
          <div class="callout"><b>Good to know:</b> ${esc(g.tip)}</div></details>`;
      }).join("")}
      <div class="list">
        <a class="lr" href="#/library"><span class="lr-ic neutral">${icon("book")}</span><div class="grow"><b>Research library</b><span>${info.papers.length} PubMed studies</span></div>${icon("chev", "chev")}</a>
        <a class="lr" href="#/model"><span class="lr-ic neutral">${icon("shield")}</span><div class="grow"><b>Model & validation</b><span>How the assessment is made and tested</span></div>${icon("chev", "chev")}</a>
      </div></div>`,
  };

  function show(name) {
    $$(".seg button", view).forEach((b) => b.classList.toggle("on", b.dataset.t === name));
    $("#tab").innerHTML = tabs[name]();
    bindLinks(view);
    const ctx = $("#ctx");
    if (ctx) {
      ctx.querySelector('[name="pain_level"]').oninput = (e) => ($("#pv").textContent = `${e.target.value} / 10`);
      ctx.querySelector('[name="itching_level"]').oninput = (e) => ($("#iv").textContent = `${e.target.value} / 10`);
      ctx.onsubmit = async (e) => {
        e.preventDefault();
        const btn = $("#save");
        btn.disabled = true;
        try {
          await api("/wound-context", { method: "POST", body: Object.fromEntries(new FormData(ctx)) });
          infoCache = null;
          toast("Details saved. The assistant will use them.");
        } catch (er) {
          toast(er.message);
        }
        btn.disabled = false;
      };
    }
  }
  $$(".seg button", view).forEach((b) => (b.onclick = () => show(b.dataset.t)));
  show("overview");
}

// ---------- model & validation ----------

async function renderModel() {
  shell(`${appbar("Model & validation", { back: "#/profile" })}<div id="mc" class="stack">
    <div class="card"><div class="skel" style="height:80px"></div></div><div class="card"><div class="skel" style="height:160px"></div></div></div>`);
  let m;
  try {
    m = await loadModel();
  } catch (e) {
    $("#mc").innerHTML = errorBox(e);
    return;
  }
  const x = m.external;
  const featName = { temperature: "Temperature", humidity: "Humidity", heart_rate: "Heart rate", systolic_bp: "Systolic BP", diastolic_bp: "Diastolic BP" };
  const imp = (obj) => {
    const max = Math.max(...Object.values(obj));
    return Object.entries(obj).sort((a, b) => b[1] - a[1]).map(([k, v]) =>
      `<div class="hbar"><div class="hb-top"><span>${featName[k] || k}</span><b>${pct(v)}</b></div>
        <div class="track"><div class="fill" style="--w:${((v / max) * 100).toFixed(1)}%;background:var(--primary)"></div></div></div>`).join("");
  };
  // bars start at 0.5 (chance), so their length is skill above chance
  const aurocBars = x
    ? x.patient_auroc.map((r) => `<div class="hbar ${r.ours ? "ours" : ""}"><div class="hb-top"><span>${esc(r.name)}</span>
        <b>${r.auroc.toFixed(3)}${r.ci ? ` <span class="subtle xsmall">(${r.ci[0].toFixed(3)}–${r.ci[1].toFixed(3)})</span>` : ""}</b></div>
        <div class="track"><div class="fill" style="--w:${Math.max(2, ((r.auroc - 0.5) / 0.25) * 100).toFixed(1)}%"></div></div></div>`).join("")
    : "";

  $("#mc").innerHTML = `
    <div class="card"><div class="row"><span class="lr-ic" style="background:var(--primary-soft);color:var(--primary)">${icon("shield")}</span>
      <div class="grow"><h3>How your assessment is made</h3><p class="subtle small">${esc(m.algorithm)} · trained ${new Date(m.trained_at).toLocaleDateString([], { month: "short", year: "numeric" })}</p></div></div>
      <p class="small muted" style="margin-top:12px">The model reads five inputs: temperature and humidity from your bandage, and heart rate and blood pressure from your watch.
      It runs only when every input is fresh (bandage within ${m.freshness.temperature} min, watch within ${m.freshness.bpm / 60} h).
      It outputs a condition (on track, healing, needs attention) and an estimated number of days to heal.</p></div>

    <div class="kpis">
      <div class="card kpi"><span>External AUROC</span><b>${x ? x.patient_auroc[0].auroc.toFixed(3) : "–"}</b><p>${x ? `${fmtInt(x.patients)} ICU patients, never seen in training` : "Not available"}</p></div>
      <div class="card kpi"><span>Holdout accuracy</span><b>${pct(m.holdout.accuracy, 1)}</b><p>Macro-F1 ${m.holdout.macro_f1.toFixed(2)} · n=${fmtInt(m.holdout.n)}</p></div>
      <div class="card kpi"><span>Days-to-heal error</span><b>${m.healing.mae_days.toFixed(1)} d</b><p>Mean absolute error · R² ${m.healing.r2.toFixed(2)}</p></div>
      <div class="card kpi"><span>Sensitivity</span><b>${x ? pct(x.sens_at_80_spec) : "–"}</b><p>At 80% specificity, external test</p></div>
    </div>

    ${x ? `<div class="card stack">
      <div><span class="tag primary">External validation</span><h3 style="margin-top:8px">Tested on real patient data</h3>
        <p class="small muted" style="margin-top:4px">${esc(x.dataset)} (${fmtInt(x.patients)} patients, ${fmtInt(x.sepsis_patients)} with sepsis, ${fmtInt(x.hours)} hourly records). Patient-level AUROC for detecting sepsis, compared with standard clinical screening rules:</p></div>
      <div class="hbars" role="list">${aurocBars}</div>
      <p class="subtle xsmall">Bar length shows AUROC above chance (0.5). 95% confidence interval in brackets.</p>
      <div class="callout"><b>Days to heal also tracks illness:</b> on the same data the model estimated ${x.healing_days_sepsis.toFixed(1)} days during sepsis versus ${x.healing_days_no_sepsis.toFixed(1)} without.</div>
      <a href="#" class="cite-link" data-url="${esc(x.url)}">${icon("external", "xs")} PhysioNet dataset · ${esc(x.license)}</a>
    </div>` : ""}

    <div class="card stack"><h3>What drives the condition result</h3><div class="hbars">${imp(m.holdout.feature_importance)}</div>
      <p class="subtle xsmall">Random Forest feature importance.</p></div>

    <div class="card stack"><h3>Per-class performance (holdout)</h3>
      <div class="hbars">${m.holdout.per_class.map((r) => `<div class="hbar"><div class="hb-top"><span>${(STATUS[r.class] || {}).label || r.class}</span><b>F1 ${r.f1.toFixed(2)}</b></div>
        <div class="track"><div class="fill" style="--w:${(r.f1 * 100).toFixed(1)}%;background:var(--primary)"></div></div></div>`).join("")}</div></div>

    <div class="card"><h3>Limitations</h3>
      <ul class="small muted" style="padding-left:18px;margin:8px 0 0;display:flex;flex-direction:column;gap:6px">
        <li>${esc(m.training.source)}</li>
        <li>${esc(m.training.healing_days_source)}</li>
        ${x ? `<li>${esc(x.label_caveat)}</li><li>Humidity: ${esc(x.missing_feature)}.</li>` : ""}
        <li>Dressing moisture is shown for context and is not a model input.</li>
        <li>WoundSense is a prototype, not a medical device, and has not been tested on wound patients.</li>
      </ul></div>`;
  bindLinks($("#mc"));
}

// ---------- research library ----------

async function renderLibrary() {
  let filter = "all";
  const view = shell(`${appbar("Research library", { back: "#/profile" })}
    <p class="muted small">Every study the assistant can cite. Titles, authors and abstracts come verbatim from PubMed.</p>
    <div class="seg" id="filters">${[["all", "All"], ["temperature", "Temp"], ["humidity", "Humidity"], ["heart_rate", "Heart"], ["blood_pressure", "BP"]]
      .map(([k, l]) => `<button data-f="${k}" class="${k === filter ? "on" : ""}">${l}</button>`).join("")}</div>
    <div id="lib" class="list"><div class="paper"><div class="skel" style="height:60px"></div></div></div>`);
  let info;
  try {
    info = await loadInfo();
  } catch (e) {
    $("#lib").innerHTML = `<div style="padding:16px">${errorBox(e)}</div>`;
    return;
  }
  const draw = () => {
    const list = info.papers.filter((p) => filter === "all" || (p.sensors || []).includes(filter)).sort((a, b) => b.year - a.year);
    $("#lib").innerHTML = list.map(paperCard).join("") || `<div class="paper subtle">No studies.</div>`;
    bindLinks(view);
  };
  $$("#filters button", view).forEach((b) => {
    b.onclick = () => {
      filter = b.dataset.f;
      $$("#filters button", view).forEach((x) => x.classList.toggle("on", x === b));
      draw();
    };
  });
  draw();
}

// ---------- devices ----------

const STATE_TEXT = { off: "Not connected", scanning: "Searching…", connecting: "Connecting…", connected: "Connected", waiting: "Waiting for a measurement", done: "Measurement received", error: "Couldn't connect" };
const stateCls = (s) => (["connected", "done"].includes(s) ? "on" : ["scanning", "connecting", "waiting"].includes(s) ? "busy" : s === "error" ? "err" : "");

function renderDevices() {
  shell(`${appbar("Devices", { back: "#/profile" })}<div id="dev" class="stack"></div>`);
  const draw = () => {
    const busyEsp = ["scanning", "connecting"].includes(live.esp);
    const busyWatch = ["scanning", "connecting", "waiting"].includes(live.watch);
    const v = live.values;
    const num = (x, d = 0) => (x == null ? "––" : Number(x).toFixed(d));
    $("#dev").innerHTML = `
      ${live.message ? errorBox(live.message) : ""}
      <section class="card device c-temp">
        <div class="device-head"><span class="device-art vital-ic">${icon("bandage", "lg")}</span>
          <div class="grow"><h3>Smart bandage</h3><span class="state ${stateCls(live.esp)}"><i></i>${STATE_TEXT[live.esp]}</span></div></div>
        ${live.esp === "connected" ? `<div class="readings"><div><span>Temp</span><b>${num(v.temperature, 1)} °C</b></div><div><span>Humidity</span><b>${num(v.humidity)} %</b></div><div><span>Moisture</span><b>${num(v.moisture, 1)}</b></div></div>` : ""}
        <button class="btn ${live.esp === "connected" ? "" : "primary"} block" id="esp" ${busyEsp || busyWatch ? "disabled" : ""}>
          ${busyEsp ? `<span class="spinner"></span> ${STATE_TEXT[live.esp]}` : live.esp === "connected" ? "Disconnect" : "Connect bandage"}</button>
      </section>
      <section class="card device c-hr">
        <div class="device-head"><span class="device-art vital-ic">${icon("watch", "lg")}</span>
          <div class="grow"><h3>MS1020 watch</h3><span class="state ${stateCls(live.watch)}"><i></i>${STATE_TEXT[live.watch]}</span></div></div>
        ${live.watch === "waiting" || live.watch === "done" ? `<div class="readings"><div><span>Heart rate</span><b>${num(v.bpm)} bpm</b></div><div style="grid-column:span 2"><span>Blood pressure</span><b>${num(v.systolic)}/${num(v.diastolic)} mmHg</b></div></div>` : ""}
        ${live.watch === "waiting"
          ? `<p class="small muted">Start a heart-rate or blood-pressure measurement on the watch. Readings appear here as they arrive.</p>
             <button class="btn primary block" id="watch-done">Done</button>`
          : `<button class="btn block" id="watch" ${busyWatch || busyEsp ? "disabled" : ""}>${busyWatch ? `<span class="spinner"></span> ${STATE_TEXT[live.watch]}` : "Measure now"}</button>`}
      </section>
      <section class="card"><div class="row"><div class="grow"><h3>Demo data</h3><p class="subtle small">Simulated readings, stored separately and never mixed with real ones.</p></div>
        <label class="switch"><input type="checkbox" id="demo" ${live.demo ? "checked" : ""} aria-label="Demo data"/><i></i></label></div></section>
      <div class="notice">${icon("info", "sm")}<span>The phone holds one Bluetooth connection at a time. The bandage streams continuously; a watch measurement briefly pauses it, then the bandage reconnects.</span></div>`;
    const esp = $("#esp");
    if (esp) esp.onclick = () => (live.esp === "connected" ? disconnectBandage() : connectBandage());
    const w = $("#watch");
    if (w) w.onclick = () => measureOnWatch();
    const wd = $("#watch-done");
    if (wd) wd.onclick = () => finishWatchSession();
    $("#demo").onchange = (e) => (e.target.checked ? startDemo() : stopDemo());
  };
  draw();
  return onLive(draw);
}

// ---------- profile ----------

function renderProfile() {
  const u = prefs.user || {};
  const row = (href, ic, title, sub) =>
    `<a class="lr" href="${href}"><span class="lr-ic neutral">${icon(ic)}</span><div class="grow"><b>${title}</b><span>${sub}</span></div>${icon("chev", "chev")}</a>`;
  const bandage = live.demo ? "Demo data on" : live.esp === "connected" ? "Bandage connected" : "Bandage not connected";
  shell(`
    ${appbar("Profile")}
    <section class="card row"><div class="avatar lg">${esc((u.name || "?")[0].toUpperCase())}</div>
      <div class="grow"><h3>${esc(u.name)}</h3><p class="subtle small">${esc(u.email)}</p></div></section>
    <div class="section-head"><h2>Care</h2></div>
    <div class="list">
      ${row("#/wound", "bandage", "My wound", "Details, care guidance and sensor guides")}
      ${row("#/scan", "camera", "Wound scans", "Photo checks and history")}
      ${row("#/devices", "watch", "Devices", bandage)}
    </div>
    <div class="section-head"><h2>Evidence</h2></div>
    <div class="list">
      ${row("#/model", "shield", "Model & validation", "Accuracy and external test on PhysioNet")}
      ${row("#/library", "book", "Research library", "28 PubMed studies behind the assistant")}
    </div>
    <div class="section-head"><h2>Settings</h2></div>
    <details class="card fold"><summary><span class="row"><span class="lr-ic neutral">${icon("server")}</span>Server</span>${icon("chev")}</summary>
      <div class="stack"><input class="input" id="server" value="${esc(prefs.server)}" inputmode="url" autocapitalize="off" aria-label="Server address" />
      <button class="btn block" id="test">Save and test connection</button><p class="small muted" id="res" aria-live="polite"></p></div></details>
    <section class="card"><h3>About WoundSense</h3>
      <p class="subtle small" style="margin-top:6px">WoundSense brings your smart bandage, watch and wound photos together so you can follow your wound's progress.
      It is a research prototype for information only, not a medical device or a diagnosis. Contact a clinician about any concern.</p></section>
    <button class="btn danger block" id="out">${icon("logout", "sm")} Sign out</button>`);
  $("#test").onclick = async () => {
    prefs.server = $("#server").value;
    $("#res").textContent = "Testing…";
    try {
      await api("/me");
      $("#res").textContent = "Connected.";
    } catch (e) {
      $("#res").textContent = e.message;
    }
  };
  $("#out").onclick = () => {
    stopDemo();
    disconnectBandage();
    prefs.token = null;
    prefs.user = null;
    infoCache = modelCache = null;
    chatLog = [];
    location.hash = "#/auth";
  };
}

// ---------- boot ----------

if (prefs.demo) startDemo();
if (!location.hash) location.hash = "#/home";
route();
