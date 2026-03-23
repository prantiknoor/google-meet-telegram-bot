"""
Telegram Bot — Google Meet Space Creator
Creates a Google Meet space with OPEN access.
Only whitelisted Telegram user IDs can use the bot.
"""

import logging
import os
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from dotenv import load_dotenv

from meet_service import create_meet_space
from health_server import start_health_server
from whitelist import (
    is_whitelisted,
    add_to_whitelist,
    remove_from_whitelist,
    list_whitelist,
    load_whitelist,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Reduce noisy framework/network logs; keep app-level conversation logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS_RAW = os.getenv("ADMIN_TELEGRAM_IDS", "")
ADMIN_IDS = set(
    int(uid.strip()) for uid in ADMIN_IDS_RAW.split(",") if uid.strip().isdigit()
)


# ─── Helpers ────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _preview_text(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def log_incoming(update: Update, command: str) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    logger.info(
        "IN command=%s chat_id=%s user_id=%s username=%s text=%s",
        command,
        message.chat_id,
        user.id,
        user.username,
        _preview_text(message.text or ""),
    )


async def send_chat_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    parse_mode: str | None = None,
):
    logger.info("OUT chat_id=%s text=%s", chat_id, _preview_text(text))
    if parse_mode:
        return await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    return await context.bot.send_message(chat_id=chat_id, text=text)


def whitelist_guard(func):
    """Decorator: blocks non-whitelisted users."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        message = update.effective_message
        if user is None or message is None:
            logger.warning("Skipped update without user/message in whitelist guard.")
            return
        if not is_whitelisted(user.id, username=user.username):
            logger.warning("Blocked user %s (%s)", user.id, user.username)
            await send_chat_message(
                context,
                message.chat_id,
                "⛔ *Access Denied*\n\nYou are not on the whitelist\\. Contact an admin to get access\\.",
                parse_mode="MarkdownV2",
            )
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


# ─── Command Handlers ────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        logger.warning("Skipped /start update without user/message.")
        return
    log_incoming(update, "/start")
    access = "✅ You are whitelisted\\." if is_whitelisted(user.id, username=user.username) else "⛔ You are NOT whitelisted\\."
    await send_chat_message(
        context,
        message.chat_id,
        (
            f"👋 Welcome, *{user.first_name}*\\!\n\n"
            f"{access}\n\n"
            "📋 *Available commands:*\n"
            "`/meet` — Create a Google Meet space\n"
            "`/help` — Show this message\n\n"
            "_Admins also have `/whitelist` management commands\\._"
        ),
        parse_mode="MarkdownV2",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if update.effective_user is None or message is None:
        logger.warning("Skipped /help update without user/message.")
        return
    log_incoming(update, "/help")
    text = (
        "📖 *Help*\n\n"
        "*User commands:*\n"
        "`/meet` — Create a new Google Meet space\\. Returns the meeting URI\\.\n"
        "`/start` — Welcome message \\& status\n\n"
    )
    if is_admin(update.effective_user.id):
        text += (
            "*Admin commands:*\n"
            "`/whitelist list` — List all whitelisted user IDs\n"
            "`/whitelist add <id>` — Add a user ID to the whitelist\n"
            "`/whitelist remove <id>` — Remove a user ID from the whitelist\n"
        )
    await send_chat_message(context, message.chat_id, text, parse_mode="MarkdownV2")


@whitelist_guard
async def meet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        logger.warning("Skipped /meet update without user/message.")
        return
    log_incoming(update, "/meet")

    msg = await send_chat_message(context, message.chat_id, "⏳ Creating Google Meet space…")

    try:
        result = create_meet_space()
        meeting_uri = result["meeting_uri"]
        logger.info("OUT chat_id=%s text=%s", message.chat_id, _preview_text(meeting_uri))
        await msg.edit_text(meeting_uri)
        logger.info("Meet space created by user %s (%s): %s", user.id, user.username, meeting_uri)

    except Exception as e:
        logger.error("Failed to create Meet space: %s", e)
        error_text = f"❌ *Failed to create meeting\\.*\n\n`{str(e)[:200]}`"
        logger.info("OUT chat_id=%s text=%s", message.chat_id, _preview_text(error_text))
        await msg.edit_text(
            text=error_text,
            parse_mode="MarkdownV2",
        )


# ─── Whitelist Admin Commands ────────────────────────────────────────────────

async def whitelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        logger.warning("Skipped /whitelist update without user/message.")
        return
    log_incoming(update, "/whitelist")

    if not is_admin(user.id):
        await send_chat_message(context, message.chat_id, "⛔ Admin only command.")
        return

    args = context.args  # e.g. ["add", "12345"] or ["list"]

    if not args or args[0] == "list":
        wl = list_whitelist()
        if not wl:
            await send_chat_message(context, message.chat_id, "📋 Whitelist is empty.")
        else:
            ids_text = "\n".join(
                f"• `{uid}`" if isinstance(uid, int) else f"• `@{uid}`"
                for uid in wl
            )
            await send_chat_message(
                context,
                message.chat_id,
                f"📋 *Whitelisted users \\({len(wl)}\\):*\n{ids_text}",
                parse_mode="MarkdownV2",
            )
        return

    if args[0] == "add":
        if len(args) < 2:
            await send_chat_message(
                context,
                message.chat_id,
                "Usage: `/whitelist add <telegram_user_id>` or `/whitelist add @username`",
                parse_mode="Markdown",
            )
            return
        identifier = args[1]
        if identifier.isdigit():
            uid = int(identifier)
            add_to_whitelist(uid)
            logger.info("Admin %s added user ID %s to whitelist", user.id, uid)
            await send_chat_message(
                context,
                message.chat_id,
                f"✅ User ID `{uid}` added to whitelist.",
                parse_mode="Markdown",
            )
        elif identifier.startswith("@"):
            username = identifier[1:]  # strip @
            if not username or not all(c.isalnum() or c == "_" for c in username):
                await send_chat_message(
                    context,
                    message.chat_id,
                    "❌ Invalid username. Must be alphanumeric or underscore (e.g., `@john_doe`).",
                    parse_mode="Markdown",
                )
                return
            add_to_whitelist(username=username)
            logger.info("Admin %s added username %s to whitelist", user.id, username)
            await send_chat_message(
                context,
                message.chat_id,
                f"✅ User `@{username}` added to whitelist.",
                parse_mode="Markdown",
            )
        else:
            await send_chat_message(
                context,
                message.chat_id,
                "❌ Invalid identifier. Use numeric ID or @username.",
                parse_mode="Markdown",
            )
        return

    if args[0] == "remove":
        if len(args) < 2:
            await send_chat_message(
                context,
                message.chat_id,
                "Usage: `/whitelist remove <telegram_user_id>` or `/whitelist remove @username`",
                parse_mode="Markdown",
            )
            return
        identifier = args[1]
        if identifier.isdigit():
            uid = int(identifier)
            removed = remove_from_whitelist(uid)
            if removed:
                logger.info("Admin %s removed user ID %s from whitelist", user.id, uid)
                await send_chat_message(
                    context,
                    message.chat_id,
                    f"🗑 User ID `{uid}` removed from whitelist.",
                    parse_mode="Markdown",
                )
            else:
                await send_chat_message(
                    context,
                    message.chat_id,
                    f"⚠️ User ID `{uid}` was not in the whitelist.",
                    parse_mode="Markdown",
                )
        elif identifier.startswith("@"):
            username = identifier[1:]  # strip @
            if not username or not all(c.isalnum() or c == "_" for c in username):
                await send_chat_message(
                    context,
                    message.chat_id,
                    "❌ Invalid username. Must be alphanumeric or underscore.",
                    parse_mode="Markdown",
                )
                return
            removed = remove_from_whitelist(username=username)
            if removed:
                logger.info("Admin %s removed username %s from whitelist", user.id, username)
                await send_chat_message(
                    context,
                    message.chat_id,
                    f"🗑 User `@{username}` removed from whitelist.",
                    parse_mode="Markdown",
                )
            else:
                await send_chat_message(
                    context,
                    message.chat_id,
                    f"⚠️ User `@{username}` was not in the whitelist.",
                    parse_mode="Markdown",
                )
        else:
            await send_chat_message(
                context,
                message.chat_id,
                "❌ Invalid identifier. Use numeric ID or @username.",
                parse_mode="Markdown",
            )
        return

    await send_chat_message(
        context,
        message.chat_id,
        "Unknown subcommand. Use: `add`, `remove`, or `list`.",
        parse_mode="Markdown",
    )


# ─── Error Handler ───────────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception: %s", context.error, exc_info=context.error)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

    load_whitelist()  # Pre-load whitelist from disk
    start_health_server()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("meet", meet_command))
    app.add_handler(CommandHandler("whitelist", whitelist_command))
    app.add_error_handler(error_handler)

    # Python 3.14 no longer creates a default loop for the main thread.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    logger.info("Bot is running. Polling for updates…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
