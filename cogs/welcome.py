"""
cogs/welcome.py — Hệ thống chào mừng thành viên mới
"""

import discord
from discord.ext import commands
from datetime import datetime

import config

# ─────────────────────────────────────────────────────────────
#  ĐIỀN THÔNG TIN VÀO ĐÂY
# ─────────────────────────────────────────────────────────────

WELCOME_CHANNEL_ID  = 1515674424391630898   # ID kênh welcome
SHOP_CHANNEL_ID     = 1515676281847414815  # ID kênh xem giá/sản phẩm
BUY_CHANNEL_ID      = 1515676405566931034   # ID kênh mua hàng (có nút mua)

# ─────────────────────────────────────────────────────────────

class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild   = member.guild
        channel = guild.get_channel(WELCOME_CHANNEL_ID)
        if not channel:
            return

        shop_ch = guild.get_channel(SHOP_CHANNEL_ID)
        buy_ch  = guild.get_channel(BUY_CHANNEL_ID)

        embed = discord.Embed(
            title=f"👋 Chào mừng đến với {guild.name}!",
            description=(
                f"Xin chào {member.mention}! 💖\n"
                "Chúng tôi rất vui khi có bạn ở đây!\n\n"
                f"🛍️ **Xem giá sản phẩm** tại {shop_ch.mention if shop_ch else '`#shop`'}\n"
                f"🛒 **Mua hàng** tại {buy_ch.mention if buy_ch else '`#mua-hang`'}\n\n"
            ),
            color=config.COLOR_PRIMARY,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=config.BOT_FOOTER)

        await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))