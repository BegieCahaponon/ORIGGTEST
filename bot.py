import os
import sqlite3
import threading
import logging
import secrets
import asyncio
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

# ============================================================
#  CONFIG — set these as environment variables on Render
# ============================================================
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "0"))
PORT         = int(os.environ.get("PORT", 5000))
DB_PATH      = "bot_data.db"
KEY_DURATION = timedelta(days=1)
# ============================================================

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
flask_app = Flask(__name__)
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


# ─────────────────────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id    INTEGER UNIQUE NOT NULL,
            telegram_name  TEXT,
            key            TEXT UNIQUE,
            active         INTEGER DEFAULT 1,
            usage_count    INTEGER DEFAULT 0,
            expires_at     TIMESTAMP,
            registered_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def generate_key():
    return secrets.token_hex(8).upper()

def now():
    return datetime.utcnow()

def expiry_from_now():
    return now() + KEY_DURATION

def format_dt(dt_str):
    if not dt_str:
        return "N/A"
    try:
        return datetime.strptime(dt_str, TIME_FORMAT).strftime("%b %d, %Y %H:%M UTC")
    except Exception:
        return str(dt_str)

def is_expired(expires_at_str):
    if not expires_at_str:
        return False
    try:
        return now() > datetime.strptime(expires_at_str, TIME_FORMAT)
    except Exception:
        return False

def time_left(expires_at_str):
    if not expires_at_str:
        return "never"
    try:
        diff = datetime.strptime(expires_at_str, TIME_FORMAT) - now()
        if diff.total_seconds() <= 0:
            return "expired"
        hours, rem = divmod(int(diff.total_seconds()), 3600)
        mins = rem // 60
        return f"{hours // 24}d {hours % 24}h" if hours >= 24 else f"{hours}h {mins}m"
    except Exception:
        return "unknown"

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


# ─────────────────────────────────────────────────────────────
#  KEYBOARDS
# ─────────────────────────────────────────────────────────────

def user_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 My Key", callback_data="mykey"),
         InlineKeyboardButton("📊 My Stats", callback_data="mystats")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Users", callback_data="users"),
         InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("🔑 My Key", callback_data="mykey"),
         InlineKeyboardButton("❓ Help", callback_data="help")]
    ])


# ─────────────────────────────────────────────────────────────
#  FLASK — Lua connects here + Render health check
# ─────────────────────────────────────────────────────────────

@flask_app.route("/health")
def health():
    return jsonify({"status": "ok"})

@flask_app.route("/")
def index():
    return jsonify({"status": "bot running"})

@flask_app.route("/validate", methods=["POST"])
def validate():
    data = request.get_json(silent=True)
    if not data or "key" not in data:
        return jsonify({"valid": False, "reason": "missing key"}), 400

    key  = data["key"].strip().upper()
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE UPPER(key)=? AND active=1", (key,)
    ).fetchone()

    if not user:
        conn.close()
        return jsonify({"valid": False, "reason": "invalid or revoked key"})

    if is_expired(user["expires_at"]):
        conn.execute("UPDATE users SET active=0 WHERE telegram_id=?", (user["telegram_id"],))
        conn.commit()
        conn.close()
        return jsonify({"valid": False, "reason": "key expired"})

    new_count = user["usage_count"] + 1
    conn.execute("UPDATE users SET usage_count=? WHERE telegram_id=?", (new_count, user["telegram_id"]))
    conn.commit()
    conn.close()

    return jsonify({
        "valid": True,
        "telegram_name": user["telegram_name"],
        "usage_count": new_count,
        "expires_at": format_dt(user["expires_at"]),
        "time_left": time_left(user["expires_at"])
    })


# ─────────────────────────────────────────────────────────────
#  TELEGRAM BOT (runs in its own thread + event loop)
# ─────────────────────────────────────────────────────────────

bot_app = None
bot_loop = None

def user_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 My Key", callback_data="mykey"),
         InlineKeyboardButton("📊 My Stats", callback_data="mystats")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Users", callback_data="users"),
         InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("🔑 My Key", callback_data="mykey"),
         InlineKeyboardButton("❓ Help", callback_data="help")]
    ])

async def expiry_checker(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    expired_users = conn.execute(
        "SELECT * FROM users WHERE active=1 AND expires_at IS NOT NULL AND expires_at <= ?",
        (now().strftime(TIME_FORMAT),)
    ).fetchall()
    for user in expired_users:
        conn.execute("UPDATE users SET active=0 WHERE telegram_id=?", (user["telegram_id"],))
        conn.commit()
        try:
            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text="⏰ *Your key has expired!*\n\nContact the admin to renew.",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⏰ Expired: @{user['telegram_name']} (`{user['telegram_id']}`)\n"
                         f"Use `/setkey {user['telegram_id']}` to renew.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
    conn.close()

async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start",  "Register & get your key"),
        BotCommand("mykey",  "Show your key & expiry"),
        BotCommand("help",   "Show all commands"),
        BotCommand("users",  "List all users (admin)"),
        BotCommand("setkey", "Set/renew a user key (admin)"),
        BotCommand("kill",   "Revoke user access (admin)"),
        BotCommand("revive", "Restore user access (admin)"),
        BotCommand("stats",  "View statistics (admin)"),
        BotCommand("notify", "Broadcast message (admin)"),
    ])

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user  = update.effective_user
    tid      = tg_user.id
    name     = tg_user.username or tg_user.first_name or "unknown"
    conn     = get_db()
    existing = conn.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()

    if existing:
        conn.close()
        if is_expired(existing["expires_at"]):
            return await update.message.reply_text(
                "⏰ Your key has *expired!*\nContact the admin to renew.",
                parse_mode="Markdown", reply_markup=user_keyboard()
            )
        if not existing["active"]:
            return await update.message.reply_text(
                "❌ Your access has been revoked. Contact the admin.",
                reply_markup=user_keyboard()
            )
        kb = admin_keyboard() if is_admin(tid) else user_keyboard()
        return await update.message.reply_text(
            f"👋 Welcome back, @{name}!\n\n"
            f"🔑 Key: `{existing['key']}`\n"
            f"⌛ Time left: `{time_left(existing['expires_at'])}`\n"
            f"📊 Total uses: `{existing['usage_count']}`",
            parse_mode="Markdown", reply_markup=kb
        )

    new_key    = generate_key()
    expires_at = expiry_from_now().strftime(TIME_FORMAT)
    conn.execute(
        "INSERT INTO users (telegram_id, telegram_name, key, active, expires_at) VALUES (?, ?, ?, 1, ?)",
        (tid, name, new_key, expires_at)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ *Welcome, @{name}!*\n\n"
        f"🎉 You are now registered!\n\n"
        f"🔑 Your Key:\n`{new_key}`\n\n"
        f"⏳ Valid for: *1 day*\n"
        f"📅 Expires: `{format_dt(expires_at)}`\n\n"
        f"📋 Copy the key and paste it into the script.",
        parse_mode="Markdown", reply_markup=user_keyboard()
    )
    if ADMIN_ID:
        await ctx.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🆕 *New user registered!*\n"
                 f"👤 @{name} · `{tid}`\n"
                 f"🔑 Key: `{new_key}`\n"
                 f"⏳ Expires: `{format_dt(expires_at)}`",
            parse_mode="Markdown"
        )

async def cmd_mykey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()
    conn.close()
    if not user:
        return await update.message.reply_text("❌ Not registered. Send /start first.")
    if is_expired(user["expires_at"]):
        return await update.message.reply_text(
            "⏰ Your key has *expired!*\nContact the admin to renew.",
            parse_mode="Markdown", reply_markup=user_keyboard()
        )
    if not user["active"]:
        return await update.message.reply_text("❌ Your access has been revoked.")
    await update.message.reply_text(
        f"🔑 *Your Key:*\n`{user['key']}`\n\n"
        f"⏳ *Expires:* `{format_dt(user['expires_at'])}`\n"
        f"⌛ *Time Left:* `{time_left(user['expires_at'])}`\n"
        f"📊 *Total Uses:* `{user['usage_count']}`",
        parse_mode="Markdown", reply_markup=user_keyboard()
    )

async def cmd_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    conn  = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY registered_at DESC").fetchall()
    conn.close()
    if not users:
        return await update.message.reply_text("📭 No users yet.", reply_markup=admin_keyboard())
    total  = len(users)
    active = sum(1 for u in users if u["active"] and not is_expired(u["expires_at"]))
    lines  = [f"👥 *Users — {total} total | {active} active*\n"]
    for u in users:
        expired = is_expired(u["expires_at"])
        icon    = "❌" if not u["active"] else ("⏰" if expired else "✅")
        key_str = f"`{u['key']}`" if u["key"] else "_no key_"
        lines.append(
            f"{icon} @{u['telegram_name']} · `{u['telegram_id']}`\n"
            f"    🔑 {key_str} · ⌛ {time_left(u['expires_at'])} · 📊 {u['usage_count']} uses"
        )
    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4090] + "\n…"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=admin_keyboard())

async def cmd_setkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    if not ctx.args:
        return await update.message.reply_text(
            "Usage:\n"
            "`/setkey <id>` — auto key (1 day)\n"
            "`/setkey <id> <key>` — custom key (1 day)\n"
            "`/setkey <id> <key> <days>` — custom key + days",
            parse_mode="Markdown", reply_markup=admin_keyboard()
        )
    try:
        target_id = int(ctx.args[0])
    except ValueError:
        return await update.message.reply_text("❌ Telegram ID must be a number.")
    new_key = ctx.args[1].strip().upper() if len(ctx.args) >= 2 else generate_key()
    days    = int(ctx.args[2]) if len(ctx.args) >= 3 else 1
    exp     = (now() + timedelta(days=days)).strftime(TIME_FORMAT)
    conn    = get_db()
    user    = conn.execute("SELECT * FROM users WHERE telegram_id=?", (target_id,)).fetchone()
    if not user:
        conn.close()
        return await update.message.reply_text(f"❌ User `{target_id}` not found.", parse_mode="Markdown")
    taken = conn.execute(
        "SELECT telegram_id FROM users WHERE UPPER(key)=? AND telegram_id!=?", (new_key, target_id)
    ).fetchone()
    if taken:
        conn.close()
        return await update.message.reply_text("❌ That key is already in use.")
    conn.execute("UPDATE users SET key=?, active=1, expires_at=? WHERE telegram_id=?", (new_key, exp, target_id))
    conn.commit()
    conn.close()
    try:
        await ctx.bot.send_message(
            chat_id=target_id,
            text=f"🎉 *Your key has been set!*\n\n"
                 f"🔑 Key:\n`{new_key}`\n\n"
                 f"⏳ Valid for: *{days} day(s)*\n"
                 f"📅 Expires: `{format_dt(exp)}`\n\n"
                 f"📋 Copy the key and paste it into the script.",
            parse_mode="Markdown", reply_markup=user_keyboard()
        )
        notify_status = "✅ User notified."
    except Exception:
        notify_status = "⚠️ Could not notify user."
    await update.message.reply_text(
        f"✅ Key set for @{user['telegram_name']}\n"
        f"🔑 `{new_key}`\n"
        f"⏳ Expires in {days} day(s): `{format_dt(exp)}`\n\n{notify_status}",
        parse_mode="Markdown", reply_markup=admin_keyboard()
    )

async def cmd_kill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    if not ctx.args:
        return await update.message.reply_text("Usage: `/kill <telegram_id>`", parse_mode="Markdown")
    try:
        target_id = int(ctx.args[0])
    except ValueError:
        return await update.message.reply_text("❌ Invalid ID.")
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (target_id,)).fetchone()
    if not user:
        conn.close()
        return await update.message.reply_text("❌ User not found.")
    conn.execute("UPDATE users SET active=0 WHERE telegram_id=?", (target_id,))
    conn.commit()
    conn.close()
    try:
        await ctx.bot.send_message(chat_id=target_id, text="🚫 Your access has been revoked by the admin.")
    except Exception:
        pass
    await update.message.reply_text(f"🔴 @{user['telegram_name']} has been killed.", reply_markup=admin_keyboard())

async def cmd_revive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    if not ctx.args:
        return await update.message.reply_text("Usage: `/revive <telegram_id>`", parse_mode="Markdown")
    try:
        target_id = int(ctx.args[0])
    except ValueError:
        return await update.message.reply_text("❌ Invalid ID.")
    conn    = get_db()
    user    = conn.execute("SELECT * FROM users WHERE telegram_id=?", (target_id,)).fetchone()
    if not user:
        conn.close()
        return await update.message.reply_text("❌ User not found.")
    new_exp = expiry_from_now().strftime(TIME_FORMAT)
    conn.execute("UPDATE users SET active=1, expires_at=? WHERE telegram_id=?", (new_exp, target_id))
    conn.commit()
    conn.close()
    try:
        await ctx.bot.send_message(
            chat_id=target_id,
            text=f"✅ Your access has been restored!\n⏳ New expiry: `{format_dt(new_exp)}`",
            parse_mode="Markdown", reply_markup=user_keyboard()
        )
    except Exception:
        pass
    await update.message.reply_text(
        f"✅ @{user['telegram_name']} revived.\n⏳ Expires: `{format_dt(new_exp)}`",
        parse_mode="Markdown", reply_markup=admin_keyboard()
    )

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    conn      = get_db()
    total     = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active    = conn.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]
    with_key  = conn.execute("SELECT COUNT(*) FROM users WHERE key IS NOT NULL").fetchone()[0]
    total_use = conn.execute("SELECT SUM(usage_count) FROM users").fetchone()[0] or 0
    top       = conn.execute("SELECT telegram_name, usage_count FROM users ORDER BY usage_count DESC LIMIT 5").fetchall()
    all_a     = conn.execute("SELECT expires_at FROM users WHERE active=1").fetchall()
    expired_c = sum(1 for u in all_a if is_expired(u["expires_at"]))
    conn.close()
    top_str = "\n".join(f"   @{u['telegram_name']}: {u['usage_count']} uses" for u in top) or "   None yet"
    await update.message.reply_text(
        f"📊 *Statistics*\n\n"
        f"👥 Total users: `{total}`\n"
        f"✅ Active: `{active}`\n"
        f"⏰ Expired: `{expired_c}`\n"
        f"🔑 With key: `{with_key}`\n"
        f"📈 Total uses: `{total_use}`\n\n"
        f"🏆 *Top 5:*\n{top_str}",
        parse_mode="Markdown", reply_markup=admin_keyboard()
    )

async def cmd_notify(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    if not ctx.args:
        return await update.message.reply_text(
            "Usage:\n"
            "`/notify <message>` — Broadcast to all users\n"
            "`/notify active <message>` — Active users only",
            parse_mode="Markdown", reply_markup=admin_keyboard()
        )
    active_only = ctx.args[0].lower() == "active"
    message     = " ".join(ctx.args[1:]) if active_only else " ".join(ctx.args)
    if not message.strip():
        return await update.message.reply_text("❌ Message cannot be empty.")
    conn  = get_db()
    users = conn.execute("SELECT * FROM users WHERE active=1").fetchall() if active_only else conn.execute("SELECT * FROM users").fetchall()
    if active_only:
        users = [u for u in users if not is_expired(u["expires_at"])]
    label = "active users" if active_only else "all users"
    conn.close()
    if not users:
        return await update.message.reply_text("📭 No users to notify.")
    status_msg = await update.message.reply_text(f"📤 Sending to {len(users)} {label}...")
    sent, failed = 0, 0
    for user in users:
        try:
            await ctx.bot.send_message(
                chat_id=user["telegram_id"],
                text=f"📢 *Message from Admin:*\n\n{message}",
                parse_mode="Markdown"
            )
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await status_msg.edit_text(
        f"✅ *Broadcast done!*\n\n📤 Sent: `{sent}`\n❌ Failed: `{failed}`\n👥 Target: {label}",
        parse_mode="Markdown", reply_markup=admin_keyboard()
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    admin_cmds = (
        "\n\n👑 *Admin Commands:*\n"
        "/users — List all users\n"
      
