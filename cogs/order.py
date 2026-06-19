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
from cogs.ticket import is_support_or_founder, is_admin_or_founder, FeedbackStarsView


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

            # ── Ghi nhận Support xử lý đơn (để tính lương khi !done) ──
            if order_code != "LBS-UNKNOWN":
                conn = db.get_conn()
                conn.execute(
                    "INSERT OR IGNORE INTO order_support (order_code, support_discord_id) VALUES (?, ?)",
                    (order_code, str(ctx.author.id))
                )
                conn.commit()
                conn.close()

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
            if not is_admin_or_founder(ctx.author):
                return await ctx.send("❌ Chỉ Admin/Founder mới được duyệt hoàn tất đơn!", delete_after=5)

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

            product_name = order_info["product_name"] if order_info else "Không rõ"

            # Tìm Support đã xử lý đơn (người dùng !order)
            support_member = None
            conn = db.get_conn()
            support_row = conn.execute(
                "SELECT support_discord_id FROM order_support WHERE order_code=?", (order_code,)
            ).fetchone()
            conn.close()
            if support_row:
                support_member = ctx.guild.get_member(int(support_row["support_discord_id"]))

            if order_info:
                db.update_order_status(order_code, "done")

                # ── Tính lương cho cả 2: Support (!order) và Admin/Founder (!done) ──
                import web_db as wdb
                amt        = order_info["amount"]
                commission = 5000 + (int(amt * 0.10) if amt >= 100000 else 0)

                # Lương Admin/Founder (người dùng !done)
                conn     = wdb.get_conn()
                web_user = conn.execute(
                    "SELECT * FROM web_users WHERE discord_id=?", (str(ctx.author.id),)
                ).fetchone()
                conn.close()
                if web_user:
                    wdb.add_salary_record(web_user["id"], order_code, commission,
                                          f"Xử lý đơn {order_code} — {amt:,}đ", role_in_order="admin")
                    print(f"[Salary-Admin] {ctx.author} — {order_code} — +{commission:,}đ")

                # Lương Support (người dùng !order)
                if support_row:
                    conn = wdb.get_conn()
                    support_web_user = conn.execute(
                        "SELECT * FROM web_users WHERE discord_id=?", (support_row["support_discord_id"],)
                    ).fetchone()
                    conn.close()
                    if support_web_user:
                        wdb.add_salary_record(support_web_user["id"], order_code, commission,
                                              f"Hỗ trợ đơn {order_code} — {amt:,}đ", role_in_order="support")
                        print(f"[Salary-Support] {support_row['support_discord_id']} — {order_code} — +{commission:,}đ")

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

            # ── Embed thông tin đầy đủ trong ticket (KHÔNG xóa tin nhắn) ──
            info_embed = discord.Embed(
                title="✅ Đơn Hàng Hoàn Tất",
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now()
            )
            info_embed.add_field(name="🛍️ Sản phẩm",         value=product_name, inline=False)
            info_embed.add_field(name="👤 Người mua",         value=customer.mention if customer else "Unknown", inline=True)
            info_embed.add_field(name="🎧 Nhân viên hỗ trợ",  value=support_member.mention if support_member else "Không rõ", inline=True)
            info_embed.add_field(name="⚙️ Người xử lý đơn",   value=ctx.author.mention, inline=True)
            info_embed.set_footer(text=config.BOT_FOOTER)
            await ctx.send(embed=info_embed)

            # ── Embed feedback cho khách trong ticket ──
            fb_embed = discord.Embed(
                title="🎉 Đơn hàng hoàn tất!",
                description=(
                    f"{customer.mention if customer else 'Bạn'} ơi, đơn hàng của bạn đã được xử lý xong! 💖\n\n"
                    "Hãy dành **1 phút** để đánh giá trải nghiệm mua hàng nhé~\n"
                    "Feedback của bạn giúp chúng tôi phục vụ tốt hơn!"
                ),
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now()
            )
            fb_embed.add_field(name="⭐ Chọn số sao bên dưới:", value="1 ⭐ → 5 ⭐⭐⭐⭐⭐", inline=False)
            fb_embed.set_footer(text=config.BOT_FOOTER)

            view = FeedbackStarsView(order_code, customer) if customer else None
            if view:
                await ctx.send(embed=fb_embed, view=view)
            else:
                fb_embed.add_field(
                    name="ℹ️ Lưu ý",
                    value="Không tìm thấy khách tự động. Dùng `!order` trước khi dùng `!done`.",
                    inline=False
                )
                await ctx.send(embed=fb_embed)

            # ── Gửi DM cho khách kèm nút tip ──
            if customer:
                try:
                    dm_embed = discord.Embed(
                        title="🎉 Đơn Hàng Hoàn Tất!",
                        description=(
                            f"Cảm ơn bạn đã mua hàng tại **{config.BOT_NAME}**! 💖\n\n"
                            "Đơn hàng của bạn đã được xử lý và giao thành công."
                        ),
                        color=config.COLOR_SUCCESS,
                        timestamp=datetime.now()
                    )
                    dm_embed.add_field(name="🧾 Mã đơn",   value=f"`{order_code}`", inline=True)
                    dm_embed.add_field(name="🛍️ Sản phẩm", value=product_name,      inline=True)
                    dm_embed.add_field(
                        name="💖 Cảm ơn bạn",
                        value="Nếu bạn hài lòng với dịch vụ, hãy ủng hộ nhân viên đã hỗ trợ bạn bằng cách tip nhé!",
                        inline=False
                    )
                    dm_embed.set_footer(text=config.BOT_FOOTER)

                    tip_view = TipView(support_member, ctx.author)
                    await customer.send(embed=dm_embed, view=tip_view)
                except discord.Forbidden:
                    print(f"[DM] Không gửi được DM cho {customer} (đã tắt DM)")

            await ctx.message.delete()

        except Exception as e:
            import traceback
            traceback.print_exc()
            await ctx.send(f"❌ Lỗi: `{e}`")

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


class TipView(discord.ui.View):
    """View DM khách — 2 nút tip cho support và người xử lý"""

    def __init__(self, support_member: discord.Member, processor_member: discord.Member):
        super().__init__(timeout=None)
        self.support_member   = support_member
        self.processor_member = processor_member

    @discord.ui.button(label="💝 Tip Nhân Viên Hỗ Trợ", style=discord.ButtonStyle.success, custom_id="tip_support")
    async def tip_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_tip(interaction, self.support_member, "Nhân viên hỗ trợ")

    @discord.ui.button(label="💝 Tip Người Xử Lý Đơn", style=discord.ButtonStyle.success, custom_id="tip_processor")
    async def tip_processor(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_tip(interaction, self.processor_member, "Người xử lý đơn")

    async def _handle_tip(self, interaction: discord.Interaction, target_member, role_label: str):
        if not target_member:
            return await interaction.response.send_message(
                f"❌ Không tìm thấy thông tin {role_label.lower()}!", ephemeral=True
            )

        # Lấy STK từ web_users (nếu Founder đã cập nhật)
        import web_db as wdb
        conn = wdb.get_conn()
        web_user = conn.execute(
            "SELECT * FROM web_users WHERE discord_id=?", (str(target_member.id),)
        ).fetchone()
        conn.close()

        embed = discord.Embed(
            title=f"💝 Tip cho {role_label}",
            color=config.COLOR_PRIMARY
        )
        embed.add_field(name="👤 Người nhận", value=target_member.mention, inline=False)

        # Kiểm tra có STK chưa (tạm để trống, Founder tự cập nhật sau)
        bank_info = None  # TODO: lấy từ DB nếu có cột bank_account riêng cho từng nhân viên

        if bank_info:
            embed.description = "Quét QR hoặc chuyển khoản theo thông tin bên dưới:"
            embed.add_field(name="🏦 STK", value=bank_info, inline=False)
        else:
            embed.description = (
                f"{target_member.mention} chưa cập nhật thông tin nhận tip.\n"
                "Founder/Admin sẽ liên hệ để hỗ trợ bạn tip trực tiếp nhé! 💖"
            )
            # Báo cho admin biết khách muốn tip
            guild = interaction.guild or (target_member.guild if target_member else None)
            if guild:
                log_ch = guild.get_channel(config.LOG_CHANNEL_ID)
                if log_ch:
                    await log_ch.send(
                        embed=discord.Embed(
                            description=f"💝 **{interaction.user}** muốn tip cho **{target_member.mention}** ({role_label})",
                            color=config.COLOR_WARNING
                        )
                    )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(OrderCog(bot))