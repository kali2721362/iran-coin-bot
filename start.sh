#!/usr/bin/env bash
set -e

# Start bot فقط اگر متغیرها ست شده باشند
if [ -n "${BOT_TOKEN:-}" ] && [ -n "${MINI_APP_URL:-}" ]; then
  python bot/bot.py &
else
  echo "⚠️ BOT_TOKEN or MINI_APP_URL not set, bot will not start"
fi

# API در foreground (سرویس خاموش نشود)
exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}