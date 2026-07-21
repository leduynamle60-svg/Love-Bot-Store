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
    from web.app import app
    port = int(os.environ.get("PORT", 10000))
    print(f"[Web] 🌐 Dashboard tại port: {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def start_web_thread():
    t = threading.Thread(target=start_web, daemon=True)
    t.start()


# ── Intents ───────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members         = True
intents.guilds          = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

async def setup_hook():
    await load_cogs()

    synced = await bot.tree.sync()
    print(f"[Slash] ✅ Đã sync {len(synced)} slash commands")

bot.setup_hook = setup_hook


# ── Events ────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"\n{'='*45}")
    print(f"  {config.BOT_NAME} đã khởi động!")
    print(f"  Đăng nhập: {bot.user} (ID: {bot.user.id})")
    print(f"{'='*45}\n")

    from cogs.ticket import OpenTicketView, OpenSupportView, CloseTicketView
    bot.add_view(OpenTicketView())
    bot.add_view(OpenSupportView())
    bot.add_view(CloseTicketView())

    # Self ping để tránh Render spin down
    async def self_ping():
        await asyncio.sleep(60)
        while not bot.is_closed():
            try:
                import aiohttp
                async with aiohttp.ClientSession() as s:
                    async with s.get("https://love-bot-store-pqjc.onrender.com") as r:
                        print(f"[Ping] ✅ {r.status}")
            except Exception as e:
                print(f"[Ping] ❌ {e}")
            await asyncio.sleep(300)

    asyncio.create_task(self_ping())

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="💖Love Store"
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
    cogs = ["cogs.ticket", "cogs.order", "cogs.admin", "cogs.welcome", "cogs.slash"]
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
    start_webhook_thread()
    start_web_thread()

    async with bot:
        await bot.start(config.BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())