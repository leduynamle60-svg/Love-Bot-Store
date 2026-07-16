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
            embed.set_image(url=qr_url)
            embed.set_footer(text=config.BOT_FOOTER)

            view = PaymentView(order_code, amount)
            await ctx.send(embed=embed, view=view)
            await ctx.message.delete()

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


class PaymentView(discord.ui.View):
    """Nút thanh toán trong ticket: xác nhận đã chuyển + mã giảm giá."""

    def __init__(self, order_code: str, original_amount: int):
        super().__init__(timeout=300)
        self.order_code      = order_code
        self.original_amount = original_amount
        self.discounted      = False

    @discord.ui.button(label="✅ Xác nhận đã thanh toán", style=discord.ButtonStyle.success, custom_id="confirm_payment")
    async def confirm_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        order_info = db.get_order_by_channel(interaction.channel.id)
        product_slug = get_product_slug(order_info, interaction.channel)
        ticket_number = get_ticket_number(interaction.channel)

        await safe_rename_ticket(interaction.channel, f"cho-xu-li-{product_slug}-{ticket_number}")

        embed = discord.Embed(
            title="⏳ Khách đã xác nhận thanh toán",
            description=(
                f"{interaction.user.mention} đã bấm **Xác nhận đã thanh toán**.\n"
                "Staff vui lòng kiểm tra ngân hàng rồi xử lý đơn nhé."
            ),
            color=config.COLOR_WARNING,
            timestamp=datetime.now()
        )
        embed.add_field(name="🧾 Mã đơn", value=f"`{self.order_code}`", inline=True)
        embed.add_field(name="📁 Ticket", value=interaction.channel.mention, inline=True)
        embed.set_footer(text=config.BOT_FOOTER)

        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="🎟️ Nhập mã giảm giá", style=discord.ButtonStyle.secondary, custom_id="enter_discount")
    async def enter_discount(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DiscountModal(self.order_code, self.original_amount, self))


class DiscountModal(discord.ui.Modal, title="🎟️ Nhập mã giảm giá"):
    code = discord.ui.TextInput(
        label="Mã giảm giá",
        placeholder="VD: SALE10K",
        max_length=30
    )

    def __init__(self, order_code: str, original_amount: int, view: PaymentView):
        super().__init__()
        self.order_code      = order_code
        self.original_amount = original_amount
        self.parent_view     = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            code     = self.code.value.strip().upper()
            discount = db.get_discount(code)

            if not discount:
                return await interaction.response.send_message(
                    "❌ Mã không hợp lệ hoặc đã được sử dụng!", ephemeral=True
                )

            # Kiểm tra hết hạn
            if discount["expires_at"]:
                expires = datetime.strptime(discount["expires_at"], "%Y-%m-%d")
                if datetime.now() > expires:
                    return await interaction.response.send_message(
                        "❌ Mã đã hết hạn!", ephemeral=True
                    )

            # Tính giá sau giảm
            discount_amt = discount["amount"]
            new_amount   = max(0, self.original_amount - discount_amt)
            amount_fmt   = f"{new_amount:,}".replace(",", ".")
            saved_fmt    = f"{discount_amt:,}".replace(",", ".")

            # Đánh dấu mã đã dùng
            db.use_discount(code)

            # Cập nhật amount trong DB
            conn = db.get_conn()
            cur = conn.cursor()
            cur.execute(
                "UPDATE orders SET amount=%s WHERE order_code=%s",
                (new_amount, self.order_code)
            )
            conn.commit()
            conn.close()

            # Tạo QR mới với giá mới
            qr_url = make_qr_url(new_amount, self.order_code)

            embed = discord.Embed(
                title="✅ Áp dụng mã thành công!",
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now()
            )
            embed.add_field(name="🎟️ Mã",        value=f"`{code}`",              inline=True)
            embed.add_field(name="💸 Giảm",       value=f"{saved_fmt} VNĐ",      inline=True)
            embed.add_field(name="💰 Còn lại",    value=f"**{amount_fmt} VNĐ**", inline=True)
            embed.add_field(name="⚠️ Lưu ý",
                            value="Quét QR bên dưới để thanh toán số tiền mới nhé!",
                            inline=False)
            embed.set_image(url=qr_url)
            embed.set_footer(text=config.BOT_FOOTER)

            self.parent_view.discounted = True
            await interaction.response.send_message(embed=embed)

        except Exception as e:
            import traceback
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)


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