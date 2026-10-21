// Bluetooth LE layer: the ESP32 bandage, the MS1020 watch, and a demo data source.
//
// tauri-plugin-blec keeps ONE active connection, so only one device is connected at a
// time. The bandage streams continuously; the watch is a short "measure now" session after
// which the bandage is reconnected.

import { startScan, stopScan, connect, disconnect, subscribe, checkPermissions } from "@mnlphlp/plugin-blec";
import { api, prefs } from "./api.js";

const ESP_NAME = "WoundSense-ESP32";
const ESP_CHAR = "beb5483e-36e1-4688-b7f5-ea07361b26a8";
const WATCH_PREFIX = "MS1020";
const WATCH_ADDR = "A4:C1:3C:DC:04:D5"; // matched too, in case the advertised name is missing
const WATCH_CHAR = "0000cc04-0000-1000-8000-00805f9b34fb";

const POST_EVERY_MS = 15000;

// ---- tiny event bus / shared state ----
const listeners = new Set();
export const live = {
  // latest values seen this session (may be newer than what the server has)
  values: {},
  at: {},
  esp: "off", // off | scanning | connecting | connected | error
  watch: "off", // off | scanning | connecting | waiting | done | error
  demo: false,
  message: "",
};
export function onLive(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
function emit() {
  listeners.forEach((fn) => fn(live));
}

// ---- parsers (pure; covered by a node smoke test) ----
const dec = new TextDecoder();

/** ESP32 payload is ASCII "temp,humidity[,moisture]". */
export function parseEsp(bytes) {
  const parts = dec.decode(new Uint8Array(bytes)).trim().split(",").map(Number);
  if (parts.length < 2 || parts.slice(0, 2).some((n) => !Number.isFinite(n))) return null;
  const [temperature, humidity, moisture] = parts;
  return { temperature, humidity, moisture: Number.isFinite(moisture) ? moisture : null };
}

/**
 * MS1020 watch packets on 0xCC04 (20 bytes). Decoded from observed traffic, not from a
 * spec, so values are range-checked and anything unrecognised is ignored:
 *   0x20 ...  byte 10 = heart rate (bpm)
 *   0xF3 ...  byte 2 = systolic, byte 3 = diastolic (mmHg)
 */
export function parseWatch(bytes) {
  const b = Array.from(bytes);
  if (b.length < 11) return null;
  if (b[0] === 0x20) {
    const bpm = b[10];
    return bpm >= 30 && bpm <= 220 ? { bpm } : null;
  }
  if (b[0] === 0xf3) {
    const [systolic, diastolic] = [b[2], b[3]];
    return systolic > diastolic && systolic >= 70 && systolic <= 250 && diastolic >= 40 && diastolic <= 150
      ? { systolic, diastolic }
      : null;
  }
  return null;
}

// ---- ingest: update live state + send to server (throttled for the bandage) ----
let lastPost = 0;
async function ingest(values, source, { force = false } = {}) {
  const now = Date.now();
  Object.assign(live.values, values);
  for (const k of Object.keys(values)) live.at[k] = now;
  emit();
  if (!prefs.token) return;
  if (!force && now - lastPost < POST_EVERY_MS) return;
  lastPost = now;
  try {
    await api("/readings", { method: "POST", body: { ...values, source } });
  } catch {
    /* server unreachable: the live value still shows, history just misses this point */
  }
}

// ---- BLE helpers ----
let seenNames = [];

// startScan() resolves as soon as the scan has STARTED (the plugin scans in the background),
// so "not found" must be decided by our own timer, not by the promise settling.
async function findDevice(match, ms) {
  seenNames = [];
  return new Promise((resolve, reject) => {
    let done = false;
    const finish = (dev) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve(dev);
    };
    const timer = setTimeout(() => finish(null), ms + 500);
    startScan((devices) => {
      seenNames = [...new Set(devices.map((x) => x.name || "(no name)"))];
      const d = devices.find((x) => match(x));
      if (d) finish(d);
    }, ms).catch((e) => {
      if (!done) {
        done = true;
        clearTimeout(timer);
        reject(e);
      }
    });
  });
}

async function ensurePermission() {
  if (!(await checkPermissions(true))) {
    throw new Error("Bluetooth permission was denied. Allow 'Nearby devices' for WoundSense in Android settings.");
  }
}

async function open(match, char, onBytes, setState, label) {
  await ensurePermission();
  setState("scanning");
  const dev = await findDevice(match, 20000);
  try {
    await stopScan();
  } catch {
    /* already stopped */
  }
  if (!dev) {
    const seen = seenNames.length ? ` Devices seen: ${seenNames.slice(0, 8).join(", ")}.` : " No Bluetooth devices were seen at all.";
    throw new Error(`Couldn't find ${label}. Make sure it's on, awake, nearby and not connected to anything else.${seen}`);
  }
  setState("connecting");
  await connect(dev.address, () => setState("off"));
  await subscribe(char, onBytes);
}

// ---- bandage (ESP32) ----
export async function connectBandage() {
  if (live.demo) stopDemo();
  live.message = "";
  try {
    await open(
      (d) => d.name === ESP_NAME,
      ESP_CHAR,
      (bytes) => {
        const v = parseEsp(bytes);
        if (v) {
          const { moisture, ...rest } = v;
          ingest(moisture === null ? rest : v, "bandage");
        }
      },
      (s) => {
        live.esp = s;
        emit();
      },
      "the bandage",
    );
    live.esp = "connected";
  } catch (e) {
    live.esp = "error";
    live.message = String(e.message || e);
  }
  emit();
}

export async function disconnectBandage() {
  try {
    await disconnect();
  } catch {
    /* not connected */
  }
  live.esp = "off";
  emit();
}

// ---- watch (MS1020) ----
let watchTimer = null;
let watchResolve = null; // setTimeout returns a plain number in a WebView, so keep the resolver separately
export async function measureOnWatch(timeoutMs = 90000) {
  const reconnectBandage = live.esp === "connected";
  if (live.demo) stopDemo();
  live.message = "";
  if (reconnectBandage) await disconnectBandage();
  const got = {};
  try {
    await open(
      (d) =>
        (d.name || "").toUpperCase().startsWith(WATCH_PREFIX) || (d.address || "").toUpperCase() === WATCH_ADDR,
      WATCH_CHAR,
      (bytes) => {
        const v = parseWatch(bytes);
        if (!v) return;
        Object.assign(got, v);
        ingest(v, "watch", { force: true });
      },
      (s) => {
        live.watch = s;
        emit();
      },
      "the watch",
    );
    live.watch = "waiting";
    emit();
    await new Promise((resolve) => {
      watchResolve = resolve;
      watchTimer = setTimeout(resolve, timeoutMs);
    });
    live.watch = Object.keys(got).length ? "done" : "error";
    if (!Object.keys(got).length) live.message = "No heart-rate or blood-pressure reading arrived from the watch.";
  } catch (e) {
    live.watch = "error";
    live.message = String(e.message || e);
  }
  watchTimer = null;
  watchResolve = null;
  try {
    await disconnect();
  } catch {
    /* already gone */
  }
  emit();
  if (reconnectBandage) connectBandage();
}

export function finishWatchSession() {
  if (watchTimer) {
    clearTimeout(watchTimer);
    if (watchResolve) watchResolve();
  }
}

// ---- demo source (clearly labelled in the UI, stored with source = "demo") ----
let demoTimer = null;
// temperature is body-equivalent, like the firmware sends (see woundsense_ble.ino)
let walk = { temperature: 36.9, humidity: 62, moisture: 3.2, bpm: 74 };
const jitter = (v, step, lo, hi) => Math.min(hi, Math.max(lo, v + (Math.random() - 0.5) * step));

export function startDemo() {
  if (demoTimer) return;
  live.demo = true;
  prefs.demo = true;
  live.values = {};
  live.at = {};
  const tick = () => {
    walk = {
      temperature: jitter(walk.temperature, 0.2, 36.3, 37.8),
      humidity: jitter(walk.humidity, 3, 45, 82),
      moisture: jitter(walk.moisture, 0.6, 0.5, 8),
      bpm: jitter(walk.bpm, 5, 60, 95),
    };
    const r = (n, d) => Number(n.toFixed(d));
    ingest(
      {
        temperature: r(walk.temperature, 1),
        humidity: r(walk.humidity, 0),
        moisture: r(walk.moisture, 1),
        bpm: r(walk.bpm, 0),
        systolic: 118 + Math.round((Math.random() - 0.5) * 6),
        diastolic: 76 + Math.round((Math.random() - 0.5) * 4),
      },
      "demo",
      { force: true },
    );
  };
  tick();
  demoTimer = setInterval(tick, 5000);
  emit();
}

export function stopDemo() {
  if (demoTimer) clearInterval(demoTimer);
  demoTimer = null;
  live.demo = false;
  prefs.demo = false;
  live.values = {};
  live.at = {};
  emit();
}
