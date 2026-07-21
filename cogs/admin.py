"""
cogs/admin.py — Lệnh quản trị dành cho Founder
"""

import discord
from discord.ext import commands
from datetime import datetime

import config
import database as db


def founder_only():
    async def predicate(ctx):
        return any(r.id == config.FOUNDER_ROLE_ID for r in ctx.author.roles)
    return commands.check(predicate)


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help_store(self, ctx):
        embed = discord.Embed(
            title="📖 Love Store — Danh sách lệnh",
            color=config.COLOR_PRIMARY
        )
        embed.add_field(
            name="🛠️ Lệnh trong Ticket (Support/Founder)",
            value=(
                "`!order <tên SP>` — Ghi đơn, gửi format vào #order\n"
                "`!qr <số tiền>` — Tạo QR thanh toán tự động\n"
                "`!done` — Hoàn tất đơn, gửi feedback cho khách\n"
                "`!cancel` — Hủy đơn\n"
                "`!checkntrail` — Link check điều kiện Nicho Trail\n"
                "`!web` — Hiện link truy cập web dashboard\n"
            ),
            inline=False
        )
        embed.add_field(
            name="👑 Lệnh Founder",
            value=(
                "`!setup_ticket [#kênh]` — Gửi embed mở ticket\n"
                "`!stats` — Thống kê đơn hàng\n"
                "`!lookup <mã đơn>` — Tra cứu đơn hàng\n"
                "`!help` — Hiện bảng lệnh này"
            ),
            inline=False
        )
        embed.add_field(
            name="📂 Script phụ (chạy riêng)",
            value=(
                "`python price_lists/price_nicho.py` — Post catalogue Nicho\n"
                "`python price_lists/price_netflix.py` — Post catalogue Netflix\n"
                "`python price_lists/price_spotify.py` — Post catalogue Spotify\n"
                "`python price_lists/price_decor.py` — Post catalogue Decor"
            ),
            inline=False
        )
        embed.set_footer(text=config.BOT_FOOTER)
        await ctx.send(embed=embed)

    @commands.command(name="stats")
    @founder_only()
    async def stats(self, ctx):
        conn = db.get_conn()
        total     = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        paid      = conn.execute("SELECT COUNT(*) FROM orders WHERE status='paid'").fetchone()[0]
        done      = conn.execute("SELECT COUNT(*) FROM orders WHERE status='done'").fetchone()[0]
        pending   = conn.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
        revenue   = conn.execute("SELECT SUM(amount) FROM orders WHERE status IN ('paid','done')").fetchone()[0] or 0
        avg_stars = conn.execute("SELECT AVG(stars) FROM feedbacks").fetchone()[0]
        conn.close()

        embed = discord.Embed(
            title="📊 Thống Kê Love Store",
            color=config.COLOR_INFO,
            timestamp=datetime.now()
        )
        embed.add_field(name="📦 Tổng đơn",      value=str(total),   inline=True)
        embed.add_field(name="✅ Đã xử lý",      value=str(done),    inline=True)
        embed.add_field(name="💳 Đã thanh toán", value=str(paid),    inline=True)
        embed.add_field(name="⏳ Đang chờ",      value=str(pending), inline=True)
        embed.add_field(name="💰 Doanh thu",     value=f"{revenue:,.0f} VNĐ".replace(",", "."), inline=True)
        embed.add_field(name="⭐ Đánh giá TB",   value=f"{avg_stars:.1f}/5" if avg_stars else "Chưa có", inline=True)
        embed.set_footer(text=config.BOT_FOOTER)
        await ctx.send(embed=embed)

    @commands.command(name="lookup")
    @founder_only()
    async def lookup(self, ctx, order_code: str):
        order = db.get_order(order_code.upper())
        if not order:
            return await ctx.send(f"❌ Không tìm thấy đơn `{order_code}`!", delete_after=8)

        status_map = {
            "pending":    "⏳ Đang chờ",
            "processing": "🔄 Đang xử lý",
            "paid":       "💳 Đã thanh toán",
            "done":       "✅ Hoàn tất",
            "cancelled":  "❌ Đã hủy",
        }
        embed = discord.Embed(
            title=f"🔍 Đơn hàng `{order['order_code']}`",
            color=config.COLOR_INFO,
            timestamp=datetime.now()
        )
        member = ctx.guild.get_member(order["user_id"])
        embed.add_field(name="👤 Khách",      value=member.mention if member else order["username"], inline=True)
        embed.add_field(name="🛍️ Sản phẩm", value=order["product_name"],                            inline=True)
        embed.add_field(name="💰 Số tiền",   value=f"{order['amount']:,} VNĐ".replace(",", "."),    inline=True)
        embed.add_field(name="📌 Trạng thái", value=status_map.get(order["status"], order["status"]), inline=True)
        embed.add_field(name="🕐 Tạo lúc",   value=order["created_at"],                             inline=True)
        if order["paid_at"]:
            embed.add_field(name="💳 Thanh toán lúc", value=order["paid_at"], inline=True)
        embed.set_footer(text=config.BOT_FOOTER)
        await ctx.send(embed=embed)

    @commands.command(name="checkntrail")
    async def cmd_check(self, ctx):
        """!checkntrail — Hiện link check điều kiện Nicho Trail"""
        embed = discord.Embed(
            title="🔍 Check Điều Kiện Nicho Trail",
            description=(
                "Bấm vào link bên dưới để kiểm tra tài khoản có đủ điều kiện mua **Nicho Trail** không nhé!\n\n"
                "[👉 Check tại đây](https://promos.discord.gg/HCxVfuJt9AbXzXtSw5yRnv9J)\n\n"
                "Sau khi vào link thì bạn hãy đăng nhập và chụp lại xem discord hiển thị gì nhé!"
            ),
            color=config.COLOR_INFO,
            timestamp=datetime.now()
        )
        embed.add_field(
            name="📌 Lưu ý",
            value=(
                "• Tài khoản phải **chưa từng dùng Nitro** lần nào\n"
                "• Tài khoản phải trên **1 tháng tuổi**"
            ),
            inline=False
        )
        embed.set_footer(text=config.BOT_FOOTER)
        await ctx.send(embed=embed)
        await ctx.message.delete()

    
    @commands.command(name="web")
    async def cmd_web(self, ctx):
        embed = discord.Embed(
            title="🌐 Love Store — Web Dashboard",
            description=(
                "Truy cập web dashboard tại link bên dưới:\n\n"
                "🔗 **Local:** http://localhost:10000\n"
                "🔗 **Public:** https://love-bot-store-pqjc.onrender.com\n\n"
                "Đăng nhập bằng tài khoản được Founder cấp nhé!"
            ),
            color=config.COLOR_INFO,
            timestamp=datetime.now()
        )

        embed.set_footer(text=config.BOT_FOOTER)

        await ctx.send(embed=embed)

        try:
            await ctx.message.delete()
        except:
            pass

    @stats.error
    @lookup.error
    async def founder_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("❌ Chỉ Founder mới dùng được lệnh này!", delete_after=5)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))

