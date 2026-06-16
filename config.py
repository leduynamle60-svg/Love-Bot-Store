# ============================================================
#   LOVE BOT STORE — Config (đọc từ .env)
# ============================================================

from dotenv import load_dotenv
import os

load_dotenv()

# --- Discord ---
BOT_TOKEN    = os.getenv("BOT_TOKEN")
GUILD_ID     = int(os.getenv("GUILD_ID"))

# Role IDs
FOUNDER_ROLE_ID = int(os.getenv("FOUNDER_ROLE_ID"))
SUPPORT_ROLE_ID = int(os.getenv("SUPPORT_ROLE_ID"))

# Channel IDs
TICKET_CATEGORY_ID    = int(os.getenv("TICKET_CATEGORY_ID"))
ORDER_CHANNEL_ID      = int(os.getenv("ORDER_CHANNEL_ID"))
FEEDBACK_CHANNEL_ID   = int(os.getenv("FEEDBACK_CHANNEL_ID"))
LOG_CHANNEL_ID        = int(os.getenv("LOG_CHANNEL_ID"))
TRANSCRIPT_CHANNEL_ID = int(os.getenv("TRANSCRIPT_CHANNEL_ID"))

# --- Thanh toán (SePay) ---
SEPAY_WEBHOOK_SECRET = os.getenv("SEPAY_WEBHOOK_SECRET")
BANK_ACCOUNT_NUMBER  = os.getenv("BANK_ACCOUNT_NUMBER")
BANK_ACCOUNT_NAME    = os.getenv("BANK_ACCOUNT_NAME")
BANK_NAME            = os.getenv("BANK_NAME")
BANK_BIN             = os.getenv("BANK_BIN")

# --- Web ---
WEB_SECRET_KEY = os.getenv("WEB_SECRET_KEY", "fallback-secret-key")
WEBHOOK_HOST   = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT   = int(os.getenv("WEBHOOK_PORT", 5000))
WEB_PORT       = int(os.getenv("WEB_PORT", 8080))


# --- Màu embed ---
COLOR_PRIMARY = 0xFF69B4
COLOR_SUCCESS = 0x2ECC71
COLOR_ERROR   = 0xE74C3C
COLOR_WARNING = 0xF39C12
COLOR_INFO    = 0x3498DB

# --- Ticket ---
TICKET_PREFIX        = "ticket"
MAX_TICKETS_PER_USER = 1

# --- Bot ---
BOT_NAME   = "Love Bot Store"
BOT_FOOTER = "Love Bot Store • Mua hàng uy tín 💖"
BOT_AVATAR = ""