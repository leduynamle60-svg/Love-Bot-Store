"""
stock.py — Gửi bảng tồn kho vào kênh Discord chỉ định
Chạy: python stock.py
"""

import discord
import asyncio
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# ─────────────────────────────────────────────────────────────
#  ĐIỀN THÔNG TIN VÀO ĐÂY
# ─────────────────────────────────────────────────────────────

CHANNEL_ID = 1515676281847414815   # ID kênh thông báo stock

# Danh sách hàng: (tên sản phẩm, giá, slot còn)
STOCK = [
    ("Nicho 1 Tháng",       "90.000đ",   0),
    ("Nicho 2 Tháng",       "99.000đ",   0),
    ("Nicho 1 Năm",         "850.000đ",  0),
    ("Nicho Gia Hạn 2T",    "95.000đ",   0),
    ("Nicho Trail 3 Tháng", "80.000đ",   0),
    ("Nicho Trail 4 Tháng", "100.000đ",  0),
    ("Yutube 1 tháng",      "20.000đ",   0),
    ("Boot sivi 1 tháng chỉ từ ", "28.000đ",  0),
    # Thêm sản phẩm khác vào đây...
    # ("Netflix 1 Tháng",   "xxx.xxxđ",  x),
    # ("Spotify 1 Tháng",   "xxx.xxxđ",  x),
]

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

    # Build bảng tồn kho
    rows = ""
    for name, price, slot in STOCK:
        if slot == 0:
            slot_str = "❌ Hết hàng"
        elif slot <= 2:
            slot_str = f"⚠️ Còn {slot}"
        else:
            slot_str = f"✅ Còn {slot}"

        rows += f"`{name:<22}` | `{price:>10}` | {slot_str}\n"

    embed = discord.Embed(
        title="SÌ TÓC",
        description=rows,
        color=0xFF69B4,
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(
        name="Chú thích",
        value="✅ Còn hàng  •  ⚠️ Sắp hết  •  ❌ Hết hàng",
        inline=False
    )
    embed.set_footer(text=config.BOT_FOOTER)

    await channel.send(embed=embed)
    print(f"✅ Đã gửi bảng tồn kho vào #{channel.name}")
    await bot.close()


bot.run(config.BOT_TOKEN)