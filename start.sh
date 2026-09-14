#!/usr/bin/env bash
set -e

# Run API in background
uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} &

# Run Telegram bot in foreground
python bot/bot.py