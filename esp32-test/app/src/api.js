// Tiny API client for the WoundSense Flask server (/api/m/*).

const KEY = "woundsense.v1";

function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {};
  }
}

function save(patch) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...load(), ...patch }));
  } catch {
    /* private mode etc. -- the app still works for this session */
  }
}

export const DEFAULT_SERVER = "http://10.120.225.170:5000";

export const prefs = {
  get server() {
    return load().server || DEFAULT_SERVER;
  },
  set server(v) {
    save({ server: String(v).trim().replace(/\/+$/, "") });
  },
  get token() {
    return load().token || null;
  },
  set token(v) {
    save({ token: v });
  },
  get user() {
    return load().user || null;
  },
  set user(v) {
    save({ user: v });
  },
  get demo() {
    return !!load().demo;
  },
  set demo(v) {
    save({ demo: !!v });
  },
};

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

let onAuthExpired = () => {};
export function setAuthExpiredHandler(fn) {
  onAuthExpired = fn;
}

async function fetchWithTimeout(url, opts, ms = 15000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...opts, signal: ctrl.signal });
  } catch (e) {
    if (e.name === "AbortError") throw new ApiError("The server took too long to respond.", 0);
    throw new ApiError(`Can't reach the server at ${prefs.server}. Is it running and on the same Wi-Fi?`, 0);
  } finally {
    clearTimeout(timer);
  }
}

function headers(json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  if (prefs.token) h.Authorization = `Bearer ${prefs.token}`;
  return h;
}

export async function api(path, { method = "GET", body, timeout } = {}) {
  const res = await fetchWithTimeout(
    `${prefs.server}/api/m${path}`,
    { method, headers: headers(!!body), body: body ? JSON.stringify(body) : undefined },
    timeout,
  );
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON error page */
  }
  if (res.status === 401 && prefs.token && !path.startsWith("/auth/")) onAuthExpired();
  if (!res.ok) throw new ApiError((data && data.error) || `Server error (${res.status})`, res.status);
  return data;
}

// Streams the chat reply; calls onText with the accumulated text. Resolves with the final text.
export async function streamChat(message, demo, history, onText) {
  const res = await fetchWithTimeout(
    `${prefs.server}/api/m/chat`,
    { method: "POST", headers: headers(), body: JSON.stringify({ message, demo, history }) },
    60000,
  );
  if (!res.ok) {
    let msg = `Server error (${res.status})`;
    try {
      msg = (await res.json()).error || msg;
    } catch {
      /* keep default */
    }
    throw new ApiError(msg, res.status);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let text = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    text += dec.decode(value, { stream: true });
    onText(text);
  }
  return text;
}
