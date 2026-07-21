"""
cogs/slash.py — Slash commands cho Love Bot Store
"""
import urllib.parse
import os
import secrets
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db



def has_ticket_manage_permission(member: discord.Member) -> bool:
    role_ids = {role.id for role in member.roles}
    return (
        config.SUPPORT_ROLE_ID in role_ids
        or config.ADMIN_ROLE_ID in role_ids
        or config.FOUNDER_ROLE_ID in role_ids
        or member.guild_permissions.administrator
    )


def has_admin_ticket_permission(member: discord.Member) -> bool:
    role_ids = {role.id for role in member.roles}
    return (
        config.ADMIN_ROLE_ID in role_ids
        or config.FOUNDER_ROLE_ID in role_ids
        or member.guild_permissions.administrator
    )




def is_founder(member: discord.Member) -> bool:
    return (
        any(role.id == config.FOUNDER_ROLE_ID for role in member.roles)
        or member.guild_permissions.administrator
    )


def is_admin(member: discord.Member) -> bool:
    return (
        is_founder(member)
        or any(role.id == config.ADMIN_ROLE_ID for role in member.roles)
    )


def is_support(member: discord.Member) -> bool:
    return (
        is_admin(member)
        or any(role.id == config.SUPPORT_ROLE_ID for role in member.roles)
    )


def privileged_rank(member: discord.Member) -> int:
    """0=member/buyer, 1=support, 2=admin, 3=founder."""
    if is_founder(member):
        return 3
    if any(role.id == config.ADMIN_ROLE_ID for role in member.roles):
        return 2
    if any(role.id == config.SUPPORT_ROLE_ID for role in member.roles):
        return 1
    return 0


def parse_money(text: str) -> int:
    value = text.strip().lower().replace(" ", "").replace(",", ".")
    if value.endswith("k"):
        amount = int(float(value[:-1]) * 1_000)
    elif value.endswith("m"):
        amount = int(float(value[:-1]) * 1_000_000)
    else:
        amount = int(float(value.replace(".", "")))

    if amount <= 0:
        raise ValueError("Số tiền phải lớn hơn 0")
    if amount > 1_000_000_000:
        raise ValueError("Số tiền vượt quá giới hạn 1 tỷ")
    return amount




def get_store_bank_config():
    """
    Đọc tài khoản nhận tiền của Love Store từ config.py hoặc biến môi trường.

    Tên khuyến nghị:
      STORE_BANK_NAME
      STORE_BANK_BIN
      STORE_BANK_ACCOUNT_NUMBER
      STORE_BANK_ACCOUNT_NAME
    """
    def pick(*names):
        for name in names:
            value = getattr(config, name, None) or os.getenv(name)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    bank_name = pick(
        "STORE_BANK_NAME",
        "BANK_NAME",
        "PAYMENT_BANK_NAME",
    )
    bank_bin = pick(
        "STORE_BANK_BIN",
        "BANK_BIN",
        "PAYMENT_BANK_BIN",
    )
    account_number = pick(
        "STORE_BANK_ACCOUNT_NUMBER",
        "BANK_ACCOUNT_NUMBER",
        "ACCOUNT_NUMBER",
        "PAYMENT_ACCOUNT_NUMBER",
    ).replace(" ", "")
    account_name = pick(
        "STORE_BANK_ACCOUNT_NAME",
        "BANK_ACCOUNT_NAME",
        "ACCOUNT_NAME",
        "PAYMENT_ACCOUNT_NAME",
    ).upper()

    return {
        "bank_name": bank_name,
        "bank_bin": bank_bin,
        "account_number": account_number,
        "account_name": account_name,
    }


def money_fmt(amount: int) -> str:
    return f"{int(amount):,}".replace(",", ".") + " VNĐ"


async def send_wallet_log(
    bot: commands.Bot,
    *,
    title: str,
    color: int,
    fields: list[tuple[str, str, bool]],
    description: str | None = None,
):
    """Gửi embed log ví; lỗi log không làm hỏng giao dịch chính."""
    channel_id = int(
        getattr(config, "WALLET_LOG_CHANNEL_ID", 0)
        or os.getenv("WALLET_LOG_CHANNEL_ID", "0")
        or 0
    )
    if not channel_id:
        print("[Wallet Log] Chưa cấu hình WALLET_LOG_CHANNEL_ID")
        return False

    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(),
        )
        for field_name, field_value, inline in fields:
            embed.add_field(
                name=str(field_name)[:256],
                value=str(field_value)[:1024] or "—",
                inline=inline,
            )

        embed.set_footer(text=getattr(config, "BOT_FOOTER", "Love Store"))
        message = await channel.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return message
    except Exception as error:
        print(f"[Wallet Log] {type(error).__name__}: {error}")
        return None


def ticket_number_from_channel(channel: discord.TextChannel) -> str:
    name = channel.name
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 4:
        return parts[1]
    return "—"


BANK_BINS = {
    "MB Bank": "970422",
    "VPBank": "970432",
    "Vietcombank": "970436",
    "Techcombank": "970407",
    "ACB": "970416",
    "BIDV": "970418",
    "VietinBank": "970415",
    "Sacombank": "970403",
    "TPBank": "970423",
    "VIB": "970441",
    "SHB": "970443",
    "MSB": "970426",
    "OCB": "970448",
    "SeABank": "970440",
    "Eximbank": "970431",
    "HDBank": "970437",
    "Agribank": "970405",
    "Nam A Bank": "970428",
    "PVcomBank": "970412",
    "Bac A Bank": "970409",
    "VietBank": "970433",
    "BaoViet Bank": "970438",
    "NCB": "970419",
    "KienlongBank": "970452",
    "ABBank": "970425",
}


class SlashCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="bxh",
        description="🏆 Bảng xếp hạng người mua trong tháng"
    )
    async def bxh(self, interaction: discord.Interaction):
        now = datetime.now()
        month = now.month
        year = now.year

        conn = db.get_conn_dict()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                LOWER(TRIM(username)) AS buyer_key,
                MIN(username) AS username,
                COUNT(*) AS total_orders,
                COALESCE(SUM(amount), 0) AS total_spent
            FROM orders
            WHERE status IN ('paid', 'done')
              AND EXTRACT(MONTH FROM created_at) = %s
              AND EXTRACT(YEAR FROM created_at) = %s
              AND username IS NOT NULL
              AND TRIM(username) <> ''
            GROUP BY LOWER(TRIM(username))
            ORDER BY total_spent DESC, total_orders DESC
            LIMIT 10
            """,
            (month, year)
        )
        rows = cur.fetchall()
        conn.close()

        embed = discord.Embed(
            title=f"🏆 BXH Người Mua Tháng {month}/{year}",
            color=config.COLOR_PRIMARY,
            timestamp=datetime.now()
        )

        if not rows:
            embed.description = "Chưa có đơn hàng nào trong tháng này!"
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines = []

            total_customers = len(rows)
            leaderboard_revenue = sum(
                int(row["total_spent"] or 0)
                for row in rows
            )
            revenue_text = f"{leaderboard_revenue:,}".replace(",", ".")

            lines.append(
                f"👥 **{total_customers} khách hàng** • "
                f"💰 **Tổng doanh thu BXH: {revenue_text} VNĐ**"
            )
            lines.append("")

            for index, row in enumerate(rows):
                rank = medals[index] if index < 3 else f"#{index + 1}"
                name = row["username"]
                order_count = int(row["total_orders"] or 0)
                spent = f"{int(row['total_spent'] or 0):,}".replace(",", ".")

                lines.append(
                    f"{rank} **{name}** — "
                    f"{order_count} đơn — {spent} VNĐ"
                )

            embed.description = "\n".join(lines)

        embed.set_footer(text=config.BOT_FOOTER)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="myorders",
        description="📦 Xem thống kê đơn hàng của bạn"
    )
    async def myorders(self, interaction: discord.Interaction):
        conn = db.get_conn_dict()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COUNT(*) AS total_orders,
                COALESCE(
                    SUM(amount) FILTER (
                        WHERE status IN ('paid', 'done')
                    ),
                    0
                ) AS total_spent
            FROM orders
            WHERE user_id=%s
            """,
            (interaction.user.id,)
        )
        summary = cur.fetchone()
        conn.close()

        total_orders = int(summary["total_orders"] if summary else 0)
        total_spent = summary["total_spent"] if summary else 0

        embed = discord.Embed(
            title=f"📦 Đơn hàng của {interaction.user.display_name}",
            description=(
                f"💵 **Tổng chi tiêu:** {money_fmt(total_spent)}\n"
                f"📦 **Tổng số đơn hàng:** {total_orders}"
            ),
            color=config.COLOR_INFO,
            timestamp=datetime.now()
        )

        if total_orders == 0:
            embed.description = (
                "Bạn chưa có đơn hàng nào!\n\n"
                f"💵 **Tổng chi tiêu:** {money_fmt(0)}\n"
                "📦 **Tổng số đơn hàng:** 0"
            )

        embed.set_footer(text=config.BOT_FOOTER)
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="checkticket",
        description="🎫 Xem tất cả ticket đang mở và tự dọn ticket rác"
    )
    async def checkticket(self, interaction: discord.Interaction):
        if not has_ticket_manage_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ Chỉ Support/Admin/Founder mới dùng được lệnh này!",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        rows = db.get_all_open_tickets()
        active = []
        stale_count = 0

        for row in rows:
            channel = interaction.guild.get_channel(row["channel_id"])

            if channel is None:
                db.close_ticket(row["channel_id"])
                stale_count += 1
                continue

            member = interaction.guild.get_member(row["user_id"])
            status = row["status"] or "pending"

            status_map = {
                "pending": "⏳ Đang chờ",
                "processing": "🔄 Đang xử lý",
                "paid": "💳 Đã thanh toán",
                "done": "✅ Hoàn tất — nên đóng",
                "cancelled": "❌ Đã hủy — nên đóng",
            }

            active.append(
                {
                    "row": row,
                    "channel": channel,
                    "member": member,
                    "status_text": status_map.get(status, status),
                }
            )

        embed = discord.Embed(
            title="🎫 Danh sách ticket đang mở",
            color=config.COLOR_INFO,
            timestamp=datetime.now()
        )

        if not active:
            embed.description = "Hiện không còn ticket nào đang mở."
            if stale_count:
                embed.description += (
                    f"\n\n🧹 Đã tự dọn **{stale_count} ticket rác**."
                )
        else:
            embed.description = f"Đang có **{len(active)} ticket** còn hoạt động."
            if stale_count:
                embed.description += (
                    f"\n🧹 Đã tự dọn **{stale_count} ticket rác**."
                )

            for item in active[:25]:
                row = item["row"]
                channel = item["channel"]
                member = item["member"]

                customer = (
                    member.mention
                    if member
                    else f"`{row['user_id']}`"
                )

                ticket_number = (
                    row["ticket_number"]
                    or ticket_number_from_channel(channel)
                )

                # Ticket hỗ trợ không có đơn hàng và không cần hiển thị
                # mã đơn/sản phẩm.
                is_support_ticket = channel.name.startswith("support-")

                if is_support_ticket:
                    field_value = (
                        f"🎟️ Mã ticket: `{ticket_number}`\n"
                        f"👤 Khách: {customer}\n"
                        f"📍 Loại: **Hỗ trợ**\n"
                        f"📌 Trạng thái: **⏳ Đang chờ hỗ trợ**\n"
                        f"🔗 {channel.mention}"
                    )
                else:
                    order_code = row["order_code"] or "Chưa có"
                    product = row["product_name"] or "Chưa order"

                    field_value = (
                        f"🎟️ Mã ticket: `{ticket_number}`\n"
                        f"👤 Khách: {customer}\n"
                        f"📍 Loại: **Mua hàng**\n"
                        f"🧾 Mã đơn: `{order_code}`\n"
                        f"🛍️ Sản phẩm: `{product}`\n"
                        f"📌 Trạng thái: **{item['status_text']}**\n"
                        f"🔗 {channel.mention}"
                    )

                embed.add_field(
                    name=f"#{channel.name}",
                    value=field_value,
                    inline=False
                )

            if len(active) > 25:
                embed.set_footer(
                    text=f"Chỉ hiển thị 25/{len(active)} ticket"
                )
            else:
                embed.set_footer(text=config.BOT_FOOTER)

        await interaction.followup.send(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="ticketinfo",
        description="🔎 Xem chi tiết ticket theo mã 4 số"
    )
    @app_commands.describe(ticket_number="Mã ticket 4 số, ví dụ 3591")
    async def ticketinfo(
        self,
        interaction: discord.Interaction,
        ticket_number: str
    ):
        if not has_ticket_manage_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ Chỉ Support/Admin/Founder mới dùng được lệnh này!",
                ephemeral=True
            )

        ticket_number = ticket_number.strip()

        if not ticket_number.isdigit() or len(ticket_number) != 4:
            return await interaction.response.send_message(
                "❌ Mã ticket phải gồm đúng 4 chữ số!",
                ephemeral=True
            )

        target_channel = None

        for channel in interaction.guild.text_channels:
            if channel.name.endswith(f"-{ticket_number}"):
                target_channel = channel
                break

        if target_channel is None:
            return await interaction.response.send_message(
                f"❌ Không tìm thấy kênh ticket có mã `{ticket_number}`.",
                ephemeral=True
            )

        ticket_row = db.get_ticket_by_channel(target_channel.id)
        order = db.get_order_by_channel_any(target_channel.id)

        if not ticket_row and not order:
            return await interaction.response.send_message(
                "⚠️ Kênh tồn tại nhưng không tìm thấy dữ liệu trong database.",
                ephemeral=True
            )

        user_id = (
            ticket_row["user_id"]
            if ticket_row
            else order["user_id"]
        )
        member = interaction.guild.get_member(user_id)

        order_code = (
            order["order_code"]
            if order
            else ticket_row["order_code"]
        )
        product = order["product_name"] if order else "Chưa order"
        status = order["status"] if order else "pending"

        status_map = {
            "pending": "⏳ Đang chờ",
            "processing": "🔄 Đang xử lý",
            "paid": "💳 Đã thanh toán",
            "done": "✅ Hoàn tất",
            "cancelled": "❌ Đã hủy",
        }

        embed = discord.Embed(
            title=f"🔎 Ticket #{ticket_number}",
            color=config.COLOR_INFO,
            timestamp=datetime.now()
        )
        embed.add_field(
            name="📁 Kênh",
            value=target_channel.mention,
            inline=False
        )
        embed.add_field(
            name="👤 Khách",
            value=member.mention if member else f"`{user_id}`",
            inline=True
        )
        embed.add_field(
            name="🧾 Mã đơn",
            value=f"`{order_code or 'Chưa có'}`",
            inline=True
        )
        embed.add_field(
            name="🛍️ Sản phẩm",
            value=product,
            inline=False
        )
        embed.add_field(
            name="📌 Trạng thái",
            value=status_map.get(status, status),
            inline=True
        )

        if order:
            embed.add_field(
                name="🎧 Người nhận đơn",
                value=order["support_name"] or "—",
                inline=True
            )
            embed.add_field(
                name="⚙️ Người xử lý",
                value=order["processor_name"] or "—",
                inline=True
            )

        embed.set_footer(text=config.BOT_FOOTER)

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="clearticket",
        description="🧹 Xóa dữ liệu ticket bị kẹt của một thành viên"
    )
    @app_commands.describe(member="Người đang bị báo còn ticket")
    async def clearticket(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):
        if not has_admin_ticket_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ Chỉ Admin/Founder mới dùng được lệnh này!",
                ephemeral=True
            )

        deleted = db.clear_tickets_by_user(member.id)

        await interaction.response.send_message(
            (
                f"✅ Đã xóa **{deleted} dữ liệu ticket** của "
                f"{member.mention}.\n"
                "Người đó có thể tạo ticket mới."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="closeticket",
        description="🔒 Đóng và xóa ticket theo mã 4 số"
    )
    @app_commands.describe(ticket_number="Mã ticket 4 số, ví dụ 3591")
    async def closeticket(
        self,
        interaction: discord.Interaction,
        ticket_number: str
    ):
        if not has_admin_ticket_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ Chỉ Admin/Founder mới dùng được lệnh này!",
                ephemeral=True
            )

        ticket_number = ticket_number.strip()

        if not ticket_number.isdigit() or len(ticket_number) != 4:
            return await interaction.response.send_message(
                "❌ Mã ticket phải gồm đúng 4 chữ số!",
                ephemeral=True
            )

        target_channel = None

        for channel in interaction.guild.text_channels:
            if channel.name.endswith(f"-{ticket_number}"):
                target_channel = channel
                break

        if target_channel is None:
            return await interaction.response.send_message(
                f"❌ Không tìm thấy ticket có mã `{ticket_number}`.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        db.close_ticket(target_channel.id)

        channel_name = target_channel.name

        await interaction.followup.send(
            f"✅ Đang đóng `#{channel_name}`...",
            ephemeral=True
        )

        try:
            await target_channel.send(
                f"🔒 Ticket được đóng từ xa bởi {interaction.user.mention}."
            )
        except discord.HTTPException:
            pass

        await target_channel.delete(
            reason=f"Đóng từ xa bởi {interaction.user}"
        )



    @app_commands.command(
        name="addroleticket",
        description="➕ Cho phép một role truy cập ticket hiện tại"
    )
    @app_commands.describe(
        role="Role cần thêm quyền xem và nhắn trong ticket"
    )
    async def addroleticket(
        self,
        interaction: discord.Interaction,
        role: discord.Role
    ):
        if not has_ticket_manage_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ Chỉ Support/Admin/Founder mới dùng được lệnh này!",
                ephemeral=True
            )

        channel = interaction.channel

        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "❌ Lệnh này chỉ dùng được trong kênh ticket!",
                ephemeral=True
            )

        # Chỉ cho dùng trong kênh có dữ liệu ticket/order.
        try:
            is_ticket = bool(
                db.get_ticket_by_channel(channel.id)
                or db.get_order_by_channel_any(channel.id)
            )
        except Exception:
            is_ticket = False

        if not is_ticket:
            return await interaction.response.send_message(
                "❌ Kênh này không phải ticket đang được hệ thống quản lý!",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        try:
            await channel.set_permissions(
                role,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                reason=f"Thêm role vào ticket bởi {interaction.user}"
            )

            await interaction.followup.send(
                f"✅ Đã cho role {role.mention} truy cập {channel.mention}.",
                ephemeral=True
            )

            try:
                await channel.send(
                    f"➕ {interaction.user.mention} đã thêm {role.mention} vào ticket."
                )
            except discord.HTTPException:
                pass

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Bot thiếu quyền **Manage Channels / Quản lý kênh**!",
                ephemeral=True
            )
        except Exception as error:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ Lỗi `/addroleticket`: `{type(error).__name__}: {error}`",
                ephemeral=True
            )

    @app_commands.command(
        name="addbank",
        description="🏦 Lưu hoặc cập nhật thông tin ngân hàng của bạn"
    )
    @app_commands.describe(
        bank_name="Chọn ngân hàng",
        account_number="Số tài khoản",
        account_name="Tên chủ tài khoản"
    )
    @app_commands.choices(
        bank_name=[
            app_commands.Choice(name="MB Bank", value="MB Bank"),
            app_commands.Choice(name="VPBank", value="VPBank"),
            app_commands.Choice(name="Vietcombank", value="Vietcombank"),
            app_commands.Choice(name="Techcombank", value="Techcombank"),
            app_commands.Choice(name="ACB", value="ACB"),
            app_commands.Choice(name="BIDV", value="BIDV"),
            app_commands.Choice(name="VietinBank", value="VietinBank"),
            app_commands.Choice(name="Sacombank", value="Sacombank"),
            app_commands.Choice(name="TPBank", value="TPBank"),
            app_commands.Choice(name="VIB", value="VIB"),
            app_commands.Choice(name="SHB", value="SHB"),
            app_commands.Choice(name="MSB", value="MSB"),
            app_commands.Choice(name="OCB", value="OCB"),
            app_commands.Choice(name="SeABank", value="SeABank"),
            app_commands.Choice(name="Eximbank", value="Eximbank"),
            app_commands.Choice(name="HDBank", value="HDBank"),
            app_commands.Choice(name="Agribank", value="Agribank"),
            app_commands.Choice(name="Nam A Bank", value="Nam A Bank"),
            app_commands.Choice(name="PVcomBank", value="PVcomBank"),
            app_commands.Choice(name="Bac A Bank", value="Bac A Bank"),
            app_commands.Choice(name="VietBank", value="VietBank"),
            app_commands.Choice(name="BaoViet Bank", value="BaoViet Bank"),
            app_commands.Choice(name="NCB", value="NCB"),
            app_commands.Choice(name="KienlongBank", value="KienlongBank"),
            app_commands.Choice(name="ABBank", value="ABBank"),
        ]
    )
    async def addbank(
        self,
        interaction: discord.Interaction,
        bank_name: app_commands.Choice[str],
        account_number: str,
        account_name: str
    ):
        if not has_ticket_manage_permission(interaction.user):
            return await interaction.response.send_message(
                "❌ Chỉ Support/Admin/Founder mới được lưu thông tin ngân hàng!",
                ephemeral=True
            )

        selected_bank = bank_name.value
        account_number = account_number.replace(" ", "").strip()
        account_name = account_name.strip().upper()
        bank_bin = BANK_BINS.get(selected_bank)

        if not account_number or not account_name:
            return await interaction.response.send_message(
                "❌ Vui lòng nhập đầy đủ số tài khoản và tên chủ tài khoản!",
                ephemeral=True
            )

        if not account_number.isdigit():
            return await interaction.response.send_message(
                "❌ Số tài khoản chỉ được chứa chữ số!",
                ephemeral=True
            )

        db.upsert_bank_account(
            discord_id=interaction.user.id,
            bank_name=selected_bank,
            bank_bin=bank_bin,
            account_number=account_number,
            account_name=account_name,
        )

        embed = discord.Embed(
            title="✅ Đã lưu thông tin ngân hàng",
            color=config.COLOR_SUCCESS,
            timestamp=datetime.now()
        )
        embed.add_field(
            name="🏦 Ngân hàng",
            value=selected_bank,
            inline=True
        )
        embed.add_field(
            name="💳 Số tài khoản",
            value=f"`{account_number}`",
            inline=True
        )
        embed.add_field(
            name="👤 Chủ tài khoản",
            value=account_name,
            inline=False
        )
        embed.add_field(
            name="🔢 BIN tự động",
            value=f"`{bank_bin}`",
            inline=True
        )
        embed.set_footer(
            text="Bot đã tự nhận BIN theo ngân hàng đã chọn."
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="infobank",
        description="🏦 Xem thông tin ngân hàng đã lưu"
    )
    @app_commands.describe(
        member="Xem thông tin của nhân viên khác (chỉ Admin/Founder)"
    )
    async def infobank(
        self,
        interaction: discord.Interaction,
        member: discord.Member = None
    ):
        target = member or interaction.user

        if target.id != interaction.user.id:
            if not has_admin_ticket_permission(interaction.user):
                return await interaction.response.send_message(
                    "❌ Chỉ Admin/Founder mới được xem thông tin ngân hàng của người khác!",
                    ephemeral=True
                )

        await interaction.response.defer(ephemeral=True)

        try:
            bank = db.get_bank_account(target.id)

            if not bank:
                message = (
                    f"❌ {target.mention} chưa lưu thông tin ngân hàng."
                    if target.id != interaction.user.id
                    else "❌ Bạn chưa lưu thông tin ngân hàng. Dùng `/addbank` trước nhé!"
                )
                return await interaction.followup.send(
                    message,
                    ephemeral=True
                )

            account_name = str(bank.get("account_name") or "")
            account_number = str(bank.get("account_number") or "")
            bank_bin = str(bank.get("bank_bin") or "")
            encoded_name = urllib.parse.quote(account_name)

            embed = discord.Embed(
                title=f"🏦 Thông tin ngân hàng — {target.display_name}",
                color=config.COLOR_INFO,
                timestamp=datetime.now()
            )
            embed.add_field(
                name="🏦 Ngân hàng",
                value=bank.get("bank_name") or "Không rõ",
                inline=True
            )
            embed.add_field(
                name="💳 Số tài khoản",
                value=f"`{account_number}`",
                inline=True
            )
            embed.add_field(
                name="👤 Chủ tài khoản",
                value=account_name or "Không rõ",
                inline=False
            )

            if bank_bin and account_number:
                qr_url = (
                    "https://img.vietqr.io/image/"
                    f"{bank_bin}-{account_number}-compact2.png"
                    f"?accountName={encoded_name}"
                )
                embed.add_field(
                    name="🔢 BIN",
                    value=f"`{bank_bin}`",
                    inline=True
                )
                embed.set_image(url=qr_url)
            else:
                embed.add_field(
                    name="ℹ️ QR",
                    value="Chưa đủ BIN hoặc số tài khoản để tạo QR.",
                    inline=False
                )

            embed.set_footer(text=config.BOT_FOOTER)

            await interaction.followup.send(
                embed=embed,
                ephemeral=True
            )

        except Exception as error:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ Lỗi `/infobank`: `{type(error).__name__}: {error}`",
                ephemeral=True
            )

    @app_commands.command(
        name="qr",
        description="💳 Tạo mã QR thanh toán ở bất kỳ kênh nào"
    )
    @app_commands.describe(
        amount="Số tiền, ví dụ 20k, 50k, 1m hoặc 50000",
        content="Nội dung chuyển khoản",
        member="Dùng tài khoản ngân hàng của người khác (Admin/Founder)"
    )
    async def qr(
        self,
        interaction: discord.Interaction,
        amount: str,
        content: str = "LOVE STORE",
        member: discord.Member = None
    ):
        target = member or interaction.user

        if target.id != interaction.user.id:
            if not has_admin_ticket_permission(interaction.user):
                return await interaction.response.send_message(
                    "❌ Chỉ Admin/Founder mới được tạo QR từ ngân hàng của người khác!",
                    ephemeral=True
                )

        await interaction.response.defer()

        try:
            amount_text = amount.strip().lower().replace(",", ".")

            if amount_text.endswith("k"):
                amount_value = int(float(amount_text[:-1]) * 1_000)
            elif amount_text.endswith("m"):
                amount_value = int(float(amount_text[:-1]) * 1_000_000)
            else:
                amount_value = int(float(amount_text))

            if amount_value <= 0:
                return await interaction.followup.send(
                    "❌ Số tiền phải lớn hơn 0!",
                    ephemeral=True
                )

            bank = db.get_bank_account(target.id)

            if not bank:
                return await interaction.followup.send(
                    (
                        f"❌ {target.mention} chưa lưu thông tin ngân hàng bằng `/addbank`."
                        if target.id != interaction.user.id
                        else "❌ Bạn chưa lưu thông tin ngân hàng. Dùng `/addbank` trước nhé!"
                    ),
                    ephemeral=True
                )

            bank_name = str(bank.get("bank_name") or "Không rõ")
            bank_bin = str(bank.get("bank_bin") or "")
            account_number = str(bank.get("account_number") or "")
            account_name = str(bank.get("account_name") or "")
            transfer_content = content.strip()[:50] or "LOVE STORE"

            if not bank_bin or not account_number:
                return await interaction.followup.send(
                    "❌ Tài khoản ngân hàng này chưa đủ BIN hoặc số tài khoản để tạo QR!",
                    ephemeral=True
                )

            qr_url = (
                "https://img.vietqr.io/image/"
                f"{bank_bin}-{account_number}-compact2.png"
                f"?amount={amount_value}"
                f"&addInfo={urllib.parse.quote(transfer_content)}"
                f"&accountName={urllib.parse.quote(account_name)}"
            )

            amount_fmt = f"{amount_value:,}".replace(",", ".")

            embed = discord.Embed(
                title="💳 Mã QR Thanh Toán",
                description="Quét mã QR bên dưới để thanh toán nhanh.",
                color=config.COLOR_PRIMARY,
                timestamp=datetime.now()
            )
            embed.add_field(
                name="🏦 Ngân hàng",
                value=bank_name,
                inline=True
            )
            embed.add_field(
                name="💳 Số tài khoản",
                value=f"`{account_number}`",
                inline=True
            )
            embed.add_field(
                name="👤 Chủ tài khoản",
                value=account_name,
                inline=False
            )
            embed.add_field(
                name="💰 Số tiền",
                value=f"**{amount_fmt} VNĐ**",
                inline=True
            )
            embed.add_field(
                name="📝 Nội dung CK",
                value=f"`{transfer_content}`",
                inline=True
            )
            embed.set_image(url=qr_url)
            embed.set_footer(
                text=f"Tạo bởi {interaction.user.display_name} • {config.BOT_FOOTER}"
            )

            await interaction.followup.send(embed=embed)

        except ValueError:
            await interaction.followup.send(
                "❌ Số tiền không hợp lệ! Ví dụ: `20k`, `1m`, `50000`.",
                ephemeral=True
            )
        except Exception as error:
            import traceback
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ Lỗi `/qr`: `{type(error).__name__}: {error}`",
                ephemeral=True
            )


    @app_commands.command(
        name="vitien",
        description="💰 Kiểm tra số dư ví Love Store"
    )
    async def vitien(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            wallet = db.get_wallet(
                interaction.user.id,
                interaction.user.display_name,
            )

            embed = discord.Embed(
                title=f"💰 Ví Love Store — {interaction.user.display_name}",
                color=config.COLOR_INFO,
                timestamp=datetime.now()
            )
            embed.add_field(
                name="💵 Số dư hiện tại",
                value=f"**{money_fmt(wallet['balance'])}**",
                inline=False
            )
            embed.add_field(
                name="📥 Tổng đã nạp",
                value=money_fmt(wallet["total_deposit"]),
                inline=True
            )
            embed.set_footer(text=config.BOT_FOOTER)

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as error:
            await interaction.followup.send(
                f"❌ Không thể tải ví: `{type(error).__name__}: {error}`",
                ephemeral=True
            )

    @app_commands.command(
        name="naptienvaovi",
        description="📥 Tạo yêu cầu nạp tiền vào ví Love Store"
    )
    @app_commands.describe(
        amount="Số tiền muốn nạp, ví dụ 20k, 50k hoặc 100000"
    )
    async def naptienvaovi(
        self,
        interaction: discord.Interaction,
        amount: str
    ):
        await interaction.response.defer(ephemeral=True)

        try:
            amount_value = parse_money(amount)
            short_amount = (
                f"{amount_value // 1_000}K"
                if amount_value % 1_000 == 0 and amount_value < 1_000_000
                else str(amount_value)
            )
            random_code = secrets.randbelow(9000) + 1000
            reference_code = f"NAPTIEN{short_amount}-{random_code}"

            bank = get_store_bank_config()

            missing = [
                key for key in (
                    "bank_name",
                    "bank_bin",
                    "account_number",
                    "account_name",
                )
                if not bank[key]
            ]
            if missing:
                return await interaction.followup.send(
                    (
                        "❌ Chưa cấu hình đủ tài khoản nhận tiền của Love Store.\n"
                        "Cần các biến: `STORE_BANK_NAME`, `STORE_BANK_BIN`, "
                        "`STORE_BANK_ACCOUNT_NUMBER`, `STORE_BANK_ACCOUNT_NAME`."
                    ),
                    ephemeral=True
                )

            request = db.create_deposit_request(
                discord_id=interaction.user.id,
                username=interaction.user.display_name,
                amount=amount_value,
                reference_code=reference_code,
            )

            qr_url = (
                "https://img.vietqr.io/image/"
                f"{bank['bank_bin']}-{bank['account_number']}-compact2.png"
                f"?amount={amount_value}"
                f"&addInfo={urllib.parse.quote(reference_code)}"
                f"&accountName={urllib.parse.quote(bank['account_name'])}"
            )

            embed = discord.Embed(
                title="📥 Nạp tiền vào ví Love Store",
                description=(
                    "Quét QR và chuyển đúng số tiền. "
                    "Không sửa nội dung chuyển khoản để Founder dễ xác nhận."
                ),
                color=config.COLOR_PRIMARY,
                timestamp=datetime.now()
            )
            embed.add_field(
                name="🏦 Ngân hàng",
                value=bank["bank_name"],
                inline=True
            )
            embed.add_field(
                name="💳 Số tài khoản",
                value=f"`{bank['account_number']}`",
                inline=True
            )
            embed.add_field(
                name="👤 Chủ tài khoản",
                value=bank["account_name"],
                inline=False
            )
            embed.add_field(
                name="💰 Số tiền",
                value=f"**{money_fmt(amount_value)}**",
                inline=True
            )
            embed.add_field(
                name="📝 Nội dung chuyển khoản",
                value=f"`{reference_code}`",
                inline=False
            )
            embed.add_field(
                name="🧾 Mã yêu cầu",
                value=f"`{request['transaction_code']}`",
                inline=True
            )
            embed.add_field(
                name="📌 Trạng thái",
                value="⏳ Đang chờ Founder duyệt",
                inline=True
            )
            embed.set_image(url=qr_url)
            embed.set_footer(text=config.BOT_FOOTER)

            await interaction.followup.send(embed=embed, ephemeral=True)

            log_message = await send_wallet_log(
                self.bot,
                title="🟡 Yêu cầu nạp tiền mới",
                color=0xF1C40F,
                fields=[
                    ("👤 Người yêu cầu", f"{interaction.user.mention}\n`{interaction.user.id}`", False),
                    ("💰 Số tiền", f"**{money_fmt(amount_value)}**", True),
                    ("🧾 Mã yêu cầu", f"`{request['transaction_code']}`", True),
                    ("📝 Nội dung chuyển khoản", f"`{reference_code}`", False),
                    ("📌 Trạng thái", "⏳ Đang chờ Founder duyệt", False),
                ],
            )

            if log_message:
                try:
                    await asyncio.to_thread(
                        db.save_wallet_log_message,
                        request["transaction_code"],
                        log_message.channel.id,
                        log_message.id,
                    )
                except Exception as save_error:
                    print(
                        "[Wallet Log Save] "
                        f"{type(save_error).__name__}: {save_error}"
                    )
        except ValueError as error:
            await interaction.followup.send(
                f"❌ Số tiền không hợp lệ: {error}",
                ephemeral=True
            )
        except Exception as error:
            await interaction.followup.send(
                f"❌ Không thể tạo yêu cầu nạp: `{type(error).__name__}: {error}`",
                ephemeral=True
            )

    @app_commands.command(
        name="congtien",
        description="➕ Cộng tiền thủ công vào ví (Founder only)"
    )
    @app_commands.describe(
        member="Người được cộng tiền",
        amount="Số tiền, ví dụ 20k, 50k hoặc 100000",
        reason="Lý do cộng tiền"
    )
    async def congtien(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: str,
        reason: str
    ):
        if not is_founder(interaction.user):
            return await interaction.response.send_message(
                "❌ Chỉ Founder mới được dùng `/congtien`!",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        try:
            amount_value = parse_money(amount)
            result = db.add_wallet_money(
                discord_id=member.id,
                username=member.display_name,
                amount=amount_value,
                reason=reason.strip()[:250],
                performed_by=interaction.user.id,
                performer_name=interaction.user.display_name,
            )

            embed = discord.Embed(
                title="✅ Đã cộng tiền vào ví",
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now()
            )
            embed.add_field(name="👤 Thành viên", value=member.mention, inline=False)
            embed.add_field(name="➕ Số tiền", value=money_fmt(amount_value), inline=True)
            embed.add_field(
                name="💰 Số dư",
                value=(
                    f"{money_fmt(result['balance_before'])} → "
                    f"**{money_fmt(result['balance_after'])}**"
                ),
                inline=False
            )
            embed.add_field(name="📝 Lý do", value=reason[:1024], inline=False)
            embed.add_field(
                name="🧾 Mã giao dịch",
                value=f"`{result['transaction_code']}`",
                inline=True
            )
            embed.set_footer(text=f"Thực hiện bởi {interaction.user}")

            await interaction.followup.send(embed=embed, ephemeral=True)

            await send_wallet_log(
                self.bot,
                title="🟢 Founder cộng tiền vào ví",
                color=0x2ECC71,
                fields=[
                    ("👑 Người thực hiện", f"{interaction.user.mention}\n`{interaction.user.id}`", False),
                    ("👤 Người nhận", f"{member.mention}\n`{member.id}`", False),
                    ("➕ Số tiền", f"**{money_fmt(amount_value)}**", True),
                    (
                        "💳 Biến động số dư",
                        f"{money_fmt(result['balance_before'])} → "
                        f"**{money_fmt(result['balance_after'])}**",
                        False,
                    ),
                    ("📝 Lý do", reason[:1024], False),
                    ("🧾 Mã giao dịch", f"`{result['transaction_code']}`", True),
                ],
            )
        except ValueError as error:
            await interaction.followup.send(f"❌ {error}", ephemeral=True)
        except Exception as error:
            await interaction.followup.send(
                f"❌ Lỗi cộng tiền: `{type(error).__name__}: {error}`",
                ephemeral=True
            )

    @app_commands.command(
        name="trutien",
        description="➖ Trừ tiền trong ví khi khách thanh toán"
    )
    @app_commands.describe(
        member="Người bị trừ tiền",
        amount="Số tiền, ví dụ 20k, 50k hoặc 100000",
        reason="Lý do trừ tiền"
    )
    async def trutien(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: str,
        reason: str
    ):
        actor_rank = privileged_rank(interaction.user)
        target_rank = privileged_rank(member)

        if actor_rank < 1:
            return await interaction.response.send_message(
                "❌ Chỉ Support/Admin/Founder mới được dùng `/trutien`!",
                ephemeral=True
            )

        # Support chỉ trừ member/buyer. Admin không được trừ Founder.
        if actor_rank == 1 and target_rank >= 1:
            return await interaction.response.send_message(
                "❌ Support chỉ được trừ tiền của Member/Buyer!",
                ephemeral=True
            )

        if actor_rank == 2 and target_rank >= 3:
            return await interaction.response.send_message(
                "❌ Admin không được trừ tiền của Founder!",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        try:
            amount_value = parse_money(amount)
            result = db.subtract_wallet_money(
                discord_id=member.id,
                username=member.display_name,
                amount=amount_value,
                reason=reason.strip()[:250],
                performed_by=interaction.user.id,
                performer_name=interaction.user.display_name,
            )

            embed = discord.Embed(
                title="✅ Đã trừ tiền trong ví",
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now()
            )
            embed.add_field(name="👤 Thành viên", value=member.mention, inline=False)
            embed.add_field(name="➖ Số tiền", value=money_fmt(amount_value), inline=True)
            embed.add_field(
                name="💰 Số dư",
                value=(
                    f"{money_fmt(result['balance_before'])} → "
                    f"**{money_fmt(result['balance_after'])}**"
                ),
                inline=False
            )
            embed.add_field(name="📝 Lý do", value=reason[:1024], inline=False)
            embed.add_field(
                name="🧾 Mã giao dịch",
                value=f"`{result['transaction_code']}`",
                inline=True
            )
            embed.set_footer(text=f"Thực hiện bởi {interaction.user}")

            await interaction.followup.send(embed=embed, ephemeral=True)

            await send_wallet_log(
                self.bot,
                title="🟠 Đã trừ tiền trong ví",
                color=0xE67E22,
                fields=[
                    ("👮 Người thực hiện", f"{interaction.user.mention}\n`{interaction.user.id}`", False),
                    ("👤 Người bị trừ", f"{member.mention}\n`{member.id}`", False),
                    ("➖ Số tiền", f"**{money_fmt(amount_value)}**", True),
                    (
                        "💳 Biến động số dư",
                        f"{money_fmt(result['balance_before'])} → "
                        f"**{money_fmt(result['balance_after'])}**",
                        False,
                    ),
                    ("📝 Lý do", reason[:1024], False),
                    ("🧾 Mã giao dịch", f"`{result['transaction_code']}`", True),
                ],
            )
        except ValueError as error:
            if str(error) == "INSUFFICIENT_BALANCE":
                wallet = db.get_wallet(member.id, member.display_name)
                return await interaction.followup.send(
                    (
                        "❌ Ví không đủ số dư!\n"
                        f"Số dư hiện tại: **{money_fmt(wallet['balance'])}**"
                    ),
                    ephemeral=True
                )

            await interaction.followup.send(f"❌ {error}", ephemeral=True)
        except Exception as error:
            await interaction.followup.send(
                f"❌ Lỗi trừ tiền: `{type(error).__name__}: {error}`",
                ephemeral=True
            )


    @app_commands.command(
        name="addcode",
        description="🎟️ Tạo mã giảm giá mới (Founder only)"
    )
    @app_commands.describe(
        code="Mã giảm giá (VD: SALE10K)",
        amount="Số tiền giảm (VD: 10k, 50k, 1m)",
        expires="Ngày hết hạn DD/MM/YYYY (để trống nếu không giới hạn)"
    )
    async def addcode(
        self,
        interaction: discord.Interaction,
        code: str,
        amount: str,
        expires: str = None
    ):
        if not any(
            role.id == config.FOUNDER_ROLE_ID
            for role in interaction.user.roles
        ):
            return await interaction.response.send_message(
                "❌ Chỉ Founder mới dùng được!",
                ephemeral=True
            )

        try:
            text = amount.strip().lower()

            if text.endswith("k"):
                amt = int(float(text[:-1]) * 1000)
            elif text.endswith("m"):
                amt = int(float(text[:-1]) * 1000000)
            else:
                amt = int(float(text))

            expires_at = None

            if expires:
                try:
                    expires_at = datetime.strptime(
                        expires.strip(),
                        "%d/%m/%Y"
                    ).strftime("%Y-%m-%d")
                except ValueError:
                    return await interaction.response.send_message(
                        "❌ Ngày hết hạn sai định dạng! Dùng: `DD/MM/YYYY`",
                        ephemeral=True
                    )

            db.create_discount(code, amt, expires_at)

            embed = discord.Embed(
                title="✅ Đã tạo mã giảm giá",
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now()
            )
            embed.add_field(
                name="🎟️ Mã",
                value=f"`{code.upper()}`",
                inline=True
            )
            embed.add_field(
                name="💰 Giảm",
                value=f"{amt:,} VNĐ".replace(",", "."),
                inline=True
            )
            embed.add_field(
                name="📅 Hết hạn",
                value=expires_at or "Không giới hạn",
                inline=True
            )
            embed.set_footer(text=config.BOT_FOOTER)

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )

        except Exception as error:
            await interaction.response.send_message(
                f"❌ Lỗi: `{error}`",
                ephemeral=True
            )

    @app_commands.command(
        name="codes",
        description="🎟️ Xem tất cả mã giảm giá (Founder only)"
    )
    async def codes(self, interaction: discord.Interaction):
        if not any(
            role.id == config.FOUNDER_ROLE_ID
            for role in interaction.user.roles
        ):
            return await interaction.response.send_message(
                "❌ Chỉ Founder mới dùng được!",
                ephemeral=True
            )

        rows = db.get_all_discounts()

        embed = discord.Embed(
            title="🎟️ Danh sách mã giảm giá",
            color=config.COLOR_INFO,
            timestamp=datetime.now()
        )

        if not rows:
            embed.description = "Chưa có mã nào!"
        else:
            for row in rows:
                status = "✅ Còn" if not row["used"] else "❌ Đã dùng"
                amount = f"{row['amount']:,}".replace(",", ".")

                embed.add_field(
                    name=f"`{row['code']}`",
                    value=(
                        f"💰 Giảm: **{amount} VNĐ**\n"
                        f"📅 HH: {row['expires_at'] or 'Không giới hạn'}\n"
                        f"📌 {status}"
                    ),
                    inline=True
                )

        embed.set_footer(text=config.BOT_FOOTER)

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="delcode",
        description="🗑️ Xóa mã giảm giá (Founder only)"
    )
    @app_commands.describe(code="Mã cần xóa")
    async def delcode(
        self,
        interaction: discord.Interaction,
        code: str
    ):
        if not any(
            role.id == config.FOUNDER_ROLE_ID
            for role in interaction.user.roles
        ):
            return await interaction.response.send_message(
                "❌ Chỉ Founder mới dùng được!",
                ephemeral=True
            )

        db.delete_discount(code)

        await interaction.response.send_message(
            f"🗑️ Đã xóa mã `{code.upper()}`!",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(SlashCog(bot))