# DMS.py

import discord
import config

# =========================

# THÔNG TIN NGƯỜI NHẬN

# =========================

USER_ID = USER_ID

# =========================

# THÔNG TIN GỬI

# =========================

WEBSITE = "(link website)[https://love-bot-store-pqjc.onrender.com/]"
USERNAME = "izad"
PASSWORD = "lovestoreizad"

NOTE = """
Tài khoản dành cho support.
Không chia sẻ cho người khác.
"""

# =========================
intents = discord.Intents.default()

bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    try:
        user = await bot.fetch_user(USER_ID)

        embed = discord.Embed(
            title="💖 LOVE STORE",
            description="Thông tin tài khoản được cấp cho bạn",
            color=0xFF69B4
        )

        embed.add_field(
            name="🌐 Website",
            value=f"`{WEBSITE}`",
            inline=False
        )

        embed.add_field(
            name="👤 Tài khoản",
            value=f"`{USERNAME}`",
            inline=True
        )

        embed.add_field(
            name="🔑 Mật khẩu",
            value=f"`{PASSWORD}`",
            inline=True
        )

        embed.add_field(
            name="📝 Ghi chú",
            value=NOTE,
            inline=False
        )

        embed.set_footer(
            text="Love Store • Nhân viên"
        )

        await user.send(embed=embed)

        print("✅ Đã gửi DM thành công")

    except Exception as e:
        print(f"❌ Lỗi: {e}")

    await bot.close()

bot.run(config.BOT_TOKEN)