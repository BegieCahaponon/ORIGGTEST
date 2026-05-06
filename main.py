import os
import telebot
import certifi
import logging
from flask import Flask, request
from threading import Thread
from pymongo import MongoClient

# --- CONFIGURATION ---
# Replace YOUR_MONGODB_CONNECTION_STRING with your link from MongoDB Atlas
TOKEN = "8387040240:AAH7FFS6YbbY-a6IZAdUpyYNBsxJnhsPoMA"
ADMIN_ID = "7817086667" 
MONGO_URL = "mongodb+srv://begiecahaponon08:<db_password>@cluster0.a8hcjx1.mongodb.net/?appName=Cluster0"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- DATABASE SETUP (SSL FIXED) ---
try:
    ca = certifi.where()
    client = MongoClient(
        MONGO_URL, 
        tlsCAFile=ca, 
        serverSelectionTimeoutMS=5000, 
        connectTimeoutMS=10000
    )
    db = client['KAPTVIP_DB']
    users_col = db['users']
    settings_col = db['settings']
    
    # Initialize license key if it doesn't exist
    if not settings_col.find_one({"id": "config"}):
        settings_col.insert_one({"id": "config", "license_key": "KAPTVIP"})
    print("✅ MongoDB Connected Successfully")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")

# --- STYLED MESSAGES ---
PREFIX = "⚡ **KAPT-VIP HUB** ⚡\n"
FOOTER = "\n\n💠 *Dev: HEROSHI*"

# --- SECURITY UTILITIES ---

def find_user_by_ip(ip):
    """Checks if the intruder's IP belongs to a registered Telegram user."""
    intruder = users_col.find_one({"locked_ip": ip})
    return intruder['uid'] if intruder else "Unknown Stranger"

# --- ADMIN COMMANDS ---

@bot.message_handler(commands=['stats'])
def stats(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        total = users_col.count_documents({})
        text = f"{PREFIX}📊 **SYSTEM STATUS**\nTotal Users: `{total}`\n\n"
        
        # Show last 10 registered users
        recent_users = users_col.find().sort("_id", -1).limit(10)
        for u in recent_users:
            status_icon = "🟢" if u.get("status") == "active" else "🔴"
            text += f"{status_icon} `{u['uid']}` | ⚡ `{u.get('usage', 0)}` uses\n"
            
        bot.reply_to(message, text + FOOTER, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Stats Error: {str(e)}")

@bot.message_handler(commands=['unblock', 'unrevoke', 'unlock'])
def unblock_user(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        target_id = message.text.split()[1].strip()
        users_col.update_one(
            {"uid": target_id}, 
            {"$set": {"status": "active", "locked_ip": None}}
        )
        bot.reply_to(message, f"{PREFIX}🔓 **USER RESTORED**\nID: `{target_id}`\nStatus: Active & IP Reset" + FOOTER, parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ Usage: `/unblock [ID]`")

@bot.message_handler(commands=['resetall'])
def reset_all(message):
    if str(message.chat.id) != ADMIN_ID: return
    # Deletes everyone except you
    users_col.delete_many({"uid": {"$ne": ADMIN_ID}})
    bot.reply_to(message, f"{PREFIX}♻️ **DATABASE WIPED**\nAll users removed." + FOOTER, parse_mode="Markdown")

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        target_id = message.text.split()[1].strip()
        if target_id == ADMIN_ID: return
        users_col.update_one({"uid": target_id}, {"$set": {"status": "killed"}})
        bot.reply_to(message, f"{PREFIX}🚫 **ACCESS REVOKED**\nID: `{target_id}`" + FOOTER, parse_mode="Markdown")
    except: pass

@bot.message_handler(commands=['setkey'])
def set_key(message):
    if str(message.chat.id) != ADMIN_ID: return
    try:
        new_key = message.text.split(maxsplit=1)[1].strip()
        settings_col.update_one({"id": "config"}, {"$set": {"license_key": new_key}})
        bot.reply_to(message, f"{PREFIX}🔑 **KEY UPDATED:** `{new_key}`" + FOOTER, parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ Usage: `/setkey [KEY]`")

@bot.message_handler(commands=['start', 'register'])
def register(message):
    uid = str(message.chat.id)
    if not users_col.find_one({"uid": uid}):
        users_col.insert_one({"uid": uid, "status": "active", "usage": 0, "locked_ip": None})
    bot.reply_to(message, f"{PREFIX}✅ **ACCESS GRANTED**\nYour ID: `{uid}`" + FOOTER, parse_mode="Markdown")

# --- LUA API ---

@app.route('/check_status')
def check_status():
    target_id = str(request.args.get('id', '')).strip()
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    user = users_col.find_one({"uid": target_id})
    if not user:
        return "not_registered"
    
    if user.get("status") == "killed":
        return "killed|0"

    # --- ADMIN ID PROTECTION ---
    if target_id == ADMIN_ID:
        if user["locked_ip"] and user["locked_ip"] != client_ip:
            intruder_id = find_user_by_ip(client_ip)
            bot.send_message(ADMIN_ID, f"🚨 **SPOOF ATTEMPT!**\nTarget: Admin ID\nIntruder TG ID: `{intruder_id}`\nIP: `{client_ip}`")
            return "killed|SPOOF_DETECTED"
    
    # --- DEVICE LOCK ---
    if not user.get("locked_ip"):
        users_col.update_one({"uid": target_id}, {"$set": {"locked_ip": client_ip}})
    elif user["locked_ip"] != client_ip:
        return "killed|IP_MISMATCH"

    # Fetch current license key
    config = settings_col.find_one({"id": "config"})
    users_col.update_one({"uid": target_id}, {"$inc": {"usage": 1}})
    
    return f"active|{config['license_key']}"

@app.route('/')
def home(): return "KAPTVIP SECURE SERVER ONLINE"

if __name__ == '__main__':
    Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
