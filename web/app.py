"""
web/app.py — Flask Web Dashboard cho Love Bot Store
"""

from flask import Flask, render_template, redirect, url_for, request, session, flash
from functools import wraps
from datetime import datetime
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

    conn = db.get_conn()

    stats = {
        "total":     conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "done":      conn.execute("SELECT COUNT(*) FROM orders WHERE status='done'").fetchone()[0],
        "pending":   conn.execute("SELECT COUNT(*) FROM orders WHERE status NOT IN ('done','cancelled')").fetchone()[0],
        "cancelled": conn.execute("SELECT COUNT(*) FROM orders WHERE status='cancelled'").fetchone()[0],
        "revenue":   conn.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status IN ('paid','done')").fetchone()[0],
        "avg_stars": conn.execute("SELECT AVG(stars) FROM feedbacks").fetchone()[0],
        "feedbacks": conn.execute("SELECT COUNT(*) FROM feedbacks").fetchone()[0],
    }

    revenue_chart = conn.execute("""
        SELECT DATE(created_at) as date, SUM(amount) as total
        FROM orders WHERE status IN ('paid','done')
        AND created_at >= DATE('now', '-7 days')
        GROUP BY DATE(created_at) ORDER BY date
    """).fetchall()

    recent_orders = conn.execute(
        "SELECT * FROM orders ORDER BY created_at DESC LIMIT 10"
    ).fetchall()

    conn.close()
    return render_template("dashboard.html",
        stats=stats,
        revenue_chart=list(revenue_chart),
        recent_orders=list(recent_orders)
    )


# ── Đơn hàng ─────────────────────────────────────────────────

@app.route("/orders")
@login_required
@role_required("founder", "admin")
def orders():
    status_filter = request.args.get("status", "all")
    search        = request.args.get("search", "").strip()

    conn   = db.get_conn()
    query  = "SELECT * FROM orders WHERE 1=1"
    params = []

    if status_filter != "all":
        query += " AND status=?"
        params.append(status_filter)
    if search:
        query += " AND (order_code LIKE ? OR username LIKE ? OR product_name LIKE ?)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]

    query += " ORDER BY created_at DESC"
    rows  = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("orders.html", orders=list(rows), status_filter=status_filter, search=search)


@app.route("/orders/my")
@login_required
def my_orders():
    rows = wdb.get_orders_by_support(session["user_id"])
    return render_template("my_orders.html", orders=rows)


@app.route("/orders/<order_code>")
@login_required
@role_required("founder", "admin")
def order_detail(order_code):
    order    = db.get_order(order_code)
    conn     = db.get_conn()
    feedback = conn.execute(
        "SELECT * FROM feedbacks WHERE order_code=?", (order_code,)
    ).fetchone()
    conn.close()
    return render_template("order_detail.html", order=order, feedback=feedback)


@app.route("/orders/<order_code>/update", methods=["POST"])
@login_required
@role_required("founder")
def update_order(order_code):
    status = request.form.get("status")
    db.update_order_status(order_code, status)

    # Map status sang text hiển thị
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

    # Gửi lệnh update embed vào bot qua file tạm
    import json
    with open("pending_updates.json", "a") as f:
        f.write(json.dumps({
            "order_code": order_code,
            "status":     status,
            "status_text": status_map.get(status, status),
            "color":      status_color.get(status, 0x3498DB)
        }) + "\n")

    flash(f"✅ Đã cập nhật trạng thái đơn `{order_code}`!", "success")
    return redirect(url_for("order_detail", order_code=order_code))


@app.route("/orders/<order_code>/delete", methods=["POST"])
@login_required
@role_required("founder")
def delete_order(order_code):
    conn = db.get_conn()
    conn.execute("DELETE FROM orders WHERE order_code=?", (order_code,))
    conn.commit()
    conn.close()
    flash(f"🗑️ Đã xóa đơn `{order_code}`!", "success")
    return redirect(url_for("orders"))


# ── Khách hàng ────────────────────────────────────────────────

@app.route("/customers")
@login_required
@role_required("founder", "admin")
def customers():
    conn = db.get_conn()
    rows = conn.execute("""
        SELECT user_id, username,
               COUNT(*) as total_orders,
               SUM(CASE WHEN status IN ('paid','done') THEN amount ELSE 0 END) as total_spent,
               MAX(created_at) as last_order
        FROM orders GROUP BY user_id, username ORDER BY total_spent DESC
    """).fetchall()
    conn.close()
    return render_template("customers.html", customers=list(rows))


@app.route("/customers/<int:user_id>")
@login_required
@role_required("founder", "admin")
def customer_detail(user_id):
    conn   = db.get_conn()
    orders = conn.execute(
        "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return render_template("customer_detail.html", orders=list(orders), user_id=user_id)


# ── Feedback ──────────────────────────────────────────────────

@app.route("/feedbacks")
@login_required
@role_required("founder", "admin")
def feedbacks():
    conn = db.get_conn()
    rows = conn.execute("SELECT * FROM feedbacks ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("feedbacks.html", feedbacks=list(rows))


# ── Lương ────────────────────────────────────────────────────

@app.route("/salary")
@login_required
def salary():
    if session["role"] == "founder":
        data = wdb.get_all_salary()
        return render_template("salary.html", salary_data=data, is_all=True)
    else:
        data = wdb.get_salary_by_support(session["user_id"])
        return render_template("salary.html", salary_data=[data] if data else [], is_all=False)


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
    user = conn.execute("SELECT * FROM web_users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    if not user:
        flash("❌ Không tìm thấy tài khoản!", "error")
        return redirect(url_for("accounts"))

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        role         = request.form.get("role", "support")
        discord_id   = request.form.get("discord_id", "").strip()

        conn = wdb.get_conn()
        conn.execute(
            "UPDATE web_users SET display_name=?, role=?, discord_id=? WHERE id=?",
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
    conn = db.get_conn()
    rows = conn.execute("SELECT * FROM logs ORDER BY created_at DESC LIMIT 200").fetchall()
    conn.close()
    return render_template("logs.html", logs=list(rows))


# ── Bảng giá ─────────────────────────────────────────────────

@app.route("/prices")
@login_required
def prices():
    conn = db.get_conn()
    rows = conn.execute("SELECT * FROM products ORDER BY category, sort_order, id").fetchall()
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
    conn.execute(
        "INSERT INTO products (category, name, price, type, note, sort_order) VALUES (?,?,?,?,?,?)",
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
    conn.execute("DELETE FROM products WHERE id=?", (product_id,))
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
    conn.execute(
        "UPDATE products SET name=?, price=?, type=?, note=?, sort_order=? WHERE id=?",
        (name, int(price), type_, note, int(order), product_id)
    )
    conn.commit()
    conn.close()
    flash("✅ Đã cập nhật sản phẩm!", "success")
    return redirect(url_for("prices"))


if __name__ == "__main__":
    wdb.init_web_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)