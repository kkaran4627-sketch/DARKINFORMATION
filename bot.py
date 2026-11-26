import os
import re
import html
import time
import sqlite3
import asyncio
import logging
from collections import defaultdict

import httpx
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

# ============================================================
# ⚙️ CONFIG — YAHAN APNI DETAILS DAALO
# ============================================================
load_dotenv()

TELEGRAM_TOKEN = ""   # BotFather se

# API 1 (Dark Info)
DARK_API_URL = "https://dark-info.site/test/api.php"
DARK_API_KEY = "Dark-info?008"

# API 2 (Altaf API)
ALTAF_API_URL = "https://altaf-api-maker.base44.app/functions/lookup"
ALTAF_API_KEY = "Demo"  # Paid key @Your_father_786k se milegi

ALLOWED_USERS = []      # Apni ID daalo, jaise [123456789]
RATE_LIMIT = 10
RATE_WINDOW = 60

# ============================================================
# 📝 LOGGING & DATABASE
# ============================================================
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

conn = sqlite3.connect("history.db", check_same_thread=False)
conn.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        tool TEXT,
        query TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

# ============================================================
# 🚦 RATE LIMITER & AUTH
# ============================================================
user_requests = defaultdict(list)

def check_rate_limit(user_id: int) -> bool:
    now = time.time()
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < RATE_WINDOW]
    if len(user_requests[user_id]) >= RATE_LIMIT:
        return False
    user_requests[user_id].append(now)
    return True

def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS

# ============================================================
# 🌐 API CALL FUNCTIONS
# ============================================================
async def call_dark_api(phone: str) -> dict:
    """Dark-Info API call (API 1)"""
    params = {"key": DARK_API_KEY, "num": phone}
    async with httpx.AsyncClient(timeout=40) as client:
        r = await client.get(DARK_API_URL, params=params)
        r.raise_for_status()
        return r.json()

async def call_altaf_api(tool: str, query: str) -> dict:
    """Altaf API call (API 2)"""
    params = {"tool": tool, "key": ALTAF_API_KEY, "q": query}
    async with httpx.AsyncClient(timeout=40) as client:
        r = await client.get(ALTAF_API_URL, params=params)
        r.raise_for_status()
        data = r.json()
        if not data.get("success"):
            raise Exception(data.get("error", "Altaf API returned success=false"))
        return data

# ============================================================
# 🎨 FORMATTERS
# ============================================================
def format_dark_info(data: dict, phone: str) -> str:
    try:
        details = data["Data"]["Main≠details"]["Details"][0]
    except (KeyError, IndexError, TypeError):
        return f"❌ Data nahi mila: <code>{html.escape(phone)}</code>"

    icons = {
        "Mobile": "📱", "Full Name": "👤", "Father's Name": "👨",
        "Address": "🏠", "Adres": "🏠", "Document Number": "🆔",
        "Email": "📧", "DOB": "🎂", "Gender": "⚧",
    }
    lines = [f"📋 <b>DARK-INFO REPORT</b>", "━━━━━━━━━━━━━━━━━━"]
    for key, value in details.items():
        if value and str(value).strip().lower() not in ("null", "none", "n/a", ""):
            icon = icons.get(key, "🔹")
            lines.append(f"{icon} <b>{html.escape(str(key))}:</b> <code>{html.escape(str(value))}</code>")
    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def format_family_info(data: dict, phone: str) -> str:
    try:
        details = data["Data"]["Main≠details"]["Details"][0]
    except (KeyError, IndexError, TypeError):
        return f"❌ Family data nahi mila: <code>{html.escape(phone)}</code>"

    family_keys = ["Full Name", "Father's Name", "Mother's Name", "Wife Name", "Husband Name", "Son Name", "Daughter Name", "Brother Name", "Sister Name", "Address", "Adres"]
    lines = [f"👨‍👩‍👧 <b>FAMILY INFO</b>", "━━━━━━━━━━━━━━━━━━"]
    found = False
    for key in family_keys:
        if key in details and details[key] and str(details[key]).strip().lower() not in ("null", "none", "n/a", ""):
            lines.append(f"🔹 <b>{key}:</b> <code>{html.escape(str(details[key]))}</code>")
            found = True
            
    if not found:
        return f"❌ <b>Family info nahi mili</b>\n\nNumber: <code>{phone}</code>"
    lines.append("━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def format_altaf_info(data: dict, query: str, tool: str) -> str:
    try:
        if tool in ("num", "pak-info"):
            # Number info format
            result = data.get("result", {})
            details = result.get("fields", result)
            if isinstance(details, list):
                details = details[0] if details else {}
            title = "🇮🇳 ALTAF INDIA INFO" if tool == "num" else "🇵🇰 ALTAF PAK INFO"
            lines = [f"📋 <b>{title}</b>", "━━━━━━━━━━━━━━━━━━"]
            for key, value in details.items():
                if value and str(value).strip().lower() not in ("null", "none", "n/a", ""):
                    lines.append(f"🔹 <b>{html.escape(str(key))}:</b> <code>{html.escape(str(value))}</code>")
            lines.append("━━━━━━━━━━━━━━━━━━")
            return "\n".join(lines)

        elif tool in ("veh-2-info", "veh2num"):
            # Vehicle info format
            fields = data["result"]["fields"]
            icons = {
                "registration": "🔢", "owner_name": "👤", "father_s_name": "👨",
                "vehicle_age": "⏳", "manufacturer": "🏭", "model": "🚙",
                "fuel_type": "⛽", "chassis_no": "🔧", "engine_no": "⚙️",
                "insurance_company": "🛡️", "insurance_valid_till": "📅",
                "rto": "📍", "address": "🏠", "owner_serial": "👑",
                "pincode": "📮", "finance_status": "💰",
            }
            title = "🚗 VEHICLE INFO" if tool == "veh-2-info" else "🔄 VEHICLE TO NUMBER"
            lines = [f"<b>{title} — {query}</b>", "━━━━━━━━━━━━━━━━━━"]
            for key, value in fields.items():
                if value and str(value).strip().lower() not in ("null", "none", "n/a", ""):
                    icon = icons.get(key, "🔹")
                    display_key = key.replace("_", " ").title()
                    lines.append(f"{icon} <b>{html.escape(display_key)}:</b> <code>{html.escape(str(value))}</code>")
            lines.append("━━━━━━━━━━━━━━━━━━")
            return "\n".join(lines)
            
    except Exception as e:
        return f"❌ Data parse error: <code>{html.escape(str(e))}</code>"
    
    return "❌ Unknown format"

# ============================================================
# 🎛️ MAIN MENU
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Aap is bot ko use nahi kar sakte.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Dark-Info (India)", callback_data="tool_dark")],
        [InlineKeyboardButton("🇮🇳 Altaf India Number", callback_data="tool_altaf_num")],
        [InlineKeyboardButton("🇵🇰 Altaf Pak Number", callback_data="tool_pak-info")],
        [InlineKeyboardButton("🚗 Vehicle Info", callback_data="tool_veh-2-info")],
        [InlineKeyboardButton("🔄 Vehicle to Number", callback_data="tool_veh2num")],
        [InlineKeyboardButton("👨‍👩‍👧 Family Info", callback_data="tool_family")],
    ])
    
    await update.message.reply_text(
        "👋 <b>Namaste!</b>\n\nMain ek Multi-Tool OSINT Bot hoon. 🕵️\n\n"
        "Neeche se koi option chunein:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )

# ============================================================
# 🔘 MENU HANDLER
# ============================================================
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_allowed(query.from_user.id):
        await query.message.reply_text("⛔ Aap is bot ko use nahi kar sakte.")
        return

    tool = query.data.replace("tool_", "")
    context.user_data["mode"] = tool
    
    prompts = {
        "dark": "📱 <b>India Number</b> bhejein (Dark-Info API)\nExample: <code>9876543210</code>",
        "altaf_num": "🇮🇳 <b>India Number</b> bhejein (Altaf API)\nExample: <code>9876543210</code>",
        "pak-info": "🇵🇰 <b>Pak Number</b> bhejein (bina +92 ke)\nExample: <code>3001234567</code>",
        "veh-2-info": "🚗 <b>Vehicle RC Number</b> bhejein\nExample: <code>MH12AB1234</code>",
        "veh2num": "🔄 <b>Vehicle Number</b> bhejein (Phone nikalne ke liye)\nExample: <code>MH12AB1234</code>",
        "family": "👨‍👩‍👧 <b>Phone Number</b> bhejein (Family info ke liye)\nExample: <code>9876543210</code>",
    }
    
    await query.message.reply_text(prompts.get(tool, "Query bhejein:"), parse_mode=ParseMode.HTML)

# ============================================================
# 💬 MAIN MESSAGE HANDLER
# ============================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ Aap is bot ko use nahi kar sakte.")
        return

    if not check_rate_limit(update.effective_user.id):
        await update.message.reply_text(f"⏳ Bahut zyada requests! {RATE_WINDOW} seconds baad try karein.")
        return

    mode = context.user_data.get("mode", "dark")  # Default Dark API
    text = update.message.text.strip()

    # Input validation
    if mode in ("dark", "altaf_num", "family"):
        match = re.search(r"(\d{10,13})", text)
        if not match:
            await update.message.reply_text("❌ Valid 10-digit number bhejein.")
            return
        query_val = match.group(1)
        if len(query_val) == 10:
            query_val = "91" + query_val
    elif mode == "pak-info":
        match = re.search(r"(\d{10,12})", text)
        if not match:
            await update.message.reply_text("❌ Valid Pak number bhejein (bina +92).")
            return
        query_val = match.group(1)
    elif mode in ("veh-2-info", "veh2num"):
        match = re.search(r"([A-Z]{2}\d{2}[A-Z]{1,2}\d{4})", text.upper())
        if not match:
            await update.message.reply_text("❌ Valid RC number bhejein. Example: <code>MH12AB1234</code>", parse_mode=ParseMode.HTML)
            return
        query_val = match.group(1)
    else:
        query_val = text

    progress = await update.message.reply_text(
        f"⏳ <b>Searching...</b>\nQuery: <code>{html.escape(query_val)}</code>",
        parse_mode=ParseMode.HTML,
    )

    try:
        # API ROUTING
        if mode == "dark":
            data = await call_dark_api(query_val)
            formatted = format_dark_info(data, query_val)
            
        elif mode == "family":
            data = await call_dark_api(query_val)
            formatted = format_family_info(data, query_val)
            
        elif mode in ("altaf_num", "pak-info", "veh-2-info", "veh2num"):
            tool_name = "num" if mode == "altaf_num" else mode
            data = await call_altaf_api(tool_name, query_val)
            formatted = format_altaf_info(data, query_val, tool_name)

        # Reply Buttons
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Copy Query", callback_data=f"copy_{query_val}")],
            [InlineKeyboardButton("🔄 Naya Search", callback_data="new_search")],
        ])

        await progress.edit_text(formatted, parse_mode=ParseMode.HTML, reply_markup=keyboard)

        # Save History
        conn.execute(
            "INSERT INTO history (user_id, tool, query) VALUES (?, ?, ?)",
            (update.effective_user.id, mode, query_val),
        )
        conn.commit()

    except httpx.TimeoutException:
        await progress.edit_text("⏰ Timeout! API ne response nahi diya.")
    except Exception as e:
        logger.exception("Lookup failed")
        await progress.edit_text(f"❌ <b>Error:</b> <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)

# ============================================================
# 🔘 BUTTON HANDLER
# ============================================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("copy_"):
        text = query.data.replace("copy_", "")
        await query.message.reply_text(f"📋 <code>{html.escape(text)}</code>", parse_mode=ParseMode.HTML)
    elif query.data == "new_search":
        await start(update, context)

# ============================================================
# 🏁 COMMANDS & MAIN
# ============================================================
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📖 Menu se option chunein aur query bhejein.\n/history - Last searches\n/stats - Bot stats")

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = conn.execute("SELECT tool, query, timestamp FROM history WHERE user_id=? ORDER BY id DESC LIMIT 10", (update.effective_user.id,)).fetchall()
    if not rows:
        await update.message.reply_text("📭 Koi history nahi.")
        return
    text = "📜 <b>Last 10 Searches</b>\n━━━━━━━━━━━━━━━━━━\n"
    for tool, q, ts in rows:
        text += f"[{tool}] <code>{q}</code> — <i>{ts}</i>\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    today = conn.execute("SELECT COUNT(*) FROM history WHERE DATE(timestamp)=DATE('now')").fetchone()[0]
    text = f"📊 <b>Bot Stats</b>\nTotal: <code>{total}</code>\nToday: <code>{today}</code>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

def main():
    if not TELEGRAM_TOKEN or "YAHAN" in TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN set nahi hai!")
        return

    asyncio.set_event_loop(asyncio.new_event_loop())
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CallbackQueryHandler(menu_handler, pattern="^tool_"))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(copy_|new_search)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Mega OSINT Bot chalu hai...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()