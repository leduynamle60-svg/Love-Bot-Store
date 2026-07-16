"""
database.py — PostgreSQL/Supabase cho Love Bot Store
"""

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    conn = psycopg2.connect(
        DATABASE_URL,
        connect_timeout=5,
        options="-c statement_timeout=5000",
    )
    conn.autocommit = False
    return conn


def get_conn_dict():
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=5,
        options="-c statement_timeout=5000",
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id                    SERIAL PRIMARY KEY,
            order_code            TEXT UNIQUE NOT NULL,
            user_id               BIGINT NOT NULL,
            username              TEXT NOT NULL,
            product_name          TEXT NOT NULL,
            amount                INTEGER NOT NULL DEFAULT 0,
            status                TEXT DEFAULT 'pending',
            ticket_channel        BIGINT,
            ticket_number         TEXT,
            support_discord_id    TEXT,
            support_name          TEXT,
            processor_discord_id  TEXT,
            processor_name        TEXT,
            created_at            TIMESTAMP DEFAULT NOW(),
            paid_at               TIMESTAMP
        )
    """)

    # Migration an toàn cho database cũ.
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS ticket_number TEXT")
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS support_discord_id TEXT")
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS support_name TEXT")
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS processor_discord_id TEXT")
    cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS processor_name TEXT")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedbacks (
            id          SERIAL PRIMARY KEY,
            order_code  TEXT NOT NULL,
            user_id     BIGINT NOT NULL,
            username    TEXT NOT NULL,
            stars       INTEGER NOT NULL,
            content     TEXT,
            message_url TEXT,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("ALTER TABLE feedbacks ADD COLUMN IF NOT EXISTS message_url TEXT")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            channel_id  BIGINT PRIMARY KEY,
            user_id     BIGINT NOT NULL,
            order_code  TEXT,
            opened_at   TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          SERIAL PRIMARY KEY,
            category    TEXT NOT NULL,
            name        TEXT NOT NULL,
            price       INTEGER NOT NULL,
            type        TEXT DEFAULT 'log',
            note        TEXT,
            sort_order  INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id         SERIAL PRIMARY KEY,
            action     TEXT NOT NULL,
            detail     TEXT,
            "user"     TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS salary (
            id            SERIAL PRIMARY KEY,
            web_user_id   INTEGER NOT NULL,
            order_code    TEXT NOT NULL,
            amount        INTEGER DEFAULT 0,
            note          TEXT,
            role_in_order TEXT DEFAULT 'support',
            created_at    TIMESTAMP DEFAULT NOW(),
            UNIQUE(web_user_id, order_code, role_in_order)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS discount_codes (
            id          SERIAL PRIMARY KEY,
            code        TEXT UNIQUE NOT NULL,
            amount      INTEGER NOT NULL,
            used        INTEGER DEFAULT 0,
            expires_at  TEXT,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS order_support (
            order_code          TEXT PRIMARY KEY,
            support_discord_id  TEXT NOT NULL
        )
    """)


    cur.execute("""
        CREATE TABLE IF NOT EXISTS bank_accounts (
            discord_id     TEXT PRIMARY KEY,
            bank_name      TEXT NOT NULL,
            bank_bin       TEXT,
            account_number TEXT NOT NULL,
            account_name   TEXT NOT NULL,
            updated_at     TIMESTAMP DEFAULT NOW()
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Supabase PostgreSQL sẵn sàng ✅")


# ── Orders ───────────────────────────────────────────────────

def create_order(order_code, user_id, username, product_name, amount, ticket_channel):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO orders
            (order_code, user_id, username, product_name, amount, ticket_channel)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (order_code, user_id, username, product_name, amount, ticket_channel),
    )
    conn.commit()
    conn.close()


def get_order(order_code):
    conn = get_conn_dict()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE order_code=%s", (order_code,))
    row = cur.fetchone()
    conn.close()
    return row


def get_order_by_channel(channel_id):
    conn = get_conn_dict()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM orders
        WHERE ticket_channel=%s
          AND status NOT IN ('done', 'cancelled')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (channel_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def get_order_by_channel_any(channel_id):
    conn = get_conn_dict()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM orders
        WHERE ticket_channel=%s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (channel_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def update_order_status(order_code, status):
    conn = get_conn()
    cur = conn.cursor()

    if status == "paid":
        cur.execute(
            "UPDATE orders SET status=%s, paid_at=NOW() WHERE order_code=%s",
            (status, order_code),
        )
    else:
        cur.execute(
            "UPDATE orders SET status=%s WHERE order_code=%s",
            (status, order_code),
        )

    conn.commit()
    conn.close()


def assign_order_support(
    order_code,
    support_discord_id,
    support_name,
    ticket_number=None,
):
    """Lưu người dùng !order là người nhận đơn."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE orders
        SET support_discord_id=%s,
            support_name=%s,
            ticket_number=COALESCE(%s, ticket_number)
        WHERE order_code=%s
        """,
        (
            str(support_discord_id),
            support_name,
            ticket_number,
            order_code,
        ),
    )
    conn.commit()
    conn.close()


def assign_order_processor(order_code, processor_discord_id, processor_name):
    """Lưu người dùng !done là người xử lý đơn."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE orders
        SET processor_discord_id=%s,
            processor_name=%s
        WHERE order_code=%s
        """,
        (
            str(processor_discord_id),
            processor_name,
            order_code,
        ),
    )
    conn.commit()
    conn.close()


def order_exists(order_code):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM orders WHERE order_code=%s", (order_code,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists


def create_manual_order(
    order_code,
    user_id,
    username,
    product_name,
    amount,
    status="pending",
    ticket_number=None,
    support_name="",
    processor_name="",
):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO orders (
            order_code, user_id, username, product_name, amount, status,
            ticket_channel, ticket_number, support_name, processor_name
        )
        VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s)
        """,
        (
            order_code,
            user_id,
            username,
            product_name,
            amount,
            status,
            ticket_number,
            support_name,
            processor_name,
        ),
    )
    conn.commit()
    conn.close()


def update_order_full(
    old_order_code,
    new_order_code,
    user_id,
    username,
    product_name,
    amount,
    status,
    ticket_number,
    support_name,
    processor_name,
):
    conn = get_conn()
    cur = conn.cursor()

    try:
        if old_order_code != new_order_code:
            cur.execute(
                "SELECT 1 FROM orders WHERE order_code=%s",
                (new_order_code,),
            )
            if cur.fetchone():
                raise ValueError("Mã đơn mới đã tồn tại")

        cur.execute(
            """
            UPDATE orders
            SET order_code=%s,
                user_id=%s,
                username=%s,
                product_name=%s,
                amount=%s,
                status=%s,
                ticket_number=%s,
                support_name=%s,
                processor_name=%s
            WHERE order_code=%s
            """,
            (
                new_order_code,
                user_id,
                username,
                product_name,
                amount,
                status,
                ticket_number,
                support_name,
                processor_name,
                old_order_code,
            ),
        )

        if old_order_code != new_order_code:
            cur.execute(
                "UPDATE feedbacks SET order_code=%s WHERE order_code=%s",
                (new_order_code, old_order_code),
            )
            cur.execute(
                "UPDATE salary SET order_code=%s WHERE order_code=%s",
                (new_order_code, old_order_code),
            )
            cur.execute(
                "UPDATE order_support SET order_code=%s WHERE order_code=%s",
                (new_order_code, old_order_code),
            )
            cur.execute(
                "UPDATE tickets SET order_code=%s WHERE order_code=%s",
                (new_order_code, old_order_code),
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



def get_done_context(channel_id):
    """Lấy order, ticket và support trong một kết nối duy nhất."""
    conn = get_conn_dict()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM orders
            WHERE ticket_channel=%s
              AND status NOT IN ('done', 'cancelled')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (channel_id,),
        )
        order_info = cur.fetchone()

        cur.execute(
            "SELECT * FROM tickets WHERE channel_id=%s",
            (channel_id,),
        )
        ticket_row = cur.fetchone()

        support_row = None
        order_code = None
        if order_info:
            order_code = order_info["order_code"]
        elif ticket_row:
            order_code = ticket_row["order_code"]

        if order_code:
            cur.execute(
                """
                SELECT support_discord_id
                FROM order_support
                WHERE order_code=%s
                """,
                (order_code,),
            )
            support_row = cur.fetchone()

        return order_info, ticket_row, support_row
    finally:
        conn.close()


def finish_order(order_code, processor_discord_id, processor_name):
    """Gộp cập nhật processor và status done trong một query."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE orders
            SET processor_discord_id=%s,
                processor_name=%s,
                status='done'
            WHERE order_code=%s
            """,
            (
                str(processor_discord_id),
                processor_name,
                order_code,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Tickets ──────────────────────────────────────────────────

def open_ticket(channel_id, user_id, order_code=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tickets (channel_id, user_id, order_code)
        VALUES (%s, %s, %s)
        ON CONFLICT (channel_id)
        DO UPDATE SET user_id=EXCLUDED.user_id, order_code=EXCLUDED.order_code
        """,
        (channel_id, user_id, order_code),
    )
    conn.commit()
    conn.close()


def close_ticket(channel_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM tickets WHERE channel_id=%s", (channel_id,))
    conn.commit()
    conn.close()


def count_open_tickets(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tickets WHERE user_id=%s", (user_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_ticket_by_channel(channel_id):
    conn = get_conn_dict()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tickets WHERE channel_id=%s", (channel_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_all_open_tickets():
    conn = get_conn_dict()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            t.channel_id,
            t.user_id,
            t.order_code,
            t.opened_at,
            o.product_name,
            o.status,
            o.ticket_number
        FROM tickets t
        LEFT JOIN orders o ON o.order_code=t.order_code
        ORDER BY t.opened_at DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return list(rows)


def clear_tickets_by_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM tickets WHERE user_id=%s", (user_id,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted


# ── Feedbacks ────────────────────────────────────────────────

def save_feedback(order_code, user_id, username, stars, content):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO feedbacks (order_code, user_id, username, stars, content)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (order_code, user_id, username, stars, content),
    )
    conn.commit()
    conn.close()


def get_feedback_by_order(order_code):
    conn = get_conn_dict()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM feedbacks
        WHERE order_code=%s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (order_code,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def upsert_manual_feedback(order_code, user_id, username, stars, content):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id
        FROM feedbacks
        WHERE order_code=%s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (order_code,),
    )
    row = cur.fetchone()

    if row:
        cur.execute(
            """
            UPDATE feedbacks
            SET user_id=%s, username=%s, stars=%s, content=%s
            WHERE id=%s
            """,
            (user_id, username, stars, content, row[0]),
        )
    else:
        cur.execute(
            """
            INSERT INTO feedbacks (order_code, user_id, username, stars, content)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (order_code, user_id, username, stars, content),
        )

    conn.commit()
    conn.close()


# ── Discount Codes ───────────────────────────────────────────

def create_discount(code, amount, expires_at=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO discount_codes (code, amount, expires_at)
        VALUES (%s,%s,%s)
        """,
        (code.upper(), amount, expires_at),
    )
    conn.commit()
    conn.close()


def get_discount(code):
    conn = get_conn_dict()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM discount_codes
        WHERE code=%s AND used=0
        """,
        (code.upper(),),
    )
    row = cur.fetchone()
    conn.close()
    return row


def use_discount(code):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE discount_codes SET used=1 WHERE code=%s",
        (code.upper(),),
    )
    conn.commit()
    conn.close()


def get_all_discounts():
    conn = get_conn_dict()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM discount_codes ORDER BY created_at DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return list(rows)


def delete_discount(code):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM discount_codes WHERE code=%s",
        (code.upper(),),
    )
    conn.commit()
    conn.close()


# ── Bank Accounts ────────────────────────────────────────────

def upsert_bank_account(
    discord_id,
    bank_name,
    account_number,
    account_name,
    bank_bin=None,
):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO bank_accounts (
            discord_id,
            bank_name,
            bank_bin,
            account_number,
            account_name,
            updated_at
        )
        VALUES (%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (discord_id)
        DO UPDATE SET
            bank_name=EXCLUDED.bank_name,
            bank_bin=EXCLUDED.bank_bin,
            account_number=EXCLUDED.account_number,
            account_name=EXCLUDED.account_name,
            updated_at=NOW()
        """,
        (
            str(discord_id),
            bank_name,
            bank_bin or None,
            account_number,
            account_name,
        ),
    )
    conn.commit()
    conn.close()


def get_bank_account(discord_id):
    print("1. Bắt đầu get_bank_account")

    conn = get_conn_dict()
    print("2. Đã kết nối DB")

    cur = conn.cursor()
    print("3. Đã tạo cursor")

    cur.execute(
        "SELECT * FROM bank_accounts WHERE discord_id=%s",
        (str(discord_id),),
    )
    print("4. Đã execute")

    row = cur.fetchone()
    print("5. Đã fetch")

    conn.close()
    print("6. Đóng kết nối")

    return row


def delete_bank_account(discord_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM bank_accounts WHERE discord_id=%s",
        (str(discord_id),),
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted
