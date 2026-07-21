"""
web/app.py — Flask Web Dashboard cho Love Bot Store
"""

from flask import Flask, render_template, redirect, url_for, request, session, flash
from functools import wraps
from datetime import datetime
import random, string
import json
import urllib.request
import urllib.error
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database as db
import web_db as wdb

app = Flask(__name__)
import config
app.secret_key = config.WEB_SECRET_KEY


# ── Decorators ───────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") not in roles:
                flash("❌ Bạn không có quyền truy cập trang này!", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Auth ─────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user     = wdb.verify_user(username, password)

        if user:
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            session["role"]     = user["role"]
            session["display"]  = user["display_name"]
            return redirect(url_for("dashboard"))
        else:
            flash("❌ Sai tên đăng nhập hoặc mật khẩu!", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    if session["role"] == "support":
        return redirect(url_for("my_orders"))

    conn = db.get_conn_dict()
    c    = conn.cursor()

    def q(sql):
        c.execute(sql)
        row = c.fetchone()
        return list(row.values())[0] if row else 0

    stats = {
        "total":     q("SELECT COUNT(*) FROM orders"),
        "done":      q("SELECT COUNT(*) FROM orders WHERE status='done'"),
        "pending":   q("SELECT COUNT(*) FROM orders WHERE status NOT IN ('done','cancelled')"),
        "cancelled": q("SELECT COUNT(*) FROM orders WHERE status='cancelled'"),
        "revenue":   q("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status IN ('paid','done')"),
        "avg_stars": q("SELECT AVG(stars) FROM feedbacks"),
        "feedbacks": q("SELECT COUNT(*) FROM feedbacks"),
    }

    c.execute("""
        SELECT DATE(created_at) AS date, SUM(amount) AS total
        FROM orders
        WHERE status IN ('paid', 'done')
          AND created_at >= NOW() - INTERVAL '7 days'
        GROUP BY DATE(created_at)
        ORDER BY date
    """)

    revenue_rows = c.fetchall()

    revenue_chart = [
        [
            row["date"].strftime("%d/%m") if row["date"] else "",
            int(row["total"] or 0)
        ]
        for row in revenue_rows
    ]

    c.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 10")
    recent_orders = c.fetchall()

    conn.close()
    return render_template("dashboard.html",
        stats=stats,
        revenue_chart=revenue_chart,
        recent_orders=list(recent_orders)
    )


# ── Helpers V2.1 ─────────────────────────────────────────────

def _generate_order_code():
    while True:
        code = "LS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not db.order_exists(code):
            return code


def _generate_ticket_number():
    return f"{random.randint(0, 9999):04d}"


def _parse_int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default



def _send_order_to_discord(order):
    """Gửi lại đơn vào #order bằng chính tài khoản bot Discord."""
    bot_token = (
        os.getenv("DISCORD_BOT_TOKEN")
        or os.getenv("BOT_TOKEN")
        or getattr(config, "DISCORD_BOT_TOKEN", "")
        or getattr(config, "BOT_TOKEN", "")
    ).strip()

    channel_id = str(
        os.getenv("ORDER_CHANNEL_ID")
        or getattr(config, "ORDER_CHANNEL_ID", "")
    ).strip()

    if not bot_token:
        raise RuntimeError(
            "Chưa cấu hình DISCORD_BOT_TOKEN hoặc BOT_TOKEN"
        )

    if not channel_id:
        raise RuntimeError(
            "Chưa cấu hình ORDER_CHANNEL_ID"
        )

    status_map = {
        "pending": "⏳ Đang chờ",
        "processing": "🔄 Đang xử lý",
        "paid": "💳 Đã thanh toán",
        "done": "✅ Hoàn tất",
        "cancelled": "❌ Đã hủy",
    }

    color_map = {
        "pending": 0xF1C40F,
        "processing": 0x3498DB,
        "paid": 0x9B59B6,
        "done": 0x2ECC71,
        "cancelled": 0xE74C3C,
    }

    user_id = str(order["user_id"] or "").strip()
    customer_value = (
        f"<@{user_id}>"
        if user_id and user_id != "0"
        else (order["username"] or "Unknown")
    )

    ticket_channel = order["ticket_channel"]
    ticket_number = order["ticket_number"]

    if ticket_channel:
        ticket_field_name = "📁 Ticket"
        ticket_value = f"<#{ticket_channel}>"
    else:
        ticket_field_name = "📁 Ticket"
        ticket_value = "*Không xác định*"

    created_at = order["created_at"]
    if created_at:
        try:
            time_text = created_at.strftime("%d/%m/%Y %H:%M")
        except AttributeError:
            time_text = str(created_at)
    else:
        time_text = datetime.now().strftime("%d/%m/%Y %H:%M")

    status = order["status"] or "processing"

    embed = {
        "title": "📦 Đơn Hàng Mới",
        "color": color_map.get(
            status,
            int(getattr(config, "COLOR_INFO", 0x3498DB))
        ),
        "fields": [
            {
                "name": "🧾 Mã đơn",
                "value": f"`{order['order_code']}`",
                "inline": True,
            },
            {
                "name": "👤 Khách hàng",
                "value": customer_value,
                "inline": True,
            },
            {
                "name": "🛍️ Sản phẩm",
                "value": order["product_name"] or "Không rõ",
                "inline": False,
            },
            {
                "name": ticket_field_name,
                "value": ticket_value,
                "inline": True,
            },
            {
                "name": "📌 Trạng thái",
                "value": status_map.get(status, status),
                "inline": True,
            },
            {
                "name": "🕐 Thời gian",
                "value": time_text,
                "inline": True,
            },
        ],
        "footer": {
            "text": config.BOT_FOOTER
        },
    }

    payload = json.dumps(
        {
            "embeds": [embed],
            "allowed_mentions": {
                "parse": []
            },
        }
    ).encode("utf-8")

    api_url = (
        f"https://discord.com/api/v10/channels/"
        f"{channel_id}/messages"
    )

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json",
            "User-Agent": "LoveBotStore-Web/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status not in (200, 201):
                raise RuntimeError(
                    f"Discord API trả mã HTTP {response.status}"
                )
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Discord API lỗi HTTP {error.code}: {detail[:300]}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Không kết nối được Discord API: {error.reason}"
        ) from error




# ── Wallet helpers ───────────────────────────────────────────

def _discord_bot_token():
    return (
        os.getenv("DISCORD_BOT_TOKEN")
        or os.getenv("BOT_TOKEN")
        or getattr(config, "DISCORD_BOT_TOKEN", "")
        or getattr(config, "BOT_TOKEN", "")
    ).strip()


def _send_discord_channel_embed(channel_id, embed):
    """Gửi embed vào một kênh Discord bằng Bot REST API."""
    token = _discord_bot_token()
    if not token:
        raise RuntimeError("Chưa cấu hình DISCORD_BOT_TOKEN hoặc BOT_TOKEN")

    channel_id = int(channel_id or 0)
    if not channel_id:
        raise RuntimeError("Chưa cấu hình WALLET_LOG_CHANNEL_ID")

    payload = json.dumps({
        "embeds": [embed],
        "allowed_mentions": {"parse": []},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        data=payload,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "LoveBotStore-Web/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status in (200, 201)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Không gửi được wallet log: HTTP {error.code} — {detail[:300]}"
        ) from error



def _edit_discord_channel_embed(channel_id, message_id, embed):
    """Sửa embed log ví cũ thay vì gửi tin nhắn mới."""
    token = _discord_bot_token()
    if not token:
        raise RuntimeError("Chưa cấu hình DISCORD_BOT_TOKEN hoặc BOT_TOKEN")

    channel_id = int(channel_id or 0)
    message_id = int(message_id or 0)
    if not channel_id or not message_id:
        raise RuntimeError("Yêu cầu chưa có log_channel_id/log_message_id")

    payload = json.dumps({
        "embeds": [embed],
        "allowed_mentions": {"parse": []},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}",
        data=payload,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "LoveBotStore-Web/1.0",
        },
        method="PATCH",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Không sửa được wallet log: HTTP {error.code} — {detail[:300]}"
        ) from error



def _find_wallet_log_message(channel_id, transaction_code, limit=100):
    """
    Tìm message log ví cũ bằng mã giao dịch trong tối đa `limit` tin gần nhất.

    Dùng để cứu các yêu cầu cũ chưa được lưu log_message_id.
    Trả về message_id hoặc None.
    """
    token = _discord_bot_token()
    if not token:
        raise RuntimeError("Chưa cấu hình DISCORD_BOT_TOKEN hoặc BOT_TOKEN")

    channel_id = int(channel_id or 0)
    if not channel_id:
        raise RuntimeError("Chưa cấu hình WALLET_LOG_CHANNEL_ID")

    req = urllib.request.Request(
        (
            f"https://discord.com/api/v10/channels/{channel_id}/messages"
            f"?limit={max(1, min(int(limit), 100))}"
        ),
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "LoveBotStore-Web/1.0",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            messages = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Không đọc được wallet log: HTTP {error.code} — {detail[:300]}"
        ) from error

    needle = str(transaction_code).strip().upper()

    for message in messages:
        # Chỉ sửa message do chính bot hiện tại gửi.
        author = message.get("author") or {}
        if not author.get("bot"):
            continue

        searchable_parts = [message.get("content") or ""]

        for embed in message.get("embeds") or []:
            searchable_parts.append(embed.get("title") or "")
            searchable_parts.append(embed.get("description") or "")

            for field in embed.get("fields") or []:
                searchable_parts.append(field.get("name") or "")
                searchable_parts.append(field.get("value") or "")

        searchable_text = "\n".join(searchable_parts).upper()
        if needle in searchable_text:
            return int(message["id"])

    return None


def _edit_or_recover_wallet_log(
    transaction_code,
    log_channel_id,
    log_message_id,
    updated_embed,
):
    """
    Ưu tiên sửa đúng message đã lưu.

    Nếu ID bị thiếu hoặc message cũ không còn đúng ID:
    - quét các tin gần nhất trong kênh log;
    - tìm embed chứa transaction_code;
    - sửa embed đó;
    - lưu lại channel/message ID vào database.

    Chỉ khi hoàn toàn không tìm thấy message cũ mới gửi log mới.
    """
    configured_channel_id = int(
        getattr(config, "WALLET_LOG_CHANNEL_ID", 0)
        or os.getenv("WALLET_LOG_CHANNEL_ID", "0")
        or 0
    )

    channel_id = int(log_channel_id or configured_channel_id or 0)
    message_id = int(log_message_id or 0)

    if not channel_id:
        raise RuntimeError("Chưa cấu hình WALLET_LOG_CHANNEL_ID")

    # Trường hợp DB đã lưu đủ ID.
    if message_id:
        try:
            _edit_discord_channel_embed(
                channel_id,
                message_id,
                updated_embed,
            )
            return {
                "edited": True,
                "channel_id": channel_id,
                "message_id": message_id,
                "recovered": False,
            }
        except Exception as error:
            print(
                "[Wallet Discord Log] ID cũ không sửa được, "
                f"đang tìm lại message: {error}"
            )

    # Cứu các giao dịch cũ bị NULL message_id hoặc ID sai.
    recovered_message_id = _find_wallet_log_message(
        channel_id,
        transaction_code,
    )

    if recovered_message_id:
        _edit_discord_channel_embed(
            channel_id,
            recovered_message_id,
            updated_embed,
        )
        db.save_wallet_log_message(
            transaction_code,
            channel_id,
            recovered_message_id,
        )
        return {
            "edited": True,
            "channel_id": channel_id,
            "message_id": recovered_message_id,
            "recovered": True,
        }

    # Không tìm thấy log cũ: lúc này mới gửi message mới.
    _send_wallet_web_log(
        updated_embed["title"],
        updated_embed["color"],
        updated_embed["fields"],
        updated_embed.get("description"),
    )
    return {
        "edited": False,
        "channel_id": channel_id,
        "message_id": None,
        "recovered": False,
    }



def _wallet_log_embed(title, color, fields):
    return {
        "title": title,
        "color": color,
        "fields": fields,
        "footer": {"text": getattr(config, "BOT_FOOTER", "Love Store")},
        "timestamp": datetime.utcnow().isoformat(),
    }



def _send_wallet_web_log(title, color, fields, description=None):
    channel_id = (
        getattr(config, "WALLET_LOG_CHANNEL_ID", 0)
        or os.getenv("WALLET_LOG_CHANNEL_ID", "0")
    )
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {"text": getattr(config, "BOT_FOOTER", "Love Store")},
        "timestamp": datetime.utcnow().isoformat(),
    }
    return _send_discord_channel_embed(channel_id, embed)


def _send_discord_dm(discord_id, *, content=None, embed=None):
    """Gửi DM Discord bằng nội dung chữ, embed hoặc cả hai."""
    token = _discord_bot_token()
    if not token:
        raise RuntimeError("Chưa cấu hình DISCORD_BOT_TOKEN hoặc BOT_TOKEN")

    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "LoveBotStore-Web/1.0",
    }

    create_payload = json.dumps({
        "recipient_id": str(discord_id)
    }).encode("utf-8")

    create_req = urllib.request.Request(
        "https://discord.com/api/v10/users/@me/channels",
        data=create_payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(create_req, timeout=10) as response:
            dm_channel = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Không tạo được DM channel: HTTP {error.code} — {detail[:300]}"
        ) from error

    channel_id = dm_channel.get("id")
    if not channel_id:
        raise RuntimeError("Discord không trả về ID kênh DM")

    payload_data = {
        "allowed_mentions": {"parse": []}
    }
    if content:
        payload_data["content"] = str(content)
    if embed:
        payload_data["embeds"] = [embed]

    if not content and not embed:
        raise ValueError("DM phải có content hoặc embed")

    message_payload = json.dumps(payload_data).encode("utf-8")

    message_req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        data=message_payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(message_req, timeout=10) as response:
            return response.status in (200, 201)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Không gửi được DM: HTTP {error.code} — {detail[:300]}"
        ) from error


def _money(value):
    return f"{int(value or 0):,}".replace(",", ".") + " VNĐ"


# ── Đơn hàng ─────────────────────────────────────────────────

@app.route("/orders")
@login_required
@role_required("founder", "admin")
def orders():
    status_filter = request.args.get("status", "all")
    search        = request.args.get("search", "").strip()

    conn   = db.get_conn_dict()
    c      = conn.cursor()
    query  = "SELECT * FROM orders WHERE 1=1"
    params = []

    if status_filter != "all":
        query += " AND status=%s"
        params.append(status_filter)
    if search:
        query += " AND (order_code ILIKE %s OR username ILIKE %s OR product_name ILIKE %s)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]

    query += " ORDER BY created_at DESC"
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return render_template("orders.html", orders=list(rows), status_filter=status_filter, search=search)



@app.route("/orders/create", methods=["GET", "POST"])
@login_required
@role_required("founder", "admin")
def create_manual_order():
    defaults = {
        "order_code": _generate_order_code(),
        "ticket_number": _generate_ticket_number(),
        "status": "done",
        "stars": 5,
    }

    if request.method == "POST":
        order_code = request.form.get("order_code", "").strip().upper()
        ticket_number = request.form.get("ticket_number", "").strip()
        username = request.form.get("username", "").strip()
        user_id = _parse_int(request.form.get("user_id"), 0)
        product_name = request.form.get("product_name", "").strip()
        amount = _parse_int(request.form.get("amount"), 0)
        support_name = request.form.get("support_name", "").strip()
        processor_name = request.form.get("processor_name", "").strip()
        status = request.form.get("status", "done").strip()
        feedback_content = request.form.get("feedback_content", "").strip()
        stars = max(1, min(5, _parse_int(request.form.get("stars"), 5)))

        defaults.update(request.form.to_dict())

        if not order_code or not username or not product_name:
            flash("❌ Mã đơn, người mua và sản phẩm không được để trống!", "error")
        elif not ticket_number.isdigit() or len(ticket_number) != 4:
            flash("❌ Mã ticket phải gồm đúng 4 chữ số!", "error")
        elif amount < 0:
            flash("❌ Số tiền không hợp lệ!", "error")
        elif db.order_exists(order_code):
            flash(f"❌ Mã đơn `{order_code}` đã tồn tại, không thể tạo trùng!", "error")
        else:
            try:
                db.create_manual_order(
                    order_code, user_id, username, product_name, amount, status,
                    ticket_number, support_name, processor_name
                )
                if feedback_content:
                    db.upsert_manual_feedback(order_code, user_id, username, stars, feedback_content)
                wdb.add_log(
                    "Thêm đơn thủ công",
                    f"{order_code} — {product_name} — {amount:,}đ",
                    session.get("display", "Web")
                )
                flash(f"✅ Đã tạo đơn `{order_code}`!", "success")
                return redirect(url_for("order_detail", order_code=order_code))
            except Exception as e:
                flash(f"❌ Không thể tạo đơn: {e}", "error")

    return render_template("create_order.html", defaults=defaults)


@app.route("/orders/my")
@login_required
def my_orders():
    rows = wdb.get_orders_by_support(session["user_id"])
    return render_template("my_orders.html", orders=rows)


@app.route("/orders/<order_code>")
@login_required
@role_required("founder", "admin")
def order_detail(order_code):
    order = db.get_order(order_code)
    if not order:
        flash("❌ Không tìm thấy đơn hàng!", "error")
        return redirect(url_for("orders"))

    feedback = db.get_feedback_by_order(order_code)
    return render_template("order_detail.html", order=order, feedback=feedback)



@app.route("/orders/<order_code>/send-discord", methods=["POST"])
@login_required
@role_required("founder", "admin")
def send_order_to_discord(order_code):
    order = db.get_order(order_code)

    if not order:
        flash("❌ Không tìm thấy đơn hàng!", "error")
        return redirect(url_for("orders"))

    try:
        _send_order_to_discord(order)

        try:
            wdb.add_log(
                "Gửi lại đơn vào Discord",
                f"{order_code} — {order['product_name']}",
                session.get("display", "Web")
            )
        except Exception as log_error:
            print(
                "[Web Order Resend] Không ghi được log: "
                f"{type(log_error).__name__}: {log_error}"
            )

        flash(
            f"✅ Đã gửi lại đơn `{order_code}` vào kênh #order!",
            "success"
        )

    except Exception as error:
        flash(
            f"❌ Không gửi được đơn vào Discord: {error}",
            "error"
        )

    return redirect(url_for("order_detail", order_code=order_code))


@app.route("/orders/<order_code>/edit", methods=["GET", "POST"])
@login_required
@role_required("founder", "admin")
def edit_order(order_code):
    order = db.get_order(order_code)
    if not order:
        flash("❌ Không tìm thấy đơn hàng!", "error")
        return redirect(url_for("orders"))

    feedback = db.get_feedback_by_order(order_code)

    if request.method == "POST":
        new_code = request.form.get("order_code", "").strip().upper()
        ticket_number = request.form.get("ticket_number", "").strip()
        username = request.form.get("username", "").strip()
        user_id = _parse_int(request.form.get("user_id"), 0)
        product_name = request.form.get("product_name", "").strip()
        amount = _parse_int(request.form.get("amount"), 0)
        support_name = request.form.get("support_name", "").strip()
        processor_name = request.form.get("processor_name", "").strip()
        status = request.form.get("status", "pending").strip()
        feedback_content = request.form.get("feedback_content", "").strip()
        stars = max(1, min(5, _parse_int(request.form.get("stars"), 5)))

        if not new_code or not username or not product_name:
            flash("❌ Mã đơn, người mua và sản phẩm không được để trống!", "error")
        elif not ticket_number.isdigit() or len(ticket_number) != 4:
            flash("❌ Mã ticket phải gồm đúng 4 chữ số!", "error")
        elif amount < 0:
            flash("❌ Số tiền không hợp lệ!", "error")
        elif new_code != order_code and db.order_exists(new_code):
            flash(f"❌ Mã đơn `{new_code}` đã tồn tại!", "error")
        else:
            try:
                db.update_order_full(
                    order_code, new_code, user_id, username, product_name, amount,
                    status, ticket_number, support_name, processor_name
                )
                if feedback_content:
                    db.upsert_manual_feedback(new_code, user_id, username, stars, feedback_content)
                wdb.add_log(
                    "Sửa đơn hàng",
                    f"{order_code} -> {new_code}",
                    session.get("display", "Web")
                )
                flash(f"✅ Đã cập nhật đơn `{new_code}`!", "success")
                return redirect(url_for("order_detail", order_code=new_code))
            except Exception as e:
                flash(f"❌ Không thể cập nhật đơn: {e}", "error")

    return render_template("edit_order.html", order=order, feedback=feedback)


@app.route("/orders/<order_code>/update", methods=["POST"])
@login_required
@role_required("founder")
def update_order(order_code):
    status = request.form.get("status")
    db.update_order_status(order_code, status)

    status_map = {
        "pending":    "⏳ Đang chờ",
        "processing": "🔄 Đang xử lý",
        "paid":       "💳 Đã thanh toán",
        "done":       "✅ Hoàn tất",
        "cancelled":  "❌ Đã hủy",
    }
    status_color = {
        "pending":    0xF39C12,
        "processing": 0x3498DB,
        "paid":       0x9B59B6,
        "done":       0x2ECC71,
        "cancelled":  0xE74C3C,
    }

    import json
    with open("pending_updates.json", "a") as f:
        f.write(json.dumps({
            "order_code":  order_code,
            "status":      status,
            "status_text": status_map.get(status, status),
            "color":       status_color.get(status, 0x3498DB)
        }) + "\n")

    flash(f"✅ Đã cập nhật trạng thái đơn `{order_code}`!", "success")
    return redirect(url_for("order_detail", order_code=order_code))


@app.route("/orders/<order_code>/delete", methods=["POST"])
@login_required
@role_required("founder")
def delete_order(order_code):
    conn = db.get_conn()
    c    = conn.cursor()
    c.execute("DELETE FROM orders WHERE order_code=%s", (order_code,))
    conn.commit()
    conn.close()
    flash(f"🗑️ Đã xóa đơn `{order_code}`!", "success")
    return redirect(url_for("orders"))




# ── Ví tiền ──────────────────────────────────────────────────

@app.route("/wallets")
@login_required
@role_required("founder", "admin")
def wallets():
    status_filter = request.args.get("status", "pending").strip()
    search = request.args.get("search", "").strip()

    conn = db.get_conn_dict()
    try:
        c = conn.cursor()

        query = """
            SELECT
                wt.*,
                w.balance AS current_balance
            FROM wallet_transactions wt
            LEFT JOIN wallets w ON w.discord_id = wt.discord_id
            WHERE wt.transaction_type='deposit_request'
        """
        params = []

        if status_filter != "all":
            query += " AND wt.status=%s"
            params.append(status_filter)

        if search:
            query += """
                AND (
                    wt.transaction_code ILIKE %s
                    OR wt.reference_code ILIKE %s
                    OR wt.username ILIKE %s
                    OR CAST(wt.discord_id AS TEXT) ILIKE %s
                )
            """
            like = f"%{search}%"
            params.extend([like, like, like, like])

        query += " ORDER BY wt.created_at DESC"

        c.execute(query, params)
        requests = list(c.fetchall())

        c.execute("""
            SELECT
                COUNT(*) FILTER (WHERE status='pending') AS pending,
                COUNT(*) FILTER (WHERE status='completed') AS completed,
                COUNT(*) FILTER (WHERE status='rejected') AS rejected,
                COALESCE(SUM(amount) FILTER (WHERE status='completed'), 0) AS approved_amount
            FROM wallet_transactions
            WHERE transaction_type='deposit_request'
        """)
        stats = c.fetchone()

        c.execute("""
            SELECT *
            FROM wallets
            ORDER BY balance DESC, updated_at DESC
            LIMIT 100
        """)
        wallet_rows = list(c.fetchall())

    finally:
        conn.close()

    return render_template(
        "wallets.html",
        requests=requests,
        wallets=wallet_rows,
        stats=stats,
        status_filter=status_filter,
        search=search,
    )


@app.route("/wallets/<transaction_code>/approve", methods=["POST"])
@login_required
@role_required("founder")
def approve_wallet_deposit(transaction_code):
    conn = db.get_conn()
    try:
        c = conn.cursor()

        # Khóa yêu cầu để không thể bấm duyệt hai lần.
        c.execute(
            """
            SELECT id, discord_id, username, amount, reference_code, status,
                   log_channel_id, log_message_id
            FROM wallet_transactions
            WHERE transaction_code=%s
              AND transaction_type='deposit_request'
            FOR UPDATE
            """,
            (transaction_code,),
        )
        request_row = c.fetchone()

        if not request_row:
            conn.rollback()
            flash("❌ Không tìm thấy yêu cầu nạp tiền!", "error")
            return redirect(url_for("wallets"))

        (
            request_id, discord_id, username, amount, reference_code, status,
            log_channel_id, log_message_id
        ) = request_row

        if status != "pending":
            conn.rollback()
            flash(
                f"⚠️ Yêu cầu `{transaction_code}` đã được xử lý trước đó.",
                "error"
            )
            return redirect(url_for("wallets"))

        c.execute(
            """
            INSERT INTO wallets (discord_id, username)
            VALUES (%s, %s)
            ON CONFLICT (discord_id)
            DO UPDATE SET
                username=EXCLUDED.username,
                updated_at=NOW()
            """,
            (discord_id, username or ""),
        )

        c.execute(
            "SELECT balance FROM wallets WHERE discord_id=%s FOR UPDATE",
            (discord_id,),
        )
        balance_before = int(c.fetchone()[0])
        balance_after = balance_before + int(amount)

        c.execute(
            """
            UPDATE wallets
            SET balance=%s,
                total_deposit=total_deposit + %s,
                updated_at=NOW()
            WHERE discord_id=%s
            """,
            (balance_after, amount, discord_id),
        )

        c.execute(
            """
            UPDATE wallet_transactions
            SET status='completed',
                performed_by=%s,
                performer_name=%s,
                balance_before=%s,
                balance_after=%s,
                reason=COALESCE(reason, '') || %s
            WHERE id=%s
            """,
            (
                int(session.get("user_id") or 0),
                session.get("display", "Web"),
                balance_before,
                balance_after,
                " | Duyệt và cộng ví trên web",
                request_id,
            ),
        )

        conn.commit()

    except Exception as error:
        conn.rollback()
        flash(f"❌ Không thể duyệt yêu cầu: {error}", "error")
        return redirect(url_for("wallets"))
    finally:
        conn.close()

    dm_error = None
    try:
        _send_discord_dm(
            discord_id,
            embed={
                "title": "✅ Nạp tiền thành công",
                "description": (
                    "Yêu cầu nạp tiền của bạn đã được Founder duyệt "
                    "và cộng vào ví Love Store."
                ),
                "color": 0x2ECC71,
                "fields": [
                    {
                        "name": "🧾 Mã giao dịch",
                        "value": f"`{transaction_code}`",
                        "inline": True,
                    },
                    {
                        "name": "💰 Số tiền",
                        "value": f"**{_money(amount)}**",
                        "inline": True,
                    },
                    {
                        "name": "💳 Số dư mới",
                        "value": f"**{_money(balance_after)}**",
                        "inline": False,
                    },
                    {
                        "name": "📝 Nội dung chuyển khoản",
                        "value": f"`{reference_code}`",
                        "inline": False,
                    },
                ],
                "footer": {
                    "text": getattr(config, "BOT_FOOTER", "Love Store")
                },
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as error:
        dm_error = str(error)

    try:
        updated_embed = _wallet_log_embed(
            "🟢 Yêu cầu nạp tiền đã được duyệt",
            0x2ECC71,
            [
                {"name": "👤 Khách hàng", "value": f"<@{discord_id}>\n`{discord_id}`", "inline": False},
                {"name": "💰 Số tiền", "value": f"**{_money(amount)}**", "inline": True},
                {"name": "🧾 Mã yêu cầu", "value": f"`{transaction_code}`", "inline": True},
                {"name": "📝 Nội dung chuyển khoản", "value": f"`{reference_code}`", "inline": False},
                {"name": "📌 Trạng thái", "value": "✅ Đã duyệt và cộng tiền vào ví", "inline": False},
                {"name": "👑 Người duyệt", "value": session.get("display", "Web"), "inline": False},
                {"name": "💳 Biến động số dư", "value": f"{_money(balance_before)} → **{_money(balance_after)}**", "inline": False},
            ],
        )

        _edit_or_recover_wallet_log(
            transaction_code,
            log_channel_id,
            log_message_id,
            updated_embed,
        )
    except Exception as log_error:
        print(f"[Wallet Discord Log] {log_error}")

    try:
        wdb.add_log(
            "Duyệt nạp ví",
            f"{transaction_code} — {username} — {_money(amount)}",
            session.get("display", "Web"),
        )
    except Exception as log_error:
        print(f"[Wallet Log] {log_error}")

    if dm_error:
        flash(
            f"✅ Đã cộng {_money(amount)} vào ví, nhưng không DM được khách: {dm_error}",
            "success"
        )
    else:
        flash(
            f"✅ Đã duyệt `{transaction_code}`, cộng {_money(amount)} và DM khách!",
            "success"
        )

    return redirect(url_for("wallets"))


@app.route("/wallets/<transaction_code>/mark-completed", methods=["POST"])
@login_required
@role_required("founder")
def mark_wallet_deposit_completed(transaction_code):
    """Đánh dấu đã xử lý khi tiền đã được cộng thủ công bằng /congtien."""
    conn = db.get_conn()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, discord_id, username, amount, reference_code, status
            FROM wallet_transactions
            WHERE transaction_code=%s
              AND transaction_type='deposit_request'
            FOR UPDATE
            """,
            (transaction_code,),
        )
        row = c.fetchone()

        if not row:
            conn.rollback()
            flash("❌ Không tìm thấy yêu cầu nạp tiền!", "error")
            return redirect(url_for("wallets"))

        request_id, discord_id, username, amount, reference_code, status = row

        if status != "pending":
            conn.rollback()
            flash("⚠️ Yêu cầu này đã được xử lý trước đó.", "error")
            return redirect(url_for("wallets"))

        c.execute(
            "SELECT balance FROM wallets WHERE discord_id=%s",
            (discord_id,),
        )
        wallet_row = c.fetchone()
        current_balance = int(wallet_row[0]) if wallet_row else 0

        c.execute(
            """
            UPDATE wallet_transactions
            SET status='completed',
                performed_by=%s,
                performer_name=%s,
                balance_before=%s,
                balance_after=%s,
                reason=COALESCE(reason, '') || %s
            WHERE id=%s
            """,
            (
                int(session.get("user_id") or 0),
                session.get("display", "Web"),
                current_balance,
                current_balance,
                " | Đã cộng thủ công, web chỉ xác nhận",
                request_id,
            ),
        )
        conn.commit()

    except Exception as error:
        conn.rollback()
        flash(f"❌ Không thể xác nhận yêu cầu: {error}", "error")
        return redirect(url_for("wallets"))
    finally:
        conn.close()

    dm_error = None
    try:
        _send_discord_dm(
            discord_id,
            embed={
                "title": "✅ Đã xác nhận nạp tiền",
                "description": (
                    "Founder đã xác nhận tiền được cộng thủ công "
                    "vào ví Love Store của bạn."
                ),
                "color": 0x3498DB,
                "fields": [
                    {
                        "name": "🧾 Mã giao dịch",
                        "value": f"`{transaction_code}`",
                        "inline": True,
                    },
                    {
                        "name": "💰 Số tiền",
                        "value": f"**{_money(amount)}**",
                        "inline": True,
                    },
                    {
                        "name": "💳 Số dư hiện tại",
                        "value": f"**{_money(current_balance)}**",
                        "inline": False,
                    },
                ],
                "footer": {
                    "text": getattr(config, "BOT_FOOTER", "Love Store")
                },
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as error:
        dm_error = str(error)

    try:
        _send_wallet_web_log(
            "🔵 Xác nhận đã cộng tiền thủ công",
            0x3498DB,
            [
                {"name": "👤 Khách hàng", "value": f"{username or 'Không rõ'}\n`{discord_id}`", "inline": False},
                {"name": "👑 Người xác nhận", "value": session.get("display", "Web"), "inline": False},
                {"name": "💰 Số tiền yêu cầu", "value": f"**{_money(amount)}**", "inline": True},
                {"name": "💳 Số dư hiện tại", "value": f"**{_money(current_balance)}**", "inline": True},
                {"name": "🧾 Mã giao dịch", "value": f"`{transaction_code}`", "inline": False},
            ],
        )
    except Exception as log_error:
        print(f"[Wallet Discord Log] {log_error}")

    if dm_error:
        flash(
            f"✅ Đã đánh dấu hoàn tất, nhưng không DM được khách: {dm_error}",
            "success"
        )
    else:
        flash("✅ Đã đánh dấu hoàn tất và DM khách!", "success")

    return redirect(url_for("wallets"))


@app.route("/wallets/<transaction_code>/reject", methods=["POST"])
@login_required
@role_required("founder")
def reject_wallet_deposit(transaction_code):
    reject_reason = request.form.get("reason", "").strip() or "Không xác nhận được giao dịch"

    conn = db.get_conn()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, discord_id, amount, reference_code, status,
                   log_channel_id, log_message_id
            FROM wallet_transactions
            WHERE transaction_code=%s
              AND transaction_type='deposit_request'
            FOR UPDATE
            """,
            (transaction_code,),
        )
        row = c.fetchone()

        if not row:
            conn.rollback()
            flash("❌ Không tìm thấy yêu cầu nạp tiền!", "error")
            return redirect(url_for("wallets"))

        (
            request_id, discord_id, amount, reference_code, status,
            log_channel_id, log_message_id
        ) = row

        if status != "pending":
            conn.rollback()
            flash("⚠️ Yêu cầu này đã được xử lý trước đó.", "error")
            return redirect(url_for("wallets"))

        c.execute(
            """
            UPDATE wallet_transactions
            SET status='rejected',
                performed_by=%s,
                performer_name=%s,
                reason=%s
            WHERE id=%s
            """,
            (
                int(session.get("user_id") or 0),
                session.get("display", "Web"),
                reject_reason[:500],
                request_id,
            ),
        )
        conn.commit()

    except Exception as error:
        conn.rollback()
        flash(f"❌ Không thể từ chối yêu cầu: {error}", "error")
        return redirect(url_for("wallets"))
    finally:
        conn.close()

    dm_error = None
    try:
        _send_discord_dm(
            discord_id,
            embed={
                "title": "❌ Yêu cầu nạp tiền bị từ chối",
                "description": (
                    "Yêu cầu của bạn chưa được xác nhận. "
                    "Hãy liên hệ Support nếu bạn đã chuyển khoản."
                ),
                "color": 0xE74C3C,
                "fields": [
                    {
                        "name": "🧾 Mã giao dịch",
                        "value": f"`{transaction_code}`",
                        "inline": True,
                    },
                    {
                        "name": "💰 Số tiền",
                        "value": f"**{_money(amount)}**",
                        "inline": True,
                    },
                    {
                        "name": "📝 Nội dung chuyển khoản",
                        "value": f"`{reference_code}`",
                        "inline": False,
                    },
                    {
                        "name": "📌 Lý do",
                        "value": reject_reason[:1024],
                        "inline": False,
                    },
                ],
                "footer": {
                    "text": getattr(config, "BOT_FOOTER", "Love Store")
                },
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as error:
        dm_error = str(error)

    try:
        updated_embed = _wallet_log_embed(
            "🔴 Yêu cầu nạp tiền đã bị từ chối",
            0xE74C3C,
            [
                {"name": "👤 Khách hàng", "value": f"<@{discord_id}>\n`{discord_id}`", "inline": False},
                {"name": "💰 Số tiền", "value": f"**{_money(amount)}**", "inline": True},
                {"name": "🧾 Mã yêu cầu", "value": f"`{transaction_code}`", "inline": True},
                {"name": "📝 Nội dung chuyển khoản", "value": f"`{reference_code}`", "inline": False},
                {"name": "📌 Trạng thái", "value": "❌ Đã từ chối", "inline": False},
                {"name": "👑 Người từ chối", "value": session.get("display", "Web"), "inline": False},
                {"name": "📄 Lý do", "value": reject_reason[:1024], "inline": False},
            ],
        )

        _edit_or_recover_wallet_log(
            transaction_code,
            log_channel_id,
            log_message_id,
            updated_embed,
        )
    except Exception as log_error:
        print(f"[Wallet Discord Log] {log_error}")

    if dm_error:
        flash(
            f"✅ Đã từ chối yêu cầu, nhưng không DM được khách: {dm_error}",
            "success"
        )
    else:
        flash("✅ Đã từ chối yêu cầu và DM khách!", "success")

    return redirect(url_for("wallets"))


# ── Khách hàng ────────────────────────────────────────────────

@app.route("/customers")
@login_required
@role_required("founder", "admin")
def customers():
    conn = db.get_conn_dict()
    c    = conn.cursor()
    c.execute("""
        SELECT user_id, username,
               COUNT(*) as total_orders,
               SUM(CASE WHEN status IN ('paid','done') THEN amount ELSE 0 END) as total_spent,
               MAX(created_at) as last_order
        FROM orders GROUP BY user_id, username ORDER BY total_spent DESC NULLS LAST
    """)
    rows = c.fetchall()
    conn.close()
    return render_template("customers.html", customers=list(rows))


@app.route("/customers/<int:user_id>")
@login_required
@role_required("founder", "admin")
def customer_detail(user_id):
    conn = db.get_conn_dict()
    c    = conn.cursor()
    c.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY created_at DESC", (user_id,))
    rows = c.fetchall()
    conn.close()
    return render_template("customer_detail.html", orders=list(rows), user_id=user_id)


# ── Feedback ──────────────────────────────────────────────────

@app.route("/feedbacks")
@login_required
@role_required("founder", "admin")
def feedbacks():
    conn = db.get_conn_dict()
    c    = conn.cursor()
    c.execute("SELECT * FROM feedbacks ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return render_template("feedbacks.html", feedbacks=list(rows))



@app.route("/feedbacks/edit-discord", methods=["GET", "POST"])
@login_required
@role_required("founder")
def edit_discord_feedback():
    result = None

    if request.method == "POST":
        message_url = request.form.get("message_url", "").strip()
        new_order_code = request.form.get("order_code", "").strip().upper()
        new_product_name = request.form.get("product_name", "").strip()

        if not message_url or not new_order_code or not new_product_name:
            flash("❌ Vui lòng nhập đủ link tin nhắn, mã đơn và sản phẩm!", "error")
        else:
            try:
                from webhook_server import edit_feedback_message_sync
                result = edit_feedback_message_sync(
                    message_url,
                    new_order_code,
                    new_product_name
                )

                if result.get("success"):
                    wdb.add_log(
                        "Sửa feedback Discord",
                        f"{new_order_code} — {new_product_name}",
                        session.get("display", "Web")
                    )
                    flash("✅ Đã sửa mã đơn và sản phẩm trên feedback Discord!", "success")
                else:
                    flash(
                        f"❌ {result.get('message', 'Không sửa được tin nhắn')}",
                        "error"
                    )
            except Exception as e:
                flash(f"❌ Lỗi sửa feedback Discord: {e}", "error")

    return render_template("edit_discord_feedback.html", result=result)


# ── Lương ────────────────────────────────────────────────────

@app.route("/salary")
@login_required
def salary():
    if session["role"] == "founder":
        data = wdb.get_all_salary()
    else:
        data = wdb.get_salary_by_support(session["user_id"])
    return render_template("salary.html", salary_data=data, is_all=session["role"] == "founder")


# ── Quản lý tài khoản ────────────────────────────────────────

@app.route("/accounts")
@login_required
@role_required("founder")
def accounts():
    users = wdb.get_all_users()
    return render_template("accounts.html", users=users)


@app.route("/accounts/create", methods=["GET", "POST"])
@login_required
@role_required("founder")
def create_account():
    if request.method == "POST":
        username     = request.form.get("username", "").strip()
        password     = request.form.get("password", "").strip()
        display_name = request.form.get("display_name", "").strip()
        role         = request.form.get("role", "support")
        discord_id   = request.form.get("discord_id", "").strip()

        if not username or not password:
            flash("❌ Vui lòng điền đầy đủ thông tin!", "error")
        elif wdb.get_user_by_username(username):
            flash("❌ Tên đăng nhập đã tồn tại!", "error")
        else:
            wdb.create_user(username, password, display_name, role, discord_id)
            flash(f"✅ Đã tạo tài khoản {username} ({role})!", "success")
            return redirect(url_for("accounts"))

    return render_template("create_account.html")


@app.route("/accounts/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("founder")
def edit_account(user_id):
    conn = wdb.get_conn()
    c    = conn.cursor()
    c.execute("SELECT * FROM web_users WHERE id=%s", (user_id,))
    user = c.fetchone()
    conn.close()

    if not user:
        flash("❌ Không tìm thấy tài khoản!", "error")
        return redirect(url_for("accounts"))

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        role         = request.form.get("role", "support")
        discord_id   = request.form.get("discord_id", "").strip()

        conn = wdb.get_conn()
        c    = conn.cursor()
        c.execute(
            "UPDATE web_users SET display_name=%s, role=%s, discord_id=%s WHERE id=%s",
            (display_name, role, discord_id, user_id)
        )
        conn.commit()
        conn.close()
        flash("✅ Đã cập nhật tài khoản!", "success")
        return redirect(url_for("accounts"))

    return render_template("edit_account.html", user=user)


@app.route("/accounts/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("founder")
def delete_account(user_id):
    if user_id == session["user_id"]:
        flash("❌ Không thể xóa tài khoản đang đăng nhập!", "error")
    else:
        wdb.delete_user(user_id)
        flash("🗑️ Đã xóa tài khoản!", "success")
    return redirect(url_for("accounts"))


@app.route("/accounts/<int:user_id>/reset", methods=["POST"])
@login_required
@role_required("founder")
def reset_password(user_id):
    new_pass = request.form.get("new_password", "").strip()
    if not new_pass:
        flash("❌ Mật khẩu không được để trống!", "error")
    else:
        wdb.reset_password(user_id, new_pass)
        flash("✅ Đã đặt lại mật khẩu!", "success")
    return redirect(url_for("accounts"))


# ── Log ───────────────────────────────────────────────────────

@app.route("/logs")
@login_required
@role_required("founder", "admin")
def logs():
    conn = db.get_conn_dict()
    c    = conn.cursor()
    c.execute('SELECT * FROM logs ORDER BY created_at DESC LIMIT 200')
    rows = c.fetchall()
    conn.close()
    return render_template("logs.html", logs=list(rows))


# ── Bảng giá ─────────────────────────────────────────────────

@app.route("/prices")
@login_required
def prices():
    conn = db.get_conn_dict()
    c    = conn.cursor()
    c.execute("SELECT * FROM products ORDER BY category, sort_order, id")
    rows = c.fetchall()
    conn.close()

    from collections import defaultdict
    categories = defaultdict(list)
    for r in rows:
        categories[r["category"]].append(r)

    return render_template("prices.html", categories=dict(categories),
                           is_founder=session["role"] == "founder")


@app.route("/prices/add", methods=["POST"])
@login_required
@role_required("founder")
def add_product():
    category = request.form.get("category", "").strip()
    name     = request.form.get("name", "").strip()
    price    = request.form.get("price", "0").strip()
    type_    = request.form.get("type", "log").strip()
    note     = request.form.get("note", "").strip()
    order    = request.form.get("sort_order", "0").strip()

    if not category or not name:
        flash("❌ Vui lòng điền đầy đủ thông tin!", "error")
        return redirect(url_for("prices"))

    conn = db.get_conn()
    c    = conn.cursor()
    c.execute(
        "INSERT INTO products (category, name, price, type, note, sort_order) VALUES (%s,%s,%s,%s,%s,%s)",
        (category, name, int(price), type_, note, int(order))
    )
    conn.commit()
    conn.close()
    flash(f"✅ Đã thêm sản phẩm {name}!", "success")
    return redirect(url_for("prices"))


@app.route("/prices/<int:product_id>/delete", methods=["POST"])
@login_required
@role_required("founder")
def delete_product(product_id):
    conn = db.get_conn()
    c    = conn.cursor()
    c.execute("DELETE FROM products WHERE id=%s", (product_id,))
    conn.commit()
    conn.close()
    flash("🗑️ Đã xóa sản phẩm!", "success")
    return redirect(url_for("prices"))

@app.route("/prices/<int:product_id>/edit", methods=["POST"])
@login_required
@role_required("founder")
def edit_product(product_id):
    name  = request.form.get("name", "").strip()
    price = request.form.get("price", "0").strip()
    type_ = request.form.get("type", "log").strip()
    note  = request.form.get("note", "").strip()
    order = request.form.get("sort_order", "0").strip()

    conn = db.get_conn()
    c    = conn.cursor()
    c.execute(
        "UPDATE products SET name=%s, price=%s, type=%s, note=%s, sort_order=%s WHERE id=%s",
        (name, int(price), type_, note, int(order), product_id)
    )
    conn.commit()
    conn.close()
    flash("✅ Đã cập nhật sản phẩm!", "success")
    return redirect(url_for("prices"))


if __name__ == "__main__":
    db.init_db()
    wdb.init_web_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)