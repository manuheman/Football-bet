import sys
import os
import asyncio
import logging
import requests
import uuid

# ---------------- Django Setup ----------------
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ethio_bet.settings")

import django
django.setup()

# ---------------- Logging ----------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- Imports ----------------
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler, filters, ContextTypes
)
from asgiref.sync import sync_to_async
from bot_dashboard.models import UserProfile, ChapaPayment, Withdrawal

# ---------------- Conversation Steps ----------------
FIRST, LAST, PHONE = range(3)
DEPOSIT_AMOUNT, DEPOSIT_PHONE = range(2)
WITHDRAW_AMOUNT, WITHDRAW_METHOD, WITHDRAW_PHONE, WITHDRAW_NAME, WITHDRAW_CONFIRM = range(5)

# ---------------- API Keys ----------------
CHAPA_SECRET = "CHASECK-OtxJDfVcR7i3qTckDUbKFPK3ZIOLGjmA"

# ---------------- Bot Token ----------------
BOT_TOKEN = "8661608966:AAFXphBOs9rgCzK9VJCrJtgPL_Vfe-M3cp0"

# Replace the old URL with the new Cloudflare quick tunnel
CLOUDFLARE_URL = "https://subcommittee-comparison-masters-buying.trycloudflare.com"

# ---------------- Buttons ----------------
def get_main_buttons(telegram_id):
    match_url = f"{CLOUDFLARE_URL}/users/telegram_id/{telegram_id}/"
    buttons = [
        [InlineKeyboardButton("🎯 Match", web_app=WebAppInfo(url=match_url))],
        [
            InlineKeyboardButton("📝 Profile", callback_data="profile"),
            InlineKeyboardButton("💰 Balance", callback_data="balance")
        ],
        [
            InlineKeyboardButton("💳 Deposit", callback_data="deposit"),
            InlineKeyboardButton("💸 Withdrawal", callback_data="withdrawal")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])

# ---------------- Optimized Message Sending ----------------
async def typing_and_send(update: Update, text: str, reply_markup=None):
    try:
        # Send message directly without sleep
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        logger.info(f"Sent message to {update.effective_user.id}: {text}")
    except Exception as e:
        logger.error(f"Error sending message: {e}")

async def typing_and_edit(query, text: str, reply_markup=None):
    try:
        if query.message.text:  # Only edit text if it's a text message
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        elif query.message.photo:  # Edit caption if it's a photo
            await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            # fallback: send new message
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        logger.info(f"Edited message for {query.from_user.id}: {text}")
    except Exception as e:
        logger.error(f"Error editing message: {e}")
# ---------------- Start ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    logger.info(f"[START] User started bot: {telegram_id}")

    user_exists = await sync_to_async(UserProfile.objects.filter(telegram_id=telegram_id).exists)()

    if user_exists:
        try:
            photo_path = os.path.join(os.path.dirname(__file__), "football.png")
            with open(photo_path, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption="⚽ *Welcome back to Ethio Bet!*\n\nChoose an option:",
                    reply_markup=get_main_buttons(telegram_id),
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Photo send error: {e}")
        return ConversationHandler.END

    context.user_data.clear()
    await typing_and_send(update, "✨ *Welcome to Ethio Bet Bot!* ✨\n\nEnter your *first name*:")
    return FIRST

# ---------------- Registration ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    telegram_id = update.effective_user.id

    if 'first_name' not in context.user_data:
        context.user_data['first_name'] = text
        await typing_and_send(update, "Enter your *last name*:") 
        return LAST

    if 'last_name' not in context.user_data:
        context.user_data['last_name'] = text
        await typing_and_send(update, "Enter your *phone number*:") 
        return PHONE

    context.user_data['phone_number'] = text
    try:
        await sync_to_async(UserProfile.objects.update_or_create)(
            telegram_id=telegram_id,
            defaults={
                'first_name': context.user_data['first_name'],
                'last_name': context.user_data['last_name'],
                'phone_number': text,
                'balance': 0,
                'bonus': 0
            }
        )
        await typing_and_send(update, "✅ *Registration complete!*")
        await typing_and_send(update, "Choose an option:", reply_markup=get_main_buttons(telegram_id))
    except Exception as e:
        logger.error(f"[REGISTER ERROR] {e}", exc_info=True)
        await typing_and_send(update, "❌ Registration failed.")
    context.user_data.clear()
    return ConversationHandler.END

# ---------------- Deposit Flow ----------------
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await typing_and_edit(query, "💰 *Enter deposit amount:*")
    return DEPOSIT_AMOUNT

async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        context.user_data["deposit_amount"] = amount
        await typing_and_send(update, "📱 Enter your *phone number* for Chapa payment:")
        return DEPOSIT_PHONE
    except ValueError:
        await typing_and_send(update, "❌ Invalid amount. Enter a number.")
        return DEPOSIT_AMOUNT

async def deposit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text
    telegram_id = update.effective_user.id
    amount = context.user_data.get("deposit_amount")

    if not amount or amount <= 0:
        await typing_and_send(update, "❌ Invalid deposit amount. Please start again.")
        return ConversationHandler.END

    tx_ref = f"ethio_bet_{uuid.uuid4().hex[:10]}"
    await sync_to_async(ChapaPayment.objects.create)(
        telegram_id=telegram_id,
        tx_ref=tx_ref,
        amount=amount
    )

    payload = {
        "amount": str(amount),
        "currency": "ETB",
        "email": f"{telegram_id}@ethiobet.com",
        "first_name": "Telegram",
        "last_name": "User",
        "phone_number": phone,
        "tx_ref": tx_ref,
        "callback_url": f"{CLOUDFLARE_URL}/chapa-callback/",
        "return_url": f"https://t.me/betbot123bot",
        "customization": {"title": "Ethio Deposit", "description": "Deposit funds to your wallet"},
        "metadata": {"telegram_id": str(telegram_id)}
    }

    headers = {"Authorization": f"Bearer {CHAPA_SECRET}", "Content-Type": "application/json"}

    try:
        response = requests.post("https://api.chapa.co/v1/transaction/initialize", json=payload, headers=headers)
        data = response.json()
        checkout_url = data.get("data", {}).get("checkout_url")
        if checkout_url:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Pay with Chapa", web_app=WebAppInfo(url=checkout_url))]])
            await typing_and_send(update,
                f"💰 *Deposit Amount:* {amount} ETB\nClick the button below to complete payment inside Telegram.",
                reply_markup=keyboard
            )
        else:
            await typing_and_send(update, "❌ Payment initialization failed. Please try again.")
    except Exception as e:
        logger.error(f"[DEPOSIT] Exception: {e}", exc_info=True)
        await typing_and_send(update, "❌ Payment system error. Please try again later.")

    context.user_data.pop("deposit_amount", None)
    return ConversationHandler.END

# ---------------- Withdraw Flow ----------------
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await typing_and_edit(query, "💸 *Enter withdrawal amount:*")
    return WITHDRAW_AMOUNT

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        telegram_id = update.effective_user.id
        user = await sync_to_async(UserProfile.objects.get)(telegram_id=telegram_id)

        if amount <= 0:
            await typing_and_send(update, "❌ Amount must be greater than 0.")
            return WITHDRAW_AMOUNT
        if amount > user.balance:
            await typing_and_send(update, f"❌ Insufficient balance. Your balance: {user.balance:.2f} ETB")
            return WITHDRAW_AMOUNT

        context.user_data['withdraw_amount'] = amount
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("TeleBirr", callback_data="TeleBirr")],
            [InlineKeyboardButton("M-Pesa", callback_data="MPessa")],
            [InlineKeyboardButton("CBE Birr", callback_data="CBEBirr")]
        ])
        await typing_and_send(update, "💳 Choose withdrawal method:", reply_markup=keyboard)
        return WITHDRAW_METHOD
    except ValueError:
        await typing_and_send(update, "❌ Invalid amount. Enter a number.")
        return WITHDRAW_AMOUNT
    except UserProfile.DoesNotExist:
        await typing_and_send(update, "❌ User not found. Please register with /start.")
        return ConversationHandler.END

async def withdraw_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['withdraw_method'] = query.data
    await typing_and_edit(query, f"📱 Enter your phone number for {query.data}:")
    return WITHDRAW_PHONE

async def withdraw_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['withdraw_phone'] = update.message.text
    await typing_and_send(update, "📝 Enter your full name as registered with the payment method:")
    return WITHDRAW_NAME

async def withdraw_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['withdraw_name'] = update.message.text
    amount = context.user_data['withdraw_amount']
    method = context.user_data['withdraw_method']
    phone = context.user_data['withdraw_phone']
    name = context.user_data['withdraw_name']

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm", callback_data="withdraw_confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="back")]
    ])
    await typing_and_send(update,
        f"💸 *Withdrawal Summary*\n\n"
        f"Amount: {amount:.2f} ETB\n"
        f"Method: {method}\n"
        f"Phone: {phone}\n"
        f"Name: {name}\n\nConfirm withdrawal?",
        reply_markup=keyboard
    )
    return WITHDRAW_CONFIRM

# ---------------- Withdraw Confirm ----------------
async def withdraw_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    telegram_id = query.from_user.id

    # Get withdrawal data from user_data
    amount = context.user_data.get('withdraw_amount')
    method_input = context.user_data.get('withdraw_method')
    phone = context.user_data.get('withdraw_phone')
    name = context.user_data.get('withdraw_name')

    if not all([amount, method_input, phone, name]):
        await typing_and_edit(query, "❌ Withdrawal data incomplete. Please start again.")
        context.user_data.clear()
        return ConversationHandler.END

    # Map human-readable method to DB value
    method_map = {"TeleBirr": "telebirr", "MPessa": "mpesa", "CBEBirr": "cbe_birr"}
    method = method_map.get(method_input, "telebirr")

    # Get user object
    try:
        user = await sync_to_async(UserProfile.objects.get)(telegram_id=telegram_id)
    except UserProfile.DoesNotExist:
        await typing_and_edit(query, "❌ User not found. Please register with /start.")
        context.user_data.clear()
        return ConversationHandler.END

    # Check balance
    if amount > user.balance:
        await typing_and_edit(query, f"❌ Insufficient balance. Withdrawal failed.\nYour balance: {user.balance:.2f} ETB")
        context.user_data.clear()
        return ConversationHandler.END

    # Deduct balance
    user.balance -= amount
    await sync_to_async(user.save)()

    # Create withdrawal entry
    withdrawal = await sync_to_async(Withdrawal.objects.create)(
        telegram_id=telegram_id,
        amount=amount,
        method=method,
        phone_number=phone,
        full_name=name,
        status="pending"
    )

    # Confirm to user
    await typing_and_edit(query,
        f"✅ Withdrawal request submitted!\n"
        f"ID: {withdrawal.withdraw_id}\n"
        f"Amount: {amount:.2f} ETB\n"
        f"Method: {method.title()}\n"
        f"Status: Pending Admin Approval"
    )

    # ---------------- Notify Admin Bot ----------------
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

    ADMIN_BOT_TOKEN = "8035842320:AAGuOcRdwwxb5jcH1uXMrYg3zgJiM3mQmgk"
    ADMIN_IDS = [1351052276]  # List of admin Telegram IDs

    admin_bot = Bot(token=ADMIN_BOT_TOKEN)
    admin_text = (
        f"💸 <b>Withdrawal Request</b>\n\n"
        f"User: {name} ({telegram_id})\n"
        f"Amount: {amount:.2f} ETB\n"
        f"Method: {method.title()}\n"
        f"Phone: {phone}\n"
        f"Status: Pending"
    )

    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{withdrawal.id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{withdrawal.id}")
        ]
    ])

    # Send to all admins
    for admin_id in ADMIN_IDS:
        try:
            await admin_bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                reply_markup=admin_keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"[ADMIN NOTIFY ERROR] {e}")

    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END
# ---------------- Handle Buttons ----------------
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    telegram_id = query.from_user.id

    if data == "deposit":
        return await deposit_start(update, context)
    elif data == "withdrawal":
        return await withdraw_start(update, context)
    elif data == "profile":
        try:
            user = await sync_to_async(UserProfile.objects.get)(telegram_id=telegram_id)
            text = (
                f"📝 *Profile*\n\n"
                f"Name: {user.first_name} {user.last_name}\n"
                f"Phone: {user.phone_number}\n"
                f"Balance: 💵 {user.balance:.2f}\n"
                f"Bonus: 🎁 {user.bonus:.2f}"
            )
        except UserProfile.DoesNotExist:
            text = "Profile not found."
        await typing_and_edit(query, text, reply_markup=get_back_button())
    elif data == "balance":
        try:
            user = await sync_to_async(UserProfile.objects.get)(telegram_id=telegram_id)
            text = f"💰 *Your Balance*\n\nBalance: 💵 {user.balance:.2f}\nBonus: {user.bonus:.2f}"
        except UserProfile.DoesNotExist:
            text = "Profile not found. Please register first with /start."
        await typing_and_edit(query, text, reply_markup=get_back_button())
    elif data == "back":
        await typing_and_edit(query, "Main Menu:", reply_markup=get_main_buttons(telegram_id))
    elif data == "withdraw_confirm":
        return await withdraw_confirm(update, context)

# ---------------- Cancel ----------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await typing_and_send(update, "❌ Operation cancelled.")

# ---------------- Main ----------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    register_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FIRST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            LAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    deposit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, pattern="deposit")],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            DEPOSIT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_start, pattern="withdrawal")],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_METHOD: [CallbackQueryHandler(withdraw_method)],
            WITHDRAW_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_phone)],
            WITHDRAW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_name)],
            WITHDRAW_CONFIRM: [CallbackQueryHandler(withdraw_confirm, pattern="withdraw_confirm")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(register_conv)
    app.add_handler(deposit_conv)
    app.add_handler(withdraw_conv)
    app.add_handler(CallbackQueryHandler(handle_button))

    app.run_polling()

if __name__ == "__main__":
    main()