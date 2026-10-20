import secrets
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent / "wound_bandage.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            temperature REAL, humidity REAL,
            heart_rate REAL, systolic_bp REAL, diastolic_bp REAL,
            source TEXT DEFAULT 'simulated',
            condition TEXT, confidence REAL, healing_days REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            last_seen TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS wound_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            cause TEXT,
            severity TEXT,
            pain_level INTEGER,
            itching_level INTEGER,
            days_since_onset INTEGER,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )
    # Databases created before the sensor change (pH / exudate / SpO2) lack these columns.
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(readings)")}
    for col, decl in [("heart_rate", "REAL"), ("systolic_bp", "REAL"), ("diastolic_bp", "REAL"),
                      ("source", "TEXT DEFAULT 'simulated'")]:
        if col not in existing:
            conn.execute(f"ALTER TABLE readings ADD COLUMN {col} {decl}")
    conn.commit()
    conn.close()


def save_reading(user_id, features, condition, confidence, healing_days, source="simulated"):
    conn = get_db()
    conn.execute(
        """INSERT INTO readings
           (user_id, temperature, humidity, heart_rate, systolic_bp, diastolic_bp,
            source, condition, confidence, healing_days, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id, features["temperature"], features["humidity"], features["heart_rate"],
            features["systolic_bp"], features["diastolic_bp"], source,
            condition, confidence, healing_days, datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


# Readings saved before the sensor change have no heart_rate / BP; skip them everywhere.
_CURRENT = "heart_rate IS NOT NULL"


def get_latest_reading(user_id):
    conn = get_db()
    row = conn.execute(
        f"SELECT * FROM readings WHERE user_id = ? AND {_CURRENT} ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_reading_history(user_id, limit=8):
    conn = get_db()
    rows = conn.execute(
        f"SELECT * FROM readings WHERE user_id = ? AND {_CURRENT} ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_reading_count(user_id):
    conn = get_db()
    row = conn.execute(
        f"SELECT COUNT(*) as c FROM readings WHERE user_id = ? AND {_CURRENT}", (user_id,)
    ).fetchone()
    conn.close()
    return row["c"] if row else 0


def save_chat_message(user_id, role, content):
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (user_id, role, content, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_chat_history(user_id, limit=30):
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY id ASC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_wound_context(user_id, cause, severity, pain_level, itching_level, days_since_onset, notes):
    conn = get_db()
    conn.execute(
        """INSERT INTO wound_context
           (user_id, cause, severity, pain_level, itching_level, days_since_onset, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, cause, severity, pain_level, itching_level, days_since_onset, notes,
         datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_latest_wound_context(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM wound_context WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_wound_context_history(user_id, limit=6):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM wound_context WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- ESP32 device pairing ----------

def get_or_create_device(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM devices WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        conn.execute(
            "INSERT INTO devices (user_id, token, created_at) VALUES (?, ?, ?)",
            (user_id, secrets.token_urlsafe(18), datetime.utcnow().isoformat()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM devices WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row)


def regenerate_device_token(user_id):
    get_or_create_device(user_id)
    conn = get_db()
    conn.execute(
        "UPDATE devices SET token = ?, last_seen = NULL WHERE user_id = ?",
        (secrets.token_urlsafe(18), user_id),
    )
    conn.commit()
    conn.close()
    return get_or_create_device(user_id)


def get_device_by_token(token):
    conn = get_db()
    row = conn.execute("SELECT * FROM devices WHERE token = ?", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


def touch_device(device_id):
    conn = get_db()
    conn.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (datetime.utcnow().isoformat(), device_id))
    conn.commit()
    conn.close()
