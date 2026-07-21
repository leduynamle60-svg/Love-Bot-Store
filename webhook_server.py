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
    Payload mẫu: { "id": ..., "transferAmount": 50000, "description": "LS-ABC123", ... }
    """
    data      = request.json or {}
    raw_body  = request.get_data(as_text=True)
    signature = request.headers.get("X-Webhook-Signature", "")

    # Verify chữ ký
    if config.SEPAY_WEBHOOK_SECRET and not verify_sepay(raw_body, signature):
        return jsonify({"success": False, "message": "Invalid signature"}), 401

    amount      = int(data.get("transferAmount", 0))
    description = data.get("description", "").upper()

    # Tìm mã đơn trong nội dung CK (dạng LS-XXXXXX)
    import re
    match = re.search(r"LS-[A-Z0-9]{6}", description)
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

# ── Web nội bộ V2.1: sửa feedback Discord ───────────────────
def _parse_discord_message_url(message_url: str):
    """Nhận link https://discord.com/channels/GUILD/CHANNEL/MESSAGE."""
    import re
    match = re.search(r"discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)", message_url)
    if not match:
        raise ValueError("Link tin nhắn Discord không hợp lệ")
    return tuple(int(x) for x in match.groups())


def edit_feedback_message_sync(message_url: str, new_order_code: str, new_product_name: str):
    """
    Được gọi từ Flask thread. Chỉ sửa 2 field trong embed feedback:
    - Mã đơn
    - Sản phẩm
    Không sửa số sao, nội dung feedback, khách hàng hoặc thời gian.
    """
    if not _bot or not _bot.loop or _bot.is_closed():
        return {"success": False, "message": "Bot Discord chưa online"}

    try:
        guild_id, channel_id, message_id = _parse_discord_message_url(message_url)
    except ValueError as e:
        return {"success": False, "message": str(e)}

    async def _edit():
        import discord
        guild = _bot.get_guild(guild_id)
        if not guild:
            return {"success": False, "message": "Bot không ở trong server của link này"}

        channel = guild.get_channel(channel_id)
        if channel is None:
            try:
                channel = await _bot.fetch_channel(channel_id)
            except Exception:
                return {"success": False, "message": "Không tìm thấy kênh hoặc bot thiếu quyền xem kênh"}

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return {"success": False, "message": "Không tìm thấy tin nhắn"}
        except discord.Forbidden:
            return {"success": False, "message": "Bot thiếu quyền đọc lịch sử tin nhắn"}

        if message.author.id != _bot.user.id:
            return {"success": False, "message": "Bot chỉ có thể sửa tin nhắn do chính nó gửi"}
        if not message.embeds:
            return {"success": False, "message": "Tin nhắn này không có embed feedback"}

        old = message.embeds[0]
        new_embed = discord.Embed.from_dict(old.to_dict())
        changed_order = False
        changed_product = False

        for index, field in enumerate(list(new_embed.fields)):
            name = field.name.strip().lower()
            if "mã đơn" in name or "ma don" in name:
                new_embed.set_field_at(index, name=field.name, value=f"`{new_order_code}`", inline=field.inline)
                changed_order = True
            elif "sản phẩm" in name or "san pham" in name:
                new_embed.set_field_at(index, name=field.name, value=new_product_name, inline=field.inline)
                changed_product = True

        if not changed_order or not changed_product:
            return {
                "success": False,
                "message": "Embed không có đủ field Mã đơn và Sản phẩm để sửa"
            }

        try:
            await message.edit(embed=new_embed)
        except discord.Forbidden:
            return {"success": False, "message": "Bot thiếu quyền sửa tin nhắn"}

        return {
            "success": True,
            "message": "Đã cập nhật feedback Discord",
            "channel_id": channel_id,
            "message_id": message_id,
        }

    future = asyncio.run_coroutine_threadsafe(_edit(), _bot.loop)
    try:
        return future.result(timeout=15)
    except Exception as e:
        return {"success": False, "message": f"Discord xử lý quá lâu hoặc lỗi: {e}"}
