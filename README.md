# PredictXI — Fantasy Football Telegram Bot

## Quick Deploy to Railway

### Step 1 — Upload to GitHub
1. Create a new repo at github.com (call it `predictxi-bot`)
2. Upload ALL these files into it

### Step 2 — Deploy on Railway
1. Go to railway.app → New Project → Deploy from GitHub repo
2. Select your `predictxi-bot` repo
3. Railway auto-detects Python ✅

### Step 3 — Set Environment Variables on Railway
In Railway dashboard → your project → Variables tab, add:

```
TELEGRAM_TOKEN=8830179167:AAGzVcVRXZsbO6BC4YpBrLhC0a7iTwjF5EY
FOOTBALL_API_KEY=9422a31d741937c1364b31e283a0ea14
```

### Step 4 — Deploy!
Click Deploy → watch logs → bot goes live in ~2 minutes 🚀

---

## Bot Commands
- `/start` — Welcome message
- `/fixtures` — Pick an upcoming PL match
- `/predict` — Get AI predicted XI
- `/captain` — Captain & vice-captain advice
- `/bench` — Best substitute options
- `/darkhorse` — Low-owned hidden gems
- `/updates` — Injury & suspension alerts
- `/compare` — Prediction accuracy tracker

---

## Files
- `bot.py` — Main Telegram bot handlers
- `football_api.py` — API-Football API wrapper
- `predictor.py` — AI scoring & team selection engine
- `requirements.txt` — Python dependencies
- `Procfile` — Railway process file
- `railway.toml` — Railway config
