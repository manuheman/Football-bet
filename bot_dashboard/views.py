import json
import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from telegram import Bot
from django.utils import timezone
import requests

from .models import UserProfile, Game, Bet, BetSelection, ChapaPayment

logger = logging.getLogger(__name__)
BOT_TOKEN = "8661608966:AAFXphBOs9rgCzK9VJCrJtgPL_Vfe-M3cp0"
CHAPA_SECRET = "CHASECK-OtxJDfVcR7i3qTckDUbKFPK3ZIOLGjmA"



# ---------------- User Dashboard ----------------
# ---------------- User Dashboard ----------------


def user_detail(request, telegram_id):
    """
    Render the user dashboard with today's games and user profile.
    Filters games by selected country and league if provided.
    """
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)

    today = timezone.localdate()  # server-side date

    # Get country and league from GET parameters (dropdown selections)
    selected_country = request.GET.get('country', '').strip().lower()
    selected_league = request.GET.get('league', '').strip()

    # Base queryset: today's games that are not finished
    games = Game.objects.filter(game_datetime__date=today, finished=False)

    # Apply country filter if selected
    if selected_country:
        games = games.filter(country__iexact=selected_country)

    # Apply league filter if selected
    if selected_league:
        games = games.filter(league__iexact=selected_league)

    # Prepare games data for template
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
            "type": getattr(game, "type", ""),  # Optional field if exists
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
@csrf_exempt
def place_bet(request):
    """
    Handle AJAX request to place a bet:
    - Deduct from bonus first, then balance.
    - Validate odds and bet types.
    - Save Bet and BetSelection entries.
    """
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

    # Convert list to dict if needed
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

    # Create Bet entry
    bet_obj = Bet.objects.create(
        user=user,
        bet_amount=bet_amount,
        total_odds=total_odds,
        potential_win=potential_win
    )

    # Create BetSelection entries
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
    """
    Display bet history for a user and update bet statuses dynamically.
    Automatically credit user's balance if a bet is won (only once).
    Works with Telegram WebApp links (no login required).
    """
    if not telegram_id:
        return HttpResponse("Missing telegram_id", status=400)

    user_profile = get_object_or_404(UserProfile, telegram_id=telegram_id)
    user_bets = Bet.objects.filter(user=user_profile).order_by('-created_at')

    bets_with_selections = []

    for bet in user_bets:
        selections = BetSelection.objects.filter(bet=bet)
        sel_with_status = []

        for sel in selections:
            result = sel.is_correct()  # True, False, or None
            if result is True:
                match_status = 'Finished ✔'
            elif result is False:
                match_status = 'Finished ✖'
            else:
                match_status = 'Pending'

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


# ---------------- Chapa Payment Callback ----------------
@csrf_exempt
def chapa_callback(request):
    """
    Handles Chapa payment callbacks.
    """
    try:
        data = request.GET if request.method == "GET" else request.POST
        tx_ref = data.get("tx_ref") or data.get("trx_ref") or data.get("ref_id")
        status = data.get("status")
        amount = float(data.get("amount", 0))

        logger.info(f"[CHAPA CALLBACK] Received: {data}")

        if not tx_ref:
            logger.error("[CHAPA] Missing tx_ref in callback")
            return JsonResponse({"status": "error", "message": "Missing tx_ref"})

        payment = ChapaPayment.objects.filter(tx_ref=tx_ref, status="pending").first()
        if not payment:
            logger.error(f"[CHAPA] No unprocessed payment found for tx_ref: {tx_ref}")
            return JsonResponse({"status": "error", "message": "Payment not found or already processed"})

        telegram_id = payment.telegram_id

        if status != "success" or amount <= 0:
            logger.warning(f"[CHAPA] Payment failed or invalid: status={status}, amount={amount}")
            return JsonResponse({"status": "failed", "message": "Payment failed or invalid"})

        user = UserProfile.objects.filter(telegram_id=telegram_id).first()
        if not user:
            logger.error(f"[CHAPA] No user found with telegram_id: {telegram_id}")
            return JsonResponse({"status": "error", "message": "User not found"})

        old_balance = user.balance
        user.balance += amount
        user.save()
        logger.info(f"[CHAPA] Updated balance for {telegram_id}: +{amount} ETB (old={old_balance}, new={user.balance})")

        bot = Bot(token=BOT_TOKEN)
        try:
            bot.send_message(
                chat_id=telegram_id,
                text=(
                    f"✅ Deposit successful!\n"
                    f"💵 Old Balance: {old_balance} ETB\n"
                    f"💰 New Balance: {user.balance} ETB\n"
                    f"🔗 [Go to Dashboard](http://127.0.0.1:8000/users/telegram_id/{telegram_id}/)"
                ),
                parse_mode="Markdown"
            )
            logger.info(f"[CHAPA] Telegram message sent to {telegram_id}")
        except Exception as e:
            logger.error(f"[CHAPA] Failed to send Telegram message: {e}")

        payment.status = "success"
        payment.completed_at = timezone.now()
        payment.save()

        return JsonResponse({"status": "success", "message": "Balance updated and user notified"})

    except Exception as e:
        logger.error(f"[CHAPA CALLBACK ERROR]: {e}", exc_info=True)
        return JsonResponse({"status": "error", "message": str(e)})