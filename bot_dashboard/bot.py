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
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler, filters, ContextTypes
)
from asgiref.sync import sync_to_async
from bot_dashboard.models import UserProfile, Withdrawal   # ChapaPayment still removed

# ---------------- Conversation Steps ----------------
LANGUAGE, FIRST, LAST, PHONE = range(4)
WITHDRAW_AMOUNT, WITHDRAW_METHOD, WITHDRAW_PHONE, WITHDRAW_NAME, WITHDRAW_CONFIRM = range(5)
DEPOSIT_AMOUNT, DEPOSIT_PHONE = range(2)   # new deposit states

# ---------------- Minimums ----------------
MIN_DEPOSIT_AMOUNT = 10.0
MIN_WITHDRAW_AMOUNT = 50.0

# ---------------- Bot Token ----------------
BOT_TOKEN = "8619308377:AAHyLWpBLOovN1IcXzAMz1rOpHrBfI0uWsg"

# ---------------- Translation Helper ----------------
def t(lang: str, en_text: str, am_text: str) -> str:
    return am_text if lang == "am" else en_text

# ---------------- Language Buttons ----------------
def get_language_buttons():
    buttons = [
        [InlineKeyboardButton("English", callback_data="lang_en")],
        [InlineKeyboardButton("አማርኛ", callback_data="lang_am")]
    ]
    return InlineKeyboardMarkup(buttons)

# ---------------- Cloudflare Tunnel ----------------
CLOUDFLARE_URL = "http://ethio-bet.duckdns.org"

# Chapa payment configuration
CHAPA_SECRET_KEY = "CHASECK-OtxJDfVcR7i3qTckDUbKFPK3ZIOLGjmA"
CHAPA_INIT_URL = "https://api.chapa.co/v1/transaction/initialize"
CHAPA_VERIFY_URL = "https://api.chapa.co/v1/transaction/verify/{}"
CALLBACK_URL = "https://citizens-fence-peter-inns.trycloudflare.com/chapa/callback/"  # Full public URL
# ---------------- Buttons ----------------
def get_main_buttons(telegram_id):
    match_url = f"{CLOUDFLARE_URL}/users/telegram_id/{telegram_id}/"
    bingo_url = f"{CLOUDFLARE_URL}/bingo/{telegram_id}/"
    buttons = [
        [InlineKeyboardButton("🎯 Match", web_app=WebAppInfo(url=match_url)), InlineKeyboardButton("🎯 Play Bingo", web_app=WebAppInfo(url=bingo_url))],
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
            InlineKeyboardButton("Contact Us", url="https://t.me/Football_bet21")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])

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
    """Handle /start command: skip language selection, start registration directly"""
    telegram_id = update.effective_user.id
    logger.info(f"[START] User started bot: {telegram_id}")

    # Check if user exists
    user_exists = await sync_to_async(UserProfile.objects.filter(telegram_id=telegram_id).exists)()

    if user_exists:
        try:
            user = await sync_to_async(UserProfile.objects.get)(telegram_id=telegram_id)

            photo_path = os.path.join(os.path.dirname(__file__), "football.png")
            with open(photo_path, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=f"⚽ *Welcome back to Ethio Bet!* 🎉\n\nChoose an option below to continue:",
                    reply_markup=get_main_buttons(telegram_id),
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Photo send error: {e}")
        return ConversationHandler.END

    # New user: skip language selection, ask first name directly
    context.user_data.clear()
    await typing_and_send(
        update,
        "✨ *Welcome to Ethio Bet Bot!* ✨\n\nLet’s get started! Enter your *first name* to create your profile."
    )
    return FIRST  # Start registration conversation

# ---------------- Deposit Flow ----------------
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

    try:
        # make sure user exists before continuing
        await sync_to_async(UserProfile.objects.get)(telegram_id=query.from_user.id)
    except UserProfile.DoesNotExist:
        await typing_and_edit(query, "❌ User not found. Please register with /start.", reply_markup=get_back_button())
        return ConversationHandler.END

    await typing_and_edit(query, f"💵 *Enter deposit amount (minimum {MIN_DEPOSIT_AMOUNT:.0f} ETB):*", reply_markup=get_back_button())
    return DEPOSIT_AMOUNT

async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount <= 0:
            await typing_and_send(update, "❌ Amount must be greater than 0.", reply_markup=get_back_button())
            return DEPOSIT_AMOUNT
        if amount < MIN_DEPOSIT_AMOUNT:
            await typing_and_send(update, f"❌ Minimum deposit is {MIN_DEPOSIT_AMOUNT:.0f} ETB.", reply_markup=get_back_button())
            return DEPOSIT_AMOUNT
        context.user_data['deposit_amount'] = amount
        await typing_and_send(update, "📱 Enter the phone number you will use for payment:", reply_markup=get_back_button())
        return DEPOSIT_PHONE
    except ValueError:
        await typing_and_send(update, "❌ Invalid amount. Enter a number.", reply_markup=get_back_button())
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
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("💳 Complete Payment", web_app=WebAppInfo(url=checkout_url))
            ], [InlineKeyboardButton("⬅️ Back", callback_data="back")]])
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
            await typing_and_send(update, f"❌ {error}", reply_markup=get_back_button())
    except Exception as e:
        logger.error(f"[DEPOSIT INIT ERROR] {e}", exc_info=True)
        await typing_and_send(update, "❌ Unable to contact payment server; try again later.", reply_markup=get_back_button())

    context.user_data.clear()
    return ConversationHandler.END

async def language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang = 'am' if query.data == "lang_am" else 'en'
    context.user_data['language'] = lang

    await typing_and_edit(
        query,
        t(lang,
          "✨ *Welcome to Ethio Bet Bot!* ✨\n\nEnter your *first name*:",
          "✨ *Ethio Bet ቦት እንኳን ደህና መጡ!* ✨\n\n*ስምዎን* ያስገቡ:")
    )
    return FIRST

# ---------------- Registration ----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    telegram_id = update.effective_user.id
    lang = context.user_data.get('language', 'en')

    if 'first_name' not in context.user_data:
        context.user_data['first_name'] = text
        await typing_and_send(update, t(lang, "Enter your *last name*:", "የእርስዎን *የአያት ስም* ያስገቡ:"))
        return LAST

    if 'last_name' not in context.user_data:
        context.user_data['last_name'] = text
        await typing_and_send(update, t(lang, "Enter your *phone number*:", "*ስልክ ቁጥር* ያስገቡ:"))
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
                'language': lang,
            }
        )
        await typing_and_send(update, t(lang, "✅ *Registration complete!*", "✅ *ምዝገባ ተጠናቋል!*"))
        await typing_and_send(update, t(lang, "Choose an option:", "አማራጮችን ይምረጡ:"), reply_markup=get_main_buttons(telegram_id))
    except Exception as e:
        logger.error(f"[REGISTER ERROR] {e}", exc_info=True)
        await typing_and_send(update, t(lang, "❌ Registration failed.", "❌ ምዝገባ አልተሳካም።"))
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
        await typing_and_edit(query, "❌ User not found. Please register with /start.", reply_markup=get_back_button())
        return ConversationHandler.END

    await typing_and_edit(query, f"💸 *Enter withdrawal amount (minimum {MIN_WITHDRAW_AMOUNT:.0f} ETB):*", reply_markup=get_back_button())
    return WITHDRAW_AMOUNT

# ---------------- Deposit Flow ----------------
async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)

    try:
        # make sure user exists before continuing
        await sync_to_async(UserProfile.objects.get)(telegram_id=query.from_user.id)
    except UserProfile.DoesNotExist:
        await typing_and_edit(query, "❌ User not found. Please register with /start.", reply_markup=get_back_button())
        return ConversationHandler.END

    await typing_and_edit(query, f"💵 *Enter deposit amount (minimum {MIN_DEPOSIT_AMOUNT:.0f} ETB):*", reply_markup=get_back_button())
    return DEPOSIT_AMOUNT

async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount <= 0:
            await typing_and_send(update, "❌ Amount must be greater than 0.", reply_markup=get_back_button())
            return DEPOSIT_AMOUNT
        if amount < MIN_DEPOSIT_AMOUNT:
            await typing_and_send(update, f"❌ Minimum deposit is {MIN_DEPOSIT_AMOUNT:.0f} ETB.", reply_markup=get_back_button())
            return DEPOSIT_AMOUNT
        context.user_data['deposit_amount'] = amount
        await typing_and_send(update, "📱 Enter the phone number you will use for payment:", reply_markup=get_back_button())
        return DEPOSIT_PHONE
    except ValueError:
        await typing_and_send(update, "❌ Invalid amount. Enter a number.", reply_markup=get_back_button())
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
                [InlineKeyboardButton("💳 Complete Payment", web_app=WebAppInfo(url=checkout_url))],
                [InlineKeyboardButton("⬅️ Back", callback_data="back")]
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
            await typing_and_send(update, f"❌ {error}", reply_markup=get_back_button())
    except Exception as e:
        logger.error(f"[DEPOSIT INIT ERROR] {e}", exc_info=True)
        await typing_and_send(update, "❌ Unable to contact payment server; try again later.", reply_markup=get_back_button())

    context.user_data.clear()
    return ConversationHandler.END

#withdrawal flow functions
# ---------------- Withdraw Flow ----------------

# Step 1: Ask for withdrawal amount
async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = context.user_data.get('user')
    lang = user.language if user else 'en'

    try:
        amount = float(text)
        if amount <= 0:
            await typing_and_send(update, "❌ Amount must be greater than 0." if lang == 'en' else "❌ መጠኑ 0 በላይ መሆን አለበት።", reply_markup=get_back_button())
            return WITHDRAW_AMOUNT
        if amount < MIN_WITHDRAW_AMOUNT:
            await typing_and_send(update, f"❌ Minimum withdrawal amount is {MIN_WITHDRAW_AMOUNT:.0f} ETB." if lang == 'en' else f"❌ የከፍያ ዝርዝር ዝርዝር እንዲሁ የሚለው ከ{MIN_WITHDRAW_AMOUNT:.0f} ETB በታች አይደለም።", reply_markup=get_back_button())
            return WITHDRAW_AMOUNT
        if user.balance < amount:
            await typing_and_send(update, "❌ Insufficient balance." if lang == 'en' else "❌ የተገኘዎ ቀሪ ገንዘብ በቂ አይደለም።", reply_markup=get_back_button())
            return WITHDRAW_AMOUNT

        context.user_data['withdraw_amount'] = amount

        # Ask for method using inline buttons
        buttons = [
            [InlineKeyboardButton("Telebirr", callback_data="method_telebirr")],
            [InlineKeyboardButton("M-Pesa", callback_data="method_mpesa")],
            [InlineKeyboardButton("CBE Birr", callback_data="method_cbe_birr")],
        ]
        await typing_and_send(update, "💳 Choose withdrawal method:" if lang == 'en' else "💳 የገንዘብ ማስመዝገብ ዘዴ ይምረጡ፡፡",
                              reply_markup=InlineKeyboardMarkup(buttons))
        return WITHDRAW_METHOD

    except ValueError:
        await typing_and_send(update, "❌ Invalid amount. Enter a number." if lang == 'en' else "❌ መጠኑ ትክክል አይደለም። ቁጥር ያስገቡ።")
        return WITHDRAW_AMOUNT


# Step 2: Handle withdrawal method selection
async def withdraw_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.replace("method_", "")
    context.user_data['withdraw_method'] = method
    user = context.user_data.get('user')
    lang = user.language if user else 'en'

    await typing_and_edit(query, "📱 Enter account or phone number for this method:" if lang == 'en' else "📱 በዚህ ዘዴ አካውንት ወይም ስልክ ቁጥር ያስገቡ።", reply_markup=get_back_button())
    return WITHDRAW_PHONE


# Step 3: Ask for account / phone number
async def withdraw_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data['withdraw_phone'] = phone
    user = context.user_data.get('user')
    lang = user.language if user else 'en'

    await typing_and_send(update, "✍️ Enter full name for withdrawal:" if lang == 'en' else "✍️ ሙሉ ስምዎን ያስገቡ።", reply_markup=get_back_button())
    return WITHDRAW_NAME


# Step 4: Ask for full name
async def withdraw_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_name = update.message.text.strip()
    context.user_data['withdraw_name'] = full_name
    user = context.user_data.get('user')
    lang = user.language if user else 'en'

    amount = context.user_data.get('withdraw_amount')
    method = context.user_data.get('withdraw_method')
    phone = context.user_data.get('withdraw_phone')

    # Confirmation inline buttons
    buttons = [
        [InlineKeyboardButton("✅ Confirm", callback_data="withdraw_confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="back")]
    ]
    text = (
        f"💸 *Withdrawal Summary*\n\n"
        f"Amount: {amount:.2f} ETB\n"
        f"Method: {method.title()}\n"
        f"Phone/Account: {phone}\n"
        f"Full Name: {full_name}\n\n"
        "Tap *Confirm* to proceed or *Cancel* to go back."
    )
    await typing_and_send(update, text, reply_markup=InlineKeyboardMarkup(buttons))
    return WITHDRAW_CONFIRM

# ---------------- Withdraw Step 5: Confirm & Server Transfer ----------------
async def withdraw_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = context.user_data.get('user')
    lang = user.language if user else 'en'

    # Gather withdrawal info
    amount = context.user_data.get('withdraw_amount')
    method = context.user_data.get('withdraw_method')
    phone = context.user_data.get('withdraw_phone')
    full_name = context.user_data.get('withdraw_name')

    logger.info(
        "User %s confirming withdrawal: amount=%s, method=%s, phone=%s, full_name=%s",
        user.telegram_id if user else "unknown", amount, method, phone, full_name
    )

    # Safety checks
    if not user:
        await typing_and_edit(
            query,
            "❌ User not found." if lang == 'en' else "❌ ተጠቃሚ አልተገኘም።"
        )
        context.user_data.clear()
        return ConversationHandler.END

    if user.balance < amount:
        await typing_and_edit(
            query,
            "❌ Insufficient balance." if lang == 'en' else "❌ የተገኘዎ ቀሪ ገንዘብ በቂ አይደለም።"
        )
        context.user_data.clear()
        return ConversationHandler.END

    # Deduct balance and put on hold
    user.balance -= amount
    user.hold_balance = getattr(user, "hold_balance", 0) + amount
    await sync_to_async(user.save)()

    # Create withdrawal record
    withdrawal = await sync_to_async(Withdrawal.objects.create)(
        user=user,
        telegram_id=user.telegram_id,
        amount=amount,
        method=method,
        phone_number=phone,
        full_name=full_name,
        status="pending"
    )

    logger.info("Withdrawal record created: %s", withdrawal.withdraw_id)

    # Prepare payload for server-side transfer initiation
    url = f"{CLOUDFLARE_URL}/chapa/initiate_transfer/"
    payload = {
        "telegram_id": user.telegram_id,
        "amount": amount,
        "full_name": full_name,
        "phone_number": phone,
        "method": method
    }

    logger.info("Sending withdrawal request to server: %s", payload)

    try:
        resp = requests.post(url, json=payload, timeout=20)
        try:
            data = resp.json()
        except ValueError:
            logger.error("Server response is not valid JSON: %s", resp.text)
            # rollback hold
            user.balance += amount
            user.hold_balance -= amount
            await sync_to_async(user.save)()
            await typing_and_edit(
                query,
                "❌ Failed to process server response." if lang == 'en' else "❌ ከሰርቨር መልስ ማስተካከል አልቻለም።",
                reply_markup=get_main_buttons(user.telegram_id)
            )
            context.user_data.clear()
            return ConversationHandler.END

        logger.info("Server response: status_code=%s, data=%s", resp.status_code, data)

        if resp.status_code == 200 and data.get("success"):
            # Update withdrawal as processed (optional)
            withdrawal.is_processed = True
            await sync_to_async(withdrawal.save)()
            await typing_and_edit(
                query,
                f"✅ Withdrawal request submitted!\nAmount: {amount:.2f} ETB\nMethod: {method.title()}"
                if lang == 'en' else
                f"✅ ገንዘብ መውሰድ ጥያቄ ተሰጥቷል!\nመጠን: {amount:.2f} ETB\nዘዴ: {method.title()}",
                reply_markup=get_main_buttons(user.telegram_id)
            )
        else:
            # rollback hold balance
            user.balance += amount
            user.hold_balance -= amount
            await sync_to_async(user.save)()
            error_msg = data.get('error', 'Unknown error')
            logger.warning("Withdrawal failed: %s", error_msg)
            await typing_and_edit(
                query,
                f"❌ Withdrawal failed: {error_msg}" if lang == 'en' else f"❌ ገንዘብ መውሰድ አልተሳካም: {error_msg}",
                reply_markup=get_main_buttons(user.telegram_id)
            )

    except requests.RequestException as e:
        logger.error("[WITHDRAW ERROR] HTTP request failed: %s", e, exc_info=True)
        # rollback hold balance
        user.balance += amount
        user.hold_balance -= amount
        await sync_to_async(user.save)()
        await typing_and_edit(
            query,
            "❌ Unable to initiate transfer. Try again later." if lang == 'en' else
            "❌ ገንዘብ መውሰድ አልቻለም። ከዚህ በኋላ ደግመው ይሞክሩ።",
            reply_markup=get_main_buttons(user.telegram_id)
        )

    except Exception as e:
        logger.error("[WITHDRAW ERROR] Unhandled exception: %s", e, exc_info=True)
        # rollback hold balance
        user.balance += amount
        user.hold_balance -= amount
        await sync_to_async(user.save)()
        await typing_and_edit(
            query,
            "❌ Unexpected error occurred." if lang == 'en' else "❌ ያልታወቀ ስህተት ተፈጠረ።",
            reply_markup=get_main_buttons(user.telegram_id)
        )

    # Clear user context
    context.user_data.clear()
    logger.info("Withdrawal process completed for user %s", user.telegram_id)
    return ConversationHandler.END
# ---------------- Handle Buttons ----------------
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    telegram_id = query.from_user.id

    # ---------------- Handle Withdrawal Start ----------------
    if data == "withdrawal":
        return await withdraw_start(update, context)

    # ---------------- Handle Withdrawal Method Selection ----------------
    elif data.startswith("method_"):
        return await withdraw_method(update, context)

    # ---------------- Handle Withdrawal Confirmation ----------------
    elif data == "withdraw_confirm":
        return await withdraw_confirm(update, context)

    # ---------------- Handle Profile ----------------
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
            text = "⚠️ Profile not found. Please register first with /start."
        await typing_and_edit(query, text, reply_markup=get_back_button())

    # ---------------- Handle Balance ----------------
    elif data == "balance":
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
        try:
            user = await sync_to_async(UserProfile.objects.get)(telegram_id=telegram_id)
            text = f"💰 *Your Balance*\n\nBalance: 💵 {user.balance:.2f}\nBonus: 🎁 {user.bonus:.2f}"
        except UserProfile.DoesNotExist:
            text = "⚠️ Profile not found. Please register first with /start."
        await typing_and_edit(query, text, reply_markup=get_back_button())

    # ---------------- Handle Back to Main Menu ----------------
    elif data == "back":
        await typing_and_edit(query, "🏠 Main Menu:", reply_markup=get_main_buttons(telegram_id))

    # ---------------- Default Catch ----------------
    else:
        await typing_and_edit(query, "⚠️ Unknown action. Please try again.", reply_markup=get_main_buttons(telegram_id))


# ---------------- Cancel ----------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = context.user_data.get('language', 'en')
    context.user_data.clear()
    await typing_and_send(update, t(lang, "❌ Operation cancelled.", "❌ እርዳታ ተወው ተሰናክሏል."))

# ---------------- Main ----------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    register_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANGUAGE: [CallbackQueryHandler(language_selection, pattern="lang_.*")],
            FIRST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            LAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
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

    deposit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, pattern="deposite")],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            DEPOSIT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(register_conv)
    app.add_handler(withdraw_conv)
    app.add_handler(deposit_conv)          # add deposit handler
    app.add_handler(CallbackQueryHandler(handle_button))

    app.run_polling()

if __name__ == "__main__":
    main()
