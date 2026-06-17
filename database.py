import psycopg2
from psycopg2.extras import RealDictCursor
import os

DB_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DB_URL)

def execute_query(query, params=()):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(query, params)
    conn.commit()
    conn.close()

def fetch_one(query, params=()):
    conn = get_conn()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        res = cur.fetchone()
    conn.close()
    return res

def fetch_all(query, params=()):
    conn = get_conn()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        res = cur.fetchall()
    conn.close()
    return res

# ── API cho bot ──────────────────────────────────────────────

def create_order(order_code, user_id, username, product_name, amount, ticket_channel):
    execute_query("""INSERT INTO orders (order_code, user_id, username, product_name, amount, ticket_channel)
                     VALUES (%s, %s, %s, %s, %s, %s)""", 
                  (order_code, user_id, username, product_name, amount, ticket_channel))

def get_order(order_code):
    return fetch_one("SELECT * FROM orders WHERE order_code = %s", (order_code,))

def update_order_status(order_code, status):
    if status == "paid":
        execute_query("UPDATE orders SET status=%s, paid_at=NOW() WHERE order_code=%s", (status, order_code))
    else:
        execute_query("UPDATE orders SET status=%s WHERE order_code=%s", (status, order_code))

def get_order_by_channel(channel_id):
    return fetch_one("SELECT * FROM orders WHERE ticket_channel=%s AND status NOT IN ('done', 'cancelled')", (channel_id,))

def open_ticket(channel_id, user_id, order_code=None):
    execute_query("INSERT INTO tickets (channel_id, user_id, order_code) VALUES (%s, %s, %s) ON CONFLICT (channel_id) DO UPDATE SET user_id=%s, order_code=%s", 
                  (channel_id, user_id, order_code, user_id, order_code))

def close_ticket(channel_id):
    execute_query("DELETE FROM tickets WHERE channel_id=%s", (channel_id,))

def count_open_tickets(user_id):
    res = fetch_one("SELECT COUNT(*) as count FROM tickets WHERE user_id=%s", (user_id,))
    return res['count'] if res else 0

def save_feedback(order_code, user_id, username, stars, content):
    execute_query("INSERT INTO feedbacks (order_code, user_id, username, stars, content) VALUES (%s, %s, %s, %s, %s)",
                  (order_code, user_id, username, stars, content))

def init_db():
    print("[DB] Đang kết nối Supabase...")