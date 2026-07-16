"""
menu.py — Gửi embed menu sản phẩm dạng dropdown vào kênh chỉ định
Chạy: python menu.py
"""

import discord
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# ─────────────────────────────────────────────────────────────
#  ĐIỀN THÔNG TIN VÀO ĐÂY
# ─────────────────────────────────────────────────────────────

CHANNEL_ID    = 1515676281847414815  # ID kênh gửi menu
THUMBNAIL_URL = ""                   # URL ảnh thumbnail (để trống nếu không có)
BANNER_URL    = "https://cdn.discordapp.com/emojis/1516028466347380786.webp?size=128"                   # URL ảnh banner (để trống nếu không có)
MENU_TITLE    = "BẢNG GIÁ LOVE STORE"  # Tiêu đề menu

# Danh sách sản phẩm: (emoji, tên, mô tả ngắn)
PRODUCTS = [
    ("🎮", "Nicho Boost",      "Dạng login"),
    ("🎨", "de-co / Bảng tên", "Dạng login"),
    ("⚡", "Boot Sivi",     "Nâng cấp server"),
    ("🎵", "Si-potti-fy Premium",  "Dạng add family"),
    ("▶️", "Yutube Premium",  "Dạng add family"),
    ("🎬", "Net-fo-lic Premium",  "Dạng cấp acc"),
    # Thêm sản phẩm khác vào đây...
    # ("emoji", "Tên sản phẩm", "Mô tả ngắn"),
]

# ─────────────────────────────────────────────────────────────

class MenuSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=name,
                description=desc,
                emoji=emoji
            )
            for emoji, name, desc in PRODUCTS
        ]
        super().__init__(
            placeholder="NHẬP VÀO ĐÂY ĐỂ XEM GIÁ",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="menu_select"
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        # Tìm sản phẩm được chọn
        product = next((p for p in PRODUCTS if p[1] == selected), None)
        if product:
            emoji, name, desc = product
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"{emoji} **{name}** — {desc}\n\nVào kênh mua hàng để tạo ticket mua hàng nhé!",
                    color=config.COLOR_PRIMARY
                ),
                ephemeral=True
            )


class MenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MenuSelect())


# ─────────────────────────────────────────────────────────────

intents = discord.Intents.default()
bot     = discord.Client(intents=intents)


@bot.event
async def on_ready():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"❌ Không tìm thấy kênh ID: {CHANNEL_ID}")
        await bot.close()
        return

    embed = discord.Embed(
        title=f"{MENU_TITLE}",
        description="Đọc chính sách & bảo hành trước khi mua nhé\n\nChọn sản phẩm bên dưới để xem thông tin chi tiết",
        color=config.COLOR_PRIMARY
    )
    embed.set_footer(text=config.BOT_FOOTER)
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    if BANNER_URL:
        embed.set_image(url=BANNER_URL)

    await channel.send(embed=embed, view=MenuView())
    print(f"✅ Đã gửi menu vào #{channel.name}")
    await bot.close()


bot.run(config.BOT_TOKEN)