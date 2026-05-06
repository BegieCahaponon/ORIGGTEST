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

# Load/Save Database
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f: return json.load(f)
    return {"users": {}, "settings": {"license_key": "KAPT-VIP-LIFETIME"}}

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f, indent=4)

db = load_db()

# --- BOT COMMANDS ---

@bot.message_handler(commands=['start', 'register'])
def register(message):
    uid = str(message.chat.id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "status": "active",
            "usage_count": 0,
            "country": "Unknown",
            "registered": True
        }
        save_db(db)
        bot.reply_to(message, f"✅ Registered! Your ID: `{uid}`\nUse this ID in the script.", parse_mode="Markdown")
    else:
        bot.reply_to(message, "You are already registered.")

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            target = message.text.split()[1]
            if target in db["users"]:
                db["users"][target]["status"] = "killed"
                save_db(db)
                bot.reply_to(message, f"🚫 User {target} has been KILLED.")
            else: bot.reply_to(message, "User not found.")
        except: bot.reply_to(message, "Usage: /kill [ID]")

@bot.message_handler(commands=['stats'])
def stats(message):
    if str(message.chat.id) == ADMIN_ID:
        total = len(db["users"])
        text = f"📊 **Total Users:** {total}\n\n"
        for uid, data in db["users"].items():
            text += f"ID: `{uid}` | {data['country']} | Uses: {data['usage_count']} | {data['status']}\n"
        bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['setkey'])
def set_key(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            new_key = message.text.split()[1]
            db["settings"]["license_key"] = new_key
            save_db(db)
            bot.reply_to(message, f"🔑 License Key updated to: `{new_key}`")
        except: bot.reply_to(message, "Usage: /setkey [NEW_KEY]")

# --- FLASK API ---

@app.route('/check_status')
def check_status():
    user_id = request.args.get('id')
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    
    if not user_id or user_id not in db["users"]:
        return "not_registered"

    user = db["users"][user_id]
    
    # Check Geolocation if unknown
    if user["country"] == "Unknown":
        try:
            geo = requests.get(f"http://ip-api.com/json/{user_ip}").json()
            user["country"] = geo.get("country", "Unknown")
        except: pass

    # Increase usage count
    user["usage_count"] += 1
    save_db(db)
    
    return f"{user['status']}|{db['settings']['license_key']}"

@app.route('/')
def home(): return "KAPTVIP Server Active"

if __name__ == '__main__':
    Thread(target=lambda: bot.polling(none_stop=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
