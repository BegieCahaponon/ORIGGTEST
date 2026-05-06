import os
import telebot
from flask import Flask, request
from threading import Thread

# Use Environment Variables for security (Set these in Render Dashboard)
TOKEN = os.environ.get('8387040240:AAH7FFS6YbbY-a6IZAdUpyYNBsxJnhsPoMA')
ADMIN_ID = os.environ.get('7817086667')

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
    return "HEROSHI Monitor is Online"

def run_bot():
    bot.polling(none_stop=True)

if __name__ == '__main__':
    # Start Telegram bot in a background thread
    Thread(target=run_bot).start()
    # Start Flask on the port Render provides
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
