import os
import sqlite3
import threading
import logging
import secrets
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, filters, ContextTypes

# ============================================================
#  CONFIG — set these as environment variables on Render
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))   # Your Telegram numeric ID
PORT      = int(os.environ.get("PORT", 5000))
DB_PATH   = "bot_data.db"
# ============================================================

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)

flask_app = Flask(__name__)
tg_app: Application = None
loop: asyncio.AbstractEventLoop = None


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
            registered_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────────────────
#  FLASK — Lua script connects here
# ─────────────────────────────────────────────────────────────

@flask_app.route("/health")
def health():
    """Render health check endpoint."""
    return jsonify({"status": "ok"})


@flask_app.route("/validate", methods=["POST"])
def validate():
    """
    Lua sends:  { "key": "XXXXXXXXXXXX" }
    Returns:    { "valid": true, "telegram_name": "...", "usage_count": N }
             or { "valid": false, "reason": "..." }
    """
    data = request.get_json(silent=True)
    if not data or "key" not in data:
        return jsonify({"valid": False, "reason": "missing key"}), 400

    key  = data["key"].strip()
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE key=? AND active=1", (key,)
    ).fetchone()

    if not user:
        conn.close()
        return jsonify({"valid": False, "reason": "invalid or revoked key"})

    new_count = user["usage_count"] + 1
    conn.execute("UPDATE users SET usage_count=? WHERE key=?", (new_count, key))
    conn.commit()
    conn.close()

    return jsonify({
        "valid": True,
        "telegram_name": user["telegram_name"],
        "usage_count": new_count
    })


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


# ─────────────────────────────────────────────────────────────
#  USER COMMANDS
# ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user = update.effective_user
    tid     = tg_user.id
    name    = tg_user.username or tg_user.first_name or "unknown"

    conn     = get_db()
    existing = conn.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()

    if existing:
        conn.close()
        if not existing["active"]:
            return await update.message.reply_text(
                "❌ Your access has been revoked. Contact the admin."
            )
        key_str = f"`{existing['key']}`" if existing["key"] else "_not assigned yet_"
        return await update.message.reply_text(
            f"👋 Welcome back, @{name}!\n"
            f"🔑 Key: {key_str}\n"
            f"📊 Total uses: `{existing['usage_count']}`",
            parse_mode="Markdown"
        )

    # New user — register
    conn.execute(
        "INSERT INTO users (telegram_id, telegram_name) VALUES (?, ?)", (tid, name)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ Registered as @{name}!\n"
        "⏳ Waiting for the admin to assign your key.\n"
        "Use /mykey to check anytime."
    )

    if ADMIN_ID:
        await ctx.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🆕 *New user registered!*\n"
                 f"👤 @{name}\n"
                 f"🆔 `{tid}`\n\n"
                 f"➡️ Use `/setkey {tid}` to assign a key.",
            parse_mode="Markdown"
        )


async def cmd_mykey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone()
    conn.close()

    if not user:
        return await update.message.reply_text("❌ Not registered. Send /start first.")
    if not user["active"]:
        return await update.message.reply_text("❌ Your access has been revoked.")
    if not user["key"]:
        return await update.message.reply_text("⏳ No key assigned yet. Contact the admin.")

    await update.message.reply_text(
        f"🔑 *Your Key:*\n`{user['key']}`\n\n"
        f"📊 *Total Uses:* `{user['usage_count']}`",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────────────────────
#  ADMIN COMMANDS
# ─────────────────────────────────────────────────────────────

async def cmd_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")

    conn  = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY registered_at DESC").fetchall()
    conn.close()

    if not users:
        return await update.message.reply_text("📭 No users registered yet.")

    total  = len(users)
    active = sum(1 for u in users if u["active"])
    lines  = [f"👥 *Users — {total} total | {active} active*\n"]

    for u in users:
        icon    = "✅" if u["active"] else "❌"
        key_str = f"`{u['key']}`" if u["key"] else "_no key_"
        lines.append(
            f"{icon} @{u['telegram_name']} · ID: `{u['telegram_id']}`\n"
            f"    🔑 {key_str} · 📊 {u['usage_count']} uses"
        )

    text = "\n".join(lines)
    if len(text) > 4096:
        text = text[:4090] + "\n…"

    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_setkey(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")

    if not ctx.args:
        return await update.message.reply_text(
            "Usage:\n"
            "`/setkey <telegram_id>` — auto-generate key\n"
            "`/setkey <telegram_id> <custom_key>` — set custom key",
            parse_mode="Markdown"
        )

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        return await update.message.reply_text("❌ Telegram ID must be a number.")

    new_key = ctx.args[1] if len(ctx.args) >= 2 else secrets.token_hex(10).upper()

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (target_id,)).fetchone()
    if not user:
        conn.close()
        return await update.message.reply_text(f"❌ User `{target_id}` not found.", parse_mode="Markdown")

    taken = conn.execute(
        "SELECT telegram_id FROM users WHERE key=? AND telegram_id!=?", (new_key, target_id)
    ).fetchone()
    if taken:
        conn.close()
        return await update.message.reply_text("❌ That key is already used by another user.")

    conn.execute("UPDATE users SET key=?, active=1 WHERE telegram_id=?", (new_key, target_id))
    conn.commit()
    conn.close()

    try:
        await ctx.bot.send_message(
            chat_id=target_id,
            text=f"🎉 Your key has been set!\n\n🔑 Key: `{new_key}`",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ Key assigned to @{user['telegram_name']}\n🔑 `{new_key}`",
        parse_mode="Markdown"
    )


async def cmd_kill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")

    if not ctx.args:
        return await update.message.reply_text("Usage: `/kill <telegram_id>`", parse_mode="Markdown")

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        return await update.message.reply_text("❌ Invalid Telegram ID.")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (target_id,)).fetchone()
    if not user:
        conn.close()
        return await update.message.reply_text(f"❌ User `{target_id}` not found.", parse_mode="Markdown")

    conn.execute("UPDATE users SET active=0 WHERE telegram_id=?", (target_id,))
    conn.commit()
    conn.close()

    try:
        await ctx.bot.send_message(
            chat_id=target_id,
            text="🚫 Your access has been revoked by the admin."
        )
    except Exception:
        pass

    await update.message.reply_text(f"🔴 @{user['telegram_name']} has been killed.")


async def cmd_revive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")

    if not ctx.args:
        return await update.message.reply_text("Usage: `/revive <telegram_id>`", parse_mode="Markdown")

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        return await update.message.reply_text("❌ Invalid Telegram ID.")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (target_id,)).fetchone()
    if not user:
        conn.close()
        return await update.message.reply_text(f"❌ User `{target_id}` not found.", parse_mode="Markdown")

    conn.execute("UPDATE users SET active=1 WHERE telegram_id=?", (target_id,))
    conn.commit()
    conn.close()

    try:
        await ctx.bot.send_message(
            chat_id=target_id,
            text="✅ Your access has been restored!"
        )
    except Exception:
        pass

    await update.message.reply_text(f"✅ @{user['telegram_name']} revived.")


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("❌ Admin only.")

    conn      = get_db()
    total     = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active    = conn.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0]
    with_key  = conn.execute("SELECT COUNT(*) FROM users WHERE key IS NOT NULL").fetchone()[0]
    total_use = conn.execute("SELECT SUM(usage_count) FROM users").fetchone()[0] or 0
    top       = conn.execute(
        "SELECT telegram_name, usage_count FROM users ORDER BY usage_count DESC LIMIT 5"
    ).fetchall()
    conn.close()

    top_str = "\n".join(
        f"   @{u['telegram_name']}: {u['usage_count']} uses" for u in top
    ) or "   None yet"

    await update.message.reply_text(
        f"📊 *Statistics*\n\n"
        f"👥 Total users: `{total}`\n"
        f"✅ Active: `{active}`\n"
        f"🔑 With key: `{with_key}`\n"
        f"📈 Total script uses: `{total_use}`\n\n"
        f"🏆 *Top 5 Users:*\n{top_str}",
        parse_mode="Markdown"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid        = update.effective_user.id
    admin_cmds = (
        "\n\n👑 *Admin Commands:*\n"
        "/users — List all users\n"
        "/setkey `<id>` `[key]` — Assign key\n"
        "/kill `<id>` — Revoke access\n"
        "/revive `<id>` — Restore access\n"
        "/stats — View statistics"
    ) if is_admin(uid) else ""

    await update.message.reply_text(
        "🤖 *Available Commands:*\n"
        "/start — Register / view status\n"
        "/mykey — Show your key & usage count\n"
        "/help — Show this menu"
        + admin_cmds,
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


def main():
    global tg_app, loop

    init_db()
    logging.info("Database ready.")

    tg_app = Application.builder().token(BOT_TOKEN).build()

    tg_app.add_handler(CommandHandler("start",  cmd_start))
    tg_app.add_handler(CommandHandler("mykey",  cmd_mykey))
    tg_app.add_handler(CommandHandler("help",   cmd_help))
    tg_app.add_handler(CommandHandler("users",  cmd_users))
    tg_app.add_handler(CommandHandler("setkey", cmd_setkey))
    tg_app.add_handler(CommandHandler("kill",   cmd_kill))
    tg_app.add_handler(CommandHandler("revive", cmd_revive))
    tg_app.add_handler(CommandHandler("stats",  cmd_stats))

    threading.Thread(target=run_flask, daemon=True).start()
    logging.info(f"HTTP bridge on port {PORT}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    logging.info("Bot polling started.")
    tg_app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)


if __name__ == "__main__":
    main()
