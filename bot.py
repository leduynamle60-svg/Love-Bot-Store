"""
bot.py — Entry point chính của Love Bot Store
Chạy: python bot.py
"""

import discord
from discord.ext import commands
import asyncio
import threading
import sys, os

import config
import database as db
import web_db as wdb
from webhook_server import set_bot, start_webhook_thread

# ── Web Dashboard ─────────────────────────────────────────────
def start_web():
    sys.path.insert(0, os.path.dirname(__file__))
    from web.app import app
    print(f"[Web] 🌐 Dashboard: http://localhost:8080")
    print(f"[Web] 👤 Đăng nhập: founder / admin123")
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

def start_web_thread():
    t = threading.Thread(target=start_web, daemon=True)
    t.start()

# ── Intents ───────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members         = True
intents.guilds          = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ── Events ────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"\n{'='*45}")
    print(f"  {config.BOT_NAME} đã khởi động!")
    print(f"  Đăng nhập: {bot.user} (ID: {bot.user.id})")
    print(f"{'='*45}\n")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="💖 Love Bot Store"
        )
    )

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ Bạn không có quyền dùng lệnh này!", delete_after=5)
    else:
        raise error

# ── Load Cogs ─────────────────────────────────────────────────
async def load_cogs():
    cogs = ["cogs.ticket", "cogs.order", "cogs.admin", "cogs.welcome"]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            print(f"[Cog] ✅ Loaded: {cog}")
        except Exception as e:
            print(f"[Cog] ❌ Lỗi load {cog}: {e}")

# ── Main ──────────────────────────────────────────────────────
async def main():
    db.init_db()
    wdb.init_web_db()
    set_bot(bot)
    start_webhook_thread()   # SePay webhook port 5000
    start_web_thread()       # Web dashboard port 8080

    async with bot:
        await load_cogs()
        await bot.start(config.BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())