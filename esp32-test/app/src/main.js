import { api, prefs, ApiError, setAuthExpiredHandler, streamChat, DEFAULT_SERVER } from "./api.js";
import {
  live, onLive, connectBandage, disconnectBandage, measureOnWatch, finishWatchSession, startDemo, stopDemo,
} from "./ble.js";
import { lineChart, sparkline } from "./charts.js";

// ---------- helpers ----------

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function ago(ms) {
  if (!ms) return "no data yet";
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 20) return "just now";
  if (s < 3600) return `${Math.round(s / 60) || 1} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

async function openLink(url) {
  try {
    const { openUrl } = await import("@tauri-apps/plugin-opener");
    await openUrl(url);
  } catch {
    window.open(url, "_blank");
  }
}

const ICON = {
  home: '<path d="M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  wound: '<path d="M12 2s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/><path d="M9.5 14a2.5 2.5 0 0 0 2.5 2.5"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  device: '<rect x="7" y="2.5" width="10" height="19" rx="3"/><path d="M10 6h4"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  temp: '<path d="M10 14.5V5a2 2 0 1 1 4 0v9.5a4 4 0 1 1-4 0z"/>',
  drop: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
  moist: '<path d="M4 9c3-3 5 3 8 0s5 3 8 0M4 15c3-3 5 3 8 0s5 3 8 0"/>',
  heart: '<path d="M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.6 4.3 4.3 0 0 1 19.5 10C19.5 15.4 12 20 12 20z"/>',
  bp: '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
  send: '<path d="M4 12l16-8-6 18-3-7z"/>',
  camera: '<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.5"/>',
  trend: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  chev: '<path d="M9 5l7 7-7 7"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
};
const icon = (n, cls = "") =>
  `<svg class="ic ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[n]}</svg>`;

const METRICS = {
  temperature: { title: "Temperature", unit: "°C", color: "yellow", hex: "#B8860B", icon: "temp", fields: ["temperature"], dec: 1, hist: "temperature" },
  humidity: { title: "Humidity", unit: "%", color: "blue", hex: "#3F6FD1", icon: "drop", fields: ["humidity"], dec: 0, hist: "humidity" },
  moisture: { title: "Moisture", unit: "/ 10", color: "green", hex: "#5D7F25", icon: "moist", fields: ["moisture"], dec: 1, hist: "moisture" },
  heart_rate: { title: "Heart rate", unit: "bpm", color: "pink", hex: "#D6458F", icon: "heart", fields: ["bpm"], dec: 0, hist: "heart_rate" },
  blood_pressure: { title: "Blood pressure", unit: "mmHg", color: "lilac", hex: "#7A5BD0", icon: "bp", fields: ["systolic", "diastolic"], dec: 0, hist: "blood_pressure" },
};
const TYPE_NAME = {
  Pressure: "Pressure wound", Diabetic: "Diabetic wound", Venous: "Venous leg wound", Surgical: "Surgical wound",
  Bruises: "Bruise", Burn: "Burn", Abrasion: "Abrasion (graze)", Laceration: "Laceration", Normal: "Normal-looking skin", Cut: "Cut",
};
const TIPS = [
  { icon: "drop", title: "Keep it moist, not soaked", id: "junker_2013", cite: "Junker et al., 2013",
    body: "Wounds treated in a moist environment re-epithelialise better than dry ones. Aim for steady moisture readings rather than big swings." },
  { icon: "temp", title: "Watch the temperature trend", id: "fierheller_2010", cite: "Fierheller et al., 2010",
    body: "A wound that stays warmer than the skin around it is a classic early sign of infection. A steady settle toward normal is what you want to see." },
  { icon: "heart", title: "Rest and keep stress low", id: "kiecolt_glaser_1995", cite: "Kiecolt-Glaser et al., 1995",
    body: "In one controlled study, a small punch wound took about 9 days longer to heal in people under chronic stress (48.7 vs 39.3 days)." },
  { icon: "bp", title: "Look after your circulation", id: "wolny_2024", cite: "Wolny et al., 2024",
    body: "Healthy blood flow carries oxygen and nutrients to healing tissue. Vascular disease was the strongest systemic predictor of non-healing in a 149-patient cohort." },
  { icon: "chat", title: "Know when to call your clinician", id: null, cite: null,
    body: "Spreading redness, pus, fever, a bad smell or pain that keeps rising deserve a prompt check, whatever the app shows." },
];
const TILE_ORDER = ["temperature", "humidity", "moisture", "heart_rate", "blood_pressure"];
const demoQS = () => (live.demo ? "1" : "0");

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
    if (v === undefined || v === null) return { text: "--", at: 0 };
    out.push(Number(v).toFixed(metric.dec));
    at = Math.max(at, t || 0);
  }
  return { text: out.join("/"), at };
}

// ---------- shell / router ----------

const app = $("#app");
let cleanup = null;
let infoCache = null;

setAuthExpiredHandler(() => {
  prefs.token = null;
  location.hash = "#/auth";
});

function shell(html, { nav = true } = {}) {
  app.innerHTML = `<main id="view" class="view ${nav ? "with-nav" : ""}">${html}</main>${nav ? navHtml() : ""}`;
  return $("#view");
}

function navHtml() {
  const raw = location.hash.split("/")[1] || "home";
  const cur = { wound: "profile", devices: "profile" }[raw] || raw;
  const item = (id, ic, label) =>
    `<a href="#/${id}" class="nav-item ${cur === id ? "active" : ""}" aria-label="${label}">${icon(ic)}<span>${label}</span></a>`;
  return `<nav class="nav">${item("home", "home", "Home")}${item("trends", "trend", "Trends")}
    <a href="#/scan" class="nav-scan" aria-label="Scan wound">${icon("camera")}</a>
    ${item("chat", "chat", "Ask AI")}${item("profile", "user", "You")}</nav>`;
}

function errorBox(e) {
  return `<div class="notice error">${esc(e.message || e)}</div>`;
}

async function loadInfo() {
  if (!infoCache) infoCache = await api("/wound-info");
  return infoCache;
}

async function route() {
  if (cleanup) {
    cleanup();
    cleanup = null;
  }
  const [, name = "home", arg] = location.hash.split("/");
  if (!prefs.token) return renderAuth();
  const views = { home: renderHome, metric: renderMetric, wound: renderWound, trends: renderTrends, scan: renderScan, chat: renderChat, devices: renderDevices, profile: renderProfile, auth: renderHome };
  cleanup = (await (views[name] || renderHome)(arg)) || null;
}
window.addEventListener("hashchange", route);

// ---------- auth ----------

function renderAuth() {
  let mode = "login";
  const draw = (err = "") => {
    shell(
      `<div class="auth">
        <div class="brand"><div class="logo">${icon("wound")}</div><h1>WoundSense</h1>
          <p>Smart-bandage monitoring that keeps your wound care in view.</p></div>
        <div class="seg"><button data-m="login" class="${mode === "login" ? "on" : ""}">Sign in</button>
          <button data-m="signup" class="${mode === "signup" ? "on" : ""}">Create account</button></div>
        <form id="f" class="stack">
          ${mode === "signup" ? '<input name="name" placeholder="Your name" autocomplete="name" required />' : ""}
          <input name="email" type="email" placeholder="Email" autocomplete="email" required />
          <input name="password" type="password" placeholder="Password (6+ characters)" autocomplete="${mode === "login" ? "current-password" : "new-password"}" required />
          ${err ? `<div class="notice error">${esc(err)}</div>` : ""}
          <button class="btn primary" id="go">${mode === "login" ? "Sign in" : "Create account"}</button>
        </form>
        <details class="server"><summary>Server address</summary>
          <input id="server" value="${esc(prefs.server)}" placeholder="${DEFAULT_SERVER}" />
          <p class="muted">The computer running <code>mobile_server.py</code>, on the same Wi-Fi as this phone.</p>
        </details>
      </div>`,
      { nav: false },
    );
    document.querySelectorAll(".seg button").forEach((b) => (b.onclick = () => ((mode = b.dataset.m), draw())));
    $("#f").onsubmit = async (e) => {
      e.preventDefault();
      const fd = Object.fromEntries(new FormData(e.target));
      prefs.server = $("#server").value || DEFAULT_SERVER;
      $("#go").disabled = true;
      $("#go").textContent = "Please wait…";
      try {
        const r = await api(mode === "login" ? "/auth/login" : "/auth/signup", { method: "POST", body: fd });
        prefs.token = r.token;
        prefs.user = r.user;
        infoCache = null;
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

const HERO = {
  healthy: { cls: "ok", emoji: "On track" },
  wound_healing: { cls: "warn", emoji: "Healing" },
  infected: { cls: "alert", emoji: "Needs attention" },
};

async function renderHome() {
  const name = (prefs.user?.name || "").split(" ")[0];
  const hr = new Date().getHours();
  const greet = hr < 12 ? "Good morning" : hr < 18 ? "Good afternoon" : "Good evening";
  const view = shell(`
    <header class="top">
      <div><p class="muted">${greet}</p><h1>${esc(name) || "Welcome"}</h1></div>
      <a class="pill" id="conn" href="#/devices"></a>
    </header>
    <section id="hero" class="hero skeleton"></section>
    <section id="overall"></section>
    <div class="quick">
      <a href="#/chat" class="qa"><span class="qa-ic blue">${icon("chat")}</span>Ask AI</a>
      <a href="#/devices" class="qa"><span class="qa-ic pink">${icon("device")}</span>Devices</a>
      <a href="#/wound" class="qa"><span class="qa-ic green">${icon("wound")}</span>My wound</a>
      <a href="#/trends" class="qa"><span class="qa-ic yellow">${icon("trend")}</span>Trends</a>
    </div>
    <a class="scan-tile" href="#/scan" id="scan-tile"></a>
    <h2 class="sec">Live readings</h2>
    <section id="tiles" class="tiles"></section>
    <h2 class="sec">Today's tip</h2>
    <section id="tip"></section>
    <p class="fine">For information only, not a diagnosis. Contact a clinician about any concern.</p>`);
  (() => {
    const t = TIPS[Math.floor(Date.now() / 864e5) % (TIPS.length - 1)];
    $("#tip").innerHTML = `<div class="tip-card"><span class="tip-ic">${icon(t.icon)}</span>
      <div><b>${esc(t.title)}</b><p>${esc(t.body)}</p>${t.cite ? `<span class="cite">${esc(t.cite)}</span>` : ""}</div></div>`;
  })();

  let status = null;
  const hist = {};
  const connLabel = () => {
    const c = $("#conn");
    if (!c) return;
    const on = live.esp === "connected";
    c.className = `pill ${live.demo ? "demo" : on ? "on" : ""}`;
    c.innerHTML = `<i></i>${live.demo ? "Demo data" : on ? "Bandage connected" : "Bandage offline"}`;
  };

  function drawHero() {
    const el = $("#hero");
    if (!el) return;
    el.classList.remove("skeleton");
    const w = status?.wound;
    if (!w) {
      el.className = "hero empty";
      el.innerHTML = `<p class="muted">Wound status</p><h2>No assessment yet</h2>
        <p>Connect your bandage (or turn on demo data) and your first wound assessment appears here.</p>
        <a class="btn primary small" href="#/devices">Connect a device</a>`;
      return;
    }
    const h = HERO[w.condition] || HERO.wound_healing;
    const trend = { improving: "Improving", stable: "Stable", worsening: "Worsening", new: "First assessment" }[w.trend];
    el.className = `hero ${h.cls}`;
    el.innerHTML = `<a href="#/metric/healing_days" class="hero-link">
        <div class="hero-top"><span class="chip">${h.emoji}</span><span class="chip ghost">${trend}</span></div>
        <p class="muted">Estimated time to heal</p>
        <div class="hero-num"><b>${Math.round(w.healing_days)}</b><span>days</span></div>
        <p class="muted small">Updated ${ago(Date.parse(w.at))} · tap for the trend</p></a>`;
  }

  function drawExtras() {
    const o = status?.overall;
    const ov = $("#overall");
    if (ov) {
      const names = { ok: "Looking steady", watch: "Keep an eye on it", alert: "Needs attention" };
      ov.innerHTML = o
        ? `<div class="banner ${o.level}"><b>${names[o.level]}</b>
             <ul>${o.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
             <p class="fine left">Based on your latest readings and photo.</p></div>`
        : "";
    }
    const t = $("#scan-tile");
    if (t) {
      const s = status?.scan;
      t.innerHTML = `<span class="scan-ic">${icon("camera")}</span>
        <div><b>Scan your wound</b><p class="muted small">${
          s
            ? `Last scan ${ago(Date.parse(s.created_at))}: ${esc(TYPE_NAME[s.type.label] || s.type.label)}${
                s.severity ? ", " + esc(s.severity.label.toLowerCase()) + " looking" : ""
              }`
            : "Take a photo for a visual check"
        }</p></div>`;
    }
  }

  function drawTiles() {
    const el = $("#tiles");
    if (!el) return;
    el.innerHTML = TILE_ORDER.map((id) => {
      const m = METRICS[id];
      const v = currentValue(m, status);
      const series = (hist[id] || []).map((p) => p[m.fields[0]]).filter((x) => x != null);
      return `<a class="tile ${m.color} ${id === "blood_pressure" ? "wide" : ""}" href="#/metric/${id}">
        <div class="tile-top">${icon(m.icon)}<span>${m.title}</span></div>
        <div class="tile-val"><b data-val="${id}">${v.text}</b><small>${m.unit}</small></div>
        <div class="tile-foot"><span class="age" data-age="${id}">${ago(v.at)}</span>${sparkline(series, m.hex, 76, 30)}</div></a>`;
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
          const h = await api(`/history?metric=${METRICS[id].hist}&hours=24&demo=${d}`);
          hist[id] = h.points;
        }),
      );
      drawHero();
      drawExtras();
      drawTiles();
    } catch (e) {
      $("#hero").className = "hero empty";
      $("#hero").innerHTML = `<h2>Can't load your data</h2>${errorBox(e)}<a class="btn small" href="#/profile">Check server address</a>`;
      if (e instanceof ApiError && e.status === 0) drawTiles();
    }
  }

  connLabel();
  drawTiles();
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

const RANGES = [["6h", 6], ["24h", 24], ["7d", 168], ["30d", 720]];

async function renderMetric(id) {
  const isHeal = id === "healing_days";
  const m = isHeal
    ? { title: "Days to heal", unit: "days", hex: "#2F8F5B", fields: ["healing_days"], dec: 1, hist: "healing_days" }
    : METRICS[id];
  if (!m) {
    location.hash = "#/home";
    return;
  }
  let hours = 24;
  const view = shell(
    `<header class="top back"><a href="#/home" class="icon-btn" aria-label="Back">${icon("back")}</a><h1>${m.title}</h1><span></span></header>
     <section class="card detail">
       <div class="big"><b id="big">--</b><small>${m.unit}</small></div>
       <p class="muted" id="when">Touch and drag across the chart</p>
       ${id === "blood_pressure" ? '<p class="legend"><i style="background:#7A5BD0"></i>Systolic <i style="background:#8a8a8a"></i>Diastolic</p>' : ""}
       <div id="chart" class="chart-wrap"></div>
       <div class="seg small">${RANGES.map(([l, h]) => `<button data-h="${h}" class="${h === hours ? "on" : ""}">${l}</button>`).join("")}</div>
     </section>
     <section class="stats" id="stats"></section>
     <section id="guide"></section>`,
    { nav: false },
  );
  const series = m.fields.map((f, i) => ({ key: f, color: i === 0 ? m.hex : "#8a8a8a", label: f }));

  async function draw() {
    try {
      const h = await api(`/history?metric=${m.hist}&hours=${hours}&demo=${demoQS()}`);
      const last = h.points[h.points.length - 1];
      const fmt = (p) => m.fields.map((f) => (p?.[f] == null ? "--" : Number(p[f]).toFixed(m.dec))).join("/");
      $("#big").textContent = last ? fmt(last) : "--";
      lineChart($("#chart"), {
        points: h.points,
        series,
        decimals: m.dec,
        onScrub: (p) => {
          $("#big").textContent = fmt(p || last);
          $("#when").textContent = p
            ? new Date(p.t).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
            : "Touch and drag across the chart";
        },
      });
      const s = h.stats;
      $("#stats").innerHTML = s
        ? ["min", "avg", "max"].map((k) => `<div class="stat"><span>${k === "avg" ? "Average" : k === "min" ? "Lowest" : "Highest"}</span><b>${s[k].toFixed(m.dec)}</b></div>`).join("") +
          `<div class="stat"><span>Readings</span><b>${s.count}</b></div>`
        : "";
    } catch (e) {
      $("#chart").innerHTML = errorBox(e);
    }
  }
  view.querySelectorAll(".seg button").forEach((b) => {
    b.onclick = () => {
      hours = Number(b.dataset.h);
      view.querySelectorAll(".seg button").forEach((x) => x.classList.toggle("on", x === b));
      draw();
    };
  });
  draw();

  try {
    const info = await loadInfo();
    const g = isHeal ? null : info.guides[id];
    const papers = g ? g.papers.map((pid) => info.papers.find((p) => p.id === pid)).filter(Boolean) : [];
    $("#guide").innerHTML = g
      ? `<div class="card"><h3>What this means</h3><p>${esc(g.what)}</p><p>${esc(g.evidence)}</p>
           <div class="tip-note"><b>Good to know</b> ${esc(g.tip)}</div></div>
         <h2 class="sec">Research behind this</h2>${papers.map(paperCard).join("")}`
      : `<div class="card"><h3>How this is estimated</h3>
           <p>Your estimated time to heal follows the trend in your bandage's temperature, humidity and moisture readings.
           As those settle toward normal, the estimate comes down.</p></div>`;
    bindLinks(view);
  } catch {
    /* evidence is optional; the chart is the point of this screen */
  }
}

function paperCard(p) {
  return `<article class="paper"><h4>${esc(p.title)}</h4>
    <p class="muted small">${esc(p.authors)} · ${esc(p.journal)} · ${p.year}</p>
    <p class="tag">${esc(p.evidence)}</p><p>${esc(p.key_findings)}</p>
    <a href="#" data-url="${esc(p.url)}" class="link">${icon("link", "sm")} PubMed${p.doi ? " · DOI " + esc(p.doi) : ""}</a></article>`;
}

function bindLinks(root) {
  root.querySelectorAll("a[data-url]").forEach((a) => {
    a.onclick = (e) => {
      e.preventDefault();
      openLink(a.dataset.url);
    };
  });
}

// ---------- my wound ----------

async function renderWound() {
  const view = shell(`
    <header class="top"><div><p class="muted">Your care</p><h1>My wound</h1></div>
      <a href="#/scan" class="icon-btn" aria-label="Scan wound">${icon("camera")}</a></header>
    <div id="summary"></div>
    <div class="seg tabs"><button data-t="overview" class="on">Overview</button><button data-t="details">Details</button><button data-t="learn">Learn</button></div>
    <div id="tab"><p class="muted center">Loading…</p></div>`);
  let info;
  let scans = [];
  try {
    info = await loadInfo();
    scans = (await api("/scans")).scans;
  } catch (e) {
    $("#tab").innerHTML = errorBox(e);
    return;
  }
  const c = info.context || {};
  const last = scans[0];

  // summary card
  const dayN = c.created_at ? Math.max(0, Math.floor((Date.now() - Date.parse(c.created_at + (c.created_at.endsWith("Z") ? "" : "Z"))) / 864e5)) + (c.days_since_onset || 0) : null;
  $("#summary").innerHTML = `<section class="wound-hero">
      ${last ? `<img src="${last.thumb}" alt="Latest wound photo" />` : `<div class="wh-ph">${icon("wound")}</div>`}
      <div><p class="muted small">${last ? "Latest scan" : "No scan yet"}</p>
        <h2>${esc(last ? TYPE_NAME[last.type.label] || last.type.label : c.cause || "Add your details")}</h2>
        <p class="chips-row">${dayN != null ? `<span class="chip">Day ${dayN + 1}</span>` : ""}${
          c.pain_level != null ? `<span class="chip ghost">Pain ${c.pain_level}/10</span>` : ""
        }${c.itching_level != null ? `<span class="chip ghost">Itch ${c.itching_level}/10</span>` : ""}</p></div></section>`;

  const tabs = {
    overview: () => `
      <h2 class="sec first">Care tips</h2>
      ${TIPS.map((t) => {
        const p = t.id ? info.papers.find((x) => x.id === t.id) : null;
        return `<div class="tip-card"><span class="tip-ic">${icon(t.icon)}</span><div><b>${esc(t.title)}</b><p>${esc(t.body)}</p>
          ${p ? `<a href="#" data-url="${esc(p.url)}" class="cite link">${esc(t.cite)}</a>` : ""}</div></div>`;
      }).join("")}
      <a class="scan-tile" href="#/scan"><span class="scan-ic">${icon("camera")}</span><div><b>Scan your wound</b>
        <p class="muted small">${scans.length} scan${scans.length === 1 ? "" : "s"} so far</p></div></a>`,
    details: () => {
      const causes = ["Burn", "Cut or laceration", "Surgical wound", "Pressure sore", "Diabetic foot ulcer", "Venous leg ulcer", "Other"];
      const sev = ["Mild", "Moderate", "Severe"];
      const opt = (list, cur) => list.map((x) => `<option ${x === cur ? "selected" : ""}>${x}</option>`).join("");
      return `<form id="ctx" class="card stack">
        <div class="grid2">
          <label>How it happened<select name="cause"><option value="">Select…</option>${opt(causes, c.cause)}</select></label>
          <label>Severity<select name="severity"><option value="">Select…</option>${opt(sev, c.severity)}</select></label>
        </div>
        <label><span>Pain <b id="pv">${c.pain_level ?? 0}</b> / 10</span><input type="range" name="pain_level" min="0" max="10" value="${c.pain_level ?? 0}" /></label>
        <label><span>Itching <b id="iv">${c.itching_level ?? 0}</b> / 10</span><input type="range" name="itching_level" min="0" max="10" value="${c.itching_level ?? 0}" /></label>
        <label>Days since it happened<input type="number" name="days_since_onset" min="0" value="${c.days_since_onset ?? 0}" /></label>
        <label>Notes<textarea name="notes" rows="3" placeholder="Anything else worth noting">${esc(c.notes || "")}</textarea></label>
        <button class="btn primary">Save details</button><p class="muted small center" id="saved"></p></form>`;
    },
    learn: () => `
      <h2 class="sec first">Your sensors</h2>
      ${["temperature", "humidity", "moisture", "heart_rate", "blood_pressure"].map((k) => info.guides[k]).map((g) => `<details class="card fold"><summary>${esc(g.title)}</summary>
        <p>${esc(g.what)}</p><p>${esc(g.evidence)}</p><div class="tip-note"><b>Good to know</b> ${esc(g.tip)}</div></details>`).join("")}
      <details class="card fold"><summary>Research library (${info.papers.length} studies)</summary>
        <div class="lib">${info.papers.map(paperCard).join("")}</div></details>`,
  };

  function show(name) {
    view.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.t === name));
    $("#tab").innerHTML = `<div class="rise">${tabs[name]()}</div>`;
    bindLinks(view);
    const ctx = $("#ctx");
    if (ctx) {
      ctx.querySelector('[name="pain_level"]').oninput = (e) => ($("#pv").textContent = e.target.value);
      ctx.querySelector('[name="itching_level"]').oninput = (e) => ($("#iv").textContent = e.target.value);
      ctx.onsubmit = async (e) => {
        e.preventDefault();
        try {
          await api("/wound-context", { method: "POST", body: Object.fromEntries(new FormData(ctx)) });
          infoCache = null;
          $("#saved").textContent = "Saved. Your assistant will use this.";
        } catch (er) {
          $("#saved").textContent = er.message;
        }
      };
    }
  }
  view.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => show(b.dataset.t)));
  show("overview");
}

// ---------- trends ----------

async function renderTrends() {
  let hours = 24;
  const view = shell(`
    <header class="top"><div><p class="muted">How you're progressing</p><h1>Trends</h1></div></header>
    <div class="seg">${[["24h", 24], ["7d", 168], ["30d", 720]].map(([l, h]) => `<button data-h="${h}" class="${h === hours ? "on" : ""}">${l}</button>`).join("")}</div>
    <section class="card trend-hero"><p class="muted small">Estimated days to heal</p>
      <div class="big"><b id="th-val">--</b><small>days</small></div><div id="th-chart" class="chart-wrap"></div></section>
    <div id="cards" class="trend-cards"></div>`);

  async function draw() {
    const d = demoQS();
    try {
      const [heal, ...rest] = await Promise.all([
        api(`/history?metric=healing_days&hours=${hours}&demo=${d}`),
        ...TILE_ORDER.map((id) => api(`/history?metric=${METRICS[id].hist}&hours=${hours}&demo=${d}`)),
      ]);
      const last = heal.points[heal.points.length - 1];
      $("#th-val").textContent = last ? Number(last.healing_days).toFixed(0) : "--";
      lineChart($("#th-chart"), { points: heal.points, series: [{ key: "healing_days", color: "#2F8F5B" }], decimals: 0,
        onScrub: (p) => ($("#th-val").textContent = (p || last) ? Number((p || last).healing_days).toFixed(0) : "--") });
      $("#cards").innerHTML = TILE_ORDER.map((id, i) => {
        const m = METRICS[id];
        const h = rest[i];
        const vals = h.points.map((p) => p[m.fields[0]]).filter((x) => x != null);
        const s = h.stats;
        const change = vals.length > 1 ? vals[vals.length - 1] - vals[0] : null;
        const arrow = change == null ? "" : change > 0 ? "↑" : change < 0 ? "↓" : "→";
        return `<a class="tcard ${m.color}" href="#/metric/${id}">
          <div class="tile-top">${icon(m.icon)}<span>${m.title}</span></div>
          <div class="tc-main"><div><b>${s ? s.avg.toFixed(m.dec) : "--"}</b><small>${m.unit} avg</small></div>${sparkline(vals, m.hex, 90, 34)}</div>
          <p class="tc-foot">${s ? `${s.min.toFixed(m.dec)} – ${s.max.toFixed(m.dec)} ${change != null ? `· ${arrow} ${Math.abs(change).toFixed(m.dec)}` : ""}` : "No data in this range"}</p></a>`;
      }).join("");
    } catch (e) {
      $("#cards").innerHTML = errorBox(e);
    }
  }
  view.querySelectorAll(".seg button").forEach((b) => {
    b.onclick = () => {
      hours = Number(b.dataset.h);
      view.querySelectorAll(".seg button").forEach((x) => x.classList.toggle("on", x === b));
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
  const bars = r.type.top
    .slice(0, 3)
    .map(
      (t) =>
        `<div class="bar"><span>${esc(TYPE_NAME[t.label] || t.label)}</span><em>${Math.round(t.p * 100)}%</em><i style="--w:${Math.round(t.p * 100)}%"></i></div>`,
    )
    .join("");
  return `
    ${r.quality.map((w) => `<div class="notice">${esc(w)}</div>`).join("")}
    ${r.notes.map((w) => `<div class="notice error">${esc(w)}</div>`).join("")}
    <div class="res-head"><p class="muted small">Looks most like</p>
      <h3 class="res-title">${esc(TYPE_NAME[r.type.label] || r.type.label)}</h3></div>
    <div class="bars">${bars}</div>
    ${r.severity ? `<p class="chips-row"><span class="chip">Visual severity: ${esc(r.severity.label)}</span></p>` : ""}
    <div class="tip-note"><b>Tracking tip</b> Scan at the same time each day, in the same light, to see how your wound changes.
      If you notice spreading redness, pus, fever or pain that keeps rising, contact your clinician.</div>`;
}

async function renderScan() {
  shell(
    `
    <header class="top back"><a href="#/home" class="icon-btn" aria-label="Back">${icon("back")}</a><h1>Scan wound</h1><span></span></header>
    <section class="card">
      <div id="preview" class="preview"><div class="ph">${icon("camera")}<p>Take or choose a photo of the wound</p></div></div>
      <p class="muted small tip">Good light, wound centred and in focus, about 15-20 cm away, nothing else in frame (no faces).</p>
      <div class="row2">
        <label class="btn primary file">Take photo<input id="cam" type="file" accept="image/*" capture="environment" hidden /></label>
        <label class="btn file">Choose photo<input id="gal" type="file" accept="image/*" hidden /></label>
      </div>
      <div id="result"></div>
    </section>
    <h2 class="sec">Previous scans</h2><div id="history" class="muted">Loading…</div>`,
    { nav: false },
  );

  async function loadHistory() {
    try {
      const h = await api("/scans");
      $("#history").className = "";
      $("#history").innerHTML = h.scans.length
        ? h.scans
            .map(
              (s) => `<div class="scan-row"><img src="${s.thumb}" alt="" /><div><b>${esc(TYPE_NAME[s.type.label] || s.type.label)}</b>
            <p class="muted small">${new Date(s.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}${
              s.severity ? " · " + esc(s.severity.label) : ""
            }${s.reliable ? "" : " · retake suggested"}</p></div></div>`,
            )
            .join("")
        : '<p class="muted">No scans yet.</p>';
    } catch (e) {
      $("#history").innerHTML = errorBox(e);
    }
  }

  async function handle(file) {
    if (!file) return;
    $("#result").innerHTML = '<p class="muted center">Analysing photo…</p>';
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
  $("#cam").onchange = (e) => handle(e.target.files[0]);
  $("#gal").onchange = (e) => handle(e.target.files[0]);
  loadHistory();
}

// ---------- chat ----------

function renderMarkdown(text) {
  const clean = text.replace(/[\u200b\u200c\u200d\u2060]/g, "").replace(/\u3010/g, "[").replace(/\u3011/g, "]");
  const inline = (raw) => {
    let h = esc(raw);
    h = h.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|\s)\*(?!\s)(.+?)\*(?=\s|$|[.,;])/g, "$1<i>$2</i>");
    return h.replace(/\[([A-Z][\w'’ -]+ et al\.,? \d{4}[a-z]?)\]/g, '<span class="cite">$1</span>');
  };
  const cells = (ln) => ln.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  const lines = clean.split("\n");
  let out = "";
  let list = false;
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    if (list && !/^\s*[-*•]\s+/.test(ln)) (out += "</ul>"), (list = false);
    // table: a row of |cells| followed by a |---|---| separator
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
  const view = shell(`<header class="top"><div><p class="muted">Grounded in your readings and cited studies</p><h1>Ask AI</h1></div>
      <button class="icon-btn" id="newchat" aria-label="New chat" title="New chat">${icon("plus")}</button></header>
    <div id="thread" class="thread"></div>
    <div class="chips" id="chips"></div>
    <form id="cf" class="composer"><input id="msg" placeholder="Ask about your wound…" autocomplete="off" />
      <button class="send" aria-label="Send">${icon("send")}</button></form>`);
  const thread = $("#thread");
  const add = (role, html = "") => {
    const d = document.createElement("div");
    d.className = `bubble ${role}`;
    d.innerHTML = html;
    thread.appendChild(d);
    thread.scrollTop = thread.scrollHeight;
    view.scrollTop = view.scrollHeight;
    return d;
  };
  const greet = () =>
    add("bot", `<p>Hi! I can explain your readings and what research says about wound healing. I'm not a doctor, so I'll point you to a clinician for anything concerning.</p>`);
  greet();
  chatLog.forEach((t) => add(t.role === "user" ? "me" : "bot", t.role === "user" ? `<p>${esc(t.content)}</p>` : renderMarkdown(t.content)));

  const sugg = ["Is my wound infected?", "What does my temperature mean?", "Is my dressing too wet?", "How does stress affect healing?"];
  const chips = $("#chips");
  chips.innerHTML = sugg.map((s) => `<button type="button" class="chip btn-chip">${esc(s)}</button>`).join("");
  if (chatLog.length) chips.style.display = "none";
  let busy = false;
  async function send(text) {
    text = text.trim();
    if (!text || busy) return;
    busy = true;
    $("#msg").value = "";
    chips.style.display = "none";
    add("me", `<p>${esc(text)}</p>`);
    const bot = add("bot", '<p class="typing"><i></i><i></i><i></i></p>');
    const history = chatLog.slice(-8);
    try {
      const full = await streamChat(text, live.demo, history, (t) => {
        bot.innerHTML = renderMarkdown(t.split("\n\n__CITATIONS__:")[0]);
        view.scrollTop = view.scrollHeight;
      });
      const [body, cites] = full.split("\n\n__CITATIONS__:");
      bot.innerHTML = renderMarkdown(body);
      chatLog.push({ role: "user", content: text }, { role: "assistant", content: body });
      if (cites) {
        const list = JSON.parse(cites);
        bot.insertAdjacentHTML("beforeend",
          `<div class="sources"><span>Sources</span>${list.map((c) => `<a href="#" data-url="${esc(c.url)}" title="${esc(c.title)}">${esc(c.tag.replace(/[[\]]/g, ""))}</a>`).join("")}</div>`);
        bindLinks(bot);
      }
    } catch (e) {
      bot.innerHTML = errorBox(e);
    }
    busy = false;
    view.scrollTop = view.scrollHeight;
  }
  $("#cf").onsubmit = (e) => (e.preventDefault(), send($("#msg").value));
  chips.onclick = (e) => e.target.classList.contains("btn-chip") && send(e.target.textContent);
  $("#newchat").onclick = () => {
    if (busy) return;
    chatLog = [];
    thread.innerHTML = "";
    greet();
    chips.style.display = "";
  };
}

// ---------- devices ----------

const STATE_TEXT = { off: "Not connected", scanning: "Searching…", connecting: "Connecting…", connected: "Connected", waiting: "Waiting for a measurement", done: "Measurement received", error: "Couldn't connect" };

function renderDevices() {
  const view = shell(`<header class="top"><div><p class="muted">Bluetooth</p><h1>Devices</h1></div></header><div id="dev"></div>`);
  const draw = () => {
    const busyEsp = ["scanning", "connecting"].includes(live.esp);
    const busyWatch = ["scanning", "connecting", "waiting"].includes(live.watch);
    const v = live.values;
    const num = (x, d = 0) => (x == null ? "--" : Number(x).toFixed(d));
    $("#dev").innerHTML = `
      ${live.message ? `<div class="notice error">${esc(live.message)}</div>` : ""}
      <section class="card dev">
        <div class="dev-head"><span class="dev-ic yellow">${icon("wound")}</span>
          <div><h3>Smart bandage</h3><p class="muted small">ESP32 · ${STATE_TEXT[live.esp]}</p></div></div>
        ${live.esp === "connected" ? `<p class="live">${num(v.temperature, 1)} °C · ${num(v.humidity)} % · moisture ${num(v.moisture, 1)}</p>` : ""}
        <button class="btn ${live.esp === "connected" ? "" : "primary"}" id="esp" ${busyEsp || busyWatch ? "disabled" : ""}>
          ${live.esp === "connected" ? "Disconnect" : busyEsp ? STATE_TEXT[live.esp] : "Connect bandage"}</button>
      </section>
      <section class="card dev">
        <div class="dev-head"><span class="dev-ic pink">${icon("heart")}</span>
          <div><h3>Watch</h3><p class="muted small">MS1020 · ${STATE_TEXT[live.watch]}</p></div></div>
        ${live.watch === "waiting" || live.watch === "done" ? `<p class="live">${num(v.bpm)} bpm · ${num(v.systolic)}/${num(v.diastolic)} mmHg</p>` : ""}
        ${live.watch === "waiting" ? `<p class="muted small">Now start a heart-rate or blood-pressure measurement on the watch. Readings appear here.</p>
          <button class="btn primary" id="watch-done">Done</button>`
          : `<button class="btn" id="watch" ${busyWatch || busyEsp ? "disabled" : ""}>${busyWatch ? STATE_TEXT[live.watch] : "Measure on watch"}</button>`}
      </section>
      <section class="card dev">
        <div class="row"><div><h3>Demo data</h3><p class="muted small">Simulated readings, stored separately and never mixed with real ones.</p></div>
          <label class="switch"><input type="checkbox" id="demo" ${live.demo ? "checked" : ""}/><i></i></label></div>
      </section>
      <p class="fine">The phone keeps one Bluetooth connection at a time: the bandage streams continuously, and the watch is a short “measure now” session after which the bandage reconnects.</p>`;
    const esp = $("#esp");
    if (esp) esp.onclick = () => (live.esp === "connected" ? disconnectBandage() : connectBandage());
    const w = $("#watch");
    if (w) w.onclick = () => measureOnWatch();
    const wd = $("#watch-done");
    if (wd) wd.onclick = () => finishWatchSession();
    $("#demo").onchange = (e) => (e.target.checked ? startDemo() : stopDemo());
  };
  draw();
  const off = onLive(draw);
  return off;
}

// ---------- profile ----------

function renderProfile() {
  const u = prefs.user || {};
  const row = (href, ic, title, sub) =>
    `<a class="row-link" href="${href}"><span class="rl-ic">${icon(ic)}</span><div><b>${title}</b><p class="muted small">${sub}</p></div>${icon("chev", "chev")}</a>`;
  const bandage = live.demo ? "Demo data on" : live.esp === "connected" ? "Bandage connected" : "Bandage not connected";
  shell(`
    <header class="top"><div><p class="muted">Account</p><h1>You</h1></div></header>
    <section class="card profile-card"><div class="avatar">${esc((u.name || "?")[0].toUpperCase())}</div>
      <div><h3>${esc(u.name)}</h3><p class="muted small">${esc(u.email)}</p></div></section>
    <div class="list">
      ${row("#/wound", "wound", "My wound", "Details, care tips and learning")}
      ${row("#/devices", "device", "Devices", bandage + " · MS1020 watch")}
      ${row("#/scan", "camera", "Wound scans", "Photo checks and history")}
    </div>
    <details class="card fold"><summary>Server address</summary>
      <div class="stack"><input id="server" value="${esc(prefs.server)}" />
      <button class="btn" id="test">Save and test connection</button><p class="muted small" id="res"></p></div></details>
    <section class="card"><h3>About WoundSense</h3>
      <p class="muted small">WoundSense brings your smart bandage, watch and wound photos together so you can follow your wound's progress.
      It is for information only and is not a diagnosis. Contact a clinician about any concern.</p></section>
    <button class="btn danger" id="out">Sign out</button>`);
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
    infoCache = null;
    location.hash = "#/auth";
  };
}

// ---------- boot ----------

if (prefs.demo) startDemo();
if (!location.hash) location.hash = "#/home";
route();
