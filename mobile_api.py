"""JSON API for the WoundSense mobile app (served under /api/m).

Shares the web app's validated model and PubMed RAG corpus; differs only in transport:
  * token auth (Authorization: Bearer ...) instead of cookie sessions
  * readings arrive piecemeal over BLE: the bandage streams temperature, humidity and moisture,
    the watch adds heart rate and blood pressure in short "measure now" sessions
  * the condition / days-to-heal model is the web app's 5-feature model (models/*.pkl,
    externally tested on PhysioNet 2019); it runs once a fresh value exists for every input
  * moisture is stored and charted but is not a model input
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
from werkzeug.security import check_password_hash, generate_password_hash

import database as db
from data.literature_data import PAPERS

ROOT = Path(__file__).resolve().parent
bp = Blueprint("mobile", __name__, url_prefix="/api/m")

# model input -> mobile_readings column
MODEL_INPUTS = {"temperature": "temperature", "humidity": "humidity", "heart_rate": "bpm",
                "systolic_bp": "systolic", "diastolic_bp": "diastolic"}
READING_COLS = ["temperature", "humidity", "moisture", "bpm", "systolic", "diastolic"]
# how old a value may be and still feed an assessment: the bandage streams, the watch is occasional
MAX_AGE = {"temperature": timedelta(minutes=10), "humidity": timedelta(minutes=10),
           "bpm": timedelta(hours=12), "systolic": timedelta(hours=12), "diastolic": timedelta(hours=12)}
CONDITION_LABELS = {"healthy": "On track", "wound_healing": "Healing", "infected": "Needs attention"}
TOKEN_MAX_AGE = 60 * 60 * 24 * 30

# Filled in by init_mobile_api() so we can share the web app's Groq client, secret and RAG service.
_state = {"serializer": None, "groq": None, "groq_model": None, "rag": None}

PAPERS_BY_ID = {p["id"]: p for p in PAPERS}

_cond_model = joblib.load(ROOT / "models" / "condition_model.pkl")
_heal_model = joblib.load(ROOT / "models" / "healing_model.pkl")
_label_enc = joblib.load(ROOT / "models" / "label_encoder.pkl")
MODEL_META = json.loads((ROOT / "models" / "metadata.json").read_text(encoding="utf-8"))
_ext_path = ROOT / "models" / "external_validation.json"
EXTERNAL = json.loads(_ext_path.read_text(encoding="utf-8")) if _ext_path.exists() else None

SENSOR_GUIDES = {
    "temperature": {
        "title": "Temperature",
        "what": "Temperature at the bandage, reported as a body-equivalent value (the firmware adds a fixed "
                "skin-to-core offset so it lines up with clinical fever thresholds).",
        "evidence": "Warmth is a classic sign of infection. In chronic leg ulcers, a warmer periwound area was "
                    "significantly associated with infection, and infected wounds have measured 4-5 °C warmer than "
                    "healthy skin. At the whole-body level, sepsis criteria use a temperature above 38 °C or below 36 °C.",
        "tip": "The trend over hours and days says more than any single reading.",
        "papers": ["fierheller_2010", "chanmugam_2017", "nakagami_2010", "bone_1992"],
    },
    "humidity": {
        "title": "Humidity",
        "what": "Relative humidity inside the dressing. It is the strongest input to the days-to-heal estimate.",
        "evidence": "Wounds kept moist re-epithelialise faster and scar less than wounds left to dry and scab. "
                    "Too much moisture is a problem too: prolonged wetness macerates the skin around the wound, "
                    "so the goal is balance, neither too dry nor too wet.",
        "tip": "Steady readings point to a stable healing environment; big swings are worth a closer look.",
        "papers": ["winter_1962", "junker_2013", "okan_2007", "cutting_2002"],
    },
    "moisture": {
        "title": "Moisture",
        "what": "How wet the dressing pad is, on a 0-10 scale from the bandage's moisture sensor. "
                "It is shown for context and is not an input to the assessment.",
        "evidence": "Matching the dressing to the wound's moisture level is a core part of wound care. "
                    "A pad that stays saturated risks maceration of the surrounding skin.",
        "tip": "A reading that keeps climbing usually means the dressing is filling up and may need changing.",
        "papers": ["okan_2007", "cutting_2002", "woo_2009"],
    },
    "heart_rate": {
        "title": "Heart rate",
        "what": "Pulse measured by your watch, worn beside the wound.",
        "evidence": "A heart rate above 90 bpm is one of the SIRS criteria for a body-wide response to infection, "
                    "and early-warning scores built from routine vital signs predict deterioration in infected "
                    "patients. Stress, which raises heart rate, also measurably slows wound repair.",
        "tip": "Resting readings, taken at a similar time each day, are the most comparable.",
        "papers": ["bone_1992", "churpek_2017", "smith_2013", "gouin_2011"],
    },
    "blood_pressure": {
        "title": "Blood pressure",
        "what": "Systolic and diastolic pressure (mmHg) from your watch.",
        "evidence": "Low systolic pressure (100 mmHg or less) is part of the qSOFA sepsis screen. At the other end, "
                    "hypertensive patients took almost twice as long to reach a dry surgical wound (3.8 vs 2.0 days).",
        "tip": "Measure seated and rested, at similar times of day, for readings you can compare.",
        "papers": ["singer_2016", "seymour_2016", "ahmed_2011", "guo_2010"],
    },
}


def _plain(text):
    """Metadata notes are written for developers; tidy them for the app."""
    text = re.sub(r"\s*See [\w/]+\.py\.?", "", text).replace(" -- ", " - ").replace("NOT ", "not ")
    return text.strip()


def _paper_brief(p):
    return {"id": p["id"], "title": p["title"], "authors": p["authors"], "year": p["year"], "journal": p["journal"],
            "doi": p.get("doi", ""), "pmid": p.get("pmid", ""), "url": p.get("pubmed_url") or p.get("doi_url", ""),
            "sensors": p.get("biomarkers", []), "key_findings": p["key_findings"]}


# ---------- setup ----------

def init_mobile_api(app, groq_client, groq_model, rag_service):
    _state["serializer"] = URLSafeTimedSerializer(app.secret_key, salt="woundsense-mobile")
    _state["groq"] = groq_client
    _state["groq_model"] = groq_model
    _state["rag"] = rag_service

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
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(mobile_readings)").fetchall()}
    if "probs" not in cols:
        conn.execute("ALTER TABLE mobile_readings ADD COLUMN probs TEXT")
    if "model" not in cols:
        conn.execute("ALTER TABLE mobile_readings ADD COLUMN model TEXT")
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

    app.register_blueprint(bp)

    @app.after_request
    def _cors(resp):
        if request.path.startswith("/api/m"):
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp


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


def _fresh_inputs(latest, now=None):
    """Model inputs from the newest stored values that are still fresh enough; plus what is missing."""
    now = now or datetime.now(timezone.utc)
    inputs, missing = {}, []
    for feat, col in MODEL_INPUTS.items():
        item = latest.get(col)
        if item and now - datetime.fromisoformat(item["at"]) <= MAX_AGE[col]:
            inputs[feat] = float(item["value"])
        else:
            missing.append(feat)
    if not missing and inputs["diastolic_bp"] >= inputs["systolic_bp"]:
        missing = ["systolic_bp", "diastolic_bp"]
    return inputs, missing


def _predict(inputs):
    x = np.array([[inputs[f] for f in MODEL_META["features"]]])
    proba = _cond_model.predict_proba(x)[0]
    labels = _label_enc.inverse_transform(np.arange(len(proba)))
    i = int(np.argmax(proba))
    probs = {str(lbl): round(float(p), 3) for lbl, p in zip(labels, proba)}
    return str(labels[i]), float(proba[i]), float(_heal_model.predict(x)[0]), probs


@bp.route("/readings", methods=["POST"])
@auth_required
def add_reading():
    d = request.get_json(force=True) or {}
    vals = {k: _num(d, k) for k in READING_COLS}
    # sanity ranges: drop obviously broken sensor values instead of storing them
    limits = {"temperature": (25, 45), "humidity": (0, 100), "moisture": (0, 10),
              "bpm": (25, 220), "systolic": (60, 260), "diastolic": (30, 160)}
    for k, (lo, hi) in limits.items():
        if vals[k] is not None and not lo <= vals[k] <= hi:
            vals[k] = None
    if all(v is None for v in vals.values()):
        return jsonify({"error": "No valid values in reading."}), 400
    source = str(d.get("source") or "device")[:20]
    demo = source == "demo"
    now = datetime.now(timezone.utc)

    conn = db.get_db()
    # Readings arrive one device at a time, so combine this one with the freshest stored values.
    latest = {c: _latest_value(conn, g.user_id, c, demo) for c in MODEL_INPUTS.values()}
    for c in MODEL_INPUTS.values():
        if vals[c] is not None:
            latest[c] = {"value": vals[c], "at": now.isoformat()}
    inputs, missing = _fresh_inputs(latest, now)

    cond = conf = days = probs = None
    if not missing:
        cond, conf, days, probs = _predict(inputs)

    conn.execute(
        """INSERT INTO mobile_readings (user_id, temperature, humidity, moisture, bpm, systolic, diastolic,
           condition, confidence, healing_days, probs, model, source, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (g.user_id, vals["temperature"], vals["humidity"], vals["moisture"], vals["bpm"], vals["systolic"],
         vals["diastolic"], cond, conf, days, json.dumps(probs) if probs else None,
         "rf5" if cond else None, source, now.isoformat()),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "condition": cond, "probs": probs, "missing": missing,
                    "healing_days": round(days, 1) if days is not None else None})


def _overall(wound, scan):
    """Plain rules (not a trained model) that combine the sensor assessment and the latest photo."""
    rank = {"ok": 0, "watch": 1, "alert": 2}
    level, reasons = "ok", []

    def bump(lv, why):
        nonlocal level
        reasons.append(why)
        if rank[lv] > rank[level]:
            level = lv

    if wound:
        if wound["condition"] == "infected":
            bump("alert", "Your readings match the pattern the model links with infection.")
        elif wound["trend"] == "worsening":
            bump("watch", "Your readings are trending the wrong way.")
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
    latest = {c: _latest_value(conn, g.user_id, c, demo) for c in READING_COLS}
    pred = conn.execute(
        "SELECT condition, confidence, healing_days, probs, created_at FROM mobile_readings "
        f"WHERE user_id = ? AND condition IS NOT NULL AND model = 'rf5' AND {_src(demo)} "
        "ORDER BY created_at DESC LIMIT 2",
        (g.user_id,)).fetchall()
    count = conn.execute(f"SELECT COUNT(*) AS n FROM mobile_readings WHERE user_id = ? AND {_src(demo)}",
                         (g.user_id,)).fetchone()["n"]
    conn.close()
    _, missing = _fresh_inputs(latest)

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
                 "probs": json.loads(cur["probs"]) if cur["probs"] else None,
                 "trend": trend, "at": cur["created_at"]}
    scan = _latest_scan(g.user_id)
    scan_brief = None
    if scan:
        scan_brief = {"created_at": scan["created_at"], "type": scan["type"], "severity": scan["severity"],
                      "reliable": scan["reliable"]}
    return jsonify({"latest": latest, "wound": wound, "missing": missing, "reading_count": count,
                    "scan": scan_brief, "overall": _overall(wound, scan)})


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
    model_only = " AND model = 'rf5'" if metric == "healing_days" else ""
    conn = db.get_db()
    rows = conn.execute(
        f"SELECT created_at, {', '.join(cols[metric])} FROM mobile_readings "
        f"WHERE user_id = ? AND created_at >= ? AND {cols[metric][0]} IS NOT NULL AND {_src(demo)}{model_only} "
        "ORDER BY created_at",
        (g.user_id, since)).fetchall()
    conn.close()

    step = max(1, len(rows) // 300)  # keep payloads small; the chart doesn't need more
    points = [{"t": r["created_at"], **{c: r[c] for c in cols[metric]}} for r in rows[::step]]
    first = cols[metric][0]
    vals = [r[first] for r in rows]
    stats = {"min": min(vals), "max": max(vals), "avg": sum(vals) / len(vals), "count": len(vals)} if vals else None
    return jsonify({"metric": metric, "fields": cols[metric], "points": points, "stats": stats})


# ---------- model card ----------

@bp.route("/model")
@auth_required
def model_card():
    cm, hm, dq = MODEL_META["condition_model"], MODEL_META["healing_model"], MODEL_META["data_quality"]
    card = {
        "features": MODEL_META["features"],
        "trained_at": MODEL_META["trained_at"],
        "algorithm": cm["algorithm"],
        "training": {"rows": dq["training_rows_total"], "source": _plain(dq["training_data_source"]),
                     "healing_days_source": _plain(dq["healing_days_source"])},
        "holdout": {"accuracy": cm["accuracy_holdout"], "macro_f1": cm["macro_f1_holdout"],
                    "cv_mean": cm["cv5_accuracy_mean"], "cv_std": cm["cv5_accuracy_std"], "n": cm["holdout_n"],
                    "per_class": cm["per_class"], "feature_importance": cm["feature_importance"]},
        "healing": {"mae_days": hm["mae_days_holdout"], "r2": hm["r2_holdout"],
                    "feature_importance": hm["feature_importance"]},
        "external": None,
        "freshness": {k: int(v.total_seconds() // 60) for k, v in MAX_AGE.items()},
    }
    if EXTERNAL:
        ds, pt, hr, rg = (EXTERNAL["dataset"], EXTERNAL["classifier_patient"], EXTERNAL["classifier_hourly"],
                          EXTERNAL["regressor"])
        names = {"deployed_model": "WoundSense model", "baseline_sirs_plus_bp_ge2": "SIRS + BP (≥2)",
                 "baseline_sirs_vitals_eq2": "SIRS vitals (2 of 2)", "baseline_qsofa_sbp_le100": "qSOFA SBP ≤100"}
        card["external"] = {
            "dataset": ds["name"], "url": ds["url"], "license": ds["license"], "citation": ds["citation"],
            "patients": ds["patients_evaluated"], "sepsis_patients": ds["sepsis_patients"],
            "hours": ds["rows_evaluated"], "label_caveat": _plain(ds["label_caveat"]), "missing_feature": _plain(ds["missing_feature"]),
            "patient_auroc": [{"name": names[k], "auroc": pt[k]["auroc"], "ci": pt[k].get("auroc_95ci"),
                               "ours": k == "deployed_model"} for k in names if k in pt],
            "sens_at_80_spec": pt["deployed_model"]["sensitivity_at_80pct_specificity"]["sensitivity"],
            "hourly_auroc": hr["deployed_model"]["auroc"],
            "healing_auroc_patient": rg["auroc_pred_days_vs_sepsis_patient"],
            "healing_days_no_sepsis": rg["mean_pred_days_no_sepsis_hours"],
            "healing_days_sepsis": rg["mean_pred_days_sepsis_hours"],
        }
    return jsonify(card)


# ---------- wound info ----------

@bp.route("/wound-info")
@auth_required
def wound_info():
    ctx = db.get_latest_wound_context(g.user_id)
    return jsonify({
        "context": dict(ctx) if ctx else None,
        "guides": SENSOR_GUIDES,
        "papers": [_paper_brief(p) for p in PAPERS],
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

Latest readings: temperature {temperature} (body-equivalent), humidity in the dressing {humidity}, dressing moisture {moisture} (0-10 scale), heart rate {bpm}, blood pressure {bp}.
Model assessment (Random Forest on temperature, humidity, heart rate and blood pressure; trained on knowledge-based data and externally tested on PhysioNet 2019 ICU sepsis data, patient-level AUROC 0.69): {condition}, estimated days to heal {healing_days}, trend {trend}.

Latest wound photo analysis (wound type and visual severity): {scan}

Patient-reported wound context: cause {cause}; severity {severity}; pain {pain}/10; itching {itching}/10; days since onset {days}; notes {notes}.

PubMed literature retrieved for this question:
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
    latest = {c: (_latest_value(conn, uid, c, demo) or {}).get("value") for c in READING_COLS}
    pred = conn.execute(
        f"SELECT condition, healing_days FROM mobile_readings WHERE user_id = ? AND condition IS NOT NULL "
        f"AND model = 'rf5' AND {_src(demo)} ORDER BY created_at DESC LIMIT 2", (uid,)).fetchall()
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

    # Same retrieval as the web chat: the query is expanded with any out-of-range readings.
    rag = _state["rag"].build_rag_context_for_chat(
        msg, sensor_readings={"temperature": latest["temperature"], "humidity": latest["humidity"],
                              "heart_rate": latest["bpm"], "systolic_bp": latest["systolic"]}, limit=3)
    cites = rag["citations"]

    system = CHAT_PROMPT.format(
        temperature=f(latest["temperature"], " °C"), humidity=f(latest["humidity"], "%"),
        moisture=f(latest["moisture"]), bpm=f(latest["bpm"], " bpm"),
        bp=(f"{latest['systolic']:.0f}/{latest['diastolic']:.0f} mmHg"
            if latest["systolic"] is not None and latest["diastolic"] is not None else "not available"),
        condition=pred[0]["condition"] if pred else "no assessment yet (needs fresh bandage and watch readings)",
        healing_days=f(pred[0]["healing_days"]) if pred else "n/a", trend=trend,
        cause=(ctx["cause"] if ctx and ctx["cause"] else "not provided"),
        severity=(ctx["severity"] if ctx and ctx["severity"] else "not provided"),
        pain=ctx["pain_level"] if ctx else "n/a", itching=ctx["itching_level"] if ctx else "n/a",
        days=ctx["days_since_onset"] if ctx else "n/a",
        notes=(ctx["notes"] if ctx and ctx["notes"] else "none"),
        literature=rag["prompt_text"] or "No matching excerpt.", scan=scan_text,
        tags=", ".join(c["tag"] for c in cites) or "(none available for this question)")

    citations = [{"tag": c["tag"], "id": c["paper_id"], "title": c["title"], "year": c["year"],
                  "journal": c["journal"], "url": c["pubmed_url"] or c["doi_url"]} for c in cites]
    allowed = {c["tag"] for c in cites}
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
