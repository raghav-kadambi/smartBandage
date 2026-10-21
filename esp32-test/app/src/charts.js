// Dependency-free SVG charts: a scrubbable line chart and tiny sparklines.

const NS = "http://www.w3.org/2000/svg";

function niceBounds(lo, hi) {
  if (lo === hi) {
    const pad = Math.max(1, Math.abs(lo) * 0.05);
    return [lo - pad, hi + pad];
  }
  const pad = (hi - lo) * 0.18;
  return [lo - pad, hi + pad];
}

// Smooth path through points (Catmull-Rom converted to cubic beziers, y clamped to the data
// range so the curve never overshoots into values that were not measured).
function smoothPath(pts, yMin, yMax) {
  if (pts.length < 2) return "";
  const clampY = (y) => Math.min(yMax, Math.max(yMin, y));
  let d = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] || p2;
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = clampY(p1[1] + (p2[1] - p0[1]) / 6);
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = clampY(p2[1] - (p3[1] - p1[1]) / 6);
    d += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}

export function sparkline(values, color, w = 96, h = 32) {
  if (!values || values.length < 2) return `<svg width="${w}" height="${h}" aria-hidden="true"></svg>`;
  const [lo, hi] = niceBounds(Math.min(...values), Math.max(...values));
  const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - 3 - ((v - lo) / (hi - lo)) * (h - 6)]);
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">
    <path d="${smoothPath(pts, 0, h)}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round"/></svg>`;
}

/**
 * Renders into `el`. series: [{key, color, label}]. points: [{t, ...fields}].
 * onScrub(point|null) is called as the user drags across the chart.
 */
export function lineChart(el, { points, series, decimals = 1, onScrub }) {
  el.innerHTML = "";
  const data = points
    .map((p) => ({ x: Date.parse(p.t), p }))
    .filter((d) => Number.isFinite(d.x))
    .sort((a, b) => a.x - b.x);

  if (data.length === 0) {
    el.innerHTML = `<div class="chart-empty">No readings in this time range yet.<br/>
      They appear here as your bandage or watch reports in.</div>`;
    return;
  }

  const W = Math.max(280, el.clientWidth || 340);
  const H = 220;
  const m = { l: 36, r: 12, t: 12, b: 24 };
  const all = data.flatMap((d) => series.map((s) => d.p[s.key])).filter((v) => v != null);
  // every metric here is non-negative, so never pad the axis below zero
  const [padLo, hi] = niceBounds(Math.min(...all), Math.max(...all));
  const lo = Math.max(0, padLo);
  const x0 = data[0].x;
  const x1 = data[data.length - 1].x;
  const sx = (x) => (x1 === x0 ? m.l + (W - m.l - m.r) / 2 : m.l + ((x - x0) / (x1 - x0)) * (W - m.l - m.r));
  const sy = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "chart");
  let html = "";

  for (let i = 0; i <= 3; i++) {
    const v = lo + ((hi - lo) * i) / 3;
    const y = sy(v);
    html += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}" class="grid"/>
             <text x="${m.l - 6}" y="${y + 4}" text-anchor="end" class="axis">${v.toFixed(decimals > 0 ? 0 : 0)}</text>`;
  }
  const span = x1 - x0;
  const fmt = (ms) => {
    const d = new Date(ms);
    if (span < 12 * 3600 * 1000) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (span < 3 * 86400 * 1000) return d.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  };
  html += `<text x="${m.l}" y="${H - 6}" class="axis">${fmt(x0)}</text>
           <text x="${W - m.r}" y="${H - 6}" text-anchor="end" class="axis">${fmt(x1)}</text>`;

  series.forEach((s, si) => {
    const pts = data.filter((d) => d.p[s.key] != null).map((d) => [sx(d.x), sy(d.p[s.key])]);
    if (pts.length >= 2) {
      const line = smoothPath(pts, m.t, H - m.b);
      const base = H - m.b;
      if (si === 0) {
        html += `<defs><linearGradient id="g${si}" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stop-color="${s.color}" stop-opacity=".35"/><stop offset="1" stop-color="${s.color}" stop-opacity="0"/>
          </linearGradient></defs>
          <path d="${line} L${pts[pts.length - 1][0]},${base} L${pts[0][0]},${base} Z" fill="url(#g${si})"/>`;
      }
      html += `<path d="${line}" fill="none" stroke="${s.color}" stroke-width="3" stroke-linecap="round"/>`;
    } else if (pts.length === 1) {
      html += `<circle cx="${pts[0][0]}" cy="${pts[0][1]}" r="5" fill="${s.color}"/>`;
    }
  });
  html += `<g id="scrub" style="display:none"><line y1="${m.t}" y2="${H - m.b}" class="scrub-line"/></g>`;
  svg.innerHTML = html;
  el.appendChild(svg);

  const scrub = svg.querySelector("#scrub");
  const line = scrub.querySelector("line");
  const dots = series.map((s) => {
    const c = document.createElementNS(NS, "circle");
    c.setAttribute("r", "5.5");
    c.setAttribute("fill", s.color);
    c.setAttribute("stroke", "#fff");
    c.setAttribute("stroke-width", "2");
    scrub.appendChild(c);
    return c;
  });

  function at(clientX) {
    const rect = svg.getBoundingClientRect();
    const x = ((clientX - rect.left) / rect.width) * W;
    let best = data[0];
    for (const d of data) if (Math.abs(sx(d.x) - x) < Math.abs(sx(best.x) - x)) best = d;
    scrub.style.display = "";
    line.setAttribute("x1", sx(best.x));
    line.setAttribute("x2", sx(best.x));
    series.forEach((s, i) => {
      const v = best.p[s.key];
      dots[i].style.display = v == null ? "none" : "";
      if (v != null) {
        dots[i].setAttribute("cx", sx(best.x));
        dots[i].setAttribute("cy", sy(v));
      }
    });
    onScrub && onScrub(best.p);
  }
  const end = () => {
    scrub.style.display = "none";
    onScrub && onScrub(null);
  };
  svg.addEventListener("pointerdown", (e) => {
    svg.setPointerCapture(e.pointerId);
    at(e.clientX);
  });
  svg.addEventListener("pointermove", (e) => {
    if (e.buttons || e.pointerType === "touch") at(e.clientX);
  });
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  svg.addEventListener("pointerleave", end);
}
