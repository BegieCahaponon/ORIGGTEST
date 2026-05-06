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

# --- STYLED MESSAGES ---
PREFIX = "⚡ **[KAPT-VIP HUB]** ⚡\n"
FOOTER = "\n\n💠 *Dev: HEROSHI*"

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

# --- ADMIN COMMANDS ---

@bot.message_handler(commands=['stats'])
def stats(message):
    if str(message.chat.id) == ADMIN_ID:
        total_users = len(db["users"])
        text = f"{PREFIX}📊 **SYSTEM DIAGNOSTICS**\n`-----------------------`\n"
        text += f"Total Nodes: `{total_users}`\n\n"
        for uid, data in db["users"].items():
            st = "🟢" if data.get('status') == 'active' else "🔴"
            text += f"{st} `{uid}` | ⚡ `{data.get('usage_count', 0)}` uses\n"
        bot.reply_to(message, text + FOOTER, parse_mode="Markdown")
    else:
        bot.reply_to(message, PREFIX + "❌ **ACCESS DENIED.**" + FOOTER, parse_mode="Markdown")

@bot.message_handler(commands=['setkey'])
def set_key(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            # FIX: Use strip() to ensure no spaces are saved
            new_key = message.text.split(maxsplit=1)[1].strip() 
            db["settings"]["license_key"] = new_key
            save_db(db)
            msg = f"{PREFIX}🔑 **SECURITY KEY UPDATED**\n`-----------------------`\nNew Key: `{new_key}`"
            bot.reply_to(message, msg + FOOTER, parse_mode="Markdown")
        except IndexError:
            bot.reply_to(message, PREFIX + "⚠️ Usage: `/setkey [KEY]`" + FOOTER, parse_mode="Markdown")

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            target_id = str(message.text.split()[1])
            if target_id in db["users"]:
                db["users"][target_id]["status"] = "killed"
                save_db(db)
                bot.reply_to(message, f"{PREFIX}🚫 **NODE DEACTIVATED**\nID: `{target_id}`" + FOOTER, parse_mode="Markdown")
        except: pass

# --- USER COMMANDS ---

@bot.message_handler(commands=['start', 'register'])
def register(message):
    uid = str(message.chat.id)
    if uid not in db["users"]:
        db["users"][uid] = {"status": "active", "usage_count": 0, "registered": True, "locked_ip": None}
        save_db(db)
        msg = f"{PREFIX}✅ **REGISTRATION COMPLETE**\n`-----------------------`\nYour Node ID: `{uid}`"
    else:
        msg = f"{PREFIX}ℹ️ **NODE ALREADY ACTIVE**\nNode ID: `{uid}`"
    
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("🌐 Visit Community", url="https://t.me/yourlink"))
    bot.reply_to(message, msg + FOOTER, reply_markup=markup, parse_mode="Markdown")

# --- API FOR LUA ---

@app.route('/check_status')
def check_status():
    target_id = str(request.args.get('id', ''))
    if not target_id or target_id not in db["users"]:
        return "not_registered"
    
    user_data = db["users"][target_id]
    # FIX: Ensure we return the key exactly as saved
    current_key = db["settings"]["license_key"]
    
    user_data["usage_count"] = user_data.get("usage_count", 0) + 1
    save_db(db)
    
    return f"{user_data['status']}|{current_key}"

@app.route('/')
def home(): return "KAPTVIP SECURE SERVER ONLINE"

if __name__ == '__main__':
    Thread(target=lambda: bot.polling(none_stop=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
