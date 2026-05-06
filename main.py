import os
import json
import telebot
import logging
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
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return {
        "users": {
            ADMIN_ID: {"status": "active", "usage_count": 0, "locked_ip": None}
        }, 
        "settings": {"license_key": "KAPTVIP"}
    }

def save_db(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

db = load_db()

# --- ADMIN COMMANDS ---

@bot.message_handler(commands=['resetall'])
def reset_all(message):
    """Wipes the database and restarts with only the Admin."""
    if str(message.chat.id) != ADMIN_ID: return
    global db
    db = {
        "users": {
            ADMIN_ID: {"status": "active", "usage_count": 0, "locked_ip": None}
        }, 
        "settings": {"license_key": "KAPTVIP"}
    }
    save_db(db)
    bot.reply_to(message, f"{PREFIX}♻️ **DATABASE WIPED CLEAN**\nAll users have been removed.\nRegister yourself again with /start." + FOOTER, parse_mode="Markdown")

@bot.message_handler(commands=['unblock', 'unrevoke'])
def unblock_user(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        target_id = message.text.split()[1].strip()
        if target_id in db["users"]:
            db["users"][target_id]["status"] = "active"
            db["users"][target_id]["locked_ip"] = None # Reset IP lock
            save_db(db)
            bot.reply_to(message, f"{PREFIX}🔓 **USER RESTORED**\nID: `{target_id}`\nStatus: Active & IP Reset" + FOOTER, parse_mode="Markdown")
        else:
            bot.reply_to(message, f"{PREFIX}❌ ID `{target_id}` not found.")
    except:
        bot.reply_to(message, "⚠️ Usage: `/unblock [ID]`")

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        target_id = message.text.split()[1].strip()
        if target_id == ADMIN_ID: return
        if target_id in db["users"]:
            db["users"][target_id]["status"] = "killed"
            save_db(db)
            bot.reply_to(message, f"{PREFIX}🚫 **ACCESS REVOKED**\nID: `{target_id}`" + FOOTER, parse_mode="Markdown")
    except: pass

@bot.message_handler(commands=['setkey'])
def set_key(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        new_key = message.text.split(maxsplit=1)[1].strip()
        db["settings"]["license_key"] = new_key
        save_db(db)
        bot.reply_to(message, f"{PREFIX}🔑 **KEY UPDATED:** `{new_key}`" + FOOTER, parse_mode="Markdown")
    except: pass

@bot.message_handler(commands=['start', 'register'])
def register(message):
    uid = str(message.chat.id)
    if uid not in db["users"]:
        db["users"][uid] = {"status": "active", "usage_count": 0, "locked_ip": None}
        save_db(db)
        bot.reply_to(message, f"{PREFIX}✅ **REGISTERED**\nYour ID: `{uid}`" + FOOTER, parse_mode="Markdown")
    else:
        bot.reply_to(message, f"{PREFIX}ℹ️ **ALREADY ACTIVE**\nID: `{uid}`" + FOOTER, parse_mode="Markdown")

# --- LUA API ---

@app.route('/check_status')
def check_status():
    target_id = str(request.args.get('id', '')).strip()
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    # 1. Verification: Only access if ID exists in our database
    if not target_id or target_id not in db["users"]:
        return "not_registered"
    
    user_data = db["users"][target_id]

    # 2. Check if the ID is manually blocked (Revoked)
    if user_data.get("status") == "killed":
        return "killed|0"

    # 3. ANTI-SPOOFING & IP LOCK
    # If it's your Admin ID, be extra strict
    if target_id == ADMIN_ID:
        if user_data["locked_ip"] is not None and user_data["locked_ip"] != client_ip:
            # Notify you if someone tries to use your ID
            bot.send_message(ADMIN_ID, f"🚨 **WARNING!**\nSomeone tried to use your Admin ID from IP: `{client_ip}`")
            return "killed|SPOOF_DETECTED"
    
    # 4. Standard IP Lock (One ID = One Device)
    if user_data["locked_ip"] is None:
        user_data["locked_ip"] = client_ip
        save_db(db)
    elif user_data["locked_ip"] != client_ip:
        return "killed|IP_MISMATCH"

    current_key = db["settings"].get("license_key", "KAPTVIP")
    user_data["usage_count"] = user_data.get("usage_count", 0) + 1
    save_db(db)
    
    return f"active|{current_key}"

@app.route('/')
def home(): return "KAPTVIP SERVER ONLINE"

if __name__ == '__main__':
    Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
