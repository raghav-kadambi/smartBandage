"""JSON API for the WoundSense mobile app (served under /api/m).

Kept separate from app.py so the web app is untouched. Differences from the web API:
  * token auth (Authorization: Bearer ...) instead of cookie sessions
  * a reduced 3-feature model (temperature, humidity, moisture) from models/mobile/
  * a verified literature corpus (data/literature_verified.json) for RAG
  * heart rate / blood pressure from the watch are stored and shown, but do not feed the model
"""

import json
import base64
import io
import re
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import joblib
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from flask import Blueprint, Response, g, jsonify, request, stream_with_context
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from qdrant_client.models import Distance, PointStruct, VectorParams
from werkzeug.security import check_password_hash, generate_password_hash

import database as db

ROOT = Path(__file__).resolve().parent
bp = Blueprint("mobile", __name__, url_prefix="/api/m")

FEATURES = ["temperature", "humidity", "moisture"]
CONDITION_LABELS = {"healthy": "On track", "wound_healing": "Healing", "infected": "Needs attention"}
TOKEN_MAX_AGE = 60 * 60 * 24 * 30

# Filled in by init_mobile_api() so we can share the web app's Groq client, secret and RAG embedder.
_state = {"serializer": None, "groq": None, "groq_model": None, "rag_client": None, "embedder": None}

COLLECTION = "wound_verified_literature"
PAPERS = json.loads((ROOT / "data" / "literature_verified.json").read_text(encoding="utf-8"))
PAPERS_BY_ID = {p["id"]: p for p in PAPERS}

_cond_model = joblib.load(ROOT / "models" / "mobile" / "condition_model.pkl")
_heal_model = joblib.load(ROOT / "models" / "mobile" / "healing_model.pkl")
MODEL_META = json.loads((ROOT / "models" / "mobile" / "metadata.json").read_text())

SENSOR_GUIDES = {
    "temperature": {
        "title": "Temperature",
        "what": "Skin temperature at the bandage, tracked continuously.",
        "evidence": "A wound that stays warmer than the skin around it is a classic early sign of inflammation or infection. "
                    "Clinicians treat a difference of about 3-4 F (roughly 1.7-2.2 C) as meaningful. A steady move toward "
                    "normal skin temperature fits a wound that is settling down.",
        "tip": "The trend over hours and days is the most useful view, more than any single reading.",
        "papers": ["fierheller_2010", "mufti_2018", "nakagami_2010", "collins_2025", "armstrong_2007"],
    },
    "humidity": {
        "title": "Humidity",
        "what": "Relative humidity inside the dressing.",
        "evidence": "Wounds heal better in a moist environment than a dry one, and smart-dressing research tracks "
                    "moisture as a key signal. Steady readings, rather than big swings, point to a stable healing environment.",
        "tip": "Read it together with the moisture value: the pair shows how wet the dressing is.",
        "papers": ["junker_2013", "sarpong_2026", "han_2017"],
    },
    "moisture": {
        "title": "Moisture",
        "what": "How wet the dressing is, a practical stand-in for wound exudate.",
        "evidence": "A moist wound bed supports healing, while heavy exudate is linked to slower recovery: in a 149-patient "
                    "cohort, wound secretion and an inflamed wound base predicted non-healing. A falling trend as the wound "
                    "settles is a good sign.",
        "tip": "A steadily rising reading means the dressing is filling up, so it may be time to think about a change.",
        "papers": ["wolny_2024", "junker_2013", "goto_2020", "schultz_2003"],
    },
    "heart_rate": {
        "title": "Heart rate",
        "what": "Pulse measured by your watch, worn beside the wound.",
        "evidence": "Heart rate reflects activity and stress, and stress matters for healing: in a controlled study a small "
                    "wound took about 9 days longer to heal in people under chronic stress. In people with foot ulcers, "
                    "heart-rate patterns tracked how quickly wounds closed.",
        "tip": "Resting readings are the most comparable from day to day.",
        "papers": ["razjouyan_2017", "kiecolt_glaser_1995", "guo_2010"],
    },
    "blood_pressure": {
        "title": "Blood pressure",
        "what": "Systolic and diastolic pressure (mmHg) from your watch, worn beside the wound.",
        "evidence": "Healthy circulation delivers oxygen and nutrients to healing tissue, and vascular disease was the strongest "
                    "systemic predictor of non-healing in one cohort. Following pressure alongside your wound readings gives "
                    "your care team a fuller picture.",
        "tip": "Measure at similar times of day, seated and rested, for readings you can compare.",
        "papers": ["wolny_2024", "liu_2024", "wang_2023"],
    },
}


# ---------- setup ----------

def init_mobile_api(app, groq_client, groq_model, rag_service):
    _state["serializer"] = URLSafeTimedSerializer(app.secret_key, salt="woundsense-mobile")
    _state["groq"] = groq_client
    _state["groq_model"] = groq_model
    _state["rag_client"] = rag_service.client
    _state["embedder"] = rag_service.embedder

    conn = db.get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS mobile_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            temperature REAL, humidity REAL, moisture REAL,
            bpm REAL, systolic REAL, diastolic REAL,
            condition TEXT, confidence REAL, healing_days REAL,
            source TEXT, created_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mobile_user_time ON mobile_readings (user_id, created_at)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS mobile_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            result TEXT NOT NULL,
            thumb TEXT
        )"""
    )
    conn.commit()
    conn.close()

    _index_literature()
    app.register_blueprint(bp)

    @app.after_request
    def _cors(resp):
        if request.path.startswith("/api/m"):
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp


def _index_literature():
    client, embedder = _state["rag_client"], _state["embedder"]
    client.create_collection(COLLECTION, vectors_config=VectorParams(size=384, distance=Distance.COSINE))
    texts = [
        f"{p['title']}. Sensors: {', '.join(p['sensors'])}. {p['key_findings']} {p['abstract']}" for p in PAPERS
    ]
    vectors = list(embedder.embed(texts))
    client.upsert(
        COLLECTION,
        [PointStruct(id=i + 1, vector=v.tolist(), payload={"paper_id": p["id"]}) for i, (p, v) in enumerate(zip(PAPERS, vectors))],
    )


def _retrieve(query, limit=3):
    vec = list(_state["embedder"].embed([query]))[0].tolist()
    res = _state["rag_client"].query_points(COLLECTION, query=vec, limit=limit)
    out = []
    for pt in res.points:
        paper = PAPERS_BY_ID[pt.payload["paper_id"]]
        out.append({**paper, "score": round(float(pt.score), 3)})
    return out


def _citation_tag(p):
    return f"[{p['authors'].split(',')[0].split()[0]} et al., {p['year']}]"


# ---------- auth ----------

def _make_token(user_id):
    return _state["serializer"].dumps({"uid": user_id})


def auth_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "Not signed in."}), 401
        try:
            data = _state["serializer"].loads(header[7:], max_age=TOKEN_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return jsonify({"error": "Session expired. Please sign in again."}), 401
        g.user_id = data["uid"]
        return view(*args, **kwargs)
    return wrapped


@bp.route("/<path:_any>", methods=["OPTIONS"])
def _preflight(_any):
    return ("", 204)


@bp.route("/auth/signup", methods=["POST"])
def signup():
    d = request.get_json(force=True) or {}
    name, email, pw = (d.get("name") or "").strip(), (d.get("email") or "").strip().lower(), d.get("password") or ""
    if not name or not email or not pw:
        return jsonify({"error": "Name, email and password are all required."}), 400
    if len(pw) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400
    conn = db.get_db()
    if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
        conn.close()
        return jsonify({"error": "An account with that email already exists."}), 409
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (name, email, generate_password_hash(pw), datetime.utcnow().isoformat()),
    )
    conn.commit()
    user = conn.execute("SELECT id, name, email FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return jsonify({"token": _make_token(user["id"]), "user": {"name": user["name"], "email": user["email"]}})


@bp.route("/auth/login", methods=["POST"])
def login():
    d = request.get_json(force=True) or {}
    email, pw = (d.get("email") or "").strip().lower(), d.get("password") or ""
    conn = db.get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    if not user or not check_password_hash(user["password_hash"], pw):
        return jsonify({"error": "Incorrect email or password."}), 401
    return jsonify({"token": _make_token(user["id"]), "user": {"name": user["name"], "email": user["email"]}})


@bp.route("/me")
@auth_required
def me():
    conn = db.get_db()
    u = conn.execute("SELECT name, email FROM users WHERE id = ?", (g.user_id,)).fetchone()
    conn.close()
    return jsonify({"name": u["name"], "email": u["email"]}) if u else (jsonify({"error": "Unknown user."}), 401)


# ---------- readings ----------

def _num(d, key):
    v = d.get(key)
    if v is None or v == "":
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _predict(t, h, m):
    x = np.array([[t, h, m]])
    proba = _cond_model.predict_proba(x)[0]
    i = int(np.argmax(proba))
    return str(_cond_model.classes_[i]), float(proba[i]), float(_heal_model.predict(x)[0])


@bp.route("/readings", methods=["POST"])
@auth_required
def add_reading():
    d = request.get_json(force=True) or {}
    vals = {k: _num(d, k) for k in ["temperature", "humidity", "moisture", "bpm", "systolic", "diastolic"]}
    if all(v is None for v in vals.values()):
        return jsonify({"error": "No valid values in reading."}), 400
    # sanity ranges: drop obviously broken sensor values instead of storing them
    limits = {"temperature": (15, 45), "humidity": (0, 100), "moisture": (0, 10),
              "bpm": (25, 220), "systolic": (60, 260), "diastolic": (30, 160)}
    for k, (lo, hi) in limits.items():
        if vals[k] is not None and not lo <= vals[k] <= hi:
            vals[k] = None

    cond = conf = days = None
    if None not in (vals["temperature"], vals["humidity"], vals["moisture"]):
        cond, conf, days = _predict(vals["temperature"], vals["humidity"], vals["moisture"])

    conn = db.get_db()
    conn.execute(
        """INSERT INTO mobile_readings (user_id, temperature, humidity, moisture, bpm, systolic, diastolic,
           condition, confidence, healing_days, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (g.user_id, vals["temperature"], vals["humidity"], vals["moisture"], vals["bpm"], vals["systolic"],
         vals["diastolic"], cond, conf, days, str(d.get("source") or "device")[:20],
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "condition": cond, "healing_days": round(days, 1) if days is not None else None})


def _is_demo(value):
    return str(value).lower() in ("1", "true", "yes")


def _src(demo):
    """SQL fragment keeping demo-generated rows out of real history (and vice versa)."""
    return "source = 'demo'" if demo else "COALESCE(source, '') != 'demo'"


def _latest_value(conn, uid, col, demo=False):
    r = conn.execute(
        f"SELECT {col} AS v, created_at FROM mobile_readings WHERE user_id = ? AND {col} IS NOT NULL "
        f"AND {_src(demo)} ORDER BY created_at DESC LIMIT 1", (uid,)).fetchone()
    return {"value": r["v"], "at": r["created_at"]} if r else None


def _overall(wound, scan):
    """Plain rules (not a trained model) that combine the bandage assessment and the latest photo."""
    rank = {"ok": 0, "watch": 1, "alert": 2}
    level, reasons = "ok", []

    def bump(lv, why):
        nonlocal level
        reasons.append(why)
        if rank[lv] > rank[level]:
            level = lv

    if wound:
        if wound["condition"] == "infected":
            bump("alert", "Bandage readings match the pattern the model links with infection.")
        elif wound["trend"] == "worsening":
            bump("watch", "Bandage readings are trending the wrong way.")
    sev = scan.get("severity") if scan else None
    if scan and scan.get("reliable") and sev and sev["label"] == "Severe" and sev["confidence"] >= 0.6:
        bump("watch", "Your latest photo looks visually severe.")
    if not reasons and (wound or scan):
        reasons.append("Nothing in your latest data stands out.")
    return {"level": level, "reasons": reasons, "method": "rule-based"} if (wound or scan) else None


@bp.route("/status")
@auth_required
def status():
    demo = _is_demo(request.args.get("demo"))
    conn = db.get_db()
    latest = {c: _latest_value(conn, g.user_id, c, demo) for c in
              ["temperature", "humidity", "moisture", "bpm", "systolic", "diastolic"]}
    pred = conn.execute(
        "SELECT condition, confidence, healing_days, created_at FROM mobile_readings "
        f"WHERE user_id = ? AND condition IS NOT NULL AND {_src(demo)} ORDER BY created_at DESC LIMIT 2",
        (g.user_id,)).fetchall()
    count = conn.execute(f"SELECT COUNT(*) AS n FROM mobile_readings WHERE user_id = ? AND {_src(demo)}",
                         (g.user_id,)).fetchone()["n"]
    conn.close()

    wound = None
    if pred:
        cur = pred[0]
        trend = "new"
        if len(pred) == 2:
            rank = {"healthy": 0, "wound_healing": 1, "infected": 2}
            a, b = rank.get(cur["condition"], 1), rank.get(pred[1]["condition"], 1)
            trend = "improving" if a < b else "worsening" if a > b else "stable"
        wound = {"condition": cur["condition"], "label": CONDITION_LABELS.get(cur["condition"], cur["condition"]),
                 "confidence": round(cur["confidence"], 3), "healing_days": round(cur["healing_days"], 1),
                 "trend": trend, "at": cur["created_at"]}
    scan = _latest_scan(g.user_id)
    scan_brief = None
    if scan:
        scan_brief = {"created_at": scan["created_at"], "type": scan["type"], "severity": scan["severity"],
                      "reliable": scan["reliable"]}
    return jsonify({"latest": latest, "wound": wound, "reading_count": count, "scan": scan_brief,
                    "overall": _overall(wound, scan)})


@bp.route("/history")
@auth_required
def history():
    metric = request.args.get("metric", "temperature")
    hours = min(max(int(request.args.get("hours", 24)), 1), 24 * 365)
    cols = {"temperature": ["temperature"], "humidity": ["humidity"], "moisture": ["moisture"],
            "heart_rate": ["bpm"], "blood_pressure": ["systolic", "diastolic"],
            "healing_days": ["healing_days"]}
    if metric not in cols:
        return jsonify({"error": "Unknown metric."}), 400
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    demo = _is_demo(request.args.get("demo"))
    conn = db.get_db()
    rows = conn.execute(
        f"SELECT created_at, {', '.join(cols[metric])} FROM mobile_readings "
        f"WHERE user_id = ? AND created_at >= ? AND {cols[metric][0]} IS NOT NULL AND {_src(demo)} "
        "ORDER BY created_at",
        (g.user_id, since)).fetchall()
    conn.close()

    step = max(1, len(rows) // 300)  # keep payloads small; the chart doesn't need more
    points = [{"t": r["created_at"], **{c: r[c] for c in cols[metric]}} for r in rows[::step]]
    first = cols[metric][0]
    vals = [r[first] for r in rows]
    stats = {"min": min(vals), "max": max(vals), "avg": sum(vals) / len(vals), "count": len(vals)} if vals else None
    return jsonify({"metric": metric, "fields": cols[metric], "points": points, "stats": stats})


# ---------- wound info ----------

@bp.route("/wound-info")
@auth_required
def wound_info():
    ctx = db.get_latest_wound_context(g.user_id)
    papers = [{k: p[k] for k in ("id", "title", "authors", "year", "journal", "doi", "url", "evidence", "sensors", "key_findings")}
              for p in PAPERS]
    return jsonify({
        "context": dict(ctx) if ctx else None,
        "guides": SENSOR_GUIDES,
        "papers": papers,
    })


@bp.route("/wound-context", methods=["POST"])
@auth_required
def save_context():
    d = request.get_json(force=True) or {}

    def as_int(k):
        try:
            return int(d.get(k) or 0)
        except (TypeError, ValueError):
            return 0

    db.save_wound_context(
        g.user_id, cause=(d.get("cause") or "").strip(), severity=(d.get("severity") or "").strip(),
        pain_level=as_int("pain_level"), itching_level=as_int("itching_level"),
        days_since_onset=as_int("days_since_onset"), notes=(d.get("notes") or "").strip())
    return jsonify({"ok": True})



# ---------- wound photo scan ----------

SCAN_DIR = ROOT / "models" / "scan"
_scan = {"tried": False, "ok": False, "error": None}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _load_scan():
    """Load the photo model lazily so the server still starts if it hasn't been trained."""
    if _scan["tried"]:
        return _scan["ok"]
    _scan["tried"] = True
    try:
        from fastembed import ImageEmbedding

        meta = json.loads((SCAN_DIR / "metadata.json").read_text())
        _scan["meta"] = meta
        _scan["type"] = joblib.load(SCAN_DIR / "type_model.pkl")
        sev = SCAN_DIR / "severity_model.pkl"
        _scan["severity"] = joblib.load(sev) if sev.exists() else None
        _scan["train"] = np.load(SCAN_DIR / "train_embeddings.npy").astype("float32")
        _scan["embedder"] = ImageEmbedding(meta["embedding_model"])
        _scan["ok"] = True
    except Exception as e:  # missing files, bad install, etc.
        _scan["error"] = f"{type(e).__name__}: {e}"
    return _scan["ok"]


def _photo_quality(img):
    """Cheap checks that explain a bad result: tiny, dark/bright, or blurry photos."""
    warnings = []
    if min(img.size) < 200:
        warnings.append("The photo is very small. Move closer or use a higher-resolution image.")
    g = np.asarray(ImageOps.grayscale(img.resize((256, 256))), dtype="float32")
    mean = float(g.mean())
    if mean < 50:
        warnings.append("The photo is quite dark. Retake it in better light.")
    elif mean > 215:
        warnings.append("The photo is very bright or washed out. Avoid direct flash or glare.")
    lap = g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    if float(lap.var()) < 25:
        warnings.append("The photo looks blurry. Hold the phone steady and tap to focus.")
    return warnings


def _decode_image(data_url):
    raw = base64.b64decode(data_url.split(",", 1)[-1], validate=False)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Image is too large (8 MB max).")
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img).convert("RGB")
    return img


def _thumb(img, size=192):
    t = img.copy()
    t.thumbnail((size, size))
    buf = io.BytesIO()
    t.save(buf, "JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _analyze(img):
    meta = _scan["meta"]
    vec = np.asarray(list(_scan["embedder"].embed([img]))[0], dtype="float32")
    vec /= np.linalg.norm(vec)

    def head(model):
        proba = model.predict_proba(vec[None])[0]
        order = np.argsort(proba)[::-1]
        return {"label": str(model.classes_[order[0]]), "confidence": round(float(proba[order[0]]), 3),
                "top": [{"label": str(model.classes_[i]), "p": round(float(proba[i]), 3)} for i in order[:4]]}

    similarity = float((_scan["train"] @ vec).max())
    reliable = similarity >= meta["ood_similarity_threshold"]
    notes = []
    if not reliable:
        notes.append("We couldn't match this photo clearly. Try again with the wound centred, close up and in good light.")
    result = {"type": head(_scan["type"]), "severity": head(_scan["severity"]) if _scan["severity"] else None,
              "similarity": round(similarity, 3), "reliable": reliable,
              "quality": _photo_quality(img), "notes": notes}
    if result["type"]["confidence"] < 0.45:
        result["notes"].append("This is a best guess. A clearer, closer photo will sharpen it.")
    return result


@bp.route("/scan", methods=["POST"])
@auth_required
def scan():
    if not _load_scan():
        return jsonify({"error": "The wound photo model isn't available on the server yet "
                                 "(run models/train_scan_model.py).", "detail": _scan["error"]}), 503
    d = request.get_json(force=True) or {}
    try:
        img = _decode_image(d.get("image") or "")
    except (ValueError, UnidentifiedImageError, OSError):
        return jsonify({"error": "Couldn't read that image. Try a JPEG or PNG photo."}), 400
    result = _analyze(img)
    thumb = _thumb(img)
    created = datetime.now(timezone.utc).isoformat()
    conn = db.get_db()
    cur = conn.execute("INSERT INTO mobile_scans (user_id, created_at, result, thumb) VALUES (?,?,?,?)",
                       (g.user_id, created, json.dumps(result), thumb))
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return jsonify({"id": sid, "created_at": created, "thumb": thumb, **result})


@bp.route("/scans")
@auth_required
def scans():
    conn = db.get_db()
    rows = conn.execute("SELECT id, created_at, result, thumb FROM mobile_scans WHERE user_id = ? "
                        "ORDER BY created_at DESC LIMIT 20", (g.user_id,)).fetchall()
    conn.close()
    return jsonify({"scans": [{"id": r["id"], "created_at": r["created_at"], "thumb": r["thumb"],
                               **json.loads(r["result"])} for r in rows]})


def _latest_scan(uid):
    conn = db.get_db()
    r = conn.execute("SELECT created_at, result FROM mobile_scans WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                     (uid,)).fetchone()
    conn.close()
    return {"created_at": r["created_at"], **json.loads(r["result"])} if r else None



# ---------- citation guard ----------
# The model sometimes cites studies from memory. Only tags for papers actually retrieved for this
# question are allowed through; anything else in brackets that looks like a citation is dropped.

_CITE_RE = re.compile(r"(\s?)[\[\u3010]([^\[\]\u3010\u3011\n]{3,90}?(?:19|20)\d{2}[a-z]?)[\]\u3011]")


class CiteFilter:
    """Streaming filter: holds back an unclosed bracket until it can tell whether it is a citation."""

    def __init__(self, allowed):
        self.allowed = allowed  # set of "[Author et al., 2010]" strings
        self.buf = ""

    def _repl(self, m):
        keep = []
        for part in re.split(r"\s*;\s*", m.group(2)):
            tag = f"[{part.strip()}]"
            if tag in self.allowed:
                keep.append(tag)
        return (m.group(1) + " ".join(keep)) if keep else ""

    def _clean(self, text):
        return _CITE_RE.sub(self._repl, text)

    def feed(self, text):
        self.buf += text
        cut = len(self.buf)
        for opener in ("[", "\u3010"):
            i = self.buf.rfind(opener)
            if i != -1 and not any(c in self.buf[i + 1:] for c in "]\u3011"):
                cut = min(cut, i)
        # hold trailing spaces too: if a tag follows and is dropped, its leading space goes with it
        while cut > 0 and self.buf[cut - 1] == " ":
            cut -= 1
        ready, self.buf = self.buf[:cut], self.buf[cut:]
        if len(self.buf) > 100:  # clearly not a citation; stop holding it
            ready, self.buf = ready + self.buf, ""
        return self._clean(ready)

    def flush(self):
        out, self.buf = self._clean(self.buf), ""
        return out


def _clean_history(raw):
    """Chat context sent by the app (nothing is stored server-side). Keep it small and well-formed."""
    out = []
    for h in (raw or [])[-8:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
            out.append({"role": h["role"], "content": h["content"][:2000]})
    return out


# ---------- chat ----------

CHAT_PROMPT = """You are a careful wound-care information assistant inside a smart-bandage app, talking to the patient.

Latest bandage readings: temperature {temperature}, humidity {humidity}, moisture {moisture} (0-10 scale).
Bandage-sensor assessment: {condition}, estimated days to heal {healing_days}, trend {trend}.
Watch readings (the watch is worn beside the wound): heart rate {bpm}, blood pressure {bp}.

Latest wound photo analysis (wound type and visual severity): {scan}

Patient-reported wound context: cause {cause}; severity {severity}; pain {pain}/10; itching {itching}/10; days since onset {days}; notes {notes}.

Literature retrieved for this question:
{literature}

Rules:
1. Ground medical claims in the literature above. Cite ONLY with these exact bracketed tags: {tags}. If you recall other studies, state the idea as general knowledge without any citation tag. Never invent a citation, number or threshold that is not in the excerpts.
2. If the excerpts do not support an answer, say so plainly rather than guessing.
3. Be encouraging and practical. A single reading is a snapshot, so point to trends over time rather than one value.
4. If the condition is 'infected' or the patient describes fever, spreading redness, pus, or rapidly worsening pain, advise contacting a clinician promptly.
5. Never advise starting, stopping or changing medication.
6. Short, warm, plain language that reassures where the data supports it. Light markdown (bold, short bullet lists) only."""


@bp.route("/chat", methods=["POST"])
@auth_required
def chat():
    body = request.get_json(force=True) or {}
    msg = (body.get("message") or "").strip()
    if not msg:
        return jsonify({"error": "Empty message."}), 400
    uid = g.user_id
    demo = _is_demo(body.get("demo"))
    history = _clean_history(body.get("history"))

    conn = db.get_db()
    latest = {c: (_latest_value(conn, uid, c, demo) or {}).get("value") for c in
              ["temperature", "humidity", "moisture", "bpm", "systolic", "diastolic"]}
    pred = conn.execute(
        f"SELECT condition, healing_days FROM mobile_readings WHERE user_id = ? AND condition IS NOT NULL "
        f"AND {_src(demo)} ORDER BY created_at DESC LIMIT 2", (uid,)).fetchall()
    conn.close()
    ctx = db.get_latest_wound_context(uid)
    sc = _latest_scan(uid)
    if sc:
        scan_text = (f"wound type {sc['type']['label']} ({sc['type']['confidence']:.0%} confidence)"
                     + (f", visual severity {sc['severity']['label']}" if sc.get("severity") else "")
                     + ("" if sc["reliable"] else "; the photo was not a clear match, so treat this as a rough guess"))
    else:
        scan_text = "no photo scanned yet"

    trend = "unknown"
    if len(pred) == 2:
        rank = {"healthy": 0, "wound_healing": 1, "infected": 2}
        a, b = rank.get(pred[0]["condition"], 1), rank.get(pred[1]["condition"], 1)
        trend = "improving" if a < b else "worsening" if a > b else "stable"

    def f(v, unit=""):
        return "not available" if v is None else f"{v:.1f}{unit}"

    query = msg
    if latest["temperature"] is not None and latest["temperature"] > 35.0:
        query += " elevated wound temperature infection inflammation"
    if latest["moisture"] is not None and latest["moisture"] > 6:
        query += " excess wound exudate moisture"
    papers = _retrieve(query, limit=3)
    literature = "\n\n".join(
        f"- {_citation_tag(p)} {p['title']} ({p['journal']}, {p['year']}). Evidence: {p['evidence']}.\n  Findings: {p['key_findings']}"
        for p in papers)

    system = CHAT_PROMPT.format(
        temperature=f(latest["temperature"], " C"), humidity=f(latest["humidity"], "%"), moisture=f(latest["moisture"]),
        condition=pred[0]["condition"] if pred else "no assessment yet",
        healing_days=f(pred[0]["healing_days"]) if pred else "n/a", trend=trend,
        bpm=f(latest["bpm"], " bpm"),
        bp=(f"{latest['systolic']:.0f}/{latest['diastolic']:.0f} mmHg"
            if latest["systolic"] is not None and latest["diastolic"] is not None else "not available"),
        cause=(ctx["cause"] if ctx and ctx["cause"] else "not provided"),
        severity=(ctx["severity"] if ctx and ctx["severity"] else "not provided"),
        pain=ctx["pain_level"] if ctx else "n/a", itching=ctx["itching_level"] if ctx else "n/a",
        days=ctx["days_since_onset"] if ctx else "n/a",
        notes=(ctx["notes"] if ctx and ctx["notes"] else "none"),
        literature=literature or "No matching excerpt.", scan=scan_text,
        tags=", ".join(_citation_tag(p) for p in papers) or "(none available for this question)")

    citations = [{"tag": _citation_tag(p), "id": p["id"], "title": p["title"], "year": p["year"],
                  "journal": p["journal"], "url": p["url"], "evidence": p["evidence"]} for p in papers]
    allowed = {_citation_tag(p) for p in papers}
    groq, model = _state["groq"], _state["groq_model"]

    def generate():
        cf = CiteFilter(allowed)
        try:
            if not groq:
                yield ("The chat assistant isn't configured on the server yet (no GROQ_API_KEY). "
                       "Your readings and wound status still work.")
            else:
                messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": msg}]
                stream = groq.chat.completions.create(
                    model=model, messages=messages, temperature=0.4, max_completion_tokens=1500, stream=True)
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        out = cf.feed(delta)
                        if out:
                            yield out
                tail = cf.flush()
                if tail:
                    yield tail
        except Exception as e:  # network/model errors shouldn't kill the stream mid-air
            yield f"Sorry, I couldn't reach the assistant right now ({type(e).__name__})."
        if citations:
            yield "\n\n__CITATIONS__:" + json.dumps(citations)

    return Response(stream_with_context(generate()), mimetype="text/plain")
