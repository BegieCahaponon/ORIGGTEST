import os
import json
import telebot
import logging
from flask import Flask, request
from threading import Thread

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
TOKEN = "8387040240:AAH7FFS6YbbY-a6IZAdUpyYNBsxJnhsPoMA"
ADMIN_ID = "7817086667" 
DB_FILE = "users.json"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- STYLED MESSAGES ---
PREFIX = "⚡ **KAPT-VIP HUB** ⚡\n"
FOOTER = "\n\n💠 *Dev: KAPTVIP*"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                # Ensure structure exists
                if "users" not in data: data["users"] = {}
                if "settings" not in data: data["settings"] = {"license_key": "KAPTVIP"}
                return data
        except Exception as e:
            logger.error(f"DB Load Error: {e}")
    return {
        "users": {
            ADMIN_ID: {"status": "active", "usage_count": 0, "registered": True, "locked_ip": None}
        }, 
        "settings": {"license_key": "KAPTVIP"}
    }

def save_db(data):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"DB Save Error: {e}")

db = load_db()

# --- SECURITY SYSTEM ---
def send_security_alert(stolen_id, intruder_ip):
    alert_msg = (
        f"🚨 **SECURITY ALERT** 🚨\n"
        f"👤 **Targeted ID:** `{stolen_id}`\n"
        f"🌐 **Intruder IP:** `{intruder_ip}`\n"
        f"⚠️ *Access Blocked Automatically.*"
    )
    try:
        bot.send_message(ADMIN_ID, alert_msg, parse_mode="Markdown")
    except: pass

# --- FIXED COMMAND HANDLERS ---

@bot.message_handler(commands=['start', 'register'])
def register(message):
    uid = str(message.chat.id)
    if uid not in db["users"]:
        db["users"][uid] = {"status": "active", "usage_count": 0, "registered": True, "locked_ip": None}
        save_db(db)
        msg = f"{PREFIX}✅ **REGISTRATION SUCCESSFUL**\nYour ID: `{uid}`"
    else:
        msg = f"{PREFIX}ℹ️ **ALREADY REGISTERED**\nYour ID: `{uid}`"
    bot.reply_to(message, msg + FOOTER, parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
def stats(message):
    if str(message.chat.id) != ADMIN_ID: return
    
    total = len(db["users"])
    text = f"{PREFIX}📊 **SYSTEM STATUS**\nTotal Users: `{total}`\n\n"
    # Show last 10 users to avoid long messages
    for uid, data in list(db["users"].items())[-10:]:
        status_icon = "🟢" if data.get("status") == "active" else "🔴"
        text += f"{status_icon} `{uid}` | ⚡ {data.get('usage_count', 0)}\n"
    
    bot.reply_to(message, text + FOOTER, parse_mode="Markdown")

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, f"{PREFIX}⚠️ Usage: `/kill [ID]`" + FOOTER, parse_mode="Markdown")
            return
        
        target_id = parts[1].strip()
        if target_id in db["users"]:
            db["users"][target_id]["status"] = "killed"
            save_db(db)
            bot.reply_to(message, f"{PREFIX}🚫 **USER BANNED**\nID: `{target_id}`" + FOOTER, parse_mode="Markdown")
        else:
            bot.reply_to(message, f"{PREFIX}❌ ID `{target_id}` not found." + FOOTER, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Kill Error: {e}")

@bot.message_handler(commands=['unlock'])
def unlock_user(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, f"{PREFIX}⚠️ Usage: `/unlock [ID]`" + FOOTER, parse_mode="Markdown")
            return
        
        target_id = parts[1].strip()
        if target_id in db["users"]:
            db["users"][target_id]["locked_ip"] = None
            db["users"][target_id]["status"] = "active"
            save_db(db)
            bot.reply_to(message, f"{PREFIX}🔓 **USER UNLOCKED**\nID: `{target_id}`" + FOOTER, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Unlock Error: {e}")

@bot.message_handler(commands=['setkey'])
def set_key(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        new_key = message.text.split(maxsplit=1)[1].strip()
        db["settings"]["license_key"] = new_key
        save_db(db)
        bot.reply_to(message, f"{PREFIX}🔑 **KEY UPDATED**\nNew: `{new_key}`" + FOOTER, parse_mode="Markdown")
    except:
        bot.reply_to(message, f"{PREFIX}⚠️ Usage: `/setkey [KEY]`" + FOOTER, parse_mode="Markdown")

# --- LUA API ---

@app.route('/check_status')
def check_status():
    target_id = str(request.args.get('id', '')).strip()
    real_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    if not target_id or target_id not in db["users"]:
        return "not_registered"
    
    user_data = db["users"][target_id]
    
    # Status Check
    if user_data.get("status") == "killed":
        return "killed|0"

    # IP Lock Check
    if user_data.get("locked_ip") is None:
        user_data["locked_ip"] = real_ip
        save_db(db)
    elif user_data["locked_ip"] != real_ip:
        send_security_alert(target_id, real_ip)
        return "killed|IP_LOCK"

    current_key = db["settings"].get("license_key", "KAPTVIP")
    user_data["usage_count"] = user_data.get("usage_count", 0) + 1
    save_db(db)
    
    return f"active|{current_key}"

@app.route('/')
def health_check():
    return "KAPTVIP SERVER ONLINE", 200

def run_bot():
    logger.info("Bot Polling Started...")
    bot.infinity_polling()

if __name__ == '__main__':
    # Start bot in a background thread
    Thread(target=run_bot, daemon=True).start()
    # Start web server
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
