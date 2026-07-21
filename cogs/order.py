"""
cogs/order.py — Lệnh !order, !qr, !done dành cho Support/Founder
"""

import discord
import asyncio
from discord.ext import commands
from datetime import datetime
import urllib.parse
import os
import re
import unicodedata

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


def parse_amount(text: str) -> int:
    """Chuyển '20k', '1m', '1.5m', '20000' thành số nguyên VNĐ"""
    text = text.strip().lower().replace(",", ".")

    if text.endswith("k"):
        return int(float(text[:-1]) * 1_000)
    elif text.endswith("m"):
        return int(float(text[:-1]) * 1_000_000)
    else:
        return int(float(text))


def slugify_channel_part(text: str) -> str:
    """Đổi tên sản phẩm staff gõ thành dạng hợp lệ cho tên kênh Discord."""
    text = unicodedata.normalize("NFKD", text.strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "don"


def get_ticket_number(channel: discord.TextChannel) -> str:
    """Lấy 4 số cuối trong tên ticket. Nếu thiếu thì tạo tạm 0000 để không lỗi."""
    match = re.search(r"(\d{4})$", channel.name)
    return match.group(1) if match else "0000"


def get_product_slug(order_info, channel: discord.TextChannel) -> str:
    if order_info and order_info["product_name"]:
        return slugify_channel_part(order_info["product_name"])

    # fallback: lấy phần tên trước 4 số cuối, bỏ prefix trạng thái nếu có
    base = re.sub(r"-?\d{4}$", "", channel.name)
    for prefix in ("cho-xu-li-", "done-", "ticket-"):
        if base.startswith(prefix):
            base = base[len(prefix):]
    return slugify_channel_part(base)


async def safe_rename_ticket(
    channel: discord.TextChannel,
    new_name: str
) -> bool:
    """Đổi tên ticket an toàn, không để Discord API treo vô hạn."""
    new_name = new_name.lower()[:100]

    if channel.name == new_name:
        return True

    try:
        await asyncio.wait_for(
            channel.edit(
                name=new_name,
                reason="Love Store ticket status update"
            ),
            timeout=5
        )
        return True

    except asyncio.TimeoutError:
        print(
            f"[Ticket Rename] Timeout khi đổi tên kênh {channel.id}. "
            "Tiếp tục gửi thông báo hoàn tất."
        )
        return True

    except discord.NotFound:
        print(
            f"[Ticket Rename] Kênh {channel.id} đã bị xóa."
        )
        return False

    except discord.Forbidden:
        print(
            f"[Ticket Rename] Bot thiếu quyền đổi tên kênh {channel.id}. "
            "Tiếp tục gửi thông báo hoàn tất."
        )
        return True

    except discord.HTTPException as error:
        print(
            f"[Ticket Rename] Lỗi Discord API ở kênh "
            f"{channel.id}: {error}"
        )
        return True


class OrderCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _in_ticket(self, channel: discord.TextChannel) -> bool:
        # Không phụ thuộc tên kênh nữa, vì ticket sẽ đổi tên theo trạng thái.
        try:
            return bool(db.get_ticket_by_channel(channel.id) or db.get_order_by_channel(channel.id))
        except Exception:
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
                cur = conn.cursor()
                cur.execute(
                    "UPDATE orders SET product_name=%s WHERE order_code=%s",
                    (product_name, order_code)
                )
                conn.commit()
                conn.close()
            elif customer:
                db.create_order(order_code, customer.id, str(customer), product_name, 0, ctx.channel.id)

            if order_code != "LBS-UNKNOWN":
                db.update_order_status(order_code, "processing")

            # Đổi tên ticket theo đúng tên staff gõ sau !order
            ticket_number = get_ticket_number(ctx.channel)
            product_slug  = slugify_channel_part(product_name)

            if order_code != "LBS-UNKNOWN":
                db.assign_order_support(
                    order_code=order_code,
                    support_discord_id=ctx.author.id,
                    support_name=str(ctx.author),
                    ticket_number=ticket_number,
                )

            print("[!done] Bắt đầu đổi tên kênh")
            renamed = await safe_rename_ticket(
                ctx.channel,
                f"{product_slug}-{ticket_number}"
            )

            if not renamed:
                return

            # ── Ghi nhận Support xử lý đơn (để tính lương khi !done) ──
            if order_code != "LBS-UNKNOWN":
                conn = db.get_conn()
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO order_support (order_code, support_discord_id)
                    VALUES (%s, %s)
                    ON CONFLICT (order_code)
                    DO UPDATE SET support_discord_id=EXCLUDED.support_discord_id
                    """,
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
            embed.set_footer(text=config.BOT_FOOTER)
            await order_ch.send(embed=embed)

            confirm = discord.Embed(
                description=f"✅ Đã ghi nhận đơn **{product_name}** (`{order_code}`) vào {order_ch.mention}",
                color=config.COLOR_SUCCESS
            )
            await ctx.send(embed=confirm)

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
    async def cmd_qr(self, ctx, amount_str: str):
        try:
            if not is_support_or_founder(ctx.author):
                return await ctx.send("❌ Chỉ Support/Founder mới dùng lệnh này!", delete_after=5)

            if not self._in_ticket(ctx.channel):
                return await ctx.send("❌ Lệnh này chỉ dùng được trong ticket!", delete_after=5)

            try:
                amount = parse_amount(amount_str)
            except (ValueError, IndexError):
                return await ctx.send(
                    "❌ Số tiền không hợp lệ!\nVD: `!qr 20k`, `!qr 1m`, `!qr 50000`",
                    delete_after=8
                )

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
                cur = conn.cursor()
                cur.execute(
                    "UPDATE orders SET amount=%s WHERE order_code=%s",
                    (amount, order_code)
                )
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
            embed.add_field(
                name="🧭 Cách thanh toán",
                value=(
                    "• Có mã giảm giá: bấm **🎟️ Áp mã giảm giá** trước.\n"
                    "• Dùng số dư: bấm **👛 Thanh toán bằng ví**.\n"
                    "• Chuyển khoản: bấm **🏦 Lấy mã QR**."
                ),
                inline=False,
            )
            embed.set_footer(text=config.BOT_FOOTER)

            view = PaymentView(order_code, amount)
            payment_message = await ctx.send(embed=embed, view=view)
            view.message = payment_message

        except Exception as e:
            import traceback
            traceback.print_exc()
            await ctx.send(f"❌ Lỗi: `{e}`")

    # ── !done ─────────────────────────────────────────────────
    @commands.command(name="done")
    async def cmd_done(self, ctx):
        try:
            print(f"[!done] START channel={ctx.channel.id} user={ctx.author.id}")
            # 1) Check quyền — không gọi database ở bước này.
            if not (
                is_admin_or_founder(ctx.author)
                or ctx.author.guild_permissions.administrator
            ):
                return await ctx.send(
                    "❌ Chỉ Admin/Founder mới được hoàn tất đơn!",
                    delete_after=8
                )

            if not isinstance(ctx.channel, discord.TextChannel):
                return await ctx.send(
                    "❌ Lệnh này chỉ dùng được trong ticket!",
                    delete_after=5
                )

            # 2) Lấy toàn bộ dữ liệu cần thiết bằng 1 connection.
            # Chạy trong thread để psycopg2 không khóa toàn bộ bot.
            print("[!done] Bắt đầu lấy dữ liệu DB")
            try:
                order_info, ticket_row, support_row = await asyncio.wait_for(
                    asyncio.to_thread(
                        db.get_done_context,
                        ctx.channel.id
                    ),
                    timeout=7
                )
            except asyncio.TimeoutError:
                return await ctx.send(
                    "❌ Database phản hồi quá lâu. Thử lại sau vài giây nhé!",
                    delete_after=10
                )
            except Exception as error:
                return await ctx.send(
                    f"❌ Không lấy được dữ liệu đơn: "
                    f"`{type(error).__name__}: {error}`",
                    delete_after=12
                )

            print("[!done] Lấy dữ liệu DB xong")

            if not order_info and not ticket_row:
                return await ctx.send(
                    "❌ Kênh này không phải ticket đang được hệ thống quản lý!",
                    delete_after=8
                )

            customer = None
            for target, overwrite in ctx.channel.overwrites.items():
                if isinstance(target, discord.Member) and overwrite.send_messages:
                    if (
                        not is_support_or_founder(target)
                        and target.id != self.bot.user.id
                    ):
                        customer = target
                        break

            if not customer:
                user_id = (
                    order_info["user_id"]
                    if order_info
                    else ticket_row["user_id"]
                )
                customer = ctx.guild.get_member(user_id)

            if order_info:
                order_code = order_info["order_code"]
            elif ticket_row and ticket_row["order_code"]:
                order_code = ticket_row["order_code"]
            else:
                order_code = "LBS-UNKNOWN"

            product_name = (
                order_info["product_name"]
                if order_info and order_info["product_name"]
                else "Không rõ"
            )

            support_member = None
            if support_row and support_row["support_discord_id"]:
                try:
                    support_member = ctx.guild.get_member(
                        int(support_row["support_discord_id"])
                    )
                except (TypeError, ValueError):
                    support_member = None

            # 3) Ưu tiên đổi tên kênh.
            ticket_number = get_ticket_number(ctx.channel)
            product_slug = get_product_slug(order_info, ctx.channel)

            renamed = await safe_rename_ticket(
                ctx.channel,
                f"done-{product_slug}-{ticket_number}"
            )
            if not renamed:
                return

            print("[!done] Đổi tên xong hoặc đã bỏ qua timeout")

            # 4) Báo hoàn tất ngay.
            info_embed = discord.Embed(
                title="✅ Đơn Hàng Hoàn Tất",
                description=(
                    f"{customer.mention if customer else 'Khách hàng'} ơi, "
                    "đơn hàng của bạn đã được xử lý xong! 💖"
                ),
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now()
            )
            info_embed.add_field(
                name="🧾 Mã đơn",
                value=f"`{order_code}`",
                inline=True
            )
            info_embed.add_field(
                name="🛍️ Sản phẩm",
                value=product_name,
                inline=True
            )
            info_embed.add_field(
                name="👤 Người mua",
                value=customer.mention if customer else "Không rõ",
                inline=True
            )
            info_embed.add_field(
                name="🎧 Nhân viên hỗ trợ",
                value=support_member.mention if support_member else "Không rõ",
                inline=True
            )
            info_embed.add_field(
                name="⚙️ Người xử lý đơn",
                value=ctx.author.mention,
                inline=True
            )
            info_embed.set_footer(text=config.BOT_FOOTER)
            await asyncio.wait_for(
                ctx.send(embed=info_embed),
                timeout=7
            )
            print("[!done] Đã gửi thông báo hoàn tất")

            # 5) Feedback ngay sau thông báo.
            fb_embed = discord.Embed(
                title="⭐ Đánh Giá Trải Nghiệm",
                description=(
                    "Hãy dành **1 phút** để đánh giá trải nghiệm mua hàng nhé~\n"
                    "Feedback của bạn giúp chúng tôi phục vụ tốt hơn!"
                ),
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now()
            )
            fb_embed.add_field(
                name="⭐ Chọn số sao bên dưới:",
                value="1 ⭐ → 5 ⭐⭐⭐⭐⭐",
                inline=False
            )
            fb_embed.set_footer(text=config.BOT_FOOTER)

            view = FeedbackStarsView(order_code, customer) if customer else None
            if view:
                await asyncio.wait_for(
                    ctx.send(embed=fb_embed, view=view),
                    timeout=7
                )
            else:
                await asyncio.wait_for(
                    ctx.send(embed=fb_embed),
                    timeout=7
                )

            print("[!done] Đã gửi feedback")

            # 6) Hậu xử lý DB sau khi khách đã thấy thông báo.
            if order_info and order_code != "LBS-UNKNOWN":
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(
                            db.finish_order,
                            order_code,
                            ctx.author.id,
                            str(ctx.author)
                        ),
                        timeout=7
                    )
                except asyncio.TimeoutError:
                    print(f"[!done DB] Timeout khi finish order {order_code}")
                except Exception as error:
                    print(
                        f"[!done DB] {order_code}: "
                        f"{type(error).__name__}: {error}"
                    )

            # Các việc nặng khác chạy nền, không chặn phản hồi chính.
            asyncio.create_task(
                self._done_background(
                    ctx,
                    order_info,
                    order_code,
                    product_name,
                    customer,
                    support_member,
                    support_row
                )
            )

        except Exception as error:
            import traceback
            traceback.print_exc()
            try:
                await ctx.send(
                    f"❌ Lỗi khi dùng `!done`: "
                    f"`{type(error).__name__}: {error}`"
                )
            except (discord.NotFound, discord.HTTPException):
                pass

    async def _done_background(
        self,
        ctx,
        order_info,
        order_code,
        product_name,
        customer,
        support_member,
        support_row
    ):
        """Tính lương, sửa embed #order và DM sau, không chặn !done."""
        if not order_info:
            return

        try:
            import web_db as wdb

            amt = int(order_info["amount"] or 0)
            commission = 5000 + (
                int(amt * 0.10) if amt >= 100000 else 0
            )

            def salary_work():
                conn = wdb.get_conn()
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM web_users WHERE discord_id=%s",
                    (str(ctx.author.id),)
                )
                web_user = cur.fetchone()
                conn.close()

                if web_user:
                    wdb.add_salary_record(
                        web_user["id"],
                        order_code,
                        commission,
                        f"Xử lý đơn {order_code} — {amt:,}đ",
                        role_in_order="admin"
                    )

                if support_row:
                    conn = wdb.get_conn()
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT * FROM web_users WHERE discord_id=%s",
                        (str(support_row["support_discord_id"]),)
                    )
                    support_web_user = cur.fetchone()
                    conn.close()

                    if support_web_user:
                        wdb.add_salary_record(
                            support_web_user["id"],
                            order_code,
                            commission,
                            f"Hỗ trợ đơn {order_code} — {amt:,}đ",
                            role_in_order="support"
                        )

            await asyncio.wait_for(
                asyncio.to_thread(salary_work),
                timeout=12
            )
        except Exception as error:
            print(f"[!done Salary] {type(error).__name__}: {error}")

        try:
            order_ch = ctx.guild.get_channel(config.ORDER_CHANNEL_ID)
            if order_ch:
                async for msg in order_ch.history(limit=50):
                    if msg.author == ctx.guild.me and msg.embeds:
                        embed_found = msg.embeds[0]
                        found = any(
                            order_code in (field.value or "")
                            for field in embed_found.fields
                        )
                        if found:
                            new_embed = discord.Embed(
                                title="📦 Đơn Hàng Mới",
                                color=config.COLOR_SUCCESS,
                                timestamp=msg.created_at
                            )
                            for field in embed_found.fields:
                                if field.name == "📌 Trạng thái":
                                    new_embed.add_field(
                                        name="📌 Trạng thái",
                                        value="✅ Hoàn tất",
                                        inline=field.inline
                                    )
                                else:
                                    new_embed.add_field(
                                        name=field.name,
                                        value=field.value,
                                        inline=field.inline
                                    )
                            new_embed.set_footer(text=config.BOT_FOOTER)
                            await msg.edit(embed=new_embed)
                            break
        except Exception as error:
            print(f"[!done Order Embed] {type(error).__name__}: {error}")

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
                dm_embed.add_field(
                    name="🧾 Mã đơn",
                    value=f"`{order_code}`",
                    inline=True
                )
                dm_embed.add_field(
                    name="🛍️ Sản phẩm",
                    value=product_name,
                    inline=True
                )
                dm_embed.set_footer(text=config.BOT_FOOTER)

                await customer.send(
                    embed=dm_embed,
                    view=TipView(support_member, ctx.author)
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

    # ── Error handlers ────────────────────────────────────────
    @cmd_order.error
    async def order_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Thiếu tên sản phẩm!\nCú pháp: `!order <tên sản phẩm>`", delete_after=8)

    @cmd_done.error
    async def done_error(self, ctx, error):
        import traceback
        traceback.print_exception(type(error), error, error.__traceback__)

        try:
            await ctx.send(
                f"❌ Không chạy được `!done`: `{type(error).__name__}: {error}`",
                delete_after=12
            )
        except (discord.NotFound, discord.HTTPException):
            print("[!done] Không thể gửi lỗi vì ticket không còn tồn tại.")

    @cmd_qr.error
    async def qr_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Thiếu số tiền!\nVD: `!qr 20k`, `!qr 1m`, `!qr 50000`", delete_after=8)


class WalletConfirmView(discord.ui.View):
    """Bước xác nhận cuối trước khi trừ tiền trong ví."""

    def __init__(self, parent_view, buyer_id: int, amount: int):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.buyer_id = int(buyer_id)
        self.amount = int(amount)
        self.finished = False

    @discord.ui.button(
        label="✅ Xác nhận thanh toán",
        style=discord.ButtonStyle.success,
        custom_id="wallet_confirm_payment",
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if interaction.user.id != self.buyer_id:
            return await interaction.response.send_message(
                "❌ Chỉ người mua của đơn này mới được xác nhận!",
                ephemeral=True,
            )

        if self.finished:
            return await interaction.response.send_message(
                "⚠️ Yêu cầu này đã được xử lý rồi.",
                ephemeral=True,
            )

        self.finished = True
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(view=self)

        try:
            result = await asyncio.to_thread(
                db.pay_order_with_wallet,
                self.parent_view.order_code,
                interaction.user.id,
                str(interaction.user),
            )
        except PermissionError:
            self.finished = False
            return await interaction.followup.send(
                "❌ Bạn không phải người mua của đơn này!",
                ephemeral=True,
            )
        except ValueError as error:
            self.finished = False
            error_text = str(error)

            if error_text.startswith("INSUFFICIENT_BALANCE:"):
                _, balance, needed = error_text.split(":", 2)
                balance = int(balance)
                needed = int(needed)
                missing = max(0, needed - balance)

                return await interaction.followup.send(
                    "❌ **Số dư ví không đủ!**\n\n"
                    f"💳 Số dư hiện tại: **{balance:,} VNĐ**\n"
                    f"🧾 Cần thanh toán: **{needed:,} VNĐ**\n"
                    f"📉 Còn thiếu: **{missing:,} VNĐ**".replace(",", "."),
                    ephemeral=True,
                )

            messages = {
                "ORDER_NOT_FOUND": "❌ Không tìm thấy đơn hàng này.",
                "ORDER_ALREADY_PAID": "⚠️ Đơn này đã được thanh toán trước đó.",
                "ORDER_CANCELLED": "❌ Đơn này đã bị hủy.",
                "INVALID_ORDER_AMOUNT": "❌ Số tiền của đơn không hợp lệ.",
            }
            return await interaction.followup.send(
                messages.get(error_text, f"❌ Không thể thanh toán: `{error_text}`"),
                ephemeral=True,
            )
        except Exception as error:
            self.finished = False
            import traceback
            traceback.print_exc()
            return await interaction.followup.send(
                f"❌ Lỗi thanh toán ví: `{type(error).__name__}: {error}`",
                ephemeral=True,
            )

        # Thanh toán thành công: khóa toàn bộ nút ở embed gốc.
        self.parent_view.paid = True
        for child in self.parent_view.children:
            child.disabled = True

        order_info = await asyncio.to_thread(
            db.get_order_by_channel,
            interaction.channel.id,
        )
        product_slug = get_product_slug(order_info, interaction.channel)
        ticket_number = get_ticket_number(interaction.channel)

        await safe_rename_ticket(
            interaction.channel,
            f"cho-xu-li-{product_slug}-{ticket_number}",
        )

        amount_fmt = f"{result['amount']:,}".replace(",", ".")
        before_fmt = f"{result['balance_before']:,}".replace(",", ".")
        after_fmt = f"{result['balance_after']:,}".replace(",", ".")

        success = discord.Embed(
            title="✅ Thanh toán bằng ví thành công",
            description=(
                f"{interaction.user.mention} đã thanh toán đơn bằng "
                "**Ví Love Store**.\n"
                "Staff có thể bắt đầu xử lý và giao sản phẩm."
            ),
            color=config.COLOR_SUCCESS,
            timestamp=datetime.now(),
        )
        success.add_field(
            name="🧾 Mã đơn",
            value=f"`{self.parent_view.order_code}`",
            inline=True,
        )
        success.add_field(
            name="💰 Đã thanh toán",
            value=f"**{amount_fmt} VNĐ**",
            inline=True,
        )
        success.add_field(
            name="👛 Số dư ví",
            value=f"{before_fmt} → **{after_fmt} VNĐ**",
            inline=False,
        )
        success.add_field(
            name="🔖 Mã giao dịch ví",
            value=f"`{result['transaction_code']}`",
            inline=True,
        )

        if result.get("discount_code"):
            saved_fmt = f"{result['discount_amount']:,}".replace(",", ".")
            success.add_field(
                name="🎟️ Mã giảm giá",
                value=(
                    f"`{result['discount_code']}` "
                    f"(-{saved_fmt} VNĐ)"
                ),
                inline=True,
            )

        success.set_footer(text=config.BOT_FOOTER)

        await interaction.followup.send(
            embed=success,
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
            ),
        )

        # Cố gắng sửa view của tin nhắn thanh toán gốc.
        if self.parent_view.message:
            try:
                await self.parent_view.message.edit(view=self.parent_view)
            except discord.HTTPException:
                pass

        self.stop()
        self.parent_view.stop()

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ):
        import traceback

        print(
            "[WalletConfirmView Error] "
            f"button={getattr(item, 'custom_id', 'unknown')} "
            f"user={getattr(interaction.user, 'id', 'unknown')} "
            f"channel={interaction.channel_id}"
        )
        traceback.print_exception(
            type(error),
            error,
            error.__traceback__,
        )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"❌ Lỗi xác nhận ví: "
                    f"`{type(error).__name__}: {error}`",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"❌ Lỗi xác nhận ví: "
                    f"`{type(error).__name__}: {error}`",
                    ephemeral=True,
                )
        except Exception:
            traceback.print_exc()

    @discord.ui.button(
        label="❌ Hủy",
        style=discord.ButtonStyle.secondary,
        custom_id="wallet_cancel_payment",
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if interaction.user.id != self.buyer_id:
            return await interaction.response.send_message(
                "❌ Chỉ người mua mới được hủy xác nhận này.",
                ephemeral=True,
            )

        self.finished = True
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content="Đã hủy thanh toán bằng ví.",
            embed=None,
            view=self,
        )
        self.stop()


class PaymentView(discord.ui.View):
    """
    Nút thanh toán trong ticket.

    Thứ tự hợp lý:
    1. Áp mã giảm giá (nếu có).
    2. Chọn ví hoặc lấy QR.
    3. Nếu chuyển khoản, bấm xác nhận đã chuyển.
    """

    def __init__(self, order_code: str, original_amount: int):
        super().__init__(timeout=900)
        self.order_code = order_code
        self.original_amount = int(original_amount)
        self.current_amount = int(original_amount)
        self.discounted = False
        self.discount_code = None
        self.discount_amount = 0
        self.paid = False
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        try:
            order_info = await asyncio.to_thread(
                db.get_order_by_channel,
                interaction.channel.id,
            )
        except Exception:
            order_info = None

        if not order_info:
            await interaction.response.send_message(
                "❌ Không tìm thấy đơn đang hoạt động trong ticket này.",
                ephemeral=True,
            )
            return False

        if int(order_info["user_id"]) != interaction.user.id:
            await interaction.response.send_message(
                "❌ Chỉ người mua của đơn này mới dùng được các nút thanh toán!",
                ephemeral=True,
            )
            return False

        if str(order_info.get("status") or "").lower() in (
            "paid",
            "done",
            "cancelled",
        ):
            await interaction.response.send_message(
                "⚠️ Đơn này đã thanh toán, hoàn tất hoặc bị hủy.",
                ephemeral=True,
            )
            return False

        self.current_amount = int(order_info.get("amount") or 0)
        self.discount_code = order_info.get("discount_code")
        self.discount_amount = int(order_info.get("discount_amount") or 0)
        self.discounted = bool(self.discount_code)
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ):
        import traceback

        print(
            "[PaymentView Error] "
            f"button={getattr(item, 'custom_id', 'unknown')} "
            f"user={getattr(interaction.user, 'id', 'unknown')} "
            f"channel={interaction.channel_id}"
        )
        traceback.print_exception(
            type(error),
            error,
            error.__traceback__,
        )

        message = (
            "❌ Có lỗi khi xử lý nút: "
            f"`{type(error).__name__}: {error}`"
        )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    message,
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    message,
                    ephemeral=True,
                )
        except Exception:
            traceback.print_exc()

    @discord.ui.button(
        label="🎟️ Áp mã giảm giá",
        style=discord.ButtonStyle.secondary,
        custom_id="enter_discount",
        row=0,
    )
    async def enter_discount(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if self.discounted:
            return await interaction.response.send_message(
                f"✅ Đơn này đã áp mã `{self.discount_code}` rồi!",
                ephemeral=True,
            )

        await interaction.response.send_modal(
            DiscountModal(
                self.order_code,
                self.current_amount,
                self,
            )
        )

    @discord.ui.button(
        label="👛 Thanh toán bằng ví",
        style=discord.ButtonStyle.success,
        custom_id="pay_with_wallet",
        row=0,
    )
    async def pay_with_wallet(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.defer(ephemeral=True)

        wallet = await asyncio.to_thread(
            db.get_wallet,
            interaction.user.id,
            str(interaction.user),
        )

        balance = int(wallet.get("balance") or 0)
        needed = int(self.current_amount)
        missing = max(0, needed - balance)

        if balance < needed:
            return await interaction.followup.send(
                "❌ **Số dư ví không đủ!**\n\n"
                f"💳 Số dư hiện tại: **{balance:,} VNĐ**\n"
                f"🧾 Cần thanh toán: **{needed:,} VNĐ**\n"
                f"📉 Còn thiếu: **{missing:,} VNĐ**".replace(",", "."),
                ephemeral=True,
            )

        amount_fmt = f"{needed:,}".replace(",", ".")
        balance_fmt = f"{balance:,}".replace(",", ".")
        after_fmt = f"{balance - needed:,}".replace(",", ".")

        embed = discord.Embed(
            title="👛 Xác nhận thanh toán bằng ví",
            description=(
                "Tiền sẽ được trừ ngay sau khi bạn xác nhận.\n"
                "Thao tác thành công sẽ không thể tự hoàn tác."
            ),
            color=config.COLOR_WARNING,
            timestamp=datetime.now(),
        )
        embed.add_field(
            name="💰 Giá đơn",
            value=f"**{amount_fmt} VNĐ**",
            inline=True,
        )
        embed.add_field(
            name="👛 Số dư hiện tại",
            value=f"**{balance_fmt} VNĐ**",
            inline=True,
        )
        embed.add_field(
            name="💳 Số dư sau thanh toán",
            value=f"**{after_fmt} VNĐ**",
            inline=False,
        )

        if self.discount_code:
            saved_fmt = f"{self.discount_amount:,}".replace(",", ".")
            embed.add_field(
                name="🎟️ Mã đang áp dụng",
                value=f"`{self.discount_code}` (-{saved_fmt} VNĐ)",
                inline=False,
            )

        embed.set_footer(text=config.BOT_FOOTER)

        await interaction.followup.send(
            embed=embed,
            view=WalletConfirmView(
                self,
                interaction.user.id,
                needed,
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="🏦 Lấy mã QR",
        style=discord.ButtonStyle.primary,
        custom_id="get_payment_qr",
        row=1,
    )
    async def get_payment_qr(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.defer(ephemeral=True)

        amount = int(self.current_amount)
        amount_fmt = f"{amount:,}".replace(",", ".")
        qr_url = make_qr_url(amount, self.order_code)

        embed = discord.Embed(
            title="🏦 Mã QR thanh toán",
            description=(
                "Quét mã dưới đây và giữ nguyên nội dung chuyển khoản.\n"
                "Sau khi chuyển xong, bấm **✅ Tôi đã chuyển khoản** "
                "ở tin nhắn thanh toán."
            ),
            color=config.COLOR_PRIMARY,
            timestamp=datetime.now(),
        )
        embed.add_field(
            name="💰 Số tiền",
            value=f"**{amount_fmt} VNĐ**",
            inline=True,
        )
        embed.add_field(
            name="📝 Nội dung CK",
            value=f"`{self.order_code}`",
            inline=True,
        )
        embed.set_image(url=qr_url)
        embed.set_footer(text=config.BOT_FOOTER)

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )

    @discord.ui.button(
        label="✅ Tôi đã chuyển khoản",
        style=discord.ButtonStyle.secondary,
        custom_id="confirm_bank_payment",
        row=1,
    )
    async def confirm_payment(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.defer(ephemeral=True)

        order_info = await asyncio.to_thread(
            db.get_order_by_channel,
            interaction.channel.id,
        )
        product_slug = get_product_slug(order_info, interaction.channel)
        ticket_number = get_ticket_number(interaction.channel)

        await safe_rename_ticket(
            interaction.channel,
            f"cho-xu-li-{product_slug}-{ticket_number}",
        )

        embed = discord.Embed(
            title="⏳ Khách đã báo chuyển khoản",
            description=(
                f"{interaction.user.mention} đã báo **đã chuyển khoản**.\n"
                "Staff vui lòng kiểm tra ngân hàng trước khi xử lý đơn."
            ),
            color=config.COLOR_WARNING,
            timestamp=datetime.now(),
        )
        embed.add_field(
            name="🧾 Mã đơn",
            value=f"`{self.order_code}`",
            inline=True,
        )
        embed.add_field(
            name="💰 Số tiền cần kiểm tra",
            value=f"**{self.current_amount:,} VNĐ**".replace(",", "."),
            inline=True,
        )
        embed.add_field(
            name="📁 Ticket",
            value=interaction.channel.mention,
            inline=False,
        )
        embed.set_footer(text=config.BOT_FOOTER)

        await interaction.followup.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False,
            ),
        )


class DiscountModal(discord.ui.Modal, title="🎟️ Áp mã giảm giá"):
    code = discord.ui.TextInput(
        label="Mã giảm giá",
        placeholder="VD: SALE10K",
        max_length=30,
    )

    def __init__(
        self,
        order_code: str,
        current_amount: int,
        view: PaymentView,
    ):
        super().__init__()
        self.order_code = order_code
        self.current_amount = int(current_amount)
        self.parent_view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            code = self.code.value.strip().upper()
            discount = await asyncio.to_thread(
                db.get_discount,
                code,
                interaction.user.id,
            )

            if not discount:
                return await interaction.response.send_message(
                    "❌ Mã không tồn tại hoặc bạn đã sử dụng mã này trước đó!",
                    ephemeral=True,
                )

            expires_at = discount.get("expires_at")
            if expires_at:
                if isinstance(expires_at, str):
                    expires = datetime.strptime(
                        expires_at[:10],
                        "%Y-%m-%d",
                    )
                else:
                    expires = datetime.combine(
                        expires_at,
                        datetime.min.time(),
                    )

                if datetime.now() > expires:
                    return await interaction.response.send_message(
                        "❌ Mã giảm giá đã hết hạn!",
                        ephemeral=True,
                    )

            result = await asyncio.to_thread(
                db.apply_order_discount,
                self.order_code,
                interaction.user.id,
                code,
                int(discount["amount"]),
            )

            self.parent_view.current_amount = result["new_amount"]
            self.parent_view.discounted = True
            self.parent_view.discount_code = result["discount_code"]
            self.parent_view.discount_amount = result["discount_amount"]

            # Khóa nút mã để khách nhìn là biết đã áp.
            for child in self.parent_view.children:
                if getattr(child, "custom_id", None) == "enter_discount":
                    child.disabled = True
                    child.label = "✅ Đã áp mã"
                    break

            old_fmt = f"{result['old_amount']:,}".replace(",", ".")
            saved_fmt = f"{result['discount_amount']:,}".replace(",", ".")
            new_fmt = f"{result['new_amount']:,}".replace(",", ".")

            embed = discord.Embed(
                title="✅ Áp dụng mã thành công",
                description=(
                    "Giá của đơn hàng đã được cập nhật.\n"
                    "Bây giờ bạn có thể thanh toán bằng ví hoặc lấy QR mới."
                ),
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now(),
            )
            embed.add_field(
                name="🎟️ Mã",
                value=f"`{result['discount_code']}`",
                inline=True,
            )
            embed.add_field(
                name="💰 Giá gốc",
                value=f"{old_fmt} VNĐ",
                inline=True,
            )
            embed.add_field(
                name="💸 Được giảm",
                value=f"**{saved_fmt} VNĐ**",
                inline=True,
            )
            embed.add_field(
                name="✅ Cần thanh toán",
                value=f"**{new_fmt} VNĐ**",
                inline=False,
            )
            embed.set_footer(text=config.BOT_FOOTER)

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )

            if self.parent_view.message:
                try:
                    await self.parent_view.message.edit(
                        view=self.parent_view,
                    )
                except discord.HTTPException:
                    pass

        except PermissionError:
            await interaction.response.send_message(
                "❌ Chỉ người mua mới được áp mã cho đơn này!",
                ephemeral=True,
            )
        except ValueError as error:
            messages = {
                "ORDER_NOT_FOUND": "❌ Không tìm thấy đơn hàng.",
                "ORDER_ALREADY_CLOSED": (
                    "⚠️ Đơn đã thanh toán, hoàn tất hoặc bị hủy."
                ),
                "DISCOUNT_ALREADY_APPLIED": (
                    "⚠️ Đơn này đã áp một mã giảm giá rồi."
                ),
                "INVALID_DISCOUNT": "❌ Mã giảm giá không hợp lệ.",
                "DISCOUNT_NOT_FOUND": "❌ Mã giảm giá không tồn tại.",
                "DISCOUNT_ALREADY_USED_BY_USER": (
                    "❌ Bạn đã sử dụng mã giảm giá này trước đó."
                ),
                "INVALID_DISCOUNT_AMOUNT": (
                    "❌ Giá trị mã giảm giá không hợp lệ."
                ),
            }
            await interaction.response.send_message(
                messages.get(str(error), f"❌ Không thể áp mã: `{error}`"),
                ephemeral=True,
            )
        except Exception as error:
            import traceback
            traceback.print_exc()

            if interaction.response.is_done():
                await interaction.followup.send(
                    f"❌ Lỗi: `{type(error).__name__}: {error}`",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"❌ Lỗi: `{type(error).__name__}: {error}`",
                    ephemeral=True,
                )


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

        import web_db as wdb
        conn = wdb.get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM web_users WHERE discord_id=%s",
            (str(target_member.id),)
        )
        web_user = cur.fetchone()
        conn.close()

        embed = discord.Embed(
            title=f"💝 Tip cho {role_label}",
            color=config.COLOR_PRIMARY
        )
        embed.add_field(name="👤 Người nhận", value=target_member.mention, inline=False)

        bank_info = None

        if bank_info:
            embed.description = "Quét QR hoặc chuyển khoản theo thông tin bên dưới:"
            embed.add_field(name="🏦 STK", value=bank_info, inline=False)
        else:
            embed.description = (
                f"{target_member.mention} chưa cập nhật thông tin nhận tip.\n"
                "Founder/Admin sẽ liên hệ để hỗ trợ bạn tip trực tiếp nhé! 💖"
            )
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