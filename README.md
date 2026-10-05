# EasyIncomeX Telegram Bot

## Files
- `bot.py` — main bot
- `requirements.txt` — Python dependency
- `render.yaml` — Render Background Worker configuration
- `.gitignore` — protects local/runtime files
- `database.json` — initial empty database

## Render Environment Variables
Set:
- `BOT_TOKEN` = your NEW BotFather token
- `ADMIN_ID` = your Telegram numeric user ID

Never put the bot token in GitHub.

## Local run
```bash
pip install -r requirements.txt
export BOT_TOKEN="YOUR_TOKEN"
export ADMIN_ID="YOUR_ID"
python bot.py
```

Windows PowerShell:
```powershell
$env:BOT_TOKEN="YOUR_TOKEN"
$env:ADMIN_ID="YOUR_ID"
python bot.py
```

## Admin
Send `/admin` from the configured ADMIN_ID.

This safe version does not collect passwords, 2FA secrets, session cookies, or other login credentials.
