"""
web_db.py — Database web dashboard dùng PostgreSQL (Supabase)
"""

import psycopg2
import psycopg2.extras
import hashlib
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_web_db():
    conn = psycopg2.connect(DATABASE_URL)
    c    = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS web_users (
            id           SERIAL PRIMARY KEY,
            username     TEXT    UNIQUE NOT NULL,
            password     TEXT    NOT NULL,
            display_name TEXT    NOT NULL,
            role         TEXT    NOT NULL DEFAULT 'support',
            discord_id   TEXT,
            created_at   TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id         SERIAL PRIMARY KEY,
            action     TEXT    NOT NULL,
            detail     TEXT,
            "user"     TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("SELECT 1 FROM web_users WHERE role='founder'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO web_users (username, password, display_name, role) VALUES (%s,%s,%s,%s)",
            ("founder", _hash("admin123"), "Founder", "founder")
        )
        print("[Web] ✅ Tài khoản Founder mặc định: founder / admin123 — ĐỔI NGAY!")

    conn.commit()
    conn.close()


# ── Users ─────────────────────────────────────────────────────

def verify_user(username, password):
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        "SELECT * FROM web_users WHERE username=%s AND password=%s",
        (username, _hash(password))
    )
    row  = c.fetchone()
    conn.close()
    return row


def get_all_users():
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT * FROM web_users ORDER BY role, username")
    rows = c.fetchall()
    conn.close()
    return list(rows)


def get_user_by_username(username):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT * FROM web_users WHERE username=%s", (username,))
    row  = c.fetchone()
    conn.close()
    return row


def create_user(username, password, display_name, role, discord_id=""):
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        "INSERT INTO web_users (username, password, display_name, role, discord_id) VALUES (%s,%s,%s,%s,%s)",
        (username, _hash(password), display_name, role, discord_id)
    )
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("DELETE FROM web_users WHERE id=%s", (user_id,))
    conn.commit()
    conn.close()


def reset_password(user_id, new_password):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("UPDATE web_users SET password=%s WHERE id=%s", (_hash(new_password), user_id))
    conn.commit()
    conn.close()


# ── Salary ────────────────────────────────────────────────────

def get_all_salary():
    conn = get_conn()
    c    = conn.cursor()
    c.execute("""
        SELECT w.display_name, w.username, w.role,
               s.role_in_order,
               COUNT(s.id) as total_orders,
               SUM(s.amount) as total_salary
        FROM web_users w
        LEFT JOIN salary s ON w.id = s.web_user_id
        WHERE w.role IN ('support', 'admin', 'founder')
        GROUP BY w.id, w.display_name, w.username, w.role, s.role_in_order
        ORDER BY total_orders DESC NULLS LAST
    """)
    rows = c.fetchall()
    conn.close()
    return list(rows)


def get_salary_by_support(web_user_id):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("""
        SELECT w.display_name, w.username,
               s.role_in_order,
               COUNT(s.id) as total_orders,
               SUM(s.amount) as total_salary
        FROM web_users w
        LEFT JOIN salary s ON w.id = s.web_user_id
        WHERE w.id=%s
        GROUP BY w.id, w.display_name, w.username, s.role_in_order
    """, (web_user_id,))
    rows = c.fetchall()
    conn.close()
    return list(rows)


def get_orders_by_support(web_user_id):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("""
        SELECT o.*, s.amount as commission, s.role_in_order
        FROM orders o
        JOIN salary s ON o.order_code = s.order_code
        WHERE s.web_user_id = %s
        ORDER BY o.created_at DESC
    """, (web_user_id,))
    rows = c.fetchall()
    conn.close()
    return list(rows)


def add_salary_record(web_user_id, order_code, amount=0, note="", role_in_order="support"):
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        """INSERT INTO salary (web_user_id, order_code, amount, note, role_in_order)
           VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (web_user_id, order_code, role_in_order) DO NOTHING""",
        (web_user_id, order_code, amount, note, role_in_order)
    )
    conn.commit()
    conn.close()


def add_log(action, detail="", user="System"):
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        'INSERT INTO logs (action, detail, "user") VALUES (%s,%s,%s)',
        (action, detail, user)
    )
    conn.commit()
    conn.close()