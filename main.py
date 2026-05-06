import os
import json
import telebot
import requests
from flask import Flask, request
from threading import Thread

# --- CONFIGURATION ---
TOKEN = "8387040240:AAH7FFS6YbbY-a6IZAdUpyYNBsxJnhsPoMA"
ADMIN_ID = "7817086667" 
DB_FILE = "users.json"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f: return json.load(f)
        except: pass
    return {
        "users": {
            ADMIN_ID: {"status": "active", "usage_count": 0, "country": "Admin", "registered": True, "locked_ip": None}
        }, 
        "settings": {"license_key": "KAPT-VIP-LIFETIME"}
    }

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f, indent=4)

db = load_db()

# --- SECURITY ALERT SYSTEM ---
def send_security_alert(target_id, intruder_id, intruder_name):
    alert_msg = (
        f"🚨 **SECURITY ALERT: ID THEFT ATTEMPT** 🚨\n\n"
        f"👤 **Targeted ID:** `{target_id}`\n"
        f"👤 **Intruder ID:** `{intruder_id}`\n"
        f"📛 **Intruder Name:** {intruder_name}\n\n"
        f"⚠️ *Someone is trying to use an ID that isn't theirs!*"
    )
    bot.send_message(ADMIN_ID, alert_msg, parse_mode="Markdown")

# --- ADMIN COMMANDS ---
@bot.message_handler(commands=['stats'])
def stats(message):
    if str(message.chat.id) == ADMIN_ID:
        total_users = len(db["users"])
        text = f"📊 **SYSTEM STATS**\nTotal: {total_users}\n\n"
        for uid, data in db["users"].items():
            text += f"👤 `{uid}` | ⚡ {data.get('usage_count', 0)} | {data.get('status', 'active')}\n"
        bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['setkey'])
def set_key(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            new_key = message.text.split(maxsplit=1)[1].strip() 
            db["settings"]["license_key"] = new_key
            save_db(db)
            bot.reply_to(message, f"🔑 **Key Updated:** `{new_key}`")
        except: pass

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            target_id = str(message.text.split()[1])
            if target_id in db["users"]:
                db["users"][target_id]["status"] = "killed"
                save_db(db)
                bot.reply_to(message, f"🚫 **Banned:** `{target_id}`")
        except: pass

# --- USER REGISTRATION ---
@bot.message_handler(commands=['start', 'register'])
def register(message):
    uid = str(message.chat.id)
    uname = message.from_user.first_name
    
    if uid not in db["users"]:
        db["users"][uid] = {
            "name": uname,
            "status": "active", 
            "usage_count": 0, 
            "registered": True,
            "locked_ip": None # For Anti-Share
        }
        save_db(db)
        bot.reply_to(message, f"✅ **Registered!**\nWelcome {uname}. Your ID is `{uid}`.")
    else:
        bot.reply_to(message, f"ℹ️ Welcome back {uname}. Your ID is `{uid}`.")

# --- API FOR LUA (WITH ANTI-THEFT) ---
@app.route('/check_status')
def check_status():
    target_id = str(request.args.get('id', ''))
    # This is the actual user running the script
    real_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    if not target_id or target_id not in db["users"]:
        return "not_registered"
    
    user_data = db["users"][target_id]

    # [ANTI-SHARE LOGIC]
    # If the ID is already used by one IP, don't let another IP use it
    if user_data["locked_ip"] is None:
        user_data["locked_ip"] = real_ip
    elif user_data["locked_ip"] != real_ip and target_id != ADMIN_ID:
        # If IP doesn't match, it means someone else is using the ID
        send_security_alert(target_id, "Unknown/External", "IP Mismatch")
        return "killed"

    user_data["usage_count"] = user_data.get("usage_count", 0) + 1
    save_db(db)
    
    return f"{user_data['status']}|{db['settings']['license_key']}"

@app.route('/')
def home(): return "KAPTVIP Server Secure"

if __name__ == '__main__':
    Thread(target=lambda: bot.polling(none_stop=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
