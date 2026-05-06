import os
import telebot
from flask import Flask, request
from threading import Thread

# --- HARDCODED CREDENTIALS ---
TOKEN = "8387040240:AAH7FFS6YbbY-a6IZAdUpyYNBsxJnhsPoMA"
ADMIN_ID = "7817086667"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

user_database = {}

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if str(message.chat.id) == ADMIN_ID:
        try:
            target_id = message.text.split()[1]
            user_database[target_id] = "killed"
            bot.reply_to(message, f"🚫 User {target_id} deactivated.")
        except:
            bot.reply_to(message, "Usage: /kill [user_id]")

@app.route('/check_status')
def check_status():
    user_id = request.args.get('id', 'unknown')
    if user_id not in user_database:
        user_database[user_id] = "active"
        bot.send_message(ADMIN_ID, f"🆕 New Connection: {user_id}")
    return user_database.get(user_id, "active")

@app.route('/')
def home():
    return "KAPTVIP Monitor is Online"

def run_bot():
    # Adding a try-except to prevent the whole app from crashing if Telegram fails
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Bot Error: {e}")

if __name__ == '__main__':
    # Start bot thread
    Thread(target=run_bot).start()
    
    # Render needs host='0.0.0.0' to be visible externally
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
