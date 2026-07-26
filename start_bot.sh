#!/bin/bash
cd "/home/docc/Documents/Default Project"
source venv/bin/activate
export PYTHONUNBUFFERED=1
exec python -m src.main >> logs/bot.log 2>&1
