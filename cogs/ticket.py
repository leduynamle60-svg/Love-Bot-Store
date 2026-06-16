"""
cogs/ticket.py — Hệ thống ticket mua hàng Love Bot Store
"""

import discord
from discord.ext import commands
from discord import app_commands
import random, string
from datetime import datetime

import config
import database as db


def gen_order_code():
    return "LBS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def is_support_or_founder(member: discord.Member) -> bool:
    role_ids = {r.id for r in member.roles}
    return config.SUPPORT_ROLE_ID in role_ids or config.FOUNDER_ROLE_ID in role_ids


class OpenTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🛒  Mua hàng", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild  = interaction.guild
        member = interaction.user

        if db.count_open_tickets(member.id) >= config.MAX_TICKETS_PER_USER:
            return await interaction.followup.send(
                "❌ Bạn đang có ticket chưa xử lý. Vui lòng chờ Support hoàn tất đơn cũ!",
                ephemeral=True
            )

        category     = guild.get_channel(config.TICKET_CATEGORY_ID)
        support_role = guild.get_role(config.SUPPORT_ROLE_ID)
        founder_role = guild.get_role(config.FOUNDER_ROLE_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        if founder_role:
            overwrites[founder_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel_name = f"{config.TICKET_PREFIX}-{member.name}".lower().replace(" ", "-")[:32]
        ticket_ch = await guild.create_text_channel(
            name=channel_name, category=category, overwrites=overwrites,
            reason=f"Ticket mua hàng của {member}"
        )

        order_code = gen_order_code()
        db.open_ticket(ticket_ch.id, member.id, order_code)

        embed = discord.Embed(
            title="🎀 Love Bot Store — Ticket Mua Hàng",
            description=(
                f"Xin chào {member.mention}! 👋\n\n"
                f"Cảm ơn bạn đã liên hệ **{config.BOT_NAME}**.\n"
                f"Mã đơn hàng của bạn: `{order_code}`\n\n"
                "📌 **Hướng dẫn:**\n"
                "• Cho Support biết bạn muốn mua sản phẩm nào\n"
                "• Chuẩn bị đầy đủ các thông tin cho vật phẩm cần mua\n"
                "• Nếu sau 15 phút vẫn chưa thấy hỗ trợ, hãy ping họ.\n\n"
                "⏳ Vui lòng chờ Support hỗ trợ..."
            ),
            color=config.COLOR_PRIMARY,
            timestamp=datetime.now()
        )
        embed.set_footer(text=config.BOT_FOOTER)
        if config.BOT_AVATAR:
            embed.set_thumbnail(url=config.BOT_AVATAR)

        ping_msg = f"{support_role.mention if support_role else ''} {founder_role.mention if founder_role else ''}"
        await ticket_ch.send(ping_msg.strip(), embed=embed, view=CloseTicketView())
        await interaction.followup.send(f"✅ Ticket của bạn đã được tạo: {ticket_ch.mention}", ephemeral=True)
        await _log(guild, f"🎫 Ticket mới: {ticket_ch.mention} — {member.mention} (`{order_code}`)")


class OpenSupportView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎧  Liên hệ Support", style=discord.ButtonStyle.secondary, custom_id="open_support")
    async def open_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild  = interaction.guild
        member = interaction.user

        if db.count_open_tickets(member.id) >= config.MAX_TICKETS_PER_USER:
            return await interaction.followup.send(
                "❌ Bạn đang có ticket chưa xử lý. Vui lòng chờ Support hoàn tất!",
                ephemeral=True
            )

        category     = guild.get_channel(config.TICKET_CATEGORY_ID)
        support_role = guild.get_role(config.SUPPORT_ROLE_ID)
        founder_role = guild.get_role(config.FOUNDER_ROLE_ID)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        if founder_role:
            overwrites[founder_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel_name = f"support-{member.name}".lower().replace(" ", "-")[:32]
        ticket_ch = await guild.create_text_channel(
            name=channel_name, category=category, overwrites=overwrites,
            reason=f"Ticket hỗ trợ của {member}"
        )

        db.open_ticket(ticket_ch.id, member.id)

        embed = discord.Embed(
            title="🎧 Love Bot Store — Ticket Hỗ Trợ",
            description=(
                f"Xin chào {member.mention}! 👋\n\n"
                "Cảm ơn bạn đã liên hệ **Support** của chúng tôi.\n"
                "Hãy mô tả vấn đề bạn gặp phải, Support sẽ hỗ trợ ngay!\n\n"
                "⏳ Vui lòng chờ Support hỗ trợ..."
            ),
            color=config.COLOR_INFO,
            timestamp=datetime.now()
        )
        embed.set_footer(text=config.BOT_FOOTER)
        if config.BOT_AVATAR:
            embed.set_thumbnail(url=config.BOT_AVATAR)

        ping_msg = f"{support_role.mention if support_role else ''} {founder_role.mention if founder_role else ''}"
        await ticket_ch.send(ping_msg.strip(), embed=embed, view=CloseTicketView())
        await interaction.followup.send(f"✅ Ticket hỗ trợ đã được tạo: {ticket_ch.mention}", ephemeral=True)
        await _log(guild, f"🎧 Support ticket mới: {ticket_ch.mention} — {member.mention}")


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒  Đóng Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_support_or_founder(interaction.user):
            return await interaction.response.send_message("❌ Chỉ Support/Founder mới đóng được ticket!", ephemeral=True)

        await interaction.response.defer()
        channel = interaction.channel
        guild   = interaction.guild

        db.close_ticket(channel.id)
        await _log(guild, f"🔒 Ticket đóng: #{channel.name} bởi {interaction.user.mention}")

        await channel.send("✅ Ticket sẽ được xóa sau **5 giây**...")
        import asyncio
        await asyncio.sleep(5)
        await channel.delete(reason="Ticket đã hoàn tất")


class FeedbackStarsView(discord.ui.View):
    def __init__(self, order_code: str, customer: discord.Member):
        super().__init__(timeout=300)
        self.order_code = order_code
        self.customer   = customer

    async def _handle_stars(self, interaction: discord.Interaction, stars: int):
        if interaction.user.id != self.customer.id:
            return await interaction.response.send_message("❌ Chỉ người mua mới được đánh giá!", ephemeral=True)
        await interaction.response.send_modal(FeedbackModal(self.order_code, stars, self.customer))
        self.stop()

    @discord.ui.button(label="⭐ 1", style=discord.ButtonStyle.secondary, custom_id="star_1")
    async def s1(self, i, b): await self._handle_stars(i, 1)

    @discord.ui.button(label="⭐ 2", style=discord.ButtonStyle.secondary, custom_id="star_2")
    async def s2(self, i, b): await self._handle_stars(i, 2)

    @discord.ui.button(label="⭐ 3", style=discord.ButtonStyle.secondary, custom_id="star_3")
    async def s3(self, i, b): await self._handle_stars(i, 3)

    @discord.ui.button(label="⭐ 4", style=discord.ButtonStyle.success, custom_id="star_4")
    async def s4(self, i, b): await self._handle_stars(i, 4)

    @discord.ui.button(label="⭐ 5", style=discord.ButtonStyle.success, custom_id="star_5")
    async def s5(self, i, b): await self._handle_stars(i, 5)


class FeedbackModal(discord.ui.Modal, title="📝 Đánh giá đơn hàng"):
    content = discord.ui.TextInput(
        label="Nhận xét của bạn",
        placeholder="Chia sẻ trải nghiệm mua hàng...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False
    )

    def __init__(self, order_code: str, stars: int, customer: discord.Member):
        super().__init__()
        self.order_code = order_code
        self.stars      = stars
        self.customer   = customer

    # ← ĐÚNG: on_submit nằm TRONG class FeedbackModal
    async def on_submit(self, interaction: discord.Interaction):
        try:
            stars_str = "⭐" * self.stars + "✩" * (5 - self.stars)
            text      = self.content.value.strip() or "_Không có nhận xét_"

            db.save_feedback(self.order_code, self.customer.id, str(self.customer), self.stars, text)

            try:
                order        = db.get_order(self.order_code)
                product_name = order["product_name"] if order else "_Không rõ_"
            except:
                product_name = "_Không rõ_"

            guild    = interaction.guild
            fb_ch    = guild.get_channel(config.FEEDBACK_CHANNEL_ID)
            fb_embed = discord.Embed(
                title="💬 Feedback mới",
                color=config.COLOR_SUCCESS,
                timestamp=datetime.now()
            )
            fb_embed.add_field(name="⭐ Đánh giá",   value=stars_str,              inline=False)
            fb_embed.add_field(name="👤 Khách hàng", value=self.customer.mention,  inline=False)
            fb_embed.add_field(name="📦 Mã đơn",     value=f"`{self.order_code}`", inline=False)
            fb_embed.add_field(name="🛍️ Sản phẩm",  value=product_name,           inline=False)
            fb_embed.add_field(name="📝 Feedback",   value=text,                   inline=False)
            fb_embed.set_footer(text=config.BOT_FOOTER)
            if fb_ch:
                await fb_ch.send(embed=fb_embed)

            await interaction.response.send_message(
                embed=discord.Embed(
                    title="✅ Cảm ơn bạn đã đánh giá!",
                    description=f"Đánh giá **{stars_str}** của bạn đã được ghi nhận 💖\nSupport sẽ đóng ticket này ngay.",
                    color=config.COLOR_SUCCESS
                )
            )

            close_embed = discord.Embed(
                title="🔒 Sẵn sàng đóng ticket",
                description="Khách hàng đã feedback xong.\nNhấn nút bên dưới để đóng ticket.",
                color=config.COLOR_WARNING
            )
            await interaction.channel.send(embed=close_embed, view=CloseTicketView())

        except Exception as e:
            print(f"[FeedbackModal ERROR] {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.response.send_message(f"❌ Lỗi: `{e}`", ephemeral=True)
            except:
                await interaction.followup.send(f"❌ Lỗi: `{e}`", ephemeral=True)


class TicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(OpenTicketView())
        self.bot.add_view(OpenSupportView())
        self.bot.add_view(CloseTicketView())

    @commands.command(name="setup_ticket")
    @commands.has_role(config.FOUNDER_ROLE_ID)
    async def setup_ticket(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        embed  = discord.Embed(
            title="🛒 Love Bot Store — Mua Hàng",
            description=(
                "Chào mừng đến với **Love Bot Store** 💖\n\n"
                "Để mua hàng, bấm nút **🛒 Mua hàng** bên dưới.\n"
                "Bot sẽ tạo ticket riêng và Support sẽ hỗ trợ bạn ngay!\n\n"
                "📌 Xem các sản phẩm ở các kênh shop bên cạnh nhé~"
            ),
            color=config.COLOR_PRIMARY
        )
        embed.set_footer(text=config.BOT_FOOTER)
        if config.BOT_AVATAR:
            embed.set_thumbnail(url=config.BOT_AVATAR)
        await target.send(embed=embed, view=OpenTicketView())
        if target != ctx.channel:
            await ctx.send(f"✅ Đã gửi embed ticket vào {target.mention}!", delete_after=5)
        await ctx.message.delete()

    @commands.command(name="setup_support")
    @commands.has_role(config.FOUNDER_ROLE_ID)
    async def setup_support(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        embed  = discord.Embed(
            title="🎧 Love Bot Store — Hỗ Trợ",
            description=(
                "Bạn cần được hỗ trợ? Chúng tôi luôn sẵn sàng! 💖\n\n"
                "Bấm nút **🎧 Liên hệ Support** bên dưới.\n"
                "Bot sẽ tạo ticket riêng và Support sẽ phản hồi sớm nhất!"
            ),
            color=config.COLOR_INFO
        )
        embed.set_footer(text=config.BOT_FOOTER)
        if config.BOT_AVATAR:
            embed.set_thumbnail(url=config.BOT_AVATAR)
        await target.send(embed=embed, view=OpenSupportView())
        if target != ctx.channel:
            await ctx.send(f"✅ Đã gửi embed support vào {target.mention}!", delete_after=5)
        await ctx.message.delete()


async def _log(guild: discord.Guild, message: str):
    ch = guild.get_channel(config.LOG_CHANNEL_ID)
    if ch:
        await ch.send(f"`{datetime.now().strftime('%H:%M:%S')}` {message}")


async def setup(bot):
    await bot.add_cog(TicketCog(bot))