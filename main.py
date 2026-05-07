import os
import telebot
import certifi
import ssl # Added for extra security control
from flask import Flask, request
from threading import Thread
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

# --- CONFIGURATION ---
TOKEN = "8387040240:AAH7FFS6YbbY-a6IZAdUpyYNBsxJnhsPoMA"
ADMIN_ID = "7817086667" 
# Ensure your password doesn't have special characters like @ or : 
# If it does, you must URL-encode them.
MONGO_URL = "mongodb+srv://begiecahaponon08:Cahapononbegie123@cluster0.a8hcjx1.mongodb.net/?appName=Cluster0"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- STYLED MESSAGES ---
PREFIX = "⚡ **KAPT-VIP HUB** ⚡\n"
FOOTER = "\n\n💠 *Dev: HEROSHI*"

# --- ROBUST DATABASE SETUP ---
try:
    ca = certifi.where()
    # We add 'tlsAllowInvalidCertificates=True' ONLY as a temporary fix 
    # if your Render environment has outdated SSL libraries.
    client = MongoClient(
        MONGO_URL, 
        tlsCAFile=ca,
        serverSelectionTimeoutMS=5000, 
        connectTimeoutMS=10000,
        tls=True
    )
    
    # TEST THE CONNECTION IMMEDIATELY
    client.admin.command('ping')
    
    db = client['KAPTVIP_DB']
    users_col = db['users']
    settings_col = db['settings']
    
    if not settings_col.find_one({"id": "config"}):
        settings_col.insert_one({"id": "config", "license_key": "KAPTVIP"})
    print("✅ DATABASE CONNECTED: System is online.")
except Exception as e:
    print(f"❌ DATABASE CRITICAL ERROR: {e}")
    # We don't stop the script so the Web UI still shows 'Online' on Render
    users_col = None 

# --- UTILITIES ---
def is_db_ready():
    return users_col is not None

# --- ADMIN COMMANDS ---

@bot.message_handler(commands=['stats'])
def stats(message):
    if str(message.chat.id) != ADMIN_ID: return
    if not is_db_ready():
        return bot.reply_to(message, "❌ Database is currently offline. Check Render logs.")
    
    try:
        total = users_col.count_documents({})
        recent_users = users_col.find().sort("_id", -1).limit(10)
        
        text = f"{PREFIX}📊 **SYSTEM STATUS**\nTotal Users: `{total}`\n\n"
        for u in recent_users:
            status_icon = "🟢" if u.get("status") == "active" else "🔴"
            text += f"{status_icon} `{u['uid']}` | ⚡ `{u.get('usage', 0)}` uses\n"
            
        bot.reply_to(message, text + FOOTER, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Stats Error: {str(e)}")

@bot.message_handler(commands=['unblock', 'unlock'])
def unblock_user(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        target_id = message.text.split()[1].strip()
        users_col.update_one({"uid": target_id}, {"$set": {"status": "active", "locked_ip": None}})
        bot.reply_to(message, f"🔓 `{target_id}` Restored.")
    except: bot.reply_to(message, "Usage: `/unblock [ID]`")

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        target_id = message.text.split()[1].strip()
        users_col.update_one({"uid": target_id}, {"$set": {"status": "killed"}})
        bot.reply_to(message, f"🚫 `{target_id}` Banned.")
    except: pass

@bot.message_handler(commands=['setkey'])
def set_key(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        new_key = message.text.split(maxsplit=1)[1].strip()
        settings_col.update_one({"id": "config"}, {"$set": {"license_key": new_key}})
        bot.reply_to(message, f"🔑 Key set to: `{new_key}`")
    except: pass

@bot.message_handler(commands=['start', 'register'])
def register(message):
    if not is_db_ready(): return
    uid = str(message.chat.id)
    if not users_col.find_one({"uid": uid}):
        users_col.insert_one({"uid": uid, "status": "active", "usage": 0, "locked_ip": None})
    bot.reply_to(message, f"{PREFIX}✅ **REGISTERED**\nID: `{uid}`" + FOOTER, parse_mode="Markdown")

# --- LUA API ---

@app.route('/check_status')
def check_status():
    if not is_db_ready(): return "error|db_offline"
    
    target_id = str(request.args.get('id', '')).strip()
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    user = users_col.find_one({"uid": target_id})
    if not user: return "not_registered"
    if user.get("status") == "killed": return "killed|0"

    # Device Lock
    if not user.get("locked_ip"):
        users_col.update_one({"uid": target_id}, {"$set": {"locked_ip": client_ip}})
    elif user["locked_ip"] != client_ip:
        return "killed|IP_MISMATCH"

    config = settings_col.find_one({"id": "config"})
    users_col.update_one({"uid": target_id}, {"$inc": {"usage": 1}})
    return f"active|{config['license_key']}"

@app.route('/')
def home(): return "KAPTVIP SERVER: " + ("ONLINE" if is_db_ready() else "OFFLINE (DB ERROR)")

if __name__ == '__main__':
    Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
