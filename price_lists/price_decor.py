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

CHANNEL_ID    = 1515675666710790265
THUMBNAIL_URL = "https://cdn.discordapp.com/emojis/1444001440673697834.webp?size=128"                   # URL ảnh thumbnail (để trống nếu không có)

# ─────────────────────────────────────────────────────────────

PRICE_TEXT = """# <:Deco:1524606063603613778> **Bảng Giá Deco**

## DẠNG LOG
```text
Giá ditcod      Có nicho       Không nicho
66.000           25.000     
72.000           36.000     
79.000                           39.000
92.000           59.000     
105.000          69.000          69.000
111.000          75.000     
131.000          88.000          89.000
141.000          95.000          95.000
146.000                          99.000
189.000                          119.000
```

## DẠNG GIFT
```text
Giá ditcod        Giá sốp
 66.000           46.000
 79.000           52.000
 92.000           62.000
 105.000          69.000
 118.000          85.000
 131.000          89.000
 141.000          99.000
 146.000          115.000
 189.000          140.000
 220.000          160.000
```

`` × Hoàn thành trong vòng 24h-72h, nhanh nhất trong ngày ``
`` × Đảm bảo chất lượng hàng ổn định, bảo hành 1 đổi 1``

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
        title="🎮 Decoo — Bảng Giá",
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

    print(f"✅ Đã gửi bảng giá deco vào #{channel.name}")
    await bot.close()


bot.run(config.BOT_TOKEN)