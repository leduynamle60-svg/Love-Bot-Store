"""
database.py — Khởi tạo và quản lý SQLite cho Love Bot Store
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "store.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_conn_dict():
    """Alias của get_conn — dùng cho web app"""
    return get_conn()


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code      TEXT    UNIQUE NOT NULL,
            user_id         INTEGER NOT NULL,
            username        TEXT    NOT NULL,
            product_name    TEXT    NOT NULL,
            amount          INTEGER NOT NULL,
            status          TEXT    DEFAULT 'pending',
            ticket_channel  INTEGER,
            created_at      TEXT    DEFAULT (datetime('now','localtime')),
            paid_at         TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS feedbacks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code  TEXT    NOT NULL,
            user_id     INTEGER NOT NULL,
            username    TEXT    NOT NULL,
            stars       INTEGER NOT NULL,
            content     TEXT,
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            channel_id  INTEGER PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            order_code  TEXT,
            opened_at   TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category    TEXT    NOT NULL,
            name        TEXT    NOT NULL,
            price       INTEGER NOT NULL,
            type        TEXT    DEFAULT 'log',
            note        TEXT,
            sort_order  INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
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

    conn.commit()
    conn.close()
    print("[DB] Database SQLite sẵn sàng ✅")


# ── Orders ───────────────────────────────────────────────────

def create_order(order_code, user_id, username, product_name, amount, ticket_channel):
    conn = get_conn()
    conn.execute(
        """INSERT INTO orders (order_code, user_id, username, product_name, amount, ticket_channel)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (order_code, user_id, username, product_name, amount, ticket_channel)
    )
    conn.commit()
    conn.close()


def get_order(order_code):
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE order_code = ?", (order_code,)).fetchone()
    conn.close()
    return row


def update_order_status(order_code, status):
    conn = get_conn()
    if status == "paid":
        conn.execute(
            "UPDATE orders SET status=?, paid_at=datetime('now','localtime') WHERE order_code=?",
            (status, order_code)
        )
    else:
        conn.execute("UPDATE orders SET status=? WHERE order_code=?", (status, order_code))
    conn.commit()
    conn.close()


def get_order_by_channel(channel_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM orders WHERE ticket_channel=? AND status NOT IN ('done', 'cancelled')",
        (channel_id,)
    ).fetchone()
    conn.close()
    return row


# ── Tickets ──────────────────────────────────────────────────

def open_ticket(channel_id, user_id, order_code=None):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO tickets (channel_id, user_id, order_code) VALUES (?, ?, ?)",
        (channel_id, user_id, order_code)
    )
    conn.commit()
    conn.close()


def close_ticket(channel_id):
    conn = get_conn()
    conn.execute("DELETE FROM tickets WHERE channel_id=?", (channel_id,))
    conn.commit()
    conn.close()


def count_open_tickets(user_id):
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    conn.close()
    return count


def get_ticket_by_channel(channel_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tickets WHERE channel_id=?", (channel_id,)).fetchone()
    conn.close()
    return row


# ── Feedbacks ────────────────────────────────────────────────

def save_feedback(order_code, user_id, username, stars, content):
    conn = get_conn()
    conn.execute(
        "INSERT INTO feedbacks (order_code, user_id, username, stars, content) VALUES (?,?,?,?,?)",
        (order_code, user_id, username, stars, content)
    )
    conn.commit()
    conn.close()