"""
cogs/ticket.py — Hệ thống ticket mua hàng Love Bot Store
"""

import asyncio
import random
import string
from datetime import datetime

import discord
from discord.ext import commands

import config
import database as db


def gen_order_code() -> str:
    return "LBS-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=6)
    )


def gen_ticket_number() -> str:
    """Tạo mã ticket gồm đúng 4 chữ số, ví dụ 3591 hoặc 0428."""
    return f"{random.randint(0, 9999):04d}"


def is_support_or_founder(member: discord.Member) -> bool:
    role_ids = {role.id for role in member.roles}
    return (
        config.SUPPORT_ROLE_ID in role_ids
        or config.FOUNDER_ROLE_ID in role_ids
    )


def is_admin_or_founder(member: discord.Member) -> bool:
    role_ids = {role.id for role in member.roles}
    return (
        config.ADMIN_ROLE_ID in role_ids
        or config.FOUNDER_ROLE_ID in role_ids
    )


class OpenTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🛒  Mua hàng",
        style=discord.ButtonStyle.primary,
        custom_id="open_ticket",
    )
    async def open_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        try:
            await interaction.response.defer(ephemeral=True)

            guild = interaction.guild
            member = interaction.user

            if not guild:
                return await interaction.followup.send(
                    "❌ Không thể tạo ticket ngoài server!",
                    ephemeral=True,
                )

            if db.count_open_tickets(member.id) >= config.MAX_TICKETS_PER_USER:
                return await interaction.followup.send(
                    "❌ Bạn đang có ticket chưa xử lý. "
                    "Vui lòng chờ Support hoàn tất đơn cũ!",
                    ephemeral=True,
                )

            category = guild.get_channel(config.TICKET_CATEGORY_ID)
            support_role = guild.get_role(config.SUPPORT_ROLE_ID)
            founder_role = guild.get_role(config.FOUNDER_ROLE_ID)

            if category is None:
                return await interaction.followup.send(
                    "❌ Không tìm thấy category ticket. Hãy kiểm tra `TICKET_CATEGORY_ID`!",
                    ephemeral=True,
                )

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False
                ),
                member: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                ),
            }

            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

            if founder_role:
                overwrites[founder_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

            ticket_number = gen_ticket_number()
            channel_name = f"{config.TICKET_PREFIX}-{ticket_number}"

            ticket_ch = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket mua hàng của {member}",
            )

            order_code = gen_order_code()
            db.open_ticket(ticket_ch.id, member.id, order_code)

            embed = discord.Embed(
                title="🎀 Love Store — Ticket Mua Hàng",
                description=(
                    f"Xin chào {member.mention}! 👋\n\n"
                    f"Cảm ơn bạn đã liên hệ **{config.BOT_NAME}**.\n"
                    f"Mã đơn hàng của bạn: `{order_code}`\n"
                    f"Mã ticket: `{ticket_number}`\n\n"
                    "📌 **Hướng dẫn:**\n"
                    "• Cho Support biết bạn muốn mua sản phẩm nào\n"
                    "• Chuẩn bị đầy đủ thông tin cho vật phẩm cần mua\n"
                    "• Nếu sau 15 phút vẫn chưa thấy hỗ trợ, hãy ping họ.\n\n"
                    "⏳ Vui lòng chờ Support hỗ trợ..."
                ),
                color=config.COLOR_PRIMARY,
                timestamp=datetime.now(),
            )
            embed.set_footer(text=config.BOT_FOOTER)

            if config.BOT_AVATAR:
                embed.set_thumbnail(url=config.BOT_AVATAR)

            # Chỉ ping Support; Founder vẫn có quyền xem ticket nhưng không bị ping.
            ping_msg = support_role.mention if support_role else ""

            await ticket_ch.send(
                ping_msg,
                embed=embed,
                view=CloseTicketView(),
            )

            await interaction.followup.send(
                f"✅ Ticket của bạn đã được tạo: {ticket_ch.mention}",
                ephemeral=True,
            )

            await _log(
                guild,
                f"🎫 Ticket mới: {ticket_ch.mention} — "
                f"{member.mention} (`{order_code}`)",
            )

        except Exception as error:
            import traceback

            traceback.print_exc()
            print(f"[ERROR open_ticket] {error}")

            try:
                await interaction.followup.send(
                    f"❌ Lỗi: `{error}`",
                    ephemeral=True,
                )
            except Exception:
                pass


class OpenSupportView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎧  Liên hệ Support",
        style=discord.ButtonStyle.secondary,
        custom_id="open_support",
    )
    async def open_support(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        try:
            await interaction.response.defer(ephemeral=True)

            guild = interaction.guild
            member = interaction.user

            if not guild:
                return await interaction.followup.send(
                    "❌ Không thể tạo ticket ngoài server!",
                    ephemeral=True,
                )

            if db.count_open_tickets(member.id) >= config.MAX_TICKETS_PER_USER:
                return await interaction.followup.send(
                    "❌ Bạn đang có ticket chưa xử lý. "
                    "Vui lòng chờ Support hoàn tất!",
                    ephemeral=True,
                )

            category = guild.get_channel(config.TICKET_CATEGORY_ID)
            support_role = guild.get_role(config.SUPPORT_ROLE_ID)
            founder_role = guild.get_role(config.FOUNDER_ROLE_ID)

            if category is None:
                return await interaction.followup.send(
                    "❌ Không tìm thấy category ticket. Hãy kiểm tra `TICKET_CATEGORY_ID`!",
                    ephemeral=True,
                )

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False
                ),
                member: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                ),
            }

            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

            if founder_role:
                overwrites[founder_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

            ticket_number = gen_ticket_number()
            channel_name = f"support-{ticket_number}"

            ticket_ch = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket hỗ trợ của {member}",
            )

            db.open_ticket(ticket_ch.id, member.id)

            embed = discord.Embed(
                title="🎧 Love Bot Store — Ticket Hỗ Trợ",
                description=(
                    f"Xin chào {member.mention}! 👋\n\n"
                    "Cảm ơn bạn đã liên hệ **Support** của chúng tôi.\n"
                    "Hãy mô tả vấn đề bạn gặp phải, Support sẽ hỗ trợ ngay!\n\n"
                    f"Mã ticket: `{ticket_number}`\n\n"
                    "⏳ Vui lòng chờ Support hỗ trợ..."
                ),
                color=config.COLOR_INFO,
                timestamp=datetime.now(),
            )
            embed.set_footer(text=config.BOT_FOOTER)

            if config.BOT_AVATAR:
                embed.set_thumbnail(url=config.BOT_AVATAR)

            # Chỉ ping Support; Founder vẫn có quyền xem ticket nhưng không bị ping.
            ping_msg = support_role.mention if support_role else ""

            await ticket_ch.send(
                ping_msg,
                embed=embed,
                view=CloseTicketView(),
            )

            await interaction.followup.send(
                f"✅ Ticket hỗ trợ đã được tạo: {ticket_ch.mention}",
                ephemeral=True,
            )

            await _log(
                guild,
                f"🎧 Support ticket mới: {ticket_ch.mention} — {member.mention}",
            )

        except Exception as error:
            import traceback

            traceback.print_exc()
            print(f"[ERROR open_support] {error}")

            try:
                await interaction.followup.send(
                    f"❌ Lỗi: `{error}`",
                    ephemeral=True,
                )
            except Exception:
                pass


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒  Đóng Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="close_ticket",
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not is_support_or_founder(interaction.user):
            return await interaction.response.send_message(
                "❌ Chỉ Support/Founder mới đóng được ticket!",
                ephemeral=True,
            )

        await interaction.response.defer()

        channel = interaction.channel
        guild = interaction.guild

        # Xóa dữ liệu trước khi xóa kênh.
        db.close_ticket(channel.id)

        await _log(
            guild,
            f"🔒 Ticket đóng: #{channel.name} bởi {interaction.user.mention}",
        )

        await channel.send("✅ Ticket sẽ được xóa sau **5 giây**...")
        await asyncio.sleep(5)
        await channel.delete(reason="Ticket đã hoàn tất")


class FeedbackStarsView(discord.ui.View):
    def __init__(self, order_code: str, customer: discord.Member):
        super().__init__(timeout=259200)
        self.order_code = order_code
        self.customer = customer

    async def _handle_stars(
        self,
        interaction: discord.Interaction,
        stars: int,
    ):
        if interaction.user.id != self.customer.id:
            return await interaction.response.send_message(
                "❌ Chỉ người mua mới được đánh giá!",
                ephemeral=True,
            )

        await interaction.response.send_modal(
            FeedbackModal(
                self.order_code,
                stars,
                self.customer,
            )
        )
        self.stop()

    @discord.ui.button(
        label="⭐ 1",
        style=discord.ButtonStyle.secondary,
        custom_id="star_1",
    )
    async def s1(self, interaction, button):
        await self._handle_stars(interaction, 1)

    @discord.ui.button(
        label="⭐ 2",
        style=discord.ButtonStyle.secondary,
        custom_id="star_2",
    )
    async def s2(self, interaction, button):
        await self._handle_stars(interaction, 2)

    @discord.ui.button(
        label="⭐ 3",
        style=discord.ButtonStyle.secondary,
        custom_id="star_3",
    )
    async def s3(self, interaction, button):
        await self._handle_stars(interaction, 3)

    @discord.ui.button(
        label="⭐ 4",
        style=discord.ButtonStyle.success,
        custom_id="star_4",
    )
    async def s4(self, interaction, button):
        await self._handle_stars(interaction, 4)

    @discord.ui.button(
        label="⭐ 5",
        style=discord.ButtonStyle.success,
        custom_id="star_5",
    )
    async def s5(self, interaction, button):
        await self._handle_stars(interaction, 5)


class FeedbackModal(discord.ui.Modal, title="📝 Đánh giá đơn hàng"):
    content = discord.ui.TextInput(
        label="Nhận xét của bạn",
        placeholder="Chia sẻ trải nghiệm mua hàng...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    def __init__(
        self,
        order_code: str,
        stars: int,
        customer: discord.Member,
    ):
        super().__init__()
        self.order_code = order_code
        self.stars = stars
        self.customer = customer

    async def on_submit(self, interaction: discord.Interaction):
        try:
            stars_str = "⭐" * self.stars + "✩" * (5 - self.stars)
            text = self.content.value.strip() or "_Không có nhận xét_"

            db.save_feedback(
                self.order_code,
                self.customer.id,
                str(self.customer),
                self.stars,
                text,
            )

            try:
                order = db.get_order(self.order_code)
                product_name = (
                    order["product_name"] if order else "_Không rõ_"
                )
            except Exception:
                product_name = "_Không rõ_"

            guild = interaction.guild
            fb_ch = guild.get_channel(config.FEEDBACK_CHANNEL_ID)

            fb_embed = discord.Embed(
                title="💬 Feedback mới",
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now(),
            )
            fb_embed.add_field(
                name="⭐ Đánh giá",
                value=stars_str,
                inline=False,
            )
            fb_embed.add_field(
                name="👤 Khách hàng",
                value=self.customer.mention,
                inline=False,
            )
            fb_embed.add_field(
                name="📦 Mã đơn",
                value=f"`{self.order_code}`",
                inline=False,
            )
            fb_embed.add_field(
                name="🛍️ Sản phẩm",
                value=product_name,
                inline=False,
            )
            fb_embed.add_field(
                name="📝 Feedback",
                value=text,
                inline=False,
            )
            fb_embed.set_footer(text=config.BOT_FOOTER)

            if fb_ch:
                await fb_ch.send(embed=fb_embed)

            await interaction.response.send_message(
                embed=discord.Embed(
                    title="✅ Cảm ơn bạn đã đánh giá!",
                    description=(
                        f"Đánh giá **{stars_str}** của bạn đã được ghi nhận 💖\n"
                        "Support sẽ đóng ticket này ngay."
                    ),
                    color=config.COLOR_SUCCESS,
                )
            )

            close_embed = discord.Embed(
                title="🔒 Sẵn sàng đóng ticket",
                description=(
                    "Khách hàng đã feedback xong.\n"
                    "Nhấn nút bên dưới để đóng ticket."
                ),
                color=config.COLOR_WARNING,
            )

            await interaction.channel.send(
                embed=close_embed,
                view=CloseTicketView(),
            )

        except Exception as error:
            import traceback

            print(f"[FeedbackModal ERROR] {error}")
            traceback.print_exc()

            try:
                await interaction.response.send_message(
                    f"❌ Lỗi: `{error}`",
                    ephemeral=True,
                )
            except Exception:
                await interaction.followup.send(
                    f"❌ Lỗi: `{error}`",
                    ephemeral=True,
                )


class TicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._views_registered = False

    @commands.Cog.listener()
    async def on_ready(self):
        # Tránh add persistent view lặp lại khi Discord reconnect.
        if self._views_registered:
            return

        self.bot.add_view(OpenTicketView())
        self.bot.add_view(OpenSupportView())
        self.bot.add_view(CloseTicketView())
        self._views_registered = True

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Kênh ticket bị xóa thủ công thì tự dọn dữ liệu trong database."""
        try:
            ticket = db.get_ticket_by_channel(channel.id)

            if ticket:
                db.close_ticket(channel.id)
                print(
                    f"[Ticket Cleanup] Đã dọn "
                    f"#{channel.name} ({channel.id}) khỏi database"
                )

        except Exception as error:
            print(f"[Ticket Cleanup ERROR] {error}")

    @commands.command(name="setup_ticket")
    @commands.has_role(config.FOUNDER_ROLE_ID)
    async def setup_ticket(
        self,
        ctx,
        channel: discord.TextChannel = None,
    ):
        target = channel or ctx.channel

        embed = discord.Embed(
            title="🛒 Love Store — Mua Hàng",
            description=(
                "Chào mừng đến với **Love Store** 💖\n\n"
                "Để mua hàng, bấm nút **🛒 Mua hàng** bên dưới.\n"
                "Bot sẽ tạo ticket riêng và Support sẽ hỗ trợ bạn ngay!\n\n"
                "📌 Xem các sản phẩm ở các kênh shop bên cạnh nhé~"
            ),
            color=config.COLOR_PRIMARY,
        )
        embed.set_footer(text=config.BOT_FOOTER)

        if config.BOT_AVATAR:
            embed.set_thumbnail(url=config.BOT_AVATAR)

        await target.send(
            embed=embed,
            view=OpenTicketView(),
        )

        if target != ctx.channel:
            await ctx.send(
                f"✅ Đã gửi embed ticket vào {target.mention}!",
                delete_after=5,
            )

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="setup_support")
    @commands.has_role(config.FOUNDER_ROLE_ID)
    async def setup_support(
        self,
        ctx,
        channel: discord.TextChannel = None,
    ):
        target = channel or ctx.channel

        embed = discord.Embed(
            title="🎧 Love Bot Store — Hỗ Trợ",
            description=(
                "Bạn cần được hỗ trợ? Chúng tôi luôn sẵn sàng! 💖\n\n"
                "Bấm nút **🎧 Liên hệ Support** bên dưới.\n"
                "Bot sẽ tạo ticket riêng và Support sẽ phản hồi sớm nhất!"
            ),
            color=config.COLOR_INFO,
        )
        embed.set_footer(text=config.BOT_FOOTER)

        if config.BOT_AVATAR:
            embed.set_thumbnail(url=config.BOT_AVATAR)

        await target.send(
            embed=embed,
            view=OpenSupportView(),
        )

        if target != ctx.channel:
            await ctx.send(
                f"✅ Đã gửi embed support vào {target.mention}!",
                delete_after=5,
            )

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass


async def _log(
    guild: discord.Guild,
    message: str,
):
    if not guild:
        return

    channel = guild.get_channel(config.LOG_CHANNEL_ID)

    if channel:
        await channel.send(
            f"`{datetime.now().strftime('%H:%M:%S')}` {message}"
        )


async def setup(bot):
    await bot.add_cog(TicketCog(bot))
