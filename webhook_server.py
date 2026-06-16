"""
webhook_server.py — Flask server nhận webhook từ SePay
Chạy song song với bot bằng threading
"""

from flask import Flask, request, jsonify
from datetime import datetime
import hmac, hashlib, asyncio, threading

import config
import database as db

app = Flask(__name__)

# Bot instance sẽ được gán từ bot.py
_bot = None


def set_bot(bot_instance):
    global _bot
    _bot = bot_instance


def verify_sepay(payload: str, signature: str) -> bool:
    """Xác thực chữ ký SePay (HMAC-SHA256)"""
    if not config.SEPAY_WEBHOOK_SECRET:
        return True  # Bỏ qua verify nếu chưa cấu hình
    expected = hmac.new(
        config.SEPAY_WEBHOOK_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@app.route("/webhook/sepay", methods=["POST"])
def sepay_webhook():
    """
    SePay gọi endpoint này khi có tiền vào tài khoản.
    Payload mẫu: { "id": ..., "transferAmount": 50000, "description": "LBS-ABC123", ... }
    """
    data      = request.json or {}
    raw_body  = request.get_data(as_text=True)
    signature = request.headers.get("X-Webhook-Signature", "")

    # Verify chữ ký
    if config.SEPAY_WEBHOOK_SECRET and not verify_sepay(raw_body, signature):
        return jsonify({"success": False, "message": "Invalid signature"}), 401

    amount      = int(data.get("transferAmount", 0))
    description = data.get("description", "").upper()

    # Tìm mã đơn trong nội dung CK (dạng LBS-XXXXXX)
    import re
    match = re.search(r"LBS-[A-Z0-9]{6}", description)
    if not match:
        return jsonify({"success": True, "message": "No order code found"}), 200

    order_code = match.group()
    order      = db.get_order(order_code)

    if not order:
        return jsonify({"success": True, "message": "Order not found"}), 200

    if order["status"] != "pending":
        return jsonify({"success": True, "message": "Order already processed"}), 200

    if amount < order["amount"]:
        # Thanh toán thiếu — log nhưng không xác nhận
        _notify_discord(order_code, amount, order, status="underpaid")
        return jsonify({"success": True, "message": "Underpaid"}), 200

    # Xác nhận đơn hàng
    db.update_order_status(order_code, "paid")
    _notify_discord(order_code, amount, order, status="paid")

    return jsonify({"success": True, "message": "Order confirmed"}), 200


def _notify_discord(order_code: str, amount: int, order, status: str):
    """Gửi thông báo vào kênh ticket và log"""
    if not _bot:
        return

    async def _send():
        import discord
        guild = _bot.get_guild(config.GUILD_ID)
        if not guild:
            return

        ticket_ch = guild.get_channel(order["ticket_channel"])
        log_ch    = guild.get_channel(config.LOG_CHANNEL_ID)
        customer  = guild.get_member(order["user_id"])
        amount_fmt = f"{amount:,}".replace(",", ".")

        if status == "paid":
            embed = discord.Embed(
                title="✅ Thanh toán xác nhận!",
                description=(
                    f"{customer.mention if customer else order['username']} đã thanh toán thành công!\n\n"
                    f"💰 **Số tiền:** {amount_fmt} VNĐ\n"
                    f"🧾 **Mã đơn:** `{order_code}`\n\n"
                    "Support sẽ giao hàng ngay cho bạn! 💖"
                ),
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now()
            )
            embed.set_footer(text=config.BOT_FOOTER)

            # Ping support
            support_role = guild.get_role(config.SUPPORT_ROLE_ID)
            if ticket_ch:
                ping = support_role.mention if support_role else ""
                await ticket_ch.send(ping, embed=embed)
            if log_ch:
                await log_ch.send(
                    embed=discord.Embed(
                        description=f"💳 **Thanh toán:** `{order_code}` — {amount_fmt} VNĐ — {customer.mention if customer else order['username']}",
                        color=config.COLOR_SUCCESS
                    )
                )

        elif status == "underpaid":
            if ticket_ch:
                embed = discord.Embed(
                    title="⚠️ Thanh toán chưa đủ",
                    description=(
                        f"Phát hiện giao dịch `{order_code}` nhưng số tiền chưa đủ.\n"
                        f"💰 Nhận được: **{amount_fmt} VNĐ** / Cần: **{order['amount']:,} VNĐ**\n\n"
                        "Vui lòng chuyển khoản đúng số tiền!"
                    ),
                    color=config.COLOR_WARNING,
                    timestamp=datetime.now()
                )
                embed.set_footer(text=config.BOT_FOOTER)
                await ticket_ch.send(embed=embed)

    asyncio.run_coroutine_threadsafe(_send(), _bot.loop)


def run_webhook():
    """Chạy Flask trong thread riêng"""
    app.run(host=config.WEBHOOK_HOST, port=config.WEBHOOK_PORT, debug=False, use_reloader=False)


def start_webhook_thread():
    t = threading.Thread(target=run_webhook, daemon=True)
    t.start()
    print(f"[Webhook] Server đang chạy tại http://{config.WEBHOOK_HOST}:{config.WEBHOOK_PORT}")