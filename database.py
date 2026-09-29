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
            ph REAL, temperature REAL, humidity REAL,
            exudate_level REAL, oxygen_saturation REAL,
            condition TEXT, confidence REAL, healing_days REAL,
            created_at TEXT NOT NULL,
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
    conn.commit()
    conn.close()


def save_reading(user_id, features, condition, confidence, healing_days):
    conn = get_db()
    conn.execute(
        """INSERT INTO readings
           (user_id, ph, temperature, humidity, exudate_level, oxygen_saturation,
            condition, confidence, healing_days, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id, features["pH"], features["temperature"], features["humidity"],
            features["exudate_level"], features["oxygen_saturation"],
            condition, confidence, healing_days, datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_latest_reading(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM readings WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_reading_history(user_id, limit=8):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM readings WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_reading_count(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM readings WHERE user_id = ?", (user_id,)
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