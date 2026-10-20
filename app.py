import os
import json
import socket
from pathlib import Path

import joblib
import numpy as np
from groq import Groq
from flask import (
    Flask, request, jsonify, session, redirect, url_for, render_template,
    Response, stream_with_context, send_from_directory,
)
from werkzeug.security import generate_password_hash, check_password_hash

import database as db
from rag_service import rag_service
from knowledge_graph import kg

ROOT = Path(__file__).resolve().parent
load_dotenv_path = ROOT / ".env"
if load_dotenv_path.exists():
    for line in load_dotenv_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

FEATURES = ["temperature", "humidity", "heart_rate", "systolic_bp", "diastolic_bp"]
SLIDER_RANGES = {
    "temperature": {"min": 34.0, "max": 42.0, "step": 0.1, "default": 36.8},
    "humidity": {"min": 10.0, "max": 100.0, "step": 1, "default": 55},
    "heart_rate": {"min": 40.0, "max": 160.0, "step": 1, "default": 74},
    "systolic_bp": {"min": 70.0, "max": 200.0, "step": 1, "default": 118},
    "diastolic_bp": {"min": 40.0, "max": 120.0, "step": 1, "default": 76},
}
# Readings outside these bounds are rejected as sensor faults rather than predicted on.
PLAUSIBLE = {
    "temperature": (25.0, 45.0),
    "humidity": (0.0, 100.0),
    "heart_rate": (20.0, 250.0),
    "systolic_bp": (50.0, 260.0),
    "diastolic_bp": (20.0, 160.0),
}
INPUT_MODES = {"simulate", "esp32"}

condition_model = joblib.load(ROOT / "models" / "condition_model.pkl")
healing_model = joblib.load(ROOT / "models" / "healing_model.pkl")
label_encoder = joblib.load(ROOT / "models" / "label_encoder.pkl")
metadata = json.loads((ROOT / "models" / "metadata.json").read_text())

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

db.init_db()


# ---------- auth helpers ----------

def login_required(view):
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


# ---------- pages ----------

@app.route("/")
def root():
    if "user_id" in session:
        return redirect(url_for("dashboard_page"))
    return redirect(url_for("login_page"))


@app.route("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("dashboard_page"))
    return render_template("login.html")


@app.route("/signup")
def signup_page():
    if "user_id" in session:
        return redirect(url_for("dashboard_page"))
    return render_template("signup.html")


@app.route("/choose-mode")
@login_required
def mode_page():
    return render_template(
        "mode_select.html",
        user_name=session.get("user_name"),
        current_mode=session.get("input_mode"),
    )


@app.route("/dashboard")
@login_required
def dashboard_page():
    mode = session.get("input_mode")
    if mode not in INPUT_MODES:
        return redirect(url_for("mode_page"))
    return render_template(
        "dashboard.html",
        user_name=session.get("user_name"),
        slider_ranges=SLIDER_RANGES,
        input_mode=mode,
    )


@app.route("/patient")
@login_required
def patient_page():
    latest = db.get_latest_reading(session["user_id"])
    history = db.get_chat_history(session["user_id"])
    context = db.get_latest_wound_context(session["user_id"])
    return render_template(
        "patient.html",
        user_name=session.get("user_name"),
        latest=latest,
        history=history,
        context=context,
    )


@app.route("/wound-details")
@login_required
def wound_details_page():
    context = db.get_latest_wound_context(session["user_id"])
    context_history = db.get_wound_context_history(session["user_id"])
    return render_template(
        "wound_details.html",
        user_name=session.get("user_name"),
        context=context,
        context_history=context_history,
    )


@app.route("/insights")
@login_required
def insights_page():
    return render_template("insights.html", user_name=session.get("user_name"))


@app.route("/knowledge-graph")
@login_required
def knowledge_graph_page():
    return render_template("knowledge_graph.html", user_name=session.get("user_name"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ---------- auth API ----------

@app.route("/api/signup", methods=["POST"])
def api_signup():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not name or not email or not password:
        return jsonify({"error": "Name, email and password are all required."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters."}), 400

    conn = db.get_db()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "An account with that email already exists."}), 409

    from datetime import datetime
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (name, email, generate_password_hash(password), datetime.utcnow().isoformat()),
    )
    conn.commit()
    user = conn.execute("SELECT id, name FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return jsonify({"ok": True, "redirect": url_for("mode_page")})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    conn = db.get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Incorrect email or password."}), 401

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return jsonify({"ok": True, "redirect": url_for("mode_page")})


@app.route("/api/mode", methods=["POST"])
@login_required
def api_set_mode():
    mode = (request.get_json(force=True) or {}).get("mode")
    if mode not in INPUT_MODES:
        return jsonify({"error": "Mode must be 'simulate' or 'esp32'."}), 400
    session["input_mode"] = mode
    return jsonify({"ok": True, "redirect": url_for("dashboard_page")})


# ---------- prediction ----------

def parse_features(data):
    """Return (features, error). Accepts the 5 model inputs from sliders or an ESP32."""
    try:
        features = {f: float(data[f]) for f in FEATURES}
    except (KeyError, TypeError, ValueError):
        return None, f"Missing or invalid sensor values. Expected numeric: {', '.join(FEATURES)}."
    for f, (lo, hi) in PLAUSIBLE.items():
        if not lo <= features[f] <= hi:
            return None, f"{f}={features[f]} is outside the plausible range {lo}-{hi}; check the sensor."
    if features["diastolic_bp"] >= features["systolic_bp"]:
        return None, "diastolic_bp must be lower than systolic_bp."
    return features, None


def run_prediction(user_id, features, source):
    x = np.array([[features[f] for f in FEATURES]])
    proba = condition_model.predict_proba(x)[0]
    pred_idx = int(np.argmax(proba))
    condition = label_encoder.inverse_transform([pred_idx])[0]
    confidence = float(proba[pred_idx])
    healing_days = float(healing_model.predict(x)[0])

    class_probs = {
        label_encoder.inverse_transform([i])[0]: round(float(p), 3)
        for i, p in enumerate(proba)
    }

    db.save_reading(user_id, features, condition, confidence, healing_days, source=source)

    return {
        "condition": condition,
        "confidence": round(confidence, 3),
        "class_probs": class_probs,
        "healing_days": round(healing_days, 1),
        "features": features,
        "source": source,
        "reading_count": db.get_reading_count(user_id),
    }


@app.route("/api/predict", methods=["POST"])
@login_required
def api_predict():
    features, err = parse_features(request.get_json(force=True) or {})
    if err:
        return jsonify({"error": err}), 400
    return jsonify(run_prediction(session["user_id"], features, source="simulated"))


@app.route("/api/readings-history")
@login_required
def api_readings_history():
    rows = db.get_reading_history(session["user_id"], limit=8)
    return jsonify({"readings": rows})


# ---------- ESP32 device API ----------

def lan_ip():
    """Best guess at this machine's LAN address, for the ESP32 to POST to."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the outbound interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


@app.route("/api/device/reading", methods=["POST"])
def api_device_reading():
    """Called by the ESP32 (no browser session). Auth = the per-user device token shown
    on the dashboard, sent as the X-Device-Token header."""
    data = request.get_json(force=True, silent=True) or {}
    token = request.headers.get("X-Device-Token") or data.get("token")
    device = db.get_device_by_token(token) if token else None
    if not device:
        return jsonify({"error": "Unknown or missing device token."}), 401
    features, err = parse_features(data)
    if err:
        return jsonify({"error": err}), 400
    db.touch_device(device["id"])
    result = run_prediction(device["user_id"], features, source="esp32")
    return jsonify({"ok": True, "condition": result["condition"], "confidence": result["confidence"],
                    "healing_days": result["healing_days"]})


@app.route("/api/device/status")
@login_required
def api_device_status():
    device = db.get_or_create_device(session["user_id"])
    latest = db.get_latest_reading(session["user_id"])
    if latest and latest.get("source") == "esp32":
        proba = condition_model.predict_proba(np.array([[latest[f] for f in FEATURES]]))[0]
        latest["class_probs"] = {
            label_encoder.inverse_transform([i])[0]: round(float(p), 3) for i, p in enumerate(proba)
        }
    port = request.host.split(":")[1] if ":" in request.host else "5000"
    return jsonify({
        "token": device["token"],
        "last_seen": device["last_seen"],
        "endpoint": f"http://{lan_ip()}:{port}/api/device/reading",
        "latest": latest if latest and latest.get("source") == "esp32" else None,
    })


@app.route("/api/device/regenerate", methods=["POST"])
@login_required
def api_device_regenerate():
    device = db.regenerate_device_token(session["user_id"])
    return jsonify({"token": device["token"]})


# ---------- chat API with Qdrant RAG ----------

SYSTEM_PROMPT_TEMPLATE = """You are a calm, knowledgeable clinical wound-care assistant embedded in a smart-bandage \
monitoring app. You are speaking directly to the patient in a warm, reassuring, and scientifically grounded tone.

Current sensor reading from the smart bandage for this patient:
- Body temperature: {temperature} C
- Humidity under the dressing: {humidity}%
- Heart rate: {heart_rate} bpm
- Blood pressure: {systolic_bp}/{diastolic_bp} mmHg

Machine Learning Model's current assessment:
- Predicted wound condition: {condition} (confidence {confidence})
- Estimated days remaining to heal: {healing_days}
- Trend vs the previous reading: {trend}

Patient's reported wound context:
- How it happened: {cause}
- Self-rated severity: {severity}
- Pain level (0-10): {pain_level}
- Itching level (0-10): {itching_level}
- Days since the wound occurred: {days_since_onset}
- Additional notes from patient: {notes}

CLINICAL MEDICAL LITERATURE CONTEXT (Retrieved from Qdrant Vector Knowledge Base):
{clinical_literature}

Clinical Guidelines & Response Rules:
1. EVIDENCE-BASED GROUNDING: Answer the patient's question by directly incorporating and citing the relevant retrieved medical literature above.
2. CITATION SYNTAX: Cite only the studies listed above, in brackets, using exactly the author tag given for each (e.g. [Fierheller & Sibbald, 2010]). Never cite a study that is not in the list, and never invent numbers that the listed findings do not contain.
3. SENSOR CORRELATION: Connect their specific values (temperature, humidity, heart rate, blood pressure) to the thresholds in the retrieved literature -- e.g. SIRS criteria (temperature > 38 or < 36 C, heart rate > 90), the qSOFA systolic BP <= 100 mmHg criterion, moist-wound-healing evidence for humidity, or the link between hypertension and slower wound healing.
4. SAFETY: Never claim to provide a definitive diagnosis or replace their physician. If condition is 'infected' or values are abnormal, clearly advise prompt clinician review.
5. FORMATTING: Use clean markdown, concise bullet points where appropriate, and keep the explanation easy for a patient or review judge to read.
"""


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    data = request.get_json(force=True)
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "Empty message."}), 400

    user_id = session["user_id"]

    latest = db.get_latest_reading(user_id)
    wound_ctx = db.get_latest_wound_context(user_id)

    recent = db.get_reading_history(user_id, limit=2)
    trend = "not enough readings yet to tell"
    if len(recent) == 2:
        rank = {"healthy": 0, "wound_healing": 1, "infected": 2}
        prev_rank = rank.get(recent[1]["condition"], 1)
        curr_rank = rank.get(recent[0]["condition"], 1)
        if curr_rank < prev_rank:
            trend = f"improving ({recent[1]['condition']} -> {recent[0]['condition']})"
        elif curr_rank > prev_rank:
            trend = f"worsening ({recent[1]['condition']} -> {recent[0]['condition']})"
        else:
            trend = f"stable (still {recent[0]['condition']})"

    # Retrieve relevant clinical literature via Qdrant Vector RAG
    sensor_dict = {f: (latest[f] if latest else None) for f in FEATURES}
    rag_data = rag_service.build_rag_context_for_chat(
        user_message,
        sensor_readings=sensor_dict,
        limit=3,
    )
    clinical_literature = rag_data["prompt_text"] or "No specific matching literature excerpt found for this query."

    context = {
        "temperature": round(latest["temperature"], 1) if latest else "unknown",
        "humidity": round(latest["humidity"], 1) if latest else "unknown",
        "heart_rate": round(latest["heart_rate"]) if latest else "unknown",
        "systolic_bp": round(latest["systolic_bp"]) if latest else "unknown",
        "diastolic_bp": round(latest["diastolic_bp"]) if latest else "unknown",
        "condition": latest["condition"] if latest else "no reading yet",
        "confidence": round(latest["confidence"], 2) if latest else "n/a",
        "healing_days": round(latest["healing_days"], 1) if latest else "n/a",
        "trend": trend,
        "cause": wound_ctx["cause"] if wound_ctx and wound_ctx["cause"] else "not provided",
        "severity": wound_ctx["severity"] if wound_ctx and wound_ctx["severity"] else "not provided",
        "pain_level": wound_ctx["pain_level"] if wound_ctx else "not provided",
        "itching_level": wound_ctx["itching_level"] if wound_ctx else "not provided",
        "days_since_onset": wound_ctx["days_since_onset"] if wound_ctx else "not provided",
        "notes": wound_ctx["notes"] if wound_ctx and wound_ctx["notes"] else "none",
        "clinical_literature": clinical_literature,
    }
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(**context)

    db.save_chat_message(user_id, "user", user_message)

    def generate():
        if not groq_client:
            reply = (
                "I don't have a Groq API key configured yet, so I can't reach the language "
                "model. Add GROQ_API_KEY to your .env file to turn on the chat assistant. "
                f"(For reference, your latest reading looks like: {context['condition']}, "
                f"estimated {context['healing_days']} days to heal.)"
            )
            db.save_chat_message(user_id, "assistant", reply)
            yield reply
            return

        history = db.get_chat_history(user_id, limit=20)
        messages = [{"role": "system", "content": system_prompt}]
        messages += [{"role": h["role"], "content": h["content"]} for h in history]

        full_reply = ""
        try:
            completion = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0.8,
                max_completion_tokens=2048,
                top_p=1,
                reasoning_effort="medium",
                stream=True,
                stop=None,
            )
            for chunk in completion:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_reply += delta
                    yield delta
        except Exception as e:
            err_msg = f"Sorry, I couldn't reach the assistant right now ({e})."
            full_reply = err_msg
            yield err_msg
        finally:
            citations = rag_data.get("citations") or []
            if citations:
                cit_marker = "\n\n__CITATIONS__:" + json.dumps(citations)
                full_reply += cit_marker
                yield cit_marker
            if full_reply:
                db.save_chat_message(user_id, "assistant", full_reply)

    return Response(stream_with_context(generate()), mimetype="text/plain")


# ---------- Knowledge Graph & RAG APIs ----------

@app.route("/api/graph/data")
@login_required
def api_graph_data():
    """Returns the full knowledge graph elements and summary stats."""
    return jsonify(kg.to_cytoscape_json())


@app.route("/api/graph/node/<node_id>")
@login_required
def api_graph_node(node_id):
    """Returns neighborhood and full clinical details for a selected node."""
    details = kg.get_node_details(node_id)
    if not details:
        return jsonify({"error": "Node not found"}), 404
    return jsonify(details)


@app.route("/api/rag/search")
@login_required
def api_rag_search():
    """Standalone semantic search into the clinical literature vector database."""
    query = request.args.get("q", "").strip()
    sensor = request.args.get("sensor")
    limit = int(request.args.get("limit", 4))
    if not query:
        return jsonify({"results": []})
    results = rag_service.search(query, limit=limit, biomarker_filter=sensor)
    return jsonify({"results": results})



@app.route("/api/model-info")
@login_required
def api_model_info():
    return jsonify(metadata)


@app.route("/api/model-metrics")
@login_required
def api_model_metrics():
    # re-read from disk each time so a fresh `python models/train_model.py` run
    # shows up immediately without restarting the Flask server
    fresh_meta = json.loads((ROOT / "models" / "metadata.json").read_text())
    ext = ROOT / "models" / "external_validation.json"
    fresh_meta["external_validation"] = json.loads(ext.read_text()) if ext.exists() else None
    return jsonify(fresh_meta)


@app.route("/model-outputs/<path:filename>")
@login_required
def model_output_file(filename):
    return send_from_directory(ROOT / "model_outputs", filename)


@app.route("/api/wound-context", methods=["POST"])
@login_required
def api_save_wound_context():
    data = request.get_json(force=True)
    db.save_wound_context(
        session["user_id"],
        cause=(data.get("cause") or "").strip(),
        severity=(data.get("severity") or "").strip(),
        pain_level=int(data.get("pain_level") or 0),
        itching_level=int(data.get("itching_level") or 0),
        days_since_onset=int(data.get("days_since_onset") or 0),
        notes=(data.get("notes") or "").strip(),
    )
    return jsonify({"ok": True})


if __name__ == "__main__":
    # 0.0.0.0 so an ESP32 on the same Wi-Fi can reach the server; set HOST=127.0.0.1 to
    # keep it local. Debug mode is opt-in (FLASK_DEBUG=1) because the server is on the LAN.
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )