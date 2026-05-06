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
FOOTER = "\n\n💠 *Dev: KAPTVIP*"  # UPDATED DEVELOPER

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

@bot.message_handler(commands=['setkey'])
def set_key(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            new_key = message.text.split(maxsplit=1)[1].strip() 
            db["settings"]["license_key"] = new_key
            save_db(db)
            msg = f"{PREFIX}🔑 **KEY UPDATED**\n`-----------------------`\nKey: `{new_key}`"
            bot.reply_to(message, msg + FOOTER, parse_mode="Markdown")
        except IndexError:
            bot.reply_to(message, f"{PREFIX}⚠️ Usage: `/setkey [KEY]`" + FOOTER, parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
def stats(message):
    if str(message.chat.id) == ADMIN_ID:
        text = f"{PREFIX}📊 **SYSTEM STATS**\n"
        for uid, data in db["users"].items():
            st = "🟢" if data.get('status') == 'active' else "🔴"
            text += f"{st} `{uid}` | ⚡ `{data.get('usage_count', 0)}` uses\n"
        bot.reply_to(message, text + FOOTER, parse_mode="Markdown")

@bot.message_handler(commands=['start', 'register'])
def register(message):
    uid = str(message.chat.id)
    if uid not in db["users"]:
        db["users"][uid] = {"status": "active", "usage_count": 0, "registered": True, "locked_ip": None}
        save_db(db)
    msg = f"{PREFIX}✅ **NODE ACTIVE**\nID: `{uid}`"
    bot.reply_to(message, msg + FOOTER, parse_mode="Markdown")

# --- API FOR LUA ---
@app.route('/check_status')
def check_status():
    target_id = str(request.args.get('id', ''))
    if not target_id or target_id not in db["users"]:
        return "not_registered"
    
    user_data = db["users"][target_id]
    current_key = db["settings"]["license_key"].strip() # CLEAN KEY
    
    user_data["usage_count"] = user_data.get("usage_count", 0) + 1
    save_db(db)
    
    return f"{user_data['status']}|{current_key}"

if __name__ == '__main__':
    Thread(target=lambda: bot.polling(none_stop=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
