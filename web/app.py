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
        code = "LBS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
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



