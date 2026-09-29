import os
import json
from pathlib import Path

import joblib
import numpy as np
from groq import Groq
from flask import (
    Flask, request, jsonify, session, redirect, url_for, render_template,
    Response, stream_with_context,
)
from werkzeug.security import generate_password_hash, check_password_hash

import database as db

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

FEATURES = ["pH", "temperature", "humidity", "exudate_level", "oxygen_saturation"]
SLIDER_RANGES = {
    "pH": {"min": 4.0, "max": 10.0, "step": 0.05, "default": 7.2},
    "temperature": {"min": 25.0, "max": 40.0, "step": 0.1, "default": 31.5},
    "humidity": {"min": 10.0, "max": 100.0, "step": 1, "default": 47},
    "exudate_level": {"min": 0.0, "max": 10.0, "step": 0.1, "default": 2},
    "oxygen_saturation": {"min": 30.0, "max": 100.0, "step": 1, "default": 88},
}

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


@app.route("/dashboard")
@login_required
def dashboard_page():
    return render_template(
        "dashboard.html",
        user_name=session.get("user_name"),
        slider_ranges=SLIDER_RANGES,
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
    return jsonify({"ok": True, "redirect": url_for("dashboard_page")})


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
    return jsonify({"ok": True, "redirect": url_for("dashboard_page")})


# ---------- prediction API ----------

@app.route("/api/predict", methods=["POST"])
@login_required
def api_predict():
    data = request.get_json(force=True)
    try:
        features = {f: float(data[f]) for f in FEATURES}
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Missing or invalid sensor values."}), 400

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

    db.save_reading(session["user_id"], features, condition, confidence, healing_days)

    return jsonify(
        {
            "condition": condition,
            "confidence": round(confidence, 3),
            "class_probs": class_probs,
            "healing_days": round(healing_days, 1),
            "features": features,
            "reading_count": db.get_reading_count(session["user_id"]),
        }
    )


@app.route("/api/readings-history")
@login_required
def api_readings_history():
    rows = db.get_reading_history(session["user_id"], limit=8)
    return jsonify({"readings": rows})


# ---------- chat API ----------

SYSTEM_PROMPT_TEMPLATE = """You are a calm, clear wound-care assistant embedded in a smart-bandage \
monitoring app. You are speaking directly to the patient, not a clinician.

Current sensor reading for this patient:
- pH: {pH}
- Temperature: {temperature} C
- Humidity: {humidity}%
- Exudate level: {exudate_level} / 10
- Oxygen saturation: {oxygen_saturation}%

Model's current assessment:
- Predicted wound condition: {condition} (confidence {confidence})
- Estimated days remaining to heal: {healing_days}
- Trend vs the previous reading: {trend}

What the patient has told us about the wound itself:
- How it happened: {cause}
- Self-rated severity: {severity}
- Pain level (0-10): {pain_level}
- Itching level (0-10): {itching_level}
- Days since the wound occurred: {days_since_onset}
- Additional notes from patient: {notes}

Guidelines:
- Ground your answers in the sensor context above when relevant.
- Be honest that this is a prototype demo (synthetic training data, no real medical literature \
retrieval yet -- a RAG layer citing real clinical guidelines is planned next).
- Never give a definitive diagnosis. Encourage seeing a clinician for anything concerning, \
especially if the condition looks like "infected".
- Keep answers short, warm, and easy to read on a phone.
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

    context = {
        "pH": round(latest["ph"], 2) if latest else "unknown",
        "temperature": round(latest["temperature"], 1) if latest else "unknown",
        "humidity": round(latest["humidity"], 1) if latest else "unknown",
        "exudate_level": round(latest["exudate_level"], 1) if latest else "unknown",
        "oxygen_saturation": round(latest["oxygen_saturation"], 1) if latest else "unknown",
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
                temperature=1,
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
            if full_reply:
                db.save_chat_message(user_id, "assistant", full_reply)

    return Response(stream_with_context(generate()), mimetype="text/plain")



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
    return jsonify(fresh_meta)


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
    app.run(debug=True, port=5000)