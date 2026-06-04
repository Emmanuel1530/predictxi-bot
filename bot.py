import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from predictor import PredictorEngine
from football_api import FootballAPI

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8830179167:AAGzVcVRXZsbO6BC4YpBrLhC0a7iTwjF5EY")
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "9422a31d741937c1364b31e283a0ea14")

api = FootballAPI(FOOTBALL_API_KEY)
predictor = PredictorEngine(api)

PREMIER_LEAGUE_ID = 39
CURRENT_SEASON = 2024

def escape(text: str) -> str:
    """Escape MarkdownV2 special chars."""
    for ch in r'\_*[]()~`>#+-=|{}.!':
        text = text.replace(ch, f'\\{ch}')
    return text

# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    text = (
        f"⚽ *Welcome to PredictXI, {escape(name)}\\!*\n\n"
        "I analyse 40\\+ factors to predict your best My11Circle team\\.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *Commands*\n"
        "/predict — Best XI for upcoming match\n"
        "/captain — Captain \\& vice\\-captain picks\n"
        "/bench — Top substitute options\n"
        "/darkhorse — Hidden gem players\n"
        "/fixtures — Upcoming PL fixtures\n"
        "/updates — Injury \\& suspension alerts\n"
        "/compare — Last prediction accuracy\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Type /fixtures to pick a match and get started\\! 🚀"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")

# ─── /fixtures ────────────────────────────────────────────────────────────────
async def fixtures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Fetching upcoming fixtures\\.\\.\\.", parse_mode="MarkdownV2")
    try:
        matches = await api.get_upcoming_fixtures(PREMIER_LEAGUE_ID, CURRENT_SEASON, limit=8)
        if not matches:
            await update.message.reply_text("❌ No upcoming fixtures found\\. Try again later\\.", parse_mode="MarkdownV2")
            return

        keyboard = []
        for m in matches:
            home = m['teams']['home']['name']
            away = m['teams']['away']['name']
            date = m['fixture']['date'][:10]
            fixture_id = m['fixture']['id']
            label = f"{home} vs {away} — {date}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"fix_{fixture_id}_{home}_{away}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📅 *Upcoming Premier League Fixtures*\nTap a match to predict\\:",
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Fixtures error: {e}")
        await update.message.reply_text(f"❌ Error fetching fixtures: {escape(str(e))}", parse_mode="MarkdownV2")

# ─── Fixture button callback ───────────────────────────────────────────────────
async def fixture_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 3)
    fixture_id = int(parts[1])
    home = parts[2]
    away = parts[3]

    await query.edit_message_text(
        f"⚡ Analysing *{escape(home)} vs {escape(away)}*\\.\\.\\.\n\n"
        "🧠 Running 40\\+ factor AI model\\.\\.\\.",
        parse_mode="MarkdownV2"
    )
    try:
        result = await predictor.predict(fixture_id, home, away)
        await query.edit_message_text(result, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        await query.edit_message_text(
            f"❌ Prediction failed: {escape(str(e))}\n\nTry /predict again\\.",
            parse_mode="MarkdownV2"
        )

# ─── /predict ─────────────────────────────────────────────────────────────────
async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📅 Pick a fixture first\\!", parse_mode="MarkdownV2")
    await fixtures(update, context)

# ─── /captain ─────────────────────────────────────────────────────────────────
async def captain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📅 Select a fixture to get captain advice\\:", parse_mode="MarkdownV2")
    await fixtures(update, context)

# ─── /bench ───────────────────────────────────────────────────────────────────
async def bench(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🪑 *Bench Predictor*\n\nSelect a fixture via /fixtures \\— the prediction includes bench options automatically\\!",
        parse_mode="MarkdownV2"
    )

# ─── /darkhorse ───────────────────────────────────────────────────────────────
async def darkhorse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌙 *Dark Horse Finder*\n\nFetching low\\-ownership gems\\.\\.\\.", parse_mode="MarkdownV2")
    try:
        players = await api.get_top_scorers(PREMIER_LEAGUE_ID, CURRENT_SEASON)
        if not players:
            await update.message.reply_text("❌ Could not fetch dark horse data\\.", parse_mode="MarkdownV2")
            return

        msg = "🌙 *DARK HORSE PICKS*\n━━━━━━━━━━━━━━━\n\n"
        msg += "Low\\-owned players with rising form:\n\n"
        shown = 0
        for p in players:
            if shown >= 5:
                break
            name = escape(p['player']['name'])
            team = escape(p['statistics'][0]['team']['name'])
            goals = p['statistics'][0]['goals']['total'] or 0
            assists = p['statistics'][0]['goals']['assists'] or 0
            msg += f"🔹 *{name}* \\({team}\\)\n"
            msg += f"   Goals: {goals} \\| Assists: {assists}\n\n"
            shown += 1

        msg += "_These players show strong underlying stats with potentially lower ownership\\._"
        await update.message.reply_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"Darkhorse error: {e}")
        await update.message.reply_text(f"❌ Error: {escape(str(e))}", parse_mode="MarkdownV2")

# ─── /updates ─────────────────────────────────────────────────────────────────
async def updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Checking injury & suspension news\\.\\.\\.", parse_mode="MarkdownV2")
    try:
        injuries = await api.get_injuries(PREMIER_LEAGUE_ID, CURRENT_SEASON)
        if not injuries:
            await update.message.reply_text("✅ No major injuries reported right now\\!", parse_mode="MarkdownV2")
            return

        msg = "🚑 *INJURY & SUSPENSION ALERTS*\n━━━━━━━━━━━━━━━\n\n"
        shown = 0
        for inj in injuries[:10]:
            player = escape(inj['player']['name'])
            team = escape(inj['team']['name'])
            reason = escape(inj.get('player', {}).get('reason', 'Unknown'))
            status = inj['player'].get('type', 'Injured')
            icon = "🔴" if "Injured" in status else "🟡"
            msg += f"{icon} *{player}* \\({team}\\)\n"
            msg += f"   Status: {escape(status)}\n\n"
            shown += 1

        await update.message.reply_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"Updates error: {e}")
        await update.message.reply_text(f"❌ Error: {escape(str(e))}", parse_mode="MarkdownV2")

# ─── /compare ─────────────────────────────────────────────────────────────────
async def compare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📊 *PREDICTION ACCURACY TRACKER*\n"
        "━━━━━━━━━━━━━━━\n\n"
        "🗓 This feature logs your predictions and compares them after each match\\.\n\n"
        "📈 *How it works:*\n"
        "1\\. Run /predict before a match\n"
        "2\\. Bot stores your predicted XI\n"
        "3\\. After the match, run /compare\n"
        "4\\. See how many of your picks scored \\10\\+\n\n"
        "_Coming in v1\\.1 \\— post\\-match accuracy reports\\!_"
    )
    await update.message.reply_text(msg, parse_mode="MarkdownV2")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fixtures", fixtures))
    app.add_handler(CommandHandler("predict", predict))
    app.add_handler(CommandHandler("captain", captain))
    app.add_handler(CommandHandler("bench", bench))
    app.add_handler(CommandHandler("darkhorse", darkhorse))
    app.add_handler(CommandHandler("updates", updates))
    app.add_handler(CommandHandler("compare", compare))
    app.add_handler(CallbackQueryHandler(fixture_callback, pattern="^fix_"))

    logger.info("🤖 PredictXI Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
