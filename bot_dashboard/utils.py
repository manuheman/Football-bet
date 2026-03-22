# bot_dashboard/utils.py
import requests
import logging
from telegram import Bot
from asgiref.sync import sync_to_async
from .models import UserProfile, Withdrawal

logger = logging.getLogger(__name__)
BOT_TOKEN = "8661608966:AAFXphBOs9rgCzK9VJCrJtgPL_Vfe-M3cp0"
CHAPA_SECRET_KEY = "CHASECK-OtxJDfVcR7i3qTckDUbKFPK3ZIOLGjmA"


async def verify_chapa_transfer_and_alert(reference: str, telegram_id: int):
    """
    Verify a Chapa transfer by reference and alert the user via Telegram, with deep logging.
    """
    url = f"https://api.chapa.co/v1/transfers/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {CHAPA_SECRET_KEY}"
    }

    logger.info(f"[CHAPA VERIFY] Starting verification for reference: {reference}")
    logger.info(f"[CHAPA VERIFY] Request URL: {url}")
    logger.info(f"[CHAPA VERIFY] Request Headers: {headers}")

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        logger.info(f"[CHAPA VERIFY] HTTP status code: {resp.status_code}")
        logger.info(f"[CHAPA VERIFY] Raw response text: {resp.text}")

        try:
            data = resp.json()
            logger.info(f"[CHAPA VERIFY] Parsed JSON response: {data}")
        except ValueError as e:
            logger.error(f"[CHAPA VERIFY] JSON parse error: {e}")
            data = {}

        # Fetch withdrawal and user
        try:
            withdrawal = await sync_to_async(Withdrawal.objects.get)(reference=reference)
            logger.info(f"[CHAPA VERIFY] Withdrawal fetched: {withdrawal.withdraw_id}, amount: {withdrawal.amount}, status: {withdrawal.status}")
        except Withdrawal.DoesNotExist:
            logger.error(f"[CHAPA VERIFY] Withdrawal not found for reference: {reference}")
            return

        try:
            user = await sync_to_async(UserProfile.objects.get)(telegram_id=telegram_id)
            logger.info(f"[CHAPA VERIFY] User fetched: {user.telegram_id}, balance: {user.balance}, hold_balance: {getattr(user, 'hold_balance', 0)}")
        except UserProfile.DoesNotExist:
            logger.error(f"[CHAPA VERIFY] User not found: {telegram_id}")
            return

        bot = Bot(BOT_TOKEN)

        if data.get("status") == "success":
            logger.info(f"[CHAPA VERIFY] Transfer SUCCESS detected for reference {reference}")

            # Update withdrawal status
            withdrawal.status = "completed"
            await sync_to_async(withdrawal.save)()
            logger.info(f"[CHAPA VERIFY] Withdrawal {withdrawal.withdraw_id} marked as completed.")

            # Notify user via Telegram
            msg = f"✅ Your withdrawal of {withdrawal.amount:.2f} ETB has been successfully processed via {withdrawal.method.title()}!"
            await bot.send_message(chat_id=telegram_id, text=msg)
            logger.info(f"[CHAPA VERIFY] Telegram message sent to user {telegram_id}: {msg}")

        else:
            logger.warning(f"[CHAPA VERIFY] Transfer FAILED or PENDING for reference {reference}, data: {data}")

            # Update withdrawal status
            withdrawal.status = "failed"
            await sync_to_async(withdrawal.save)()
            logger.info(f"[CHAPA VERIFY] Withdrawal {withdrawal.withdraw_id} marked as failed.")

            # Rollback user hold balance
            old_balance = user.balance
            old_hold = getattr(user, "hold_balance", 0)
            user.balance += withdrawal.amount
            user.hold_balance -= withdrawal.amount
            await sync_to_async(user.save)()
            logger.info(f"[CHAPA VERIFY] User {telegram_id} balance rolled back: old_balance={old_balance}, old_hold={old_hold}, new_balance={user.balance}, new_hold={user.hold_balance}")

            # Notify user via Telegram
            msg = f"❌ Your withdrawal of {withdrawal.amount:.2f} ETB failed. Amount returned to your balance."
            await bot.send_message(chat_id=telegram_id, text=msg)
            logger.info(f"[CHAPA VERIFY] Telegram message sent to user {telegram_id}: {msg}")

    except requests.RequestException as e:
        logger.exception(f"[CHAPA VERIFY] HTTP request failed for reference {reference}: {e}")

    except Exception as e:
        logger.exception(f"[CHAPA VERIFY] Unexpected error during verification for reference {reference}: {e}")

    logger.info(f"[CHAPA VERIFY] Verification process finished for reference: {reference}")