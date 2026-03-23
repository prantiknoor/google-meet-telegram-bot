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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_IDS_RAW = os.getenv("ADMIN_TELEGRAM_IDS", "")
ADMIN_IDS = set(
    int(uid.strip()) for uid in ADMIN_IDS_RAW.split(",") if uid.strip().isdigit()
)


# ─── Helpers ────────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


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
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=(
                    "⛔ *Access Denied*\n\nYou are not on the whitelist\\. "
                    "Contact an admin to get access\\."
                ),
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
    access = "✅ You are whitelisted\\." if is_whitelisted(user.id, username=user.username) else "⛔ You are NOT whitelisted\\."
    await context.bot.send_message(
        chat_id=message.chat_id,
        text=(
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
    await context.bot.send_message(chat_id=message.chat_id, text=text, parse_mode="MarkdownV2")


@whitelist_guard
async def meet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        logger.warning("Skipped /meet update without user/message.")
        return

    msg = await context.bot.send_message(chat_id=message.chat_id, text="⏳ Creating Google Meet space…")

    try:
        result = create_meet_space()
        meeting_uri = result["meeting_uri"]
        await msg.edit_text(meeting_uri)
        logger.info("Meet space created by user %s (%s): %s", user.id, user.username, meeting_uri)

    except Exception as e:
        logger.error("Failed to create Meet space: %s", e)
        await msg.edit_text(
            text=f"❌ *Failed to create meeting\\.*\n\n`{str(e)[:200]}`",
            parse_mode="MarkdownV2",
        )


# ─── Whitelist Admin Commands ────────────────────────────────────────────────

async def whitelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        logger.warning("Skipped /whitelist update without user/message.")
        return

    if not is_admin(user.id):
        await context.bot.send_message(chat_id=message.chat_id, text="⛔ Admin only command.")
        return

    args = context.args  # e.g. ["add", "12345"] or ["list"]

    if not args or args[0] == "list":
        wl = list_whitelist()
        if not wl:
            await context.bot.send_message(chat_id=message.chat_id, text="📋 Whitelist is empty.")
        else:
            ids_text = "\n".join(
                f"• `{uid}`" if isinstance(uid, int) else f"• `@{uid}`"
                for uid in wl
            )
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"📋 *Whitelisted users \\({len(wl)}\\):*\n{ids_text}",
                parse_mode="MarkdownV2",
            )
        return

    if args[0] == "add":
        if len(args) < 2:
            await context.bot.send_message(
                chat_id=message.chat_id,
                text="Usage: `/whitelist add <telegram_user_id>` or `/whitelist add @username`",
                parse_mode="Markdown",
            )
            return
        identifier = args[1]
        if identifier.isdigit():
            uid = int(identifier)
            add_to_whitelist(uid)
            logger.info("Admin %s added user ID %s to whitelist", user.id, uid)
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"✅ User ID `{uid}` added to whitelist.",
                parse_mode="Markdown",
            )
        elif identifier.startswith("@"):
            username = identifier[1:]  # strip @
            if not username or not all(c.isalnum() or c == "_" for c in username):
                await context.bot.send_message(
                    chat_id=message.chat_id,
                    text="❌ Invalid username. Must be alphanumeric or underscore (e.g., `@john_doe`).",
                    parse_mode="Markdown",
                )
                return
            add_to_whitelist(username=username)
            logger.info("Admin %s added username %s to whitelist", user.id, username)
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"✅ User `@{username}` added to whitelist.",
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=message.chat_id,
                text="❌ Invalid identifier. Use numeric ID or @username.",
                parse_mode="Markdown",
            )
        return

    if args[0] == "remove":
        if len(args) < 2:
            await context.bot.send_message(
                chat_id=message.chat_id,
                text="Usage: `/whitelist remove <telegram_user_id>` or `/whitelist remove @username`",
                parse_mode="Markdown",
            )
            return
        identifier = args[1]
        if identifier.isdigit():
            uid = int(identifier)
            removed = remove_from_whitelist(uid)
            if removed:
                logger.info("Admin %s removed user ID %s from whitelist", user.id, uid)
                await context.bot.send_message(
                    chat_id=message.chat_id,
                    text=f"🗑 User ID `{uid}` removed from whitelist.",
                    parse_mode="Markdown",
                )
            else:
                await context.bot.send_message(
                    chat_id=message.chat_id,
                    text=f"⚠️ User ID `{uid}` was not in the whitelist.",
                    parse_mode="Markdown",
                )
        elif identifier.startswith("@"):
            username = identifier[1:]  # strip @
            if not username or not all(c.isalnum() or c == "_" for c in username):
                await context.bot.send_message(
                    chat_id=message.chat_id,
                    text="❌ Invalid username. Must be alphanumeric or underscore.",
                    parse_mode="Markdown",
                )
                return
            removed = remove_from_whitelist(username=username)
            if removed:
                logger.info("Admin %s removed username %s from whitelist", user.id, username)
                await context.bot.send_message(
                    chat_id=message.chat_id,
                    text=f"🗑 User `@{username}` removed from whitelist.",
                    parse_mode="Markdown",
                )
            else:
                await context.bot.send_message(
                    chat_id=message.chat_id,
                    text=f"⚠️ User `@{username}` was not in the whitelist.",
                    parse_mode="Markdown",
                )
        else:
            await context.bot.send_message(
                chat_id=message.chat_id,
                text="❌ Invalid identifier. Use numeric ID or @username.",
                parse_mode="Markdown",
            )
        return

    await context.bot.send_message(
        chat_id=message.chat_id,
        text="Unknown subcommand. Use: `add`, `remove`, or `list`.",
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
