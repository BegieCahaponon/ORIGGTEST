import os
import json
import telebot
from flask import Flask, request
from threading import Thread

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
            with open(DB_FILE, 'r') as f: return json.load(f)
        except: pass
    return {
        "users": {
            ADMIN_ID: {"status": "active", "usage_count": 0, "registered": True, "locked_ip": None}
        }, 
        "settings": {"license_key": "KAPTVIP"}
    }

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f, indent=4)

db = load_db()

# --- ENHANCED SECURITY NOTIFICATION ---
def send_security_alert(stolen_id, intruder_ip):
    """Notifies the Admin when an ID is used by an unauthorized IP"""
    alert_msg = (
        f"🚨 **CRITICAL SECURITY ALERT** 🚨\n"
        f"`----------------------------`\n"
        f"👤 **Targeted ID:** `{stolen_id}`\n"
        f"🌐 **Intruder IP:** `{intruder_ip}`\n"
        f"📡 **Status:** Access Terminated\n\n"
        f"⚠️ *An unauthorized device tried to hijack this ID. The connection was automatically severed.*"
    )
    bot.send_message(ADMIN_ID, alert_msg, parse_mode="Markdown")

# --- ADMIN CONTROL PANEL ---

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            args = message.text.split()
            if len(args) < 2:
                bot.reply_to(message, f"{PREFIX}⚠️ Usage: `/kill [ID]`" + FOOTER, parse_mode="Markdown")
                return
            
            target_id = str(args[1]).strip()
            if target_id in db["users"]:
                db["users"][target_id]["status"] = "killed"
                save_db(db)
                bot.reply_to(message, f"{PREFIX}🚫 **NODE DEACTIVATED**\nID: `{target_id}`\nStatus: 𝙱𝚊𝚗𝚗𝚎𝚍" + FOOTER, parse_mode="Markdown")
            else:
                bot.reply_to(message, f"{PREFIX}❌ **ID `{target_id}` NOT FOUND**" + FOOTER, parse_mode="Markdown")
        except:
            bot.reply_to(message, "❌ Error processing command.")

@bot.message_handler(commands=['unlock'])
def unlock_ip(message):
    """Resets the IP lock for a specific user ID if they get a new phone/connection"""
    if str(message.chat.id) == ADMIN_ID:
        try:
            target_id = str(message.text.split()[1]).strip()
            if target_id in db["users"]:
                db["users"][target_id]["locked_ip"] = None
                save_db(db)
                bot.reply_to(message, f"{PREFIX}🔓 **IP LOCK RESET**\nID: `{target_id}`" + FOOTER, parse_mode="Markdown")
        except:
            bot.reply_to(message, "⚠️ Usage: `/unlock [ID]`")

@bot.message_handler(commands=['setkey'])
def set_key(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            new_key = message.text.split(maxsplit=1)[1].strip() 
            db["settings"]["license_key"] = new_key
            save_db(db)
            bot.reply_to(message, f"{PREFIX}🔑 **SECURITY KEY UPDATED**\nNew Key: `{new_key}`" + FOOTER, parse_mode="Markdown")
        except:
            bot.reply_to(message, f"{PREFIX}⚠️ Usage: `/setkey [KEY]`" + FOOTER, parse_mode="Markdown")

# --- UNIVERSAL PROTECTION API ---

@app.route('/check_status')
def check_status():
    target_id = str(request.args.get('id', '')).strip()
    # Get the real IP address of the user running the script
    real_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    if not target_id or target_id not in db["users"]:
        return "not_registered"
    
    user_data = db["users"][target_id]

    # STAGE 1: Check for manual Ban
    if user_data.get("status") == "killed":
        return "killed|0"

    # STAGE 2: Universal IP Locking Logic
    if user_data.get("locked_ip") is None:
        # First use: Lock the ID to the current device's IP
        user_data["locked_ip"] = real_ip
        save_db(db)
    elif user_data["locked_ip"] != real_ip:
        # Hijack attempt: Different IP detected
        send_security_alert(target_id, real_ip)
        return "killed|SECURITY_LOCK"

    # STAGE 3: Grant Access
    current_key = db["settings"]["license_key"].strip()
    user_data["usage_count"] = user_data.get("usage_count", 0) + 1
    save_db(db)
    
    return f"active|{current_key}"

@app.route('/')
def home(): return "KAPTVIP SECURE SERVER ONLINE"

if __name__ == '__main__':
    Thread(target=lambda: bot.polling(none_stop=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
