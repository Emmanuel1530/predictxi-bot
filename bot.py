import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from predictor import PredictorEngine
from football_api import FootballAPI
from learning import LearningEngine

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN",   "8830179167:AAGzVcVRXZsbO6BC4YpBrLhC0a7iTwjF5EY")
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "9422a31d741937c1364b31e283a0ea14")

api      = FootballAPI(FOOTBALL_API_KEY)
predictor = PredictorEngine(api)
learner  = LearningEngine()

# Competition config
COMPETITIONS = {
    "pl":  {"name": "Premier League 🏴󠁧󠁢󠁥󠁮󠁧󠁿", "league_id": 39,  "season": 2024, "intl": False},
    "wc":  {"name": "World Cup 2022 🌍",        "league_id": 1,   "season": 2022, "intl": True},
}

def escape(text: str) -> str:
    for ch in r'\_*[]()~`>#+-=|{}.!':
        text = text.replace(ch, f'\\{ch}')
    return text

# ── helpers ──────────────────────────────────────────────────────────────────
def comp_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League", callback_data="comp_pl")],
        [InlineKeyboardButton("🌍 World Cup 2026",       callback_data="comp_wc")],
    ])

# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = escape(update.effective_user.first_name)
    text = (
        f"⚽ *Welcome to PredictXI, {name}\\!*\n\n"
        "I analyse 40\\+ factors to predict your best fantasy team\\.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *Commands*\n"
        "/competitions — Choose league or World Cup\n"
        "/fixtures — Upcoming fixtures\n"
        "/predict — Best XI prediction\n"
        "/captain — Captain \\& vice\\-captain\n"
        "/bench — Best substitutes\n"
        "/darkhorse — Hidden gem picks\n"
        "/updates — Injury alerts\n"
        "/learn — How accurate am I\\?\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🆕 *World Cup 2022 data available\\!* 🌍\n"
        "Use /competitions to switch between leagues\\!\n\n"
        "Start with /competitions 🚀"
    )
    await update.message.reply_text(text, parse_mode="MarkdownV2")

# ── /competitions ─────────────────────────────────────────────────────────────
async def competitions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏆 *Choose a Competition*\n\nWhich league do you want predictions for\\?",
        parse_mode="MarkdownV2",
        reply_markup=comp_keyboard()
    )

async def comp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    comp_key = query.data.split("_")[1]   # "pl" or "wc"
    comp = COMPETITIONS[comp_key]
    context.user_data["comp"] = comp_key

    await query.edit_message_text(
        f"✅ Switched to *{escape(comp['name'])}*\\!\n\n"
        f"Now use /fixtures to pick a match 📅",
        parse_mode="MarkdownV2"
    )

# ── /fixtures ─────────────────────────────────────────────────────────────────
async def fixtures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comp_key = context.user_data.get("comp", "wc")   # default World Cup since PL is off-season
    comp = COMPETITIONS[comp_key]

    await update.message.reply_text(
        f"🔄 Fetching *{escape(comp['name'])}* fixtures\\.\\.\\.",
        parse_mode="MarkdownV2"
    )
    try:
        matches = await api.get_upcoming_fixtures(comp["league_id"], comp["season"], limit=8)
        if not matches:
            await update.message.reply_text(
                f"❌ No upcoming fixtures found for *{escape(comp['name'])}*\\.\n\n"
                "Try /competitions to switch league\\.",
                parse_mode="MarkdownV2"
            )
            return

        keyboard = []
        for m in matches:
            home = m['teams']['home']['name']
            away = m['teams']['away']['name']
            date = m['fixture']['date'][:10]
            fid  = m['fixture']['id']
            label = f"{home} vs {away} — {date}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"fix_{fid}_{comp_key}_{home}|{away}")])

        await update.message.reply_text(
            f"📅 *{escape(comp['name'])} — Upcoming Fixtures*\nTap a match to predict\\:",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Fixtures error: {e}")
        await update.message.reply_text(f"❌ Error: {escape(str(e))}", parse_mode="MarkdownV2")

# ── fixture tap callback ───────────────────────────────────────────────────────
async def fixture_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # format: fix_{id}_{comp_key}_{home}|{away}
    _, fid, comp_key, teams = query.data.split("_", 3)
    home, away = teams.split("|")
    fixture_id = int(fid)
    comp = COMPETITIONS.get(comp_key, COMPETITIONS["wc"])

    await query.edit_message_text(
        f"⚡ Analysing *{escape(home)} vs {escape(away)}*\\.\\.\\.\n\n"
        "🧠 Running 40\\+ factor AI model\\.\\.\\.",
        parse_mode="MarkdownV2"
    )
    try:
        result = await predictor.predict(
            fixture_id, home, away,
            league_id=comp["league_id"],
            season=comp["season"],
            is_international=comp["intl"]
        )
        # Save prediction for learning
        learner.save_prediction(fixture_id, home, away, result["xi"])
        await query.edit_message_text(result["text"], parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        await query.edit_message_text(
            f"❌ Prediction failed: {escape(str(e))}\n\nTry /fixtures again\\.",
            parse_mode="MarkdownV2"
        )

# ── /predict ──────────────────────────────────────────────────────────────────
async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await fixtures(update, context)

# ── /captain ──────────────────────────────────────────────────────────────────
async def captain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📅 Pick a fixture to get captain advice\\:", parse_mode="MarkdownV2")
    await fixtures(update, context)

# ── /bench ────────────────────────────────────────────────────────────────────
async def bench(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🪑 *Bench Predictor*\n\nBench options are included automatically in every /predict result\\!",
        parse_mode="MarkdownV2"
    )

# ── /darkhorse ────────────────────────────────────────────────────────────────
async def darkhorse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comp_key = context.user_data.get("comp", "wc")
    comp = COMPETITIONS[comp_key]
    await update.message.reply_text("🌙 Finding hidden gems\\.\\.\\.", parse_mode="MarkdownV2")
    try:
        players = await api.get_top_scorers(comp["league_id"], comp["season"])
        if not players:
            await update.message.reply_text("❌ Could not fetch data\\.", parse_mode="MarkdownV2")
            return

        msg = f"🌙 *DARK HORSE PICKS — {escape(comp['name'])}*\n━━━━━━━━━━━━━━━\n\n"
        for p in players[:5]:
            name  = escape(p['player']['name'])
            team  = escape(p['statistics'][0]['team']['name'])
            goals = p['statistics'][0]['goals']['total'] or 0
            assts = p['statistics'][0]['goals']['assists'] or 0
            msg += f"🔹 *{name}* \\({team}\\)\n   ⚽ {goals} goals \\| 🎯 {assts} assists\n\n"

        msg += "_Rising form players — lower ownership, higher ceiling\\!_"
        await update.message.reply_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {escape(str(e))}", parse_mode="MarkdownV2")

# ── /updates ──────────────────────────────────────────────────────────────────
async def updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comp_key = context.user_data.get("comp", "wc")
    comp = COMPETITIONS[comp_key]
    await update.message.reply_text("🔄 Checking injury news\\.\\.\\.", parse_mode="MarkdownV2")
    try:
        injuries = await api.get_injuries(comp["league_id"], comp["season"])
        if not injuries:
            await update.message.reply_text("✅ No major injuries reported\\!", parse_mode="MarkdownV2")
            return

        msg = f"🚑 *INJURY ALERTS — {escape(comp['name'])}*\n━━━━━━━━━━━━━━━\n\n"
        for inj in injuries[:10]:
            player = escape(inj['player']['name'])
            team   = escape(inj['team']['name'])
            status = inj['player'].get('type', 'Injured')
            icon   = "🔴" if "Injured" in status else "🟡"
            msg += f"{icon} *{player}* \\({team}\\) — {escape(status)}\n"

        await update.message.reply_text(msg, parse_mode="MarkdownV2")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {escape(str(e))}", parse_mode="MarkdownV2")

# ── /learn ────────────────────────────────────────────────────────────────────
async def learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = learner.get_stats()
    if stats["total"] == 0:
        await update.message.reply_text(
            "📊 *Learning Engine*\n\n"
            "No predictions recorded yet\\!\n"
            "Make a prediction first using /fixtures, then come back here after the match\\. 🔄",
            parse_mode="MarkdownV2"
        )
        return

    accuracy = stats["correct"] / max(stats["total"], 1) * 100
    trend = "📈 Improving\\!" if stats.get("trend") == "up" else "📉 Learning from mistakes\\."

    msg = (
        "🧠 *LEARNING ENGINE REPORT*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"✅ Correct picks:  *{stats['correct']}*\n"
        f"❌ Wrong picks:    *{stats['wrong']}*\n"
        f"📊 Total players:  *{stats['total']}*\n"
        f"🎯 Accuracy:       *{accuracy:.1f}%*\n\n"
        f"{trend}\n\n"
        "━━━━━━━━━━━━━━━\n"
        "_The bot adjusts its weights after every match to get smarter\\._"
    )
    await update.message.reply_text(msg, parse_mode="MarkdownV2")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",        start))
    app.add_handler(CommandHandler("competitions", competitions))
    app.add_handler(CommandHandler("fixtures",     fixtures))
    app.add_handler(CommandHandler("predict",      predict))
    app.add_handler(CommandHandler("captain",      captain))
    app.add_handler(CommandHandler("bench",        bench))
    app.add_handler(CommandHandler("darkhorse",    darkhorse))
    app.add_handler(CommandHandler("updates",      updates))
    app.add_handler(CommandHandler("learn",        learn))

    app.add_handler(CallbackQueryHandler(comp_callback,    pattern="^comp_"))
    app.add_handler(CallbackQueryHandler(fixture_callback, pattern="^fix_"))

    logger.info("🤖 PredictXI Bot v2 started — PL + World Cup 2026!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
