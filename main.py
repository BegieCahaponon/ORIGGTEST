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
    # Ensure Admin is always pre-registered
    return {
        "users": {
            ADMIN_ID: {"status": "active", "usage_count": 0, "country": "Admin", "registered": True}
        }, 
        "settings": {"license_key": "KAPT-VIP-LIFETIME"}
    }

def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f, indent=4)

db = load_db()

@bot.message_handler(commands=['start', 'register'])
def register(message):
    uid = str(message.chat.id)
    if uid not in db["users"]:
        db["users"][uid] = {"status": "active", "usage_count": 0, "country": "Unknown", "registered": True}
        save_db(db)
        bot.reply_to(message, f"✅ Registered! ID: `{uid}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, "You are already registered.")

@app.route('/check_status')
def check_status():
    # Force string comparison for the ID
    user_id = str(request.args.get('id', ''))
    
    if not user_id or user_id not in db["users"]:
        return "not_registered"

    user = db["users"][user_id]
    user["usage_count"] += 1
    save_db(db)
    
    return f"{user['status']}|{db['settings']['license_key']}"

@app.route('/')
def home(): return "Server Online"

if __name__ == '__main__':
    Thread(target=lambda: bot.polling(none_stop=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
