# 🤖 Google Meet Telegram Bot

A Telegram bot that creates Google Meet spaces on demand.

**Features:**
- Creates a Meet space with **OPEN access** (anyone with the link can join)
- **Whitelist security** — only approved Telegram user IDs can use the bot
- Admins can manage the whitelist live via bot commands
- OAuth2 token is cached so Google sign-in only happens once

---

## 📋 Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | |
| Telegram bot token | Create via [@BotFather](https://t.me/BotFather) |
| Google Cloud project | With **Meet API** enabled |
| Google OAuth 2.0 credentials | Desktop app type |

---

## 🚀 Setup

### 1. Clone & install dependencies

```bash
git clone <your-repo>
cd meet_bot
pip install -r requirements.txt
```

### 2. Create a Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the **bot token**

### 3. Set up Google Cloud

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable the **Google Meet API**:
   - Navigate to **APIs & Services → Library**
   - Search "Google Meet API" and enable it
4. Create OAuth 2.0 credentials:
   - Go to **APIs & Services → Credentials**
   - Click **Create Credentials → OAuth client ID**
   - Select **Desktop app**
   - Download as `credentials.json` and place it in the bot folder

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your values
```

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_TELEGRAM_IDS=your_telegram_user_id
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_TOKEN_FILE=token.json
WHITELIST_FILE=whitelist.json
DEFAULT_WHITELIST_IDS=123456789
```

> **Tip:** Find your Telegram user ID by messaging [@userinfobot](https://t.me/userinfobot)

### 5. Generate token once (separate step)

```bash
python create_token.py
```

This opens a browser for OAuth and saves `token.json`.

### 6. Run bot

```bash
python bot.py
```

Runtime reads `token.json` and does not write token files, which is suitable for read-only production filesystems.

---

## 💬 Bot Commands

### User Commands (whitelisted users)

| Command | Description |
|---|---|
| `/start` | Welcome message and your whitelist status |
| `/meet` | Create a new Google Meet space |
| `/help` | Show available commands |

### Admin Commands

| Command | Description |
|---|---|
| `/whitelist list` | Show all whitelisted users (IDs and @usernames) |
| `/whitelist add <id\|@username>` | Add a user by ID or @username |
| `/whitelist remove <id\|@username>` | Remove a user by ID or @username |

---

## 🔐 Whitelist System

- Users can be whitelisted by **numeric Telegram ID** or **@username**
- The whitelist is stored in `whitelist.json` (auto-created)
- `DEFAULT_WHITELIST_IDS` seeds comma-separated numeric IDs into whitelist at startup
- Admin IDs are set via `ADMIN_TELEGRAM_IDS` in `.env`
- Admins are **not** automatically whitelisted — add yourself: `/whitelist add <your_id>`
- Users match by **either** ID **or** username, so they only need one entry
- The whitelist persists across bot restarts

For ephemeral deployments, set `DEFAULT_WHITELIST_IDS` so required users are restored automatically after redeploy.

**Example admin workflow:**
```
You: /whitelist add 123456789
Bot: ✅ User ID `123456789` added to whitelist.

You: /whitelist add @john_doe
Bot: ✅ User `@john_doe` added to whitelist.

You: /whitelist list
Bot: 📋 Whitelisted users (2):
     • 123456789
     • john_doe
```

---

## 📁 Project Structure

```
meet_bot/
├── bot.py            # Telegram bot handlers
├── meet_service.py   # Google Meet API integration
├── create_token.py   # One-time OAuth token generator
├── whitelist.py      # Whitelist management with persistence
├── requirements.txt
├── .env.example      # Environment variable template
├── .env              # Your config (DO NOT commit)
├── credentials.json  # Google OAuth credentials (DO NOT commit)
└── token.json        # Auto-generated OAuth token (DO NOT commit)
```

---

## 🛡️ Security Notes

- Never commit `credentials.json`, `token.json`, or `.env` to version control
- Add them to `.gitignore`:
  ```
  .env
  credentials.json
  token.json
  whitelist.json
  ```
- Only admins (set in `.env`) can modify the whitelist
- All non-whitelisted access attempts are logged

---

## 🔧 Troubleshooting

| Problem | Solution |
|---|---|
| `TELEGRAM_BOT_TOKEN is not set` | Check your `.env` file |
| `credentials.json not found` | Download from Google Cloud Console |
| `PERMISSION_DENIED` from Meet API | Ensure Meet API is enabled in your GCP project |
| `token.json` missing/invalid | Run `python create_token.py` and redeploy |
