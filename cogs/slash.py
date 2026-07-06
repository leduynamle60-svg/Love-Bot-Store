"""
cogs/slash.py — Slash commands cho Love Bot Store
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import calendar

import config
import database as db


class SlashCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bxh", description="🏆 Bảng xếp hạng người mua trong tháng")
    async def bxh(self, interaction: discord.Interaction):
        now   = datetime.now()
        month = now.month
        year  = now.year

        conn = db.get_conn()
        rows = conn.execute("""
            SELECT user_id, username,
                   COUNT(*) as total_orders,
                   SUM(amount) as total_spent
            FROM orders
            WHERE status IN ('paid', 'done')
            AND strftime('%m', created_at) = ?
            AND strftime('%Y', created_at) = ?
            GROUP BY user_id
            ORDER BY total_spent DESC
            LIMIT 10
        """, (f"{month:02d}", str(year))).fetchall()
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
            desc   = ""
            for i, row in enumerate(rows):
                medal    = medals[i] if i < 3 else f"`#{i+1}`"
                member   = interaction.guild.get_member(row["user_id"])
                name     = member.display_name if member else row["username"]
                spent    = f"{row['total_spent']:,}".replace(",", ".")
                desc    += f"{medal} **{name}** — {row['total_orders']} đơn — {spent} VNĐ\n"
            embed.description = desc

        embed.set_footer(text=config.BOT_FOOTER)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="myorders", description="📦 Xem lịch sử đơn hàng của bạn")
    async def myorders(self, interaction: discord.Interaction):
        conn = db.get_conn()
        rows = conn.execute("""
            SELECT * FROM orders
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 5
        """, (interaction.user.id,)).fetchall()
        conn.close()

        embed = discord.Embed(
            title=f"📦 Đơn hàng của {interaction.user.display_name}",
            color=config.COLOR_INFO,
            timestamp=datetime.now()
        )

        if not rows:
            embed.description = "Bạn chưa có đơn hàng nào!"
        else:
            status_map = {
                "pending":    "⏳ Đang chờ",
                "processing": "🔄 Đang xử lý",
                "paid":       "💳 Đã thanh toán",
                "done":       "✅ Hoàn tất",
                "cancelled":  "❌ Đã hủy",
            }
            for row in rows:
                embed.add_field(
                    name=f"`{row['order_code']}` — {row['product_name']}",
                    value=(
                        f"💰 {row['amount']:,} VNĐ".replace(",", ".") + "\n"
                        f"📌 {status_map.get(row['status'], row['status'])}\n"
                        f"🕐 {row['created_at']}"
                    ),
                    inline=False
                )

        embed.set_footer(text=config.BOT_FOOTER)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SlashCog(bot))