"""
web_db.py — Database web dashboard dùng SQLite
"""

import sqlite3
import hashlib
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "store.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_web_db():
    conn = get_conn()
    c    = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS web_users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT    UNIQUE NOT NULL,
            password     TEXT    NOT NULL,
            display_name TEXT    NOT NULL,
            role         TEXT    NOT NULL DEFAULT 'support',
            discord_id   TEXT,
            created_at   TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            action     TEXT    NOT NULL,
            detail     TEXT,
            user       TEXT,
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS salary (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            web_user_id  INTEGER NOT NULL,
            order_code   TEXT    NOT NULL UNIQUE,
            amount       INTEGER DEFAULT 0,
            note         TEXT,
            created_at   TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    exists = c.execute("SELECT 1 FROM web_users WHERE role='founder'").fetchone()
    if not exists:
        c.execute(
            "INSERT INTO web_users (username, password, display_name, role) VALUES (?,?,?,?)",
            ("founder", _hash("admin123"), "Founder", "founder")
        )
        print("[Web] ✅ Tài khoản Founder mặc định: founder / admin123 — ĐỔI NGAY!")

    conn.commit()
    conn.close()


# ── Users ─────────────────────────────────────────────────────

def verify_user(username, password):
    conn = get_conn()
    row  = conn.execute(
        "SELECT * FROM web_users WHERE username=? AND password=?",
        (username, _hash(password))
    ).fetchone()
    conn.close()
    return row


def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM web_users ORDER BY role, username").fetchall()
    conn.close()
    return list(rows)


def get_user_by_username(username):
    conn = get_conn()
    row  = conn.execute("SELECT * FROM web_users WHERE username=?", (username,)).fetchone()
    conn.close()
    return row


def create_user(username, password, display_name, role, discord_id=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO web_users (username, password, display_name, role, discord_id) VALUES (?,?,?,?,?)",
        (username, _hash(password), display_name, role, discord_id)
    )
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = get_conn()
    conn.execute("DELETE FROM web_users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


def reset_password(user_id, new_password):
    conn = get_conn()
    conn.execute("UPDATE web_users SET password=? WHERE id=?", (_hash(new_password), user_id))
    conn.commit()
    conn.close()


# ── Salary ────────────────────────────────────────────────────

def get_all_salary():
    conn = get_conn()
    rows = conn.execute("""
        SELECT w.display_name, w.username, w.role,
               COUNT(s.id) as total_orders,
               SUM(s.amount) as total_salary
        FROM web_users w
        LEFT JOIN salary s ON w.id = s.web_user_id
        WHERE w.role IN ('support', 'admin')
        GROUP BY w.id
        ORDER BY total_orders DESC
    """).fetchall()
    conn.close()
    return list(rows)


def get_salary_by_support(web_user_id):
    conn = get_conn()
    row  = conn.execute("""
        SELECT w.display_name, w.username,
               COUNT(s.id) as total_orders,
               SUM(s.amount) as total_salary
        FROM web_users w
        LEFT JOIN salary s ON w.id = s.web_user_id
        WHERE w.id=?
        GROUP BY w.id
    """, (web_user_id,)).fetchone()
    conn.close()
    return row


def get_orders_by_support(web_user_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT o.*, s.amount as commission
        FROM orders o
        JOIN salary s ON o.order_code = s.order_code
        WHERE s.web_user_id = ?
        ORDER BY o.created_at DESC
    """, (web_user_id,)).fetchall()
    conn.close()
    return list(rows)


def add_salary_record(web_user_id, order_code, amount=0, note=""):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO salary (web_user_id, order_code, amount, note) VALUES (?,?,?,?)",
        (web_user_id, order_code, amount, note)
    )
    conn.commit()
    conn.close()


def add_log(action, detail="", user="System"):
    conn = get_conn()
    conn.execute(
        "INSERT INTO logs (action, detail, user) VALUES (?,?,?)",
        (action, detail, user)
    )
    conn.commit()
    conn.close()