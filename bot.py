import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import db

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def play_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🪙 العب دلوقتي", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # فك كود الدعوة لو المستخدم جه بلينك زي t.me/bot?start=ref_12345
    referrer_id = None
    if context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                candidate = int(arg[4:])
                if candidate != user.id:
                    referrer_id = candidate
            except ValueError:
                pass

    already_existed = db.user_exists(user.id)
    db.get_or_create_user(user.id, first_name=user.first_name or "")

    bonus_applied = False
    if not already_existed and referrer_id:
        bonus_applied = db.apply_referral(user.id, referrer_id)

    if not WEBAPP_URL:
        await update.message.reply_text(
            "⚠️ لسه متظبطش رابط اللعبة (WEBAPP_URL) في إعدادات السيرفر."
        )
        return

    bonus_note = (
        f"\n🎁 خدت {db.REFERRAL_SIGNUP_BONUS} CCL هدية عشان جيت بدعوة صديق!"
        if bonus_applied else ""
    )
    await update.message.reply_text(
        f"أهلاً {user.first_name}! 👋\n"
        f"دوس زر اللعب وابدأ تجمع عملات CanCel (CCL) 🚀{bonus_note}",
        reply_markup=play_keyboard(),
    )


async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_username = context.bot.username
    link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    await update.message.reply_text(
        f"🔗 ابعت اللينك ده لأصدقائك، كل ما حد يدخل بيه تاخد {db.REFERRAL_REWARD} CCL:\n\n"
        f"{link}"
    )


def build_bot_app():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("invite", invite))
    return application
