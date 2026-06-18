"""
cogs/order.py — Lệnh !order, !qr, !done dành cho Support/Founder
"""

import discord
from discord.ext import commands
from datetime import datetime
import urllib.parse
import os

import config
import database as db
from cogs.ticket import is_support_or_founder, FeedbackStarsView


def make_qr_url(amount: int, order_code: str) -> str:
    content = urllib.parse.quote(order_code)
    return (
        f"https://img.vietqr.io/image/"
        f"{config.BANK_BIN}-{config.BANK_ACCOUNT_NUMBER}-compact2.png"
        f"?amount={amount}"
        f"&addInfo={content}"
        f"&accountName={urllib.parse.quote(config.BANK_ACCOUNT_NAME)}"
    )


class OrderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _in_ticket(self, channel: discord.TextChannel) -> bool:
        return (
            channel.name.startswith(config.TICKET_PREFIX + "-") or
            channel.name.startswith("support-")
        )

    # ── !order <tên sản phẩm> ────────────────────────────────
    @commands.command(name="order")
    async def cmd_order(self, ctx, *, product_name: str):
        try:
            if not is_support_or_founder(ctx.author):
                return await ctx.send("❌ Chỉ Support/Founder mới dùng lệnh này!", delete_after=5)

            if not self._in_ticket(ctx.channel):
                return await ctx.send("❌ Lệnh này chỉ dùng được trong ticket!", delete_after=5)

            ticket_info = db.get_order_by_channel(ctx.channel.id)
            ticket_row  = db.get_ticket_by_channel(ctx.channel.id)
            customer    = None

            for target, overwrite in ctx.channel.overwrites.items():
                if isinstance(target, discord.Member) and overwrite.send_messages:
                    if not is_support_or_founder(target) and target.id != self.bot.user.id:
                        customer = target
                        break

            if not customer:
                if ticket_info:
                    customer = ctx.guild.get_member(ticket_info["user_id"])
                elif ticket_row:
                    customer = ctx.guild.get_member(ticket_row["user_id"])

            if ticket_info:
                order_code = ticket_info["order_code"]
            elif ticket_row and ticket_row["order_code"]:
                order_code = ticket_row["order_code"]
            else:
                order_code = "LBS-UNKNOWN"

            if ticket_info:
                conn = db.get_conn()
                conn.execute("UPDATE orders SET product_name=? WHERE order_code=?", (product_name, order_code))
                conn.commit()
                conn.close()
            elif customer:
                db.create_order(order_code, customer.id, str(customer), product_name, 0, ctx.channel.id)

            if order_code != "LBS-UNKNOWN":
                db.update_order_status(order_code, "processing")

            order_ch = ctx.guild.get_channel(config.ORDER_CHANNEL_ID)
            if not order_ch:
                return await ctx.send("⚠️ Không tìm thấy kênh #order!", delete_after=10)

            embed = discord.Embed(title="📦 Đơn Hàng Mới", color=config.COLOR_INFO, timestamp=datetime.now())
            embed.add_field(name="🧾 Mã đơn",     value=f"`{order_code}`",                          inline=True)
            embed.add_field(name="👤 Khách hàng", value=customer.mention if customer else "Unknown", inline=True)
            embed.add_field(name="🛍️ Sản phẩm",  value=product_name,                                inline=False)
            embed.add_field(name="📁 Ticket",      value=ctx.channel.mention,                        inline=True)
            embed.add_field(name="📌 Trạng thái",  value="Đang xử lý",                              inline=True)
            embed.add_field(name="🕐 Thời gian",   value=datetime.now().strftime("%d/%m/%Y %H:%M"), inline=True)
            embed.add_field(name="⚙️ Xử lý bởi",  value=ctx.author.mention,                         inline=True)
            embed.set_footer(text=config.BOT_FOOTER)
            await order_ch.send(embed=embed)

            confirm = discord.Embed(
                description=f"✅ Đã ghi nhận đơn **{product_name}** (`{order_code}`) vào {order_ch.mention}",
                color=config.COLOR_SUCCESS
            )
            await ctx.send(embed=confirm)
            await ctx.message.delete()

        except Exception as e:
            import traceback
            traceback.print_exc()
            await ctx.send(f"❌ Lỗi: `{e}`")

    # ── !cancel ──────────────────────────────────────────────
    @commands.command(name="cancel")
    async def cmd_cancel(self, ctx):
        try:
            if not is_support_or_founder(ctx.author):
                return await ctx.send("❌ Chỉ Support/Founder mới dùng lệnh này!", delete_after=5)

            if not self._in_ticket(ctx.channel):
                return await ctx.send("❌ Lệnh này chỉ dùng được trong ticket!", delete_after=5)

            ticket_row = db.get_ticket_by_channel(ctx.channel.id)
            order_info = db.get_order_by_channel(ctx.channel.id)

            if order_info:
                order_code = order_info["order_code"]
            elif ticket_row and ticket_row["order_code"]:
                order_code = ticket_row["order_code"]
            else:
                return await ctx.send("⚠️ Không tìm thấy mã đơn để hủy.", delete_after=8)

            db.update_order_status(order_code, "cancelled")

            order_ch = ctx.guild.get_channel(config.ORDER_CHANNEL_ID)
            if order_ch:
                cancel_embed = discord.Embed(title="❌ Đơn hàng bị hủy", color=config.COLOR_ERROR, timestamp=datetime.now())
                cancel_embed.add_field(name="🧾 Mã đơn",     value=f"`{order_code}`",   inline=True)
                cancel_embed.add_field(name="📌 Trạng thái", value="Đã hủy",            inline=True)
                cancel_embed.add_field(name="📁 Ticket",     value=ctx.channel.mention, inline=True)
                cancel_embed.set_footer(text=config.BOT_FOOTER)
                await order_ch.send(embed=cancel_embed)

            await ctx.send(embed=discord.Embed(description=f"✅ Đã hủy đơn `{order_code}`", color=config.COLOR_SUCCESS))
            await ctx.message.delete()

        except Exception as e:
            import traceback
            traceback.print_exc()
            await ctx.send(f"❌ Lỗi: `{e}`")

    # ── !qr <số tiền> ────────────────────────────────────────
    @commands.command(name="qr")
    async def cmd_qr(self, ctx, amount: int):
        try:
            if not is_support_or_founder(ctx.author):
                return await ctx.send("❌ Chỉ Support/Founder mới dùng lệnh này!", delete_after=5)

            if not self._in_ticket(ctx.channel):
                return await ctx.send("❌ Lệnh này chỉ dùng được trong ticket!", delete_after=5)

            if amount <= 0:
                return await ctx.send("❌ Số tiền phải lớn hơn 0!", delete_after=5)

            ticket_info = db.get_order_by_channel(ctx.channel.id)
            ticket_row  = db.get_ticket_by_channel(ctx.channel.id)

            if ticket_info:
                order_code = ticket_info["order_code"]
            elif ticket_row and ticket_row["order_code"]:
                order_code = ticket_row["order_code"]
            else:
                order_code = "LBS-UNKNOWN"

            if ticket_info:
                conn = db.get_conn()
                conn.execute("UPDATE orders SET amount=? WHERE order_code=?", (amount, order_code))
                conn.commit()
                conn.close()

            qr_url     = make_qr_url(amount, order_code)
            amount_fmt = f"{amount:,}".replace(",", ".")

            embed = discord.Embed(
                title="💳 Thông Tin Thanh Toán",
                description=(
                    "Quét mã QR bên dưới để thanh toán.\n"
                    "Nội dung chuyển khoản **đã được điền sẵn** — không cần chỉnh!"
                ),
                color=config.COLOR_PRIMARY,
                timestamp=datetime.now()
            )
            embed.add_field(name="🏦 Ngân hàng",     value=config.BANK_NAME,                   inline=True)
            embed.add_field(name="💳 Số tài khoản",  value=f"`{config.BANK_ACCOUNT_NUMBER}`",  inline=True)
            embed.add_field(name="👤 Chủ tài khoản", value=config.BANK_ACCOUNT_NAME,           inline=True)
            embed.add_field(name="💰 Số tiền",        value=f"**{amount_fmt} VNĐ**",            inline=True)
            embed.add_field(name="📝 Nội dung CK",    value=f"`{order_code}`",                  inline=True)
            embed.add_field(name="⚠️ Lưu ý",
                            value="Giữ nguyên nội dung chuyển khoản để hệ thống xác nhận tự động!",
                            inline=False)
            embed.set_image(url=qr_url)
            embed.set_footer(text=config.BOT_FOOTER)

            await ctx.send(embed=embed)
            await ctx.message.delete()

        except Exception as e:
            import traceback
            traceback.print_exc()
            await ctx.send(f"❌ Lỗi: `{e}`")

    # ── !done ─────────────────────────────────────────────────
    @commands.command(name="done")
    async def cmd_done(self, ctx):
        try:
            if not is_support_or_founder(ctx.author):
                return await ctx.send("❌ Chỉ Support/Founder mới dùng lệnh này!", delete_after=5)

            if not self._in_ticket(ctx.channel):
                return await ctx.send("❌ Lệnh này chỉ dùng được trong ticket!", delete_after=5)

            customer   = None
            order_info = db.get_order_by_channel(ctx.channel.id)
            ticket_row = db.get_ticket_by_channel(ctx.channel.id)

            for target, overwrite in ctx.channel.overwrites.items():
                if isinstance(target, discord.Member) and overwrite.send_messages:
                    if not is_support_or_founder(target) and target.id != self.bot.user.id:
                        customer = target
                        break

            if not customer:
                if order_info:
                    customer = ctx.guild.get_member(order_info["user_id"])
                elif ticket_row:
                    customer = ctx.guild.get_member(ticket_row["user_id"])

            if order_info:
                order_code = order_info["order_code"]
            elif ticket_row and ticket_row["order_code"]:
                order_code = ticket_row["order_code"]
            else:
                order_code = "LBS-UNKNOWN"

            if order_info:
                db.update_order_status(order_code, "done")

                # Tính lương Support
                import web_db as wdb
                conn     = wdb.get_conn()
                web_user = conn.execute(
                    "SELECT * FROM web_users WHERE discord_id=?", (str(ctx.author.id),)
                ).fetchone()
                conn.close()

                if web_user:
                    amt        = order_info["amount"]
                    commission = 5000 if amt < 100000 else int(amt * 0.10)
                    wdb.add_salary_record(web_user["id"], order_code, commission, f"Đơn {order_code} — {amt:,}đ")
                    print(f"[Salary] {ctx.author} — {order_code} — +{commission:,}đ")

                # Cập nhật embed trong #order
                order_ch = ctx.guild.get_channel(config.ORDER_CHANNEL_ID)
                if order_ch:
                    async for msg in order_ch.history(limit=50):
                        if msg.author == ctx.guild.me and msg.embeds:
                            embed_found = msg.embeds[0]
                            found = any(order_code in (f.value or "") for f in embed_found.fields)
                            if found:
                                new_embed = discord.Embed(
                                    title="📦 Đơn Hàng Mới",
                                    color=config.COLOR_SUCCESS,
                                    timestamp=msg.created_at
                                )
                                for f in embed_found.fields:
                                    if f.name == "📌 Trạng thái":
                                        new_embed.add_field(name="📌 Trạng thái", value="✅ Hoàn tất", inline=f.inline)
                                    else:
                                        new_embed.add_field(name=f.name, value=f.value, inline=f.inline)
                                new_embed.set_footer(text=config.BOT_FOOTER)
                                await msg.edit(embed=new_embed)
                                break

            embed = discord.Embed(
                title="🎉 Đơn hàng hoàn tất!",
                description=(
                    f"{customer.mention if customer else 'Bạn'} ơi, đơn hàng của bạn đã được xử lý xong! 💖\n\n"
                    "Hãy dành **1 phút** để đánh giá trải nghiệm mua hàng nhé~\n"
                    "Feedback của bạn giúp chúng tôi phục vụ tốt hơn!"
                ),
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now()
            )
            embed.add_field(name="⭐ Chọn số sao bên dưới:", value="1 ⭐ → 5 ⭐⭐⭐⭐⭐", inline=False)
            embed.set_footer(text=config.BOT_FOOTER)

            view = FeedbackStarsView(order_code, customer) if customer else None
            if view:
                await ctx.send(embed=embed, view=view)
            else:
                embed.add_field(
                    name="ℹ️ Lưu ý",
                    value="Không tìm thấy khách tự động. Dùng `!order` trước khi dùng `!done`.",
                    inline=False
                )
                await ctx.send(embed=embed)
            await ctx.message.delete()

        except Exception as e:
            import traceback
            traceback.print_exc()
            await ctx.send(f"❌ Lỗi: `{e}`")

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.loop.create_task(self._check_pending_updates())

    async def _check_pending_updates(self):
        import json, asyncio
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                if os.path.exists("pending_updates.json"):
                    with open("pending_updates.json", "r") as f:
                        lines = f.readlines()

                    if lines:
                        # Xóa file trước
                        os.remove("pending_updates.json")

                        for line in lines:
                            try:
                                data       = json.loads(line.strip())
                                order_code = data["order_code"]
                                status_text = data["status_text"]
                                color      = data["color"]

                                guild    = self.bot.get_guild(config.GUILD_ID)
                                order_ch = guild.get_channel(config.ORDER_CHANNEL_ID) if guild else None

                                if order_ch:
                                    async for msg in order_ch.history(limit=100):
                                        if msg.author == guild.me and msg.embeds:
                                            found = any(order_code in (f.value or "") for f in msg.embeds[0].fields)
                                            if found:
                                                old_embed = msg.embeds[0]
                                                new_embed = discord.Embed(
                                                    title=old_embed.title,
                                                    color=color,
                                                    timestamp=msg.created_at
                                                )
                                                for f in old_embed.fields:
                                                    if f.name == "📌 Trạng thái":
                                                        new_embed.add_field(name="📌 Trạng thái", value=status_text, inline=f.inline)
                                                    else:
                                                        new_embed.add_field(name=f.name, value=f.value, inline=f.inline)
                                                new_embed.set_footer(text=config.BOT_FOOTER)
                                                await msg.edit(embed=new_embed)
                                                print(f"[Web→Discord] Đã cập nhật {order_code} → {status_text}")
                                                break
                            except Exception as e:
                                print(f"[Web→Discord ERROR] {e}")
            except Exception as e:
                print(f"[PendingUpdate ERROR] {e}")

            await asyncio.sleep(3)  # Check mỗi 3 giây

    # ── Error handlers ────────────────────────────────────────
    @cmd_order.error
    async def order_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Thiếu tên sản phẩm!\nCú pháp: `!order <tên sản phẩm>`", delete_after=8)

    @cmd_qr.error
    async def qr_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("❌ Số tiền không hợp lệ!\nCú pháp: `!qr <số tiền>` (VD: `!qr 50000`)", delete_after=8)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Thiếu số tiền!\nCú pháp: `!qr <số tiền>`", delete_after=8)


async def setup(bot):
    await bot.add_cog(OrderCog(bot))