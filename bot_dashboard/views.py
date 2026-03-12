import json
import asyncio
import logging
from decimal import Decimal
import uuid
import requests  # Added missing import for requests library
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from telegram import Bot
from django.utils import timezone

from .models import UserProfile, Game, Bet, BetSelection
from .models import ChapaPayment

logger = logging.getLogger(__name__)
BOT_TOKEN = "8661608966:AAFXphBOs9rgCzK9VJCrJtgPL_Vfe-M3cp0"
PUBLIC_URL = "https://appliances-capability-sustainability-tool.trycloudflare.com"

# Chapa payment configuration
CHAPA_SECRET_KEY = "CHASECK-OtxJDfVcR7i3qTckDUbKFPK3ZIOLGjmA"
CHAPA_INIT_URL = "https://api.chapa.co/v1/transaction/initialize"
CHAPA_VERIFY_URL = "https://api.chapa.co/v1/transaction/verify/{}"
CALLBACK_URL = f"{PUBLIC_URL}/chapa/callback/"  # Updated to use the correct public URL

# ---------------- User Dashboard ----------------
def user_detail(request, telegram_id):
    """
    Render the user dashboard with today's games and user profile.
    Filters games by selected country and league if provided.
    """
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)
    today = timezone.localdate()
    selected_country = request.GET.get('country', '').strip().lower()
    selected_league = request.GET.get('league', '').strip()

    games = Game.objects.filter(game_datetime__date=today, finished=False)
    if selected_country:
        games = games.filter(country__iexact=selected_country)
    if selected_league:
        games = games.filter(league__iexact=selected_league)

    games_data = []
    for game in games:
        server_time = timezone.localtime(game.game_datetime)
        games_data.append({
            "id": game.id,
            "team1": game.team1,
            "team2": game.team2,
            "country": game.country,
            "league": game.league,
            "country_flag_url": game.country_flag.url if game.country_flag else "",
            "type": getattr(game, "type", ""),
            "win1": float(game.win1),
            "draw": float(game.draw),
            "win2": float(game.win2),
            "double_1x": float(game.double_1x),
            "double_12": float(game.double_12),
            "double_x2": float(game.double_x2),
            "score_team1": game.score_team1,
            "score_team2": game.score_team2,
            "finished": game.finished,
            "game_datetime": game.game_datetime,
            "server_time": server_time
        })

    context = {
        "user": user,
        "games": games_data,
        "selected_country": selected_country,
        "selected_league": selected_league,
    }

    return render(request, "user_detail.html", context)


# ---------------- Place Bet ----------------
@csrf_exempt
def place_bet(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request method."})

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON."})

    telegram_id = data.get("telegram_id")
    if not telegram_id:
        return JsonResponse({"success": False, "error": "User not specified."})

    try:
        user = UserProfile.objects.get(telegram_id=telegram_id)
    except UserProfile.DoesNotExist:
        return JsonResponse({"success": False, "error": "User does not exist."})

    selected_bets = data.get("selectedBets", {})
    bet_amount = float(data.get("betAmount", 0))
    if bet_amount <= 0 or not selected_bets:
        return JsonResponse({"success": False, "error": "Invalid bet amount or no selections."})

    if isinstance(selected_bets, list):
        try:
            selected_bets = {str(bet['gameId']): bet for bet in selected_bets}
        except KeyError:
            return JsonResponse({"success": False, "error": "Each bet must include gameId."})

    total_balance = user.bonus + user.balance
    if bet_amount > total_balance:
        return JsonResponse({"success": False, "error": "Insufficient balance."})

    # Validate selections and calculate total odds
    total_odds = 1
    valid_bet_types = ['win1','draw','win2','double_1x','double_12','double_x2']

    for game_id_str, bet_info in selected_bets.items():
        try:
            game = Game.objects.get(id=int(game_id_str))
        except Game.DoesNotExist:
            return JsonResponse({"success": False, "error": f"Game {game_id_str} does not exist."})

        bet_type = bet_info.get('betType')
        if bet_type not in valid_bet_types:
            return JsonResponse({"success": False, "error": f"Invalid bet type: {bet_type}"})

        db_odds = getattr(game, bet_type)
        if float(db_odds) != float(bet_info.get('odds', 0)):
            return JsonResponse({"success": False, "error": f"Odds for {game.team1} vs {game.team2} have changed."})

        total_odds *= float(db_odds)

    potential_win = bet_amount * total_odds

    # Deduct from bonus first, then balance
    remaining = bet_amount
    if user.bonus >= remaining:
        user.bonus -= remaining
        remaining = 0
    else:
        remaining -= user.bonus
        user.bonus = 0
        user.balance -= remaining
    user.save()

    bet_obj = Bet.objects.create(
        user=user,
        bet_amount=bet_amount,
        total_odds=total_odds,
        potential_win=potential_win
    )

    for game_id_str, bet_info in selected_bets.items():
        game = Game.objects.get(id=int(game_id_str))
        BetSelection.objects.create(
            bet=bet_obj,
            game=game,
            bet_type=bet_info['betType'],
            odds=bet_info['odds'],
            match_info=bet_info.get('gameName', f"{game.team1} vs {game.team2}")
        )

    logger.info(f"[BET] User {telegram_id} placed a bet {bet_obj.ticket_id} amount={bet_amount}")
    return JsonResponse({
        "success": True,
        "ticket_id": bet_obj.ticket_id,
        "potential_win": potential_win,
        "new_balance": user.balance,
        "new_bonus": user.bonus
    })


# ---------------- Bet History ----------------
def history(request, telegram_id=None):
    if not telegram_id:
        return HttpResponse("Missing telegram_id", status=400)

    user_profile = get_object_or_404(UserProfile, telegram_id=telegram_id)
    user_bets = Bet.objects.filter(user=user_profile).order_by('-created_at')
    bets_with_selections = []

    for bet in user_bets:
        selections = BetSelection.objects.filter(bet=bet)
        sel_with_status = []

        for sel in selections:
            result = sel.is_correct()
            match_status = 'Pending'
            if result is True:
                match_status = 'Finished ✔'
            elif result is False:
                match_status = 'Finished ✖'

            sel_with_status.append({
                'match_info': sel.match_info,
                'bet_type': sel.bet_type,
                'odds': sel.odds,
                'match_status': match_status
            })

        previous_status = bet.status
        if all(sel['match_status'] == 'Finished ✔' for sel in sel_with_status):
            bet.status = 'won'
        elif any(sel['match_status'] == 'Finished ✖' for sel in sel_with_status):
            bet.status = 'lost'
        else:
            bet.status = 'pending'

        if bet.status == 'won' and not bet.processed:
            bet.user.balance += bet.potential_win
            bet.user.save()
            bet.processed = True
            bet.save()
        elif previous_status != bet.status:
            bet.save()

        bets_with_selections.append({
            'ticket_id': bet.ticket_id,
            'bet_amount': bet.bet_amount,
            'total_odds': bet.total_odds,
            'potential_win': bet.potential_win,
            'status': bet.status,
            'created_at': bet.created_at,
            'selections': sel_with_status
        })

    context = {
        'user': user_profile,
        'bets': bets_with_selections
    }

    return render(request, 'history.html', context)

# ---------------- Initialize Deposit ----------------
@csrf_exempt
def init_deposit(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"})

    try:
        data = json.loads(request.body)
        telegram_id = data.get("telegram_id")
        amount = float(data.get("amount", 0))
        phone_number = data.get("phone_number", "")

        if not telegram_id or amount <= 0 or not phone_number:
            return JsonResponse({"success": False, "error": "Invalid data"})

        user = get_object_or_404(UserProfile, telegram_id=telegram_id)

        headers = {"Authorization": f"Bearer {CHAPA_SECRET_KEY}", "Content-Type": "application/json"}
        tx_ref = f"ethio_bet_{uuid.uuid4().hex}"  # Generate tx_ref here for consistency
        payload = {
            "amount": str(amount),
            "currency": "ETB",
            "email": "noreply@ethiobet.com",
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": phone_number,
            "tx_ref": tx_ref,
            "callback_url": CALLBACK_URL,
            "meta": {"telegram_id": telegram_id},
            "customization": {
                "title": "EthioBet Deposit",
                "description": f"Deposit for {user.first_name} {user.last_name}",
            },
        }

        resp = requests.post(CHAPA_INIT_URL, json=payload, headers=headers)
        resp_data = resp.json()

        if resp.status_code == 200 and resp_data.get("status") == "success":
            checkout_url = resp_data["data"]["checkout_url"]
            
            # Create payment record in DB for callback to use
            ChapaPayment.objects.create(
                telegram_id=telegram_id,
                amount=amount,
                phone_number=phone_number,
                tx_ref=tx_ref,
                status="pending"
            )
            
            return JsonResponse({"success": True, "checkout_url": checkout_url})
        else:
            error = resp_data.get("message", "Failed to initialize payment")
            return JsonResponse({"success": False, "error": error})

    except Exception as e:
        logger.error(f"Init deposit error: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": "Internal server error"})


# ---------------- Callback / Verify Payment ----------------
@csrf_exempt
def chapa_callback(request):
    """
    Chapa calls this endpoint after payment is completed.
    We'll verify the transaction, update user's balance, and notify via Telegram.
    """
    try:
        # Accept both POST and GET payloads
        if request.method == "POST":
            data = json.loads(request.body)
            tx_ref = data.get("tx_ref")
            telegram_id = data.get("meta", {}).get("telegram_id")
        else:
            data = request.GET
            tx_ref = data.get("trx_ref")  # Chapa sends 'trx_ref' in GET params
            telegram_id = None  # Not reliably passed in GET; we'll get from model

        if not tx_ref:
            logger.error("Missing tx_ref in callback")
            return JsonResponse({"success": False, "error": "Missing tx_ref"})

        # Retrieve payment record from DB to get telegram_id and update status
        try:
            payment = ChapaPayment.objects.get(tx_ref=tx_ref)
            telegram_id = payment.telegram_id
        except ChapaPayment.DoesNotExist:
            logger.error(f"Payment record not found for tx_ref: {tx_ref}")
            return JsonResponse({"success": False, "error": "Payment record not found"})

        # Verify transaction with Chapa
        headers = {"Authorization": f"Bearer {CHAPA_SECRET_KEY}"}
        verify_resp = requests.get(CHAPA_VERIFY_URL.format(tx_ref), headers=headers)
        verify_data = verify_resp.json()

        if verify_data.get("status") != "success" or verify_data.get("data", {}).get("status") != "success":
            logger.error(f"Payment verification failed for tx_ref: {tx_ref}")
            return JsonResponse({"success": False, "error": "Payment not successful"})

        amount = float(verify_data.get("data", {}).get("amount", 0))
        user = get_object_or_404(UserProfile, telegram_id=telegram_id)

        # Update user balance
        user.balance += amount
        user.save()

        # Update payment record
        payment.status = "success"
        payment.completed_at = timezone.now()
        payment.save()

        # Send Telegram notification
        try:
            bot = Bot(token=BOT_TOKEN)
            asyncio.run(bot.send_message(
                chat_id=telegram_id,
                text=(
                    f"✅ Deposit completed!\n\n"
                    f"Amount: {amount:.2f} ETB has been credited to your account.\n"
                    f"New balance: {user.balance:.2f} ETB."
                )
            ))
        except Exception as e:
            logger.error(f"Failed to send deposit notification: {e}")

        logger.info(f"Deposit successful: tx_ref={tx_ref}, amount={amount}, user={telegram_id}")
        return JsonResponse({"success": True, "message": f"Deposit of {amount} ETB completed."})

    except Exception as e:
        logger.error(f"Chapa callback error: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": "Internal server error"})