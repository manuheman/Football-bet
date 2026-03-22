import sys
import os
import asyncio
import logging
import requests                         # <– back again, used for init call

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
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo, Bot
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler, filters, ContextTypes
)
from asgiref.sync import sync_to_async
from bot_dashboard.models import UserProfile, Withdrawal

# ---------------- Conversation Steps ----------------
LANGUAGE, FIRST, LAST, PHONE = range(4)
WITHDRAW_AMOUNT, WITHDRAW_METHOD, WITHDRAW_PHONE, WITHDRAW_NAME, WITHDRAW_CONFIRM = range(5)
DEPOSIT_AMOUNT, DEPOSIT_PHONE = range(2)

# ---------------- Bot Token ----------------
BOT_TOKEN = "7958696346:AAFdKba6dRRmNikiZfzCM5WZEim9KOox3KM"

# ---------------- Cloudflare Tunnel ----------------
CLOUDFLARE_URL = "https://ethio-bet.duckdns.org"

# ---------------- Language Strings ----------------
LANGUAGE_STRINGS = {
    "en": {
        "welcome_new": "✨ *Welcome to Ethio Bet Bot!* ✨\n\nEnter your *first name*: ",
        "welcome_back": "⚽ *Welcome back to Ethio Bet!*\n\nChoose an option:",
        "enter_last_name": "Enter your *last name*:",
        "enter_phone": "Enter your *phone number*:",
        "registration_complete": "✅ *Registration complete!*",
        "amount_must_be_positive": "❌ Amount must be greater than 0.",
        "invalid_amount": "❌ Invalid amount. Enter a number.",
        "insufficient_balance": "❌ Insufficient balance. Your balance: {balance:.2f} ETB",
        "withdraw_summary": "💸 *Withdrawal Summary*\n\nAmount: {amount:.2f} ETB\nMethod: {method}\nPhone: {phone}\nName: {name}\n\nConfirm withdrawal?",
        "withdraw_submitted": "✅ Withdrawal request submitted!\nID: {withdraw_id}\nAmount: {amount:.2f} ETB\nMethod: {method}\nStatus: Pending Admin Approval",
        "deposit_prompt": "💵 *Enter deposit amount:*",
        "enter_payment_phone": "📱 Enter the phone number you will use for payment:",
        "deposit_initialized": "✅ Deposit initialized!\n\nAmount: {amount:.2f} ETB\nPhone: {phone}\nTap the button below to complete your payment.",
        "operation_cancelled": "❌ Operation cancelled.",
        "choose_language": "🌐 Please choose your language / እባክዎ ቋንቋዎን ይምረጡ:",
        "english": "English",
        "amharic": "አማርኛ"
    },
    "am": {
        "welcome_new": "✨ *ወደ Ethio Bet Bot በእንኳን ደህና መጡ!* ✨\n\n*ስምዎን* ያስገቡ:",
        "welcome_back": "⚽ *ወደ Ethio Bet በደህና መጡ!*\n\nአማራጮችን ይምረጡ:",
        "enter_last_name": "*የአያት ስም* ያስገቡ:",
        "enter_phone": "*ስልክ ቁጥር* ያስገቡ:",
        "registration_complete": "✅ *ምዝገባ ተጠናቋል!*",
        "amount_must_be_positive": "❌ መጠኑ ከ0 በላይ መሆን አለበት።",
        "invalid_amount": "❌ የተሳሳተ መጠን። ቁጥር ያስገቡ።",
        "insufficient_balance": "❌ ቀሪ ብለንም። ቀሪ ገንዘብዎ: {balance:.2f} ETB",
        "withdraw_summary": "💸 *የገንዘብ መንቀሳቀስ ማጠቃለያ*\n\nመጠን: {amount:.2f} ETB\nዘዴ: {method}\nስልክ: {phone}\nስም: {name}\n\nማረጋገጫ ይፈልጋሉ?",
        "withdraw_submitted": "✅ ገንዘብ መንቀሳቀስ ጥያቄ ተላክቷል!\nመታወቂያ: {withdraw_id}\nመጠን: {amount:.2f} ETB\nዘዴ: {method}\nሁኔታ: እየተፈታ ያለ አስተዳደር",
        "deposit_prompt": "💵 *የገንዘብ መጨመሪያ መጠን* ያስገቡ:",
        "enter_payment_phone": "📱 ለክፍያ የምትጠቀሙበት ስልክ ቁጥር ያስገቡ:",
        "deposit_initialized": "✅ ገንዘብ መጨመሪያ ተጀምሯል!\n\nመጠን: {amount:.2f} ETB\nስልክ: {phone}\nክፍያዎን ለማጠናቀቅ በታች ያለውን አዝራር ይጫኑ።",
        "operation_cancelled": "❌ እርምጃ ተሰርዟል።",
        "choose_language": "🌐 እባክዎ ቋንቋዎን ይምረጡ / Please choose your language:",
        "english": "English",
        "amharic": "አማርኛ"
    }
}

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
            InlineKeyboardButton("💳 Deposit", callback_data="deposite"),
            InlineKeyboardButton("💸 Withdrawal", callback_data="withdrawal")
        ],
        [
            InlineKeyboardButton("Join Group", url="https://t.me/football1bet_group"),
            InlineKeyboardButton("Contact Us", url="https://t.me/Yeabweld")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])

def get_language_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(LANGUAGE_STRINGS['en']['english'], callback_data='lang_en')],
        [InlineKeyboardButton(LANGUAGE_STRINGS['en']['amharic'], callback_data='lang_am')]
    ])

# ---------------- Message Helpers ----------------
async def typing_and_send(update: Update, text: str, reply_markup=None):
    try:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        logger.info(f"Sent message to {update.effective_user.id}: {text}")
    except Exception as e:
        logger.error(f"Error sending message: {e}")

async def typing_and_edit(query, text: str, reply_markup=None):
    try:
        if query.message.text:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        elif query.message.photo:
            await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
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
                    caption=LANGUAGE_STRINGS['en']['welcome_back'],  # default English for existing users
                    reply_markup=get_main_buttons(telegram_id),
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Photo send error: {e}")
        return ConversationHandler.END

    context.user_data.clear()
    await typing_and_send(update, LANGUAGE_STRINGS['en']['choose_language'], reply_markup=get_language_buttons())
    return LANGUAGE

# ---------------- Language Selection ----------------
async def language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'lang_en':
        context.user_data['lang'] = 'en'
    else:
        context.user_data['lang'] = 'am'
    
    lang = context.user_data['lang']
    await typing_and_edit(query, LANGUAGE_STRINGS[lang]['welcome_new'])
    return FIRST

# ---------------- Registration ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    telegram_id = update.effective_user.id
    lang = context.user_data.get('lang', 'en')

    if 'first_name' not in context.user_data:
        context.user_data['first_name'] = text
        await typing_and_send(update, LANGUAGE_STRINGS[lang]['enter_last_name']) 
        return LAST

    if 'last_name' not in context.user_data:
        context.user_data['last_name'] = text
        await typing_and_send(update, LANGUAGE_STRINGS[lang]['enter_phone']) 
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
                'bonus': 0,
                'language': lang
            }
        )
        await typing_and_send(update, LANGUAGE_STRINGS[lang]['registration_complete'])
        await typing_and_send(update, LANGUAGE_STRINGS[lang]['welcome_back'], reply_markup=get_main_buttons(telegram_id))
    except Exception as e:
        logger.error(f"[REGISTER ERROR] {e}", exc_info=True)
        await typing_and_send(update, "❌ Registration failed.")
    context.user_data.clear()
    return ConversationHandler.END


# ---------------- Withdraw Flow ----------------
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # show typing to user while we fetch profile
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

    # cache user so later steps don't hit DB again
    try:
        user = await sync_to_async(UserProfile.objects.get)(telegram_id=query.from_user.id)
        context.user_data['user'] = user
    except UserProfile.DoesNotExist:
        await typing_and_edit(query, "❌ User not found. Please register with /start.")
        return ConversationHandler.END

    await typing_and_edit(query, "💸 *Enter withdrawal amount:*")
    return WITHDRAW_AMOUNT

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # show typing indicator immediately
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        amount = float(update.message.text)
        if amount <= 0:
            await typing_and_send(update, "❌ Amount must be greater than 0.")
            return WITHDRAW_AMOUNT

        # use cached user if available
        user = context.user_data.get('user')
        if not user:
            user = await sync_to_async(UserProfile.objects.get)(telegram_id=update.effective_user.id)
            context.user_data['user'] = user

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

async def withdraw_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    telegram_id = query.from_user.id

    amount = context.user_data.get('withdraw_amount')
    method_input = context.user_data.get('withdraw_method')
    phone = context.user_data.get('withdraw_phone')
    name = context.user_data.get('withdraw_name')

    if not all([amount, method_input, phone, name]):
        await typing_and_edit(query, "❌ Withdrawal data incomplete. Please start again.")
        context.user_data.clear()
        return ConversationHandler.END

    method_map = {"TeleBirr": "telebirr", "MPessa": "mpesa", "CBEBirr": "cbe_birr"}
    method = method_map.get(method_input, "telebirr")

    try:
        user = await sync_to_async(UserProfile.objects.get)(telegram_id=telegram_id)
    except UserProfile.DoesNotExist:
        await typing_and_edit(query, "❌ User not found. Please register with /start.")
        context.user_data.clear()
        return ConversationHandler.END

    if amount > user.balance:
        await typing_and_edit(query, f"❌ Insufficient balance. Withdrawal failed.\nYour balance: {user.balance:.2f} ETB")
        context.user_data.clear()
        return ConversationHandler.END

    user.balance -= amount
    await sync_to_async(user.save)()

    withdrawal = await sync_to_async(Withdrawal.objects.create)(
        telegram_id=telegram_id,
        amount=amount,
        method=method,
        phone_number=phone,
        full_name=name,
        status="pending"
    )

    await typing_and_edit(query,
        f"✅ Withdrawal request submitted!\n"
        f"ID: {withdrawal.withdraw_id}\n"
        f"Amount: {amount:.2f} ETB\n"
        f"Method: {method.title()}\n"
        f"Status: Pending Admin Approval"
    )

    context.user_data.clear()
    return ConversationHandler.END

# ---------------- Deposit Flow ----------------
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

    try:
        # make sure user exists before continuing
        await sync_to_async(UserProfile.objects.get)(telegram_id=query.from_user.id)
    except UserProfile.DoesNotExist:
        await typing_and_edit(query, "❌ User not found. Please register with /start.")
        return ConversationHandler.END

    await typing_and_edit(query, "💵 *Enter deposit amount:*")
    return DEPOSIT_AMOUNT

async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount <= 0:
            await typing_and_send(update, "❌ Amount must be greater than 0.")
            return DEPOSIT_AMOUNT
        context.user_data['deposit_amount'] = amount
        await typing_and_send(update, "📱 Enter the phone number you will use for payment:")
        return DEPOSIT_PHONE
    except ValueError:
        await typing_and_send(update, "❌ Invalid amount. Enter a number.")
        return DEPOSIT_AMOUNT

async def deposit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data['deposit_phone'] = phone
    amount = context.user_data.get('deposit_amount')
    telegram_id = update.effective_user.id

    # call the Django view to create a Chapa transaction
    url = f"{CLOUDFLARE_URL}/chapa/init_deposit/"
    payload = {
        "telegram_id": telegram_id,
        "amount": amount,
        "phone_number": phone
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        data = resp.json()
        if resp.status_code == 200 and data.get("success"):
            checkout_url = data.get("checkout_url")
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Complete Payment", web_app=WebAppInfo(url=checkout_url))]
            ])
            await typing_and_send(
                update,
                f"✅ Deposit initialized!\n\n"
                f"Amount: {amount:.2f} ETB\n"
                f"Phone: {phone}\n\n"
                "Tap the button below to complete your payment. "
                "You will receive a message when the transaction is verified.",
                reply_markup=keyboard
            )
        else:
            error = data.get("error", "Failed to initialise payment.")
            await typing_and_send(update, f"❌ {error}")
    except Exception as e:
        logger.error(f"[DEPOSIT INIT ERROR] {e}", exc_info=True)
        await typing_and_send(update, "❌ Unable to contact payment server; try again later.")

    context.user_data.clear()
    return ConversationHandler.END

# ---------------- Handle Buttons ----------------
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    telegram_id = query.from_user.id

    if data == "withdrawal":
        return await withdraw_start(update, context)
    # deposit queries are handled by deposit_conv entrypoint; no branch here
    elif data == "profile":
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
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
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
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

    # ---------------- Registration Conversation ----------------
    register_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANGUAGE: [CallbackQueryHandler(language_choice, pattern="^lang_")],
            FIRST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            LAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ---------------- Withdraw Conversation ----------------
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

    # ---------------- Deposit Conversation ----------------
    deposit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, pattern="deposite")],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            DEPOSIT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # ---------------- Add Handlers ----------------
    app.add_handler(register_conv)
    app.add_handler(withdraw_conv)
    app.add_handler(deposit_conv)
    app.add_handler(CallbackQueryHandler(handle_button))  # Handles buttons like profile, balance, back, etc.

    # ---------------- Run Bot ----------------
    app.run_polling()

if __name__ == "__main__":
    main()