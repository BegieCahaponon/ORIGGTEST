import os
import sqlite3
import threading
import logging
import secrets
import asyncio
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ============================================================
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "0"))
PORT         = int(os.environ.get("PORT", 5000))
DB_PATH      = "bot_data.db"
KEY_DURATION = timedelta(days=1)
TIME_FORMAT  = "%Y-%m-%d %H:%M:%S"
# ============================================================

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
flask_app = Flask(__name__)

# ─── DB ───────────────────────────────────────────────────────
def init_db():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id   INTEGER UNIQUE NOT NULL,
        telegram_name TEXT,
        key           TEXT UNIQUE,
        active        INTEGER DEFAULT 1,
        usage_count   INTEGER DEFAULT 0,
        expires_at    TIMESTAMP,
        registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.commit()
    c.close()

def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def gen_key():
    return secrets.token_hex(8).upper()

def utcnow():
    return datetime.utcnow()

def fmt(dt_str):
    if not dt_str:
        return "N/A"
    try:
        return datetime.strptime(dt_str, TIME_FORMAT).strftime("%b %d %Y %H:%M UTC")
    except:
        return str(dt_str)

def expired(exp_str):
    if not exp_str:
        return False
    try:
        return utcnow() > datetime.strptime(exp_str, TIME_FORMAT)
    except:
        return False

def tleft(exp_str):
    if not exp_str:
        return "never"
    try:
        d = datetime.strptime(exp_str, TIME_FORMAT) - utcnow()
        if d.total_seconds() <= 0:
            return "expired"
        h, r = divmod(int(d.total_seconds()), 3600)
        m = r // 60
        return f"{h//24}d {h%24}h" if h >= 24 else f"{h}h {m}m"
    except:
        return "unknown"

def is_admin(uid):
    return uid == ADMIN_ID

# ─── KEYBOARDS ────────────────────────────────────────────────
def kb_user():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 My Key",    callback_data="mykey"),
         InlineKeyboardButton("📊 My Stats",  callback_data="mystats")],
        [InlineKeyboardButton("❓ Help",       callback_data="help")]
    ])

def kb_admin():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Users",     callback_data="users"),
         InlineKeyboardButton("📊 Stats",     callback_data="stats")],
        [InlineKeyboardButton("🔑 My Key",    callback_data="mykey"),
         InlineKeyboardButton("❓ Help",       callback_data="help")]
    ])

def kb(uid):
    return kb_admin() if is_admin(uid) else kb_user()

# ─── FLASK ────────────────────────────────────────────────────
@flask_app.route("/")
def root():
    return jsonify({"status": "ok"})

@flask_app.route("/health")
def health():
    return jsonify({"status": "ok"})

@flask_app.route("/validate", methods=["POST"])
def validate():
    data = request.get_json(silent=True)
    if not data or "key" not in data:
        return jsonify({"valid": False, "reason": "missing key"}), 400
    key  = data["key"].strip().upper()
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE UPPER(key)=? AND active=1", (key,)).fetchone()
    if not user:
        conn.close()
        return jsonify({"valid": False, "reason": "invalid or revoked key"})
    if expired(user["expires_at"]):
        conn.execute("UPDATE users SET active=0 WHERE telegram_id=?", (user["telegram_id"],))
        conn.commit()
        conn.close()
        return jsonify({"valid": False, "reason": "key expired"})
    n = user["usage_count"] + 1
    conn.execute("UPDATE users SET usage_count=? WHERE telegram_id=?", (n, user["telegram_id"]))
    conn.commit()
    conn.close()
    return jsonify({"valid": True, "telegram_name": user["telegram_name"],
                    "usage_count": n, "time_left": tleft(user["expires_at"])})

# ─── BOT HANDLERS ─────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u    = update.effective_user
    tid  = u.id
    name = u.username or u.first_name or "unknown"
    conn = get_db()
    ex   = conn.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()
    if ex:
        conn.close()
        if expired(ex["expires_at"]):
            return await update.message.reply_text("⏰ *Key expired!* Contact admin.", parse_mode="Markdown", reply_markup=kb(tid))
        if not ex["active"]:
            return await update.message.reply_text("❌ Access revoked. Contact admin.", reply_markup=kb(tid))
        return await update.message.reply_text(
            f"👋 Welcome back @{name}!\n\n🔑 Key: `{ex['key']}`\n⌛ Left: `{tleft(ex['expires_at'])}`\n📊 Uses: `{ex['usage_count']}`",
            parse_mode="Markdown", reply_markup=kb(tid))
    new_key = gen_key()
    exp_at  = (utcnow() + KEY_DURATION).strftime(TIME_FORMAT)
    conn.execute("INSERT INTO users (telegram_id,telegram_name,key,active,expires_at) VALUES(?,?,?,1,?)",
                 (tid, name, new_key, exp_at))
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"✅ *Welcome @{name}!*\n\n🎉 Registered!\n\n🔑 Your Key:\n`{new_key}`\n\n⏳ Valid: *1 day*\n📅 Expires: `{fmt(exp_at)}`\n\n📋 Paste the key into the script.",
        parse_mode="Markdown", reply_markup=kb(tid))
    if ADMIN_ID:
        await ctx.bot.send_message(ADMIN_ID,
            f"🆕 *New user!*\n👤 @{name} · `{tid}`\n🔑 `{new_key}`\n⏳ `{fmt(exp_at)}`",
            parse_mode="Markdown")

async def cmd_mykey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()
    conn.close()
    if not user:
        return await update.message.reply_text("❌ Not registered. Send /start first.")
    if expired(user["expires_at"]):
        return await update.message.reply_text("⏰ *Key expired!* Contact admin.", parse_mode="Markdown", reply_markup=kb(tid))
    if not user["active"]:
        return await update.message.reply_text("❌ Access revoked.")
    await update.message.reply_text(
        f"🔑 *Key:*\n`{user['key']}`\n\n⏳ Expires: `{fmt(user['expires_at'])}`\n⌛ Left: `{tleft(user['expires_at'])}`\n📊 Uses: `{user['usage_count']}`",
        parse_mode="Markdown", reply_markup=kb(tid))

async def cmd_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    conn  = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY registered_at DESC").fetchall()
    conn.close()
    if not users:
        return await update.message.reply_text("📭 No users yet.", reply_markup=kb_admin())
    total  = len(users)
    active = sum(1 for u in users if u["active"] and not expired(u["expires_at"]))
    lines  = [f"👥 *{total} users | {active} active*\n"]
    for u in users:
        icon = "❌" if not u["active"] else ("⏰" if expired(u["expires_at"]) else "✅")
        lines.append(f"{icon} @{u['telegram_name']} · `{u['telegram_id']}`\n    🔑 `{u['key'] or 'none'}` · ⌛ {tleft(u['expires_at'])} · 📊 {u['usage_count']}")
    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4090] + "\n…"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb_admin())

async def cmd_setkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    if not ctx.args:
        return await update.message.reply_text(
            "Usage:\n`/setkey <id>` — auto key 1 day\n`/setkey <id> <key>` — custom key\n`/setkey <id> <key> <days>` — custom days",
            parse_mode="Markdown", reply_markup=kb_admin())
    try:
        tid = int(ctx.args[0])
    except:
        return await update.message.reply_text("❌ ID must be a number.")
    new_key = ctx.args[1].strip().upper() if len(ctx.args) >= 2 else gen_key()
    days    = int(ctx.args[2]) if len(ctx.args) >= 3 else 1
    exp_at  = (utcnow() + timedelta(days=days)).strftime(TIME_FORMAT)
    conn    = get_db()
    user    = conn.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()
    if not user:
        conn.close()
        return await update.message.reply_text("❌ User not found.")
    taken = conn.execute("SELECT telegram_id FROM users WHERE UPPER(key)=? AND telegram_id!=?", (new_key, tid)).fetchone()
    if taken:
        conn.close()
        return await update.message.reply_text("❌ Key already in use.")
    conn.execute("UPDATE users SET key=?,active=1,expires_at=? WHERE telegram_id=?", (new_key, exp_at, tid))
    conn.commit()
    conn.close()
    try:
        await ctx.bot.send_message(tid,
            f"🎉 *Key set!*\n\n🔑 `{new_key}`\n⏳ Valid: *{days} day(s)*\n📅 Expires: `{fmt(exp_at)}`\n\n📋 Paste key into script.",
            parse_mode="Markdown", reply_markup=kb_user())
        note = "✅ User notified."
    except:
        note = "⚠️ Could not notify user."
    await update.message.reply_text(
        f"✅ Key set for @{user['telegram_name']}\n🔑 `{new_key}`\n⏳ {days} day(s): `{fmt(exp_at)}`\n\n{note}",
        parse_mode="Markdown", reply_markup=kb_admin())

async def cmd_kill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    if not ctx.args:
        return await update.message.reply_text("Usage: `/kill <id>`", parse_mode="Markdown")
    try:
        tid = int(ctx.args[0])
    except:
        return await update.message.reply_text("❌ Invalid ID.")
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()
    if not user:
        conn.close()
        return await update.message.reply_text("❌ User not found.")
    conn.execute("UPDATE users SET active=0 WHERE telegram_id=?", (tid,))
    conn.commit()
    conn.close()
    try:
        await ctx.bot.send_message(tid, "🚫 Your access has been revoked by the admin.")
    except:
        pass
    await update.message.reply_text(f"🔴 @{user['telegram_name']} killed.", reply_markup=kb_admin())

async def cmd_revive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    if not ctx.args:
        return await update.message.reply_text("Usage: `/revive <id>`", parse_mode="Markdown")
    try:
        tid = int(ctx.args[0])
    except:
        return await update.message.reply_text("❌ Invalid ID.")
    conn    = get_db()
    user    = conn.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()
    if not user:
        conn.close()
        return await update.message.reply_text("❌ User not found.")
    new_exp = (utcnow() + KEY_DURATION).strftime(TIME_FORMAT)
    conn.execute("UPDATE users SET active=1,expires_at=? WHERE telegram_id=?", (new_exp, tid))
    conn.commit()
    conn.close()
    try:
        await ctx.bot.send_message(tid, f"✅ Access restored!\n⏳ Expires: `{fmt(new_exp)}`", parse_mode="Markdown", reply_markup=kb_user())
    except:
        pass
    await update.message.reply_text(f"✅ @{user['telegram_name']} revived.\n⏳ `{fmt(new_exp)}`", parse_mode="Markdown", reply_markup=kb_admin())

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    conn  = get_db()
    total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    act   = conn.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]
    uses  = conn.execute("SELECT SUM(usage_count) FROM users").fetchone()[0] or 0
    top   = conn.execute("SELECT telegram_name,usage_count FROM users ORDER BY usage_count DESC LIMIT 5").fetchall()
    conn.close()
    top_str = "\n".join(f"   @{u['telegram_name']}: {u['usage_count']}" for u in top) or "   None"
    await update.message.reply_text(
        f"📊 *Stats*\n\n👥 Total: `{total}`\n✅ Active: `{act}`\n📈 Uses: `{uses}`\n\n🏆 *Top 5:*\n{top_str}",
        parse_mode="Markdown", reply_markup=kb_admin())

async def cmd_notify(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")
    if not ctx.args:
        return await update.message.reply_text(
            "Usage:\n`/notify <msg>` — all users\n`/notify active <msg>` — active only",
            parse_mode="Markdown", reply_markup=kb_admin())
    active_only = ctx.args[0].lower() == "active"
    msg         = " ".join(ctx.args[1:]) if active_only else " ".join(ctx.args)
    if not msg.strip():
        return await update.message.reply_text("❌ Message is empty.")
    conn  = get_db()
    users = conn.execute("SELECT * FROM users WHERE active=1").fetchall() if active_only else conn.execute("SELECT * FROM users").fetchall()
    if active_only:
        users = [u for u in users if not expired(u["expires_at"])]
    label = "active users" if active_only else "all users"
    conn.close()
    if not users:
        return await update.message.reply_text("📭 No users.")
    s = await update.message.reply_text(f"📤 Sending to {len(users)} {label}...")
    sent, fail = 0, 0
    for u in users:
        try:
            await ctx.bot.send_message(u["telegram_id"], f"📢 *Message from Admin:*\n\n{msg}", parse_mode="Markdown")
            sent += 1
        except:
            fail += 1
        await asyncio.sleep(0.05)
    await s.edit_text(f"✅ *Done!*\n📤 Sent: `{sent}`\n❌ Failed: `{fail}`\n👥 {label}", parse_mode="Markdown", reply_markup=kb_admin())

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    admin_txt = (
        "\n\n👑 *Admin:*\n"
        "/users — All users\n"
        "/setkey `<id> [key] [days]` — Set key\n"
        "/kill `<id>` — Revoke access\n"
        "/revive `<id>` — Restore access\n"
        "/stats — Statistics\n"
        "/notify `<msg>` — Broadcast all\n"
        "/notify `active <msg>` — Active only"
    ) if is_admin(uid) else ""
    await update.message.reply_text(
        "🤖 *Commands:*\n/start — Register & get key\n/mykey — Show key & expiry\n/help — This menu" + admin_txt,
        parse_mode="Markdown", reply_markup=kb(uid))

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    d   = q.data

    if d == "mykey":
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (uid,)).fetchone()
        conn.close()
        if not user or not user["key"]:
            return await q.edit_message_text("❌ No key. Send /start first.")
        if expired(user["expires_at"]):
            return await q.edit_message_text("⏰ *Key expired!* Contact admin.", parse_mode="Markdown", reply_markup=kb_user())
        await q.edit_message_text(
            f"🔑 *Key:*\n`{user['key']}`\n\n⏳ `{fmt(user['expires_at'])}`\n⌛ `{tleft(user['expires_at'])}`\n📊 Uses: `{user['usage_count']}`",
            parse_mode="Markdown", reply_markup=kb_user())

    elif d == "mystats":
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (uid,)).fetchone()
        conn.close()
        if not user:
            return await q.edit_message_text("❌ Not registered.")
        await q.edit_message_text(
            f"📊 *Stats*\n\n👤 @{user['telegram_name']}\n🔑 `{user['key'] or 'none'}`\n⌛ `{tleft(user['expires_at'])}`\n📈 Uses: `{user['usage_count']}`",
            parse_mode="Markdown", reply_markup=kb_user())

    elif d == "users" and is_admin(uid):
        conn  = get_db()
        users = conn.execute("SELECT * FROM users ORDER BY registered_at DESC").fetchall()
        conn.close()
        total  = len(users)
        active = sum(1 for u in users if u["active"] and not expired(u["expires_at"]))
        lines  = [f"👥 *{total} users | {active} active*\n"]
        for u in users:
            icon = "❌" if not u["active"] else ("⏰" if expired(u["expires_at"]) else "✅")
            lines.append(f"{icon} @{u['telegram_name']} · `{u['telegram_id']}`\n    ⌛ {tleft(u['expires_at'])} · 📊 {u['usage_count']}")
        text = "\n".join(lines)
        if len(text) > 4096:
            text = text[:4090] + "\n…"
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=kb_admin())

    elif d == "stats" and is_admin(uid):
        conn  = get_db()
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        act   = conn.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]
        uses  = conn.execute("SELECT SUM(usage_count) FROM users").fetchone()[0] or 0
        conn.close()
        await q.edit_message_text(
            f"📊 *Stats*\n\n👥 Total: `{total}`\n✅ Active: `{act}`\n📈 Uses: `{uses}`",
            parse_mode="Markdown", reply_markup=kb_admin())

    elif d == "help":
        admin_txt = "\n\n👑 *Admin:* /users /setkey /kill /revive /stats /notify" if is_admin(uid) else ""
        await q.edit_message_text(
            "🤖 *Commands:*\n/start — Register\n/mykey — Your key\n/help — Menu" + admin_txt,
            parse_mode="Markdown", reply_markup=kb(uid))

# ─── EXPIRY CHECKER JOB ───────────────────────────────────────
async def expiry_checker(context: ContextTypes.DEFAULT_TYPE):
    conn  = get_db()
    users = conn.execute(
        "SELECT * FROM users WHERE active=1 AND expires_at IS NOT NULL AND expires_at<=?",
        (utcnow().strftime(TIME_FORMAT),)
    ).fetchall()
    for u in users:
        conn.execute("UPDATE users SET active=0 WHERE telegram_id=?", (u["telegram_id"],))
        conn.commit()
        try:
            await context.bot.send_message(u["telegram_id"], "⏰ *Key expired!*\nContact admin to renew.", parse_mode="Markdown")
        except:
            pass
        if ADMIN_ID:
            try:
                await context.bot.send_message(ADMIN_ID,
                    f"⏰ Expired: @{u['telegram_name']} `{u['telegram_id']}`\nUse `/setkey {u['telegram_id']}` to renew.",
                    parse_mode="Markdown")
            except:
                pass
    conn.close()

async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start",  "Register & get your key"),
        BotCommand("mykey",  "Show your key & expiry"),
        BotCommand("help",   "Show commands"),
        BotCommand("users",  "List all users (admin)"),
        BotCommand("setkey", "Set/renew key (admin)"),
        BotCommand("kill",   "Revoke access (admin)"),
        BotCommand("revive", "Restore access (admin)"),
        BotCommand("stats",  "Statistics (admin)"),
        BotCommand("notify", "Broadcast message (admin)"),
    ])

# ─── BOT THREAD ───────────────────────────────────────────────
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("mykey",  cmd_mykey))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("users",  cmd_users))
    app.add_handler(CommandHandler("setkey", cmd_setkey))
    app.add_handler(CommandHandler("kill",   cmd_kill))
    a
