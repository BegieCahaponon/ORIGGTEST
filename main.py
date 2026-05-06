import os
import json
import telebot
import requests
from flask import Flask, request
from threading import Thread

# --- CONFIGURATION ---
TOKEN = "8387040240:AAH7FFS6YbbY-a6IZAdUpyYNBsxJnhsPoMA"
ADMIN_ID = "7817086667"  # Your ID from the screenshot
DB_FILE = "users.json"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f: return json.load(f)
        except: pass
    # Default DB structure
    return {
        "users": {
            ADMIN_ID: {"status": "active", "usage_count": 0, "country": "Admin", "registered": True}
        }, 
        "settings": {"license_key": "KAPT-VIP-LIFETIME"}
    }

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f, indent=4)

db = load_db()

# --- ADMIN COMMAND FIXES ---

@bot.message_handler(commands=['stats'])
def stats(message):
    # This check ensures only YOU can see stats
    if str(message.chat.id) == ADMIN_ID:
        total_users = len(db["users"])
        text = f"📊 **KAPT-VIP SYSTEM STATS**\nTotal Registered: {total_users}\n\n"
        for uid, data in db["users"].items():
            text += f"👤 `{uid}` | 🌍 {data.get('country', '??')} | ⚡ {data.get('usage_count', 0)} uses | [{data.get('status', 'active')}]\n"
        bot.reply_to(message, text, parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Unauthorized. This command is for Admin only.")

@bot.message_handler(commands=['setkey'])
def set_key(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            # Extract new key after the command[cite: 1]
            new_key = message.text.split(maxsplit=1)[1]
            db["settings"]["license_key"] = new_key
            save_db(db)
            bot.reply_to(message, f"🔑 **License Key Updated!**\nNew Key: `{new_key}`", parse_mode="Markdown")
        except IndexError:
            bot.reply_to(message, "⚠️ Usage: `/setkey YOURNEWKEY`", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Unauthorized.")

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            target_id = str(message.text.split()[1])
            if target_id in db["users"]:
                db["users"][target_id]["status"] = "killed"
                save_db(db)
                bot.reply_to(message, f"🚫 **User Banned!**\nID `{target_id}` has been deactivated.", parse_mode="Markdown")
            else:
                bot.reply_to(message, "⚠️ User ID not found in database.")
        except IndexError:
            bot.reply_to(message, "⚠️ Usage: `/kill [USER_ID]`")
    else:
        bot.reply_to(message, "❌ Unauthorized.")

@bot.message_handler(commands=['start', 'register'])
def register(message):
    uid = str(message.chat.id)
    if uid not in db["users"]:
        db["users"][uid] = {"status": "active", "usage_count": 0, "country": "Unknown", "registered": True}
        save_db(db)
        bot.reply_to(message, f"✅ **Registration Successful!**\nYour ID: `{uid}`\nEnter this ID in your Lua script.", parse_mode="Markdown")
    else:
        bot.reply_to(message, "ℹ️ You are already in the system.")

# --- FLASK API ---

@app.route('/check_status')
def check_status():
    user_id = str(request.args.get('id', ''))
    if not user_id or user_id not in db["users"]:
        return "not_registered"
    
    user = db["users"][user_id]
    user["usage_count"] = user.get("usage_count", 0) + 1
    save_db(db)
    
    return f"{user['status']}|{db['settings']['license_key']}"

@app.route('/')
def home(): return "Bot Server Running"

if __name__ == '__main__':
    Thread(target=lambda: bot.polling(none_stop=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
