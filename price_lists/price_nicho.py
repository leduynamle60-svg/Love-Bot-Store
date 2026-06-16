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

CHANNEL_ID    = 1515675625430585446   # ID kênh để gửi
THUMBNAIL_URL = "https://cdn.discordapp.com/emojis/1515711803844202627.webp?size=128&animated=true"                   # URL ảnh thumbnail (để trống nếu không có)

# ─────────────────────────────────────────────────────────────

PRICE_TEXT = """# <a:nichooo:1515711803844202627> **Bảng Giá Nitro Boost**
##   Nitro boost log
| • ***1 Tháng*** - ` 90.000 `
| • ***2 Tháng*** - ` 99.000 `
| • ***1 Năm*** - ` 850.000 `
| • ***Gia hạn 2 Tháng*** - ` 95.000 `
- Nếu bạn đã mua **Nitro** bên mình thì có thể gia hạn lại tiếp 2 tháng với giá chỉ 95.000.
- Vui lòng chuẩn bị *tài khoản, mật khẩu, t0ken* 
## Nitro [Trail] log
| • ***3 Tháng*** - ` 80.000 `
| • ***4 Tháng*** - ` 100.000 `
- Dành cho tài khoản nào chưa xài **Nitro** lần nào và phải trên 1 tháng.
- Vui lòng chuẩn bị *tài khoản, mật khẩu, t0ken* 
`` × Hoàn thành trong 48h, nhanh nhất trong ngày ``
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
        title="🎮 Nicho — Bảng Giá",
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

    print(f"✅ Đã gửi bảng giá Nicho vào #{channel.name}")
    await bot.close()


bot.run(config.BOT_TOKEN)