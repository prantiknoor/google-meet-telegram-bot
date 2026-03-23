"""
Whitelist manager.
Stores allowed Telegram user IDs and usernames with persistence.
Thread-safe for single-process bots.
"""

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

WHITELIST_FILE = os.getenv("WHITELIST_FILE", "whitelist.json")
DEFAULT_WHITELIST_IDS = os.getenv("DEFAULT_WHITELIST_IDS", "")

_lock = threading.Lock()
_whitelist: set = set()  # Stores both int IDs and str usernames (e.g., "john_doe")


def _parse_default_ids(raw_ids: str) -> set:
    """Parse comma-separated Telegram IDs from env, ignoring invalid values."""
    default_ids: set = set()
    for value in raw_ids.split(","):
        stripped = value.strip()
        if not stripped:
            continue
        if stripped.isdigit():
            default_ids.add(int(stripped))
        else:
            logger.warning("Ignoring invalid DEFAULT_WHITELIST_IDS value: %s", stripped)
    return default_ids


# ─── Persistence ─────────────────────────────────────────────────────────────

def load_whitelist() -> None:
    """Load the whitelist from disk into memory. Call once at startup."""
    global _whitelist
    default_ids = _parse_default_ids(DEFAULT_WHITELIST_IDS)
    file_data: set = set()

    if os.path.exists(WHITELIST_FILE):
        try:
            with open(WHITELIST_FILE, "r") as fh:
                data = json.load(fh)
            # Support both old numeric format and new mixed format
            for item in data.get("user_ids", []):
                if isinstance(item, int) or (isinstance(item, str) and item.isdigit()):
                    file_data.add(int(item))
                elif isinstance(item, str):  # Username
                    file_data.add(item)
        except Exception as exc:
            logger.error("Failed to load whitelist: %s", exc)
    else:
        logger.info("No whitelist file found — starting with empty whitelist.")

    with _lock:
        _whitelist = file_data | default_ids
        # Persist merged IDs so defaults survive even if env is removed later.
        if _whitelist != file_data:
            _save_whitelist()

    num_ids = sum(1 for x in _whitelist if isinstance(x, int))
    num_usernames = sum(1 for x in _whitelist if isinstance(x, str))
    logger.info(
        "Whitelist loaded: %d user(s) (%d IDs, %d usernames)",
        len(_whitelist),
        num_ids,
        num_usernames,
    )


def _save_whitelist() -> None:
    """Persist the current in-memory whitelist to disk (must hold _lock)."""
    try:
        # Sort: numeric IDs first, then usernames alphabetically
        sorted_ids = sorted([x for x in _whitelist if isinstance(x, int)])
        sorted_usernames = sorted([x for x in _whitelist if isinstance(x, str)])
        combined = sorted_ids + sorted_usernames
        with open(WHITELIST_FILE, "w") as fh:
            json.dump({"user_ids": combined}, fh, indent=2)
    except Exception as exc:
        logger.error("Failed to save whitelist: %s", exc)


# ─── Public API ──────────────────────────────────────────────────────────────

def is_whitelisted(user_id: int, username: str = None) -> bool:
    """
    Return True if user is whitelisted by either numeric ID or username.
    Args:
        user_id: Numeric Telegram user ID
        username: Optional Telegram username (without @)
    """
    with _lock:
        if user_id in _whitelist:
            return True
        if username and username in _whitelist:
            return True
        return False


def add_to_whitelist(user_id: int = None, username: str = None) -> None:
    """
    Add a user to the whitelist by either numeric ID or username.
    Args:
        user_id: Numeric Telegram user ID
        username: Telegram username (without @)
    """
    with _lock:
        if user_id is not None:
            _whitelist.add(user_id)
            logger.info("Whitelisted user ID: %s", user_id)
        if username is not None:
            _whitelist.add(username)
            logger.info("Whitelisted username: %s", username)
        _save_whitelist()


def remove_from_whitelist(user_id: int = None, username: str = None) -> bool:
    """
    Remove a user from the whitelist by either numeric ID or username.
    Returns True if removed, False if it wasn't present.
    Args:
        user_id: Numeric Telegram user ID
        username: Telegram username (without @)
    """
    with _lock:
        removed = False
        if user_id is not None and user_id in _whitelist:
            _whitelist.discard(user_id)
            logger.info("Removed from whitelist: %s", user_id)
            removed = True
        if username is not None and username in _whitelist:
            _whitelist.discard(username)
            logger.info("Removed from whitelist: @%s", username)
            removed = True
        if removed:
            _save_whitelist()
        return removed


def list_whitelist() -> list:
    """Return a sorted list of all whitelisted entries (numeric IDs first, then usernames)."""
    with _lock:
        sorted_ids = sorted([x for x in _whitelist if isinstance(x, int)])
        sorted_usernames = sorted([x for x in _whitelist if isinstance(x, str)])
        return sorted_ids + sorted_usernames
