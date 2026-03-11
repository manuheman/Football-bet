# adminbot.py

import os
import sys
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Bot
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes, CommandHandler
from asgiref.sync import sync_to_async
from django.db.models.signals import post_save
from django.dispatch import receiver

# ---------------- Django Setup ----------------
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ethio_bet.settings")

import django
django.setup()

from bot_dashboard.models import Withdrawal, UserProfile

# ---------------- Logging ----------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- Bot Token & Admins ----------------
ADMIN_BOT_TOKEN = "8035842320:AAGuOcRdwwxb5jcH1uXMrYg3zgJiM3mQmgk"  # Admin bot token
ADMIN_IDS = [1351052276]  # Telegram user IDs of admins

bot_instance = Bot(token=ADMIN_BOT_TOKEN)

# ---------------- Helper to send withdrawal to admins ----------------
async def notify_admin(withdrawal: Withdrawal):
    text = (
        f"💸 *Withdrawal Request*\n\n"
        f"User: {withdrawal.full_name} ({withdrawal.telegram_id})\n"
        f"Amount: {withdrawal.amount:.2f} ETB\n"
        f"Method: {withdrawal.method}\n"
        f"Phone: {withdrawal.phone_number}\n"
        f"Status: {withdrawal.status}"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{withdrawal.id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{withdrawal.id}")
    ]])

    for admin_id in ADMIN_IDS:
        await bot_instance.send_message(chat_id=admin_id, text=text, reply_markup=keyboard, parse_mode="Markdown")

# ---------------- Signal: Auto-notify admin on new withdrawal ----------------
@receiver(post_save, sender=Withdrawal)
def withdrawal_post_save(sender, instance: Withdrawal, created, **kwargs):
    # Only notify if it's a new pending withdrawal
    if created and instance.status == "pending":
        import asyncio
        asyncio.run(notify_admin(instance))

# ---------------- Start Command ----------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    welcome_text = (
        "👋 *Welcome Admin!*\n\n"
        "You will receive withdrawal requests from users here automatically.\n"
        "Use /pending to re-send any pending withdrawals."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# ---------------- Admin bot command to list pending withdrawals ----------------
async def list_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = await sync_to_async(list)(Withdrawal.objects.filter(status="pending"))
    if not pending:
        await update.message.reply_text("No pending withdrawals.")
        return

    for w in pending:
        await notify_admin(w)
    await update.message.reply_text(f"Sent {len(pending)} pending withdrawals to admins.")

# ---------------- Handle Approve / Reject ----------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        action, withdraw_id = query.data.split("_")
        withdrawal = await sync_to_async(Withdrawal.objects.get)(id=withdraw_id)
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.edit_message_text("❌ Error processing request.")
        return

    user = await sync_to_async(UserProfile.objects.get)(telegram_id=withdrawal.telegram_id)

    if action == "approve":
        withdrawal.status = "approved"
        await sync_to_async(withdrawal.save)()
        await context.bot.send_message(
            chat_id=withdrawal.telegram_id,
            text=f"💸 Your withdrawal request of {withdrawal.amount:.2f} ETB has been *approved*!",
            parse_mode="Markdown"
        )
        await query.edit_message_text(f"✅ Withdrawal approved for {withdrawal.full_name} ({withdrawal.amount:.2f} ETB)")
    elif action == "reject":
        withdrawal.status = "rejected"
        await sync_to_async(withdrawal.save)()
        # refund user balance
        user.balance += withdrawal.amount
        await sync_to_async(user.save)()
        await context.bot.send_message(
            chat_id=withdrawal.telegram_id,
            text=f"❌ Your withdrawal request of {withdrawal.amount:.2f} ETB has been *rejected*. Amount refunded.",
            parse_mode="Markdown"
        )
        await query.edit_message_text(f"❌ Withdrawal rejected for {withdrawal.full_name} ({withdrawal.amount:.2f} ETB)")
    else:
        await query.edit_message_text("❌ Unknown action.")

# ---------------- Main ----------------
def main():
    app = ApplicationBuilder().token(ADMIN_BOT_TOKEN).build()

    # Start command
    app.add_handler(CommandHandler("start", start_command))

    # Command to list all pending withdrawals
    app.add_handler(CommandHandler("pending", list_pending))

    # Handle approve/reject callbacks
    app.add_handler(CallbackQueryHandler(handle_callback))

    app.run_polling()

if __name__ == "__main__":
    main()