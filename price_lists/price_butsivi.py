"""
price_lists/price_nicho.py
Script phụ — Gửi bảng giá Nicho vào kênh chỉ định
Chạy: python price_lists/price_nicho.py
"""

import discord
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

# ─────────────────────────────────────────────────────────────
#  ĐIỀN THÔNG TIN VÀO ĐÂY
# ─────────────────────────────────────────────────────────────

CHANNEL_ID    = 1515675696725364857   # ID kênh để gửi
THUMBNAIL_URL = "https://cdn.discordapp.com/emojis/879696508826558504.webp?size=128&animated=true"                   # URL ảnh thumbnail (để trống nếu không có)

# ─────────────────────────────────────────────────────────────

PRICE_TEXT = """# <a:boot_sivi:1516432675215511683>**Bảng Giá Boot sivi **
##   Boot sivi 1 tháng
| • ***1 Boot (level 0)***  - ` 15.000 `
| • ***2 Boot (level 1)***  - ` 28.000 `
| • ***7 Boot (level 2)***  - ` 90.000 `
| • ***14 Boot (level 3)*** -  `173.000 `

##   Boot sivi 3 tháng
| • ***1 Boot (level 0)***  - ` 29.000 `
| • ***2 Boot (level 1)***  - ` 55.000 `
| • ***7 Boot (level 2)***  - ` 189.000 `
| • ***14 Boot (level 3)*** -  `369.000 `
- Sốp sẽ vào sivi để bút nên không ảnh hưởng gì đến sivi
- Ngoài ra, sốp còn nhận các loại boot sivi cao hơn như 28 boot và hơn.

`` × Hoàn thành trong vòng 24h-72h, nhanh nhất trong ngày ``
`` × Đảm bảo chất lượng hàng ổn định, bảo hành 1 đổi 1 ``
**Tạo Ticket để mua ngay nhé**
### LOVE STORE Chúc Bạn Có 1 Trải Nghiệm Mua Sắm Vui Vẻ!"""

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

    # Tin nhắn 1 — Embed tiêu đề
    embed_header = discord.Embed(
        title="🎮 Boot sivi — Bảng Giá",
        description="Xem chi tiết giá bên dưới 👇",
        color=config.COLOR_PRIMARY
    )
    embed_header.set_footer(text=config.BOT_FOOTER)
    if THUMBNAIL_URL:
        embed_header.set_thumbnail(url=THUMBNAIL_URL)

    await channel.send(embed=embed_header)
    await asyncio.sleep(0.5)

    # Tin nhắn 2 — Embed giá (có viền)
    embed_price = discord.Embed(
        description=PRICE_TEXT,
        color=config.COLOR_PRIMARY
    )
    embed_price.set_footer(text=config.BOT_FOOTER)
    await channel.send(embed=embed_price)

    print(f"✅ Đã gửi bảng giá boot sivi vào #{channel.name}")
    await bot.close()


bot.run(config.BOT_TOKEN)