import json
import asyncio
import hmac
import hashlib
import logging
import random
import os
from dotenv import load_dotenv
from decimal import Decimal
from django.views.decorators.http import require_POST, require_http_methods
import uuid
import requests  # Added missing import for requests library
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from django.utils import timezone

# Load environment variables
load_dotenv()

from datetime import datetime, timedelta
from bot_dashboard.models import UserProfile, Withdrawal, ChapaPayment, Jackpot, GuessGame, JackpotBet



logger = logging.getLogger(__name__)
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
PUBLIC_URL = os.environ.get('PUBLIC_URL')
CHAPA_SECRET_KEY = os.environ.get('CHAPA_SECRET_KEY')
# Admin IDs for notifications
ADMIN_IDS = [1351052276]

bot = Bot(token=BOT_TOKEN)
admin_bot = Bot(token=os.environ.get('ADMIN_BOT_TOKEN'))

# Chapa Deposite payment configuration

CHAPA_INIT_URL = os.environ.get('CHAPA_INIT_URL')
CHAPA_VERIFY_URL = os.environ.get('CHAPA_VERIFY_URL')
CALLBACK_URL = os.environ.get('CALLBACK_URL')


#chapa withdrawal set up
# Supported bank codes
BANK_CODES = {
    "telebirr": 855,
    "cbe": 946,
    "mpesa": 266
}


from datetime import datetime, timedelta
from django.utils import timezone
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from .models import UserProfile, Game, Jackpot, GuessGame, Bet, BetSelection, JackpotBet



def user_detail(request, telegram_id):
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)

    now = timezone.now()
    today = now.date()
    day_after_tomorrow = today + timedelta(days=2)

    start_datetime = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    end_datetime = timezone.make_aware(datetime.combine(day_after_tomorrow + timedelta(days=1), datetime.min.time()))

    # Only show games that have NOT started yet
    games = Game.objects.filter(
        game_datetime__gte=start_datetime,
        game_datetime__lt=end_datetime,
        game_datetime__gt=now   # 🔥 THIS removes games when match time passes
    ).order_by('game_datetime')

    # Get selected country and league
    selected_country = request.GET.get('country', '').strip()
    selected_league = request.GET.get('league', '').strip()

    # Filter by country
    if selected_country:
        games = games.filter(country__iexact=selected_country)

    # Dynamic leagues based on selected country
    if selected_country:
        leagues = Game.objects.filter(
            country__iexact=selected_country
        ).values_list('league', flat=True).distinct()
    else:
        leagues = Game.objects.values_list('league', flat=True).distinct()

    # Filter by league
    if selected_league:
        games = games.filter(league__iexact=selected_league)

    # Prepare game data
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
        "countries": Game.objects.values_list('country', flat=True).distinct(),
        "leagues": leagues
    }

    return render(request, "user_detail.html", context)



@csrf_exempt
def place_bet(request):

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request method"})

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid request data"})

    telegram_id = data.get("telegram_id")
    wallet_type = data.get("wallet_type", "balance")
    bet_amount = float(data.get("betAmount", 0))
    selected_bets = data.get("selectedBets", {})

    if not telegram_id:
        return JsonResponse({"success": False, "error": "User not specified"})

    try:
        user = UserProfile.objects.get(telegram_id=telegram_id)
    except UserProfile.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found"})

    if bet_amount <= 0:
        return JsonResponse({"success": False, "error": "Invalid bet amount"})

    if not selected_bets:
        return JsonResponse({"success": False, "error": "No games selected"})

    # convert list to dict if needed
    if isinstance(selected_bets, list):
        selected_bets = {str(b["gameId"]): b for b in selected_bets}

    # ---------------- Wallet validation ----------------

    if wallet_type == "balance":
        if user.balance < bet_amount:
            return JsonResponse({"success": False, "error": "Insufficient balance wallet funds"})

    elif wallet_type == "bonus":
        if user.bonus < bet_amount:
            return JsonResponse({"success": False, "error": "Insufficient bonus wallet funds"})

    else:
        return JsonResponse({"success": False, "error": "Invalid wallet selected"})

    # ---------------- Validate games ----------------

    valid_types = ["win1","draw","win2","double_1x","double_12","double_x2"]

    total_odds = 1
    selections_count = 0

    for game_id, bet_info in selected_bets.items():

        try:
            game = Game.objects.get(id=int(game_id))
        except Game.DoesNotExist:
            return JsonResponse({"success": False, "error": "Selected game not found"})

        bet_type = bet_info.get("betType")

        if bet_type not in valid_types:
            return JsonResponse({"success": False, "error": "Invalid bet type selected"})

        db_odds = getattr(game, bet_type)
        user_odds = float(bet_info.get("odds", 0))

        # odds changed protection
        if float(db_odds) != user_odds:
            return JsonResponse({
                "success": False,
                "error": f"Odds changed for {game.team1} vs {game.team2}"
            })

        # ---------------- Bonus rule 1 ----------------
        if wallet_type == "bonus" and user_odds < 1.7:
            return JsonResponse({
                "success": False,
                "error": f"Bonus bet requires each game odds ≥ 1.7 ({game.team1} vs {game.team2})"
            })

        total_odds *= user_odds
        selections_count += 1

    # ---------------- Bonus rule 2 ----------------
    if wallet_type == "bonus" and selections_count < 4:
        return JsonResponse({
            "success": False,
            "error": "Bonus bets require at least 4 games"
        })

    # ---------------- Bonus rule 3 ----------------
    if wallet_type == "bonus" and total_odds < 10:
        return JsonResponse({
            "success": False,
            "error": "Bonus bets require total odds ≥ 10"
        })

    potential_win = bet_amount * total_odds

    # ---------------- Deduct wallet ----------------

    if wallet_type == "balance":
        user.balance -= bet_amount
    else:
        user.bonus -= bet_amount

    user.save()

    # ---------------- Create bet ----------------

    bet = Bet.objects.create(
        user=user,
        bet_amount=bet_amount,
        total_odds=total_odds,
        potential_win=potential_win,
        wallet_used=wallet_type
    )

    # ---------------- Save selections ----------------

    for game_id, bet_info in selected_bets.items():

        game = Game.objects.get(id=int(game_id))

        BetSelection.objects.create(
            bet=bet,
            game=game,
            bet_type=bet_info["betType"],
            odds=bet_info["odds"],
            match_info=bet_info.get(
                "gameName",
                f"{game.team1} vs {game.team2}"
            )
        )

    logger.info(f"BET PLACED | user={telegram_id} | ticket={bet.ticket_id} | wallet={wallet_type}")

    return JsonResponse({
        "success": True,
        "ticket_id": bet.ticket_id,
        "potential_win": potential_win,
        "new_balance": user.balance,
        "new_bonus": user.bonus
    })

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
        tx_ref = f"weview_{uuid.uuid4().hex}"  # Generate tx_ref here for consistency
        payload = {
            "amount": str(amount),
            "currency": "ETB",
            "email": "noreply@weview.com",
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": phone_number,
            "tx_ref": tx_ref,
            "callback_url": CALLBACK_URL,
            "meta": {"telegram_id": telegram_id},
            "customization": {
                "title": "weview Deposit",
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
    We'll verify the transaction, update user's balance, give first deposit bonus, 
    and notify via Telegram.
    """
    try:
        # Accept both POST and GET payloads
        if request.method == "POST":
            data = json.loads(request.body)
            tx_ref = data.get("tx_ref") or data.get("trx_ref")
            telegram_id = data.get("meta", {}).get("telegram_id") or data.get("telegram_id")
        else:
            data = request.GET
            tx_ref = data.get("trx_ref") or data.get("tx_ref")
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

        # ---------------- First Deposit Bonus ----------------
        # Fetch count of previous successful deposits
        previous_deposits_count = ChapaPayment.objects.filter(
            telegram_id=telegram_id,
            status="success"
        ).exclude(tx_ref=tx_ref).count()

        bonus_amount = 0
        if previous_deposits_count == 0:
            bonus_amount = amount  # 100% bonus
            user.bonus += bonus_amount

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
                    f"Deposit: {amount:.2f} ETB\n"
                    f"Bonus: {bonus_amount:.2f} ETB\n\n"
                    f"Balance: {user.balance:.2f} ETB\n"
                    f"Bonus Balance: {user.bonus:.2f} ETB"
                )
            ))
            if bonus_amount > 0:
                asyncio.run(bot.send_message(
                    chat_id=telegram_id,
                    text="🎉 Congratulations! You received a 100% First Deposit Bonus!"
                ))
        except Exception as e:
            logger.error(f"Failed to send deposit notification: {e}")

        logger.info(f"Deposit successful: tx_ref={tx_ref}, amount={amount}, bonus={bonus_amount}, user={telegram_id}")
        return JsonResponse({"success": True, "message": f"Deposit of {amount} ETB completed, bonus {bonus_amount} ETB applied."})

    except Exception as e:
        logger.error(f"Chapa callback error: {e}", exc_info=True)
        return JsonResponse({"success": False, "error": "Internal server error"})



# bot_dashboard/views.py

from django.http import JsonResponse
from .models import Bet, BetSelection

def search_ticket(request, ticket_id):
    """
    Search for a ticket and return all bet selections under it.
    """
    try:
        # Get the Bet object by ticket ID
        bet = Bet.objects.filter(ticket_id=ticket_id).first()
        if not bet:
            return JsonResponse({"success": False, "error": "No bets found for this ticket ID."})

        # Get all selections for this bet
        selections = BetSelection.objects.filter(bet=bet)
        if not selections.exists():
            return JsonResponse({"success": False, "error": "No valid bet selections found for this ticket."})

        # Prepare JSON response
        bet_data = []
        for s in selections:
            bet_data.append({
                "game_id": s.game.id,
                "game_name": f"{s.game.team1} vs {s.game.team2}",
                "bet_type": s.bet_type,
                "odds": s.odds
            })

        return JsonResponse({"success": True, "ticket_id": bet.ticket_id, "bets": bet_data})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})
    bets = Bet.objects.filter(ticket_id=ticket_id)

    if not bets.exists():
        return JsonResponse({"success": False, "error": "No bets found for this ticket ID."})

    bet_list = []
    for b in bets:
        # Adjust depending on your model fields
        game = getattr(b, 'game', None) or getattr(getattr(b, 'selection', None), 'game', None)
        if not game:
            continue  # skip if we can't find the game
        bet_list.append({
            "game_id": game.id,
            "game_name": f"{game.team1} vs {game.team2}",
            "bet_type": b.bet_type,
            "odds": str(b.odds)
        })

    if not bet_list:
        return JsonResponse({"success": False, "error": "No valid bets found for this ticket ID."})

    return JsonResponse({"success": True, "bets": bet_list})
    # Get bets under ticket
    bets = Bet.objects.filter(ticket_id=ticket_id)

    if not bets.exists():
        return JsonResponse({"success": False, "error": "No bets found for this ticket ID."})

    bet_list = []
    for b in bets:
        bet_list.append({
            "game_id": b.game.id,
            "game_name": f"{b.game.team1} vs {b.game.team2}",
            "bet_type": b.bet_type,
            "odds": str(b.odds)
        })

    return JsonResponse({"success": True, "bets": bet_list})






import uuid
@csrf_exempt
def initiate_transfer(request):
    logger.info("Initiate transfer request received.")

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid method"}, status=400)

    # Parse JSON body safely
    try:
        import json
        data = json.loads(request.body.decode())
    except Exception as e:
        logger.error("Failed to parse JSON body: %s", e, exc_info=True)
        return JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)

    telegram_id = data.get("telegram_id")
    amount = data.get("amount")
    full_name = data.get("full_name")
    phone_number = data.get("phone_number")
    method = data.get("method", "").lower()

    logger.info(
        "Request data: telegram_id=%s, amount=%s, full_name=%s, phone_number=%s, method=%s",
        telegram_id, amount, full_name, phone_number, method
    )

    # Validate input
    if not all([telegram_id, amount, full_name, phone_number, method]):
        return JsonResponse({"success": False, "error": "Missing parameters"}, status=400)

    if method not in BANK_CODES:
        return JsonResponse({"success": False, "error": f"Unsupported method: {method}"}, status=400)

    # Get user
    try:
        user = UserProfile.objects.get(telegram_id=telegram_id)
    except UserProfile.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found"}, status=404)

    try:
        amount = float(amount)
    except ValueError:
        return JsonResponse({"success": False, "error": "Invalid amount"}, status=400)

    if amount > user.balance:
        return JsonResponse({"success": False, "error": "Insufficient balance"}, status=400)

    # Deduct balance and hold
    user.balance -= amount
    user.hold_balance = getattr(user, "hold_balance", 0) + amount
    user.save()
    logger.info("User balance updated: balance=%s, hold_balance=%s", user.balance, user.hold_balance)

    # Prepare Chapa transfer payload
    reference = str(uuid.uuid4())
    payload = {
        "account_name": full_name,
        "account_number": phone_number,
        "amount": amount,
        "currency": "ETB",
        "reference": reference,
        "bank_code": BANK_CODES[method]
    }

    headers = {
        "Authorization": f"Bearer {CHAPA_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post("https://api.chapa.co/v1/transfers", json=payload, headers=headers, timeout=20)
        try:
            result = resp.json()
        except ValueError:
            # Rollback balance
            user.balance += amount
            user.hold_balance -= amount
            user.save()
            return JsonResponse({"success": False, "error": "Invalid response from Chapa API"}, status=500)

        logger.info("Chapa response: status_code=%s, response=%s", resp.status_code, result)

    except requests.RequestException as e:
        # Rollback balance
        user.balance += amount
        user.hold_balance -= amount
        user.save()
        return JsonResponse({"success": False, "error": "Failed to contact Chapa API"}, status=500)

    # Save withdrawal record
    withdrawal = Withdrawal.objects.create(
        user=user,
        telegram_id=telegram_id,
        amount=amount,
        method=method,
        phone_number=phone_number,
        full_name=full_name,
        reference=reference,
        status="pending"
    )
    logger.info("Withdrawal record created: withdraw_id=%s", withdrawal.withdraw_id)

    # Return success if Chapa API is OK
    if resp.status_code == 200 and result.get("status") in ["success", "pending"]:
        return JsonResponse({"success": True, "message": "Transfer initiated, amount on hold", "data": result})
    else:
        # Rollback balance
        user.balance += amount
        user.hold_balance -= amount
        user.save()
        return JsonResponse({"success": False, "error": result.get("message", "Transfer failed")}, status=400)   
        



#bingo game views


import random
import uuid
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from .models import UserProfile, BingoCardTemplate, BingoNumberPick, BingoGame, BingoParticipant
# ---------------- Helper to generate new game id ----------------
def generate_game_id():
    return uuid.uuid4().hex[:12]

# ---------------- Bingo Home View ----------------
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from .models import UserProfile, BingoCardTemplate, BingoGame, BingoParticipant
import uuid


# ---------------- Helper to generate new game id ----------------
def generate_game_id():
    return uuid.uuid4().hex[:12]

# ---------------- Helper: finalize bingo game ----------------
def finalize_bingo_game(game):
    """Pick a random winner, generate 20 drawn numbers, and save the game.

    Ensures only the selected winner has at least one completed line (row/col/diag)
    and prevents other participants from completing a line if possible.
    """
    if game.winner is not None:
        return None

    participants = list(BingoParticipant.objects.filter(game=game))
    if not participants:
        print(f"[WARN] Bingo game {game.game_id} has no participants to select a winner.")
        return None

    # Prefer participants who selected a number
    selectable = [p for p in participants if p.clicked_number is not None and p.card_numbers]
    if not selectable:
        selectable = [p for p in participants if p.card_numbers]
    if not selectable:
        # Fallback: pick any participant
        selectable = participants

    winner = random.choice(selectable)

    def get_bingo_lines(card_numbers):
        # card_numbers holds the 24 numbers excluding the center free space
        grid = [[None] * 5 for _ in range(5)]
        idx = 0
        for r in range(5):
            for c in range(5):
                if r == 2 and c == 2:
                    grid[r][c] = None  # free center
                else:
                    grid[r][c] = card_numbers[idx]
                    idx += 1

        def line_numbers(coords):
            return {grid[r][c] for (r, c) in coords if not (r == 2 and c == 2)}

        lines = []
        for r in range(5):
            lines.append(line_numbers([(r, c) for c in range(5)]))
        for c in range(5):
            lines.append(line_numbers([(r, c) for r in range(5)]))
        lines.append(line_numbers([(i, i) for i in range(5)]))
        lines.append(line_numbers([(i, 4 - i) for i in range(5)]))
        return lines

    winner_lines = get_bingo_lines(winner.card_numbers) if winner.card_numbers else []
    winning_line = random.choice(winner_lines) if winner_lines else set(random.sample(range(1, 81), 5))

    drawn_numbers = set(winning_line)

    other_participants = [p for p in participants if p.id != winner.id and p.card_numbers]
    other_lines = []
    for p in other_participants:
        other_lines.extend(get_bingo_lines(p.card_numbers))

    candidates = [n for n in range(1, 76) if n not in drawn_numbers]
    attempts = 0
    while len(drawn_numbers) < 20 and attempts < 5000 and candidates:
        attempts += 1
        pick = random.choice(candidates)
        new_drawn = set(drawn_numbers) | {pick}
        other_complete = any(line.issubset(new_drawn) for line in other_lines)
        if other_complete:
            candidates.remove(pick)
            continue
        drawn_numbers = new_drawn
        candidates.remove(pick)

    if len(drawn_numbers) < 20:
        extra = random.sample([n for n in range(1, 81) if n not in drawn_numbers], 20 - len(drawn_numbers))
        drawn_numbers.update(extra)

    # Shuffle the drawn numbers to make the reveal order random
    drawn_numbers = list(drawn_numbers)
    random.shuffle(drawn_numbers)

    # Payout winner by 80% of the pot from players who picked a number
    selected_players_count = sum(1 for p in participants if p.clicked_number is not None)
    total_pot = selected_players_count * 10
    payout = total_pot * 0.8
    winner.user.balance += payout
    winner.user.save()

    game.drawn_numbers = drawn_numbers
    game.winner = winner.user
    game.save()

    # Deep logging to console
    print("\n[DEEP LOG] ================================")
    print(f"[DEEP LOG] Game ID: {game.game_id}")
    print(f"[DEEP LOG] Winner: {winner.user.first_name} {winner.user.last_name} (Telegram ID: {winner.user.telegram_id})")
    print(f"[DEEP LOG] Winner's clicked number: {winner.clicked_number}")
    print(f"[DEEP LOG] Winner card numbers: {winner.card_numbers}")
    print(f"[DEEP LOG] Drawn numbers (20 total): {drawn_numbers}")
    print("[DEEP LOG] ================================\n")

    return winner










##dama views
import json
import time
try:
    from .redis_config import redis_client
    redis_available = True
except ImportError:
    redis_client = None
    redis_available = False
from .models import DamaGame

# ---------------- Dama Home View ----------------


def dama_home(request, telegram_id):
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)
    rooms = []

    if redis_available:
        try:
            # Fetch waiting games from Redis
            waiting_games = redis_client.lrange('waiting_games', 0, 49)  # up to 50
            if waiting_games:
                pipe = redis_client.pipeline()
                for game_id in waiting_games:
                    pipe.hgetall(f'game:{game_id}')
                game_states = pipe.execute()

                for game_id, game_state in zip(waiting_games, game_states):
                    if game_state and game_state.get('status') == 'waiting':
                        rooms.append({
                            'game_id': game_id,
                            'creator': game_state.get('player1_username', 'Unknown'),
                            'bet': float(game_state.get('bet_amount', 0)),
                            'status': game_state.get('status'),
                            'url': f'/dama/{telegram_id}/game_id/{game_id}/'  # Link to game page
                        })

            # Fallback to DB if no Redis data
            if not rooms:
                db_rooms = DamaGame.objects.filter(status='waiting').only('game_id', 'player1', 'bet_amount', 'status')[:50]
                for room in db_rooms:
                    rooms.append({
                        'game_id': room.game_id,
                        'creator': f'{room.player1.first_name} {room.player1.last_name}',
                        'bet': room.bet_amount,
                        'status': room.status,
                        'url': f'/dama/{telegram_id}/game_id/{room.game_id}/'  # Link to game page
                    })

        except Exception as e:
            # Fallback to DB when Redis fails
            db_rooms = DamaGame.objects.filter(status='waiting').only('game_id', 'player1', 'bet_amount', 'status')[:50]
            for room in db_rooms:
                rooms.append({
                    'game_id': room.game_id,
                    'creator': f'{room.player1.first_name} {room.player1.last_name}',
                    'bet': room.bet_amount,
                    'status': room.status,
                    'url': f'/dama/{telegram_id}/game_id/{room.game_id}/'
                })
    else:
        # No Redis, fallback to DB
        db_rooms = DamaGame.objects.filter(status='waiting').only('game_id', 'player1', 'bet_amount', 'status')[:50]
        for room in db_rooms:
            rooms.append({
                'game_id': room.game_id,
                'creator': f'{room.player1.first_name} {room.player1.last_name}',
                'bet': room.bet_amount,
                'status': room.status,
                'url': f'/dama/{telegram_id}/game_id/{room.game_id}/'
            })

    return render(request, 'dama_home.html', {'user': user, 'rooms': rooms})

# ---------------- Create Dama Room ----------------

def create_dama_room(request, telegram_id):
    if request.method == 'POST':
        user = get_object_or_404(UserProfile, telegram_id=telegram_id)
        bet_amount = float(request.POST.get('bet_amount', 0))

        # Validate bet
        if bet_amount <= 0 or bet_amount > user.balance:
            # Optionally add a message here
            return redirect('dama_home', telegram_id=telegram_id)

        # Create a unique game ID
        game_id = str(uuid.uuid4().hex[:12])

        # Create game in DB
        game = DamaGame.objects.create(
            game_id=game_id,
            player1=user,
            bet_amount=bet_amount,
            status='waiting',
            board=[]  # initial empty board
        )

        # Store game in Redis (avoid None values, Redis needs scalar types)
        game_state = {
            'player1': str(user.telegram_id),
            'player1_username': f'{user.first_name} {user.last_name}',
            'player2': '',  # empty string instead of None
            'player2_username': '',
            'board': json.dumps([]),
            'status': 'waiting',
            'bet_amount': str(bet_amount),
            'last_update': str(timezone.now())
        }
        redis_client.hmset(f'game:{game_id}', game_state)
        redis_client.lpush('waiting_games', game_id)

        # Redirect to game page
        return redirect(f'/dama/{telegram_id}/game_id/{game_id}/')

    return redirect('dama_home', telegram_id=telegram_id)

# ---------------- Dama Game Page ----------------
def dama_game(request, telegram_id, game_id):
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)
    game = get_object_or_404(DamaGame, game_id=game_id)

    # ensure user can view
    is_participant = (game.player1 == user or game.player2 == user)

    if game.status == 'waiting':
        status_message = 'Waiting for opponent...'
    elif game.status == 'playing':
        status_message = 'Game in progress'
    elif game.status == 'finished':
        status_message = 'Game finished'
    else:
        status_message = 'Unknown status'

    return render(request, 'dama_game.html', {
        'user': user,
        'game': game,
        'is_participant': is_participant,
        'status_message': status_message,
        'waiting': game.status == 'waiting'
    })


# ---------------- Join Dama Room ----------------
def join_dama_room(request, telegram_id, game_id):
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)
    try:
        game_state = redis_client.hgetall(f'game:{game_id}')
        if game_state and game_state['status'] == 'waiting':
            bet_amount = float(game_state['bet_amount'])
            if bet_amount > user.balance:
                return redirect('dama_home', telegram_id=telegram_id)

            # Update DB
            game = DamaGame.objects.get(game_id=game_id)
            game.player2 = user
            game.status = 'playing'
            game.save()

            # Update Redis
            game_state['player2'] = str(user.telegram_id)
            game_state['player2_username'] = user.first_name + ' ' + user.last_name
            game_state['status'] = 'playing'
            game_state['last_update'] = str(timezone.now())
            redis_client.hmset(f'game:{game_id}', game_state)
            redis_client.lrem('waiting_games', 0, game_id)

            return redirect('dama_game', telegram_id=telegram_id, game_id=game_id)
    except:
        pass
    return redirect('dama_home', telegram_id=telegram_id)



##bingo views
# ---------------- Bingo Home View ----------------
def bingo_home(request, telegram_id):
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)
    clicked_number = request.GET.get('clicked')
    clicked_number = int(clicked_number) if clicked_number else None
    success_message = request.GET.get('success')

    # ---------------- Balance check ----------------
    if user.balance < 10:
        return render(request, 'bingo_home.html', {
            'user_profile': user,
            'bingo_grid': [],
            'bingo_numbers_range': range(1, 81),
            'clicked_number': None,
            'picked_numbers': {},
            'game_id': None,
            'remaining_time': 0,
            'error_message': 'Insufficient balance. You need at least 10 ETB to play. Please deposit first.',
        })

    # ---------------- Get or create game ----------------
    ongoing_game = BingoGame.objects.filter(winner__isnull=True).order_by('-created_at').first()
    if not ongoing_game:
        ongoing_game = BingoGame.objects.create(
            game_id=generate_game_id(),
            timer_start=timezone.now()
        )

    if not ongoing_game.timer_start:
        ongoing_game.timer_start = timezone.now()
        ongoing_game.save()

    # ---------------- Timer ----------------
    now = timezone.now()
    elapsed = (now - ongoing_game.timer_start).total_seconds()
    remaining_time = max(int(ongoing_game.timer_seconds - elapsed), 0)

    # ---------------- Participant ----------------
    participant, _ = BingoParticipant.objects.get_or_create(
        game=ongoing_game,
        user=user,
        defaults={'clicked_number': None, 'card_numbers': []}
    )

    # ---------------- Finalize game ----------------
    if remaining_time == 0 and ongoing_game.winner is None:
        finalize_bingo_game(ongoing_game)
        card_number = participant.clicked_number if participant.clicked_number else 0
        return redirect('bingo_result', telegram_id=telegram_id,
                        game_id=ongoing_game.game_id,
                        card_number=card_number)

    # ---------------- Reset game if finished ----------------
    if ongoing_game.winner is not None:
        new_game = BingoGame.objects.create(
            game_id=generate_game_id(),
            timer_seconds=90
        )

        participants = BingoParticipant.objects.filter(game=ongoing_game)
        for p in participants:
            BingoParticipant.objects.create(
                game=new_game,
                user=p.user,
                clicked_number=None,
                card_numbers=[]
            )

        participants.delete()
        ongoing_game.delete()

        return redirect('bingo_home', telegram_id=telegram_id)

    # ---------------- Handle selection ----------------
    if clicked_number is not None:
        is_first_selection = participant.clicked_number is None

        if is_first_selection and user.balance < 10:
            return render(request, 'bingo_home.html', {
                'user_profile': user,
                'bingo_grid': [],
                'bingo_numbers_range': range(1, 81),
                'clicked_number': None,
                'picked_numbers': {},
                'game_id': ongoing_game.game_id,
                'remaining_time': remaining_time,
                'error_message': 'Insufficient balance.',
            })

        already_taken = BingoParticipant.objects.filter(
            game=ongoing_game,
            clicked_number=clicked_number
        ).exclude(user=user).exists()

        if not already_taken:
            participant.clicked_number = clicked_number

            template = BingoCardTemplate.objects.filter(number=clicked_number).first()
            if not template:
                import random
                b = random.sample(range(1, 17), 5)
                i = random.sample(range(17, 33), 5)
                n = random.sample(range(33, 49), 4)
                g = random.sample(range(49, 65), 5)
                o = random.sample(range(65, 81), 5)

                auto_card_numbers = b + i + n + g + o
                template = BingoCardTemplate.objects.create(
                    number=clicked_number,
                    card_numbers=auto_card_numbers
                )

            participant.card_numbers = template.card_numbers
            participant.save()

            if is_first_selection:
                user.balance -= 10
                user.save()

            return redirect(f'/bingo/{telegram_id}/?success=Card selected successfully!')

    # ================= ✅ FIXED GRID HERE =================
    bingo_grid = []

    if participant.card_numbers:
        numbers = participant.card_numbers

        b = numbers[0:5]
        i = numbers[5:10]
        n = numbers[10:14]
        g = numbers[14:19]
        o = numbers[19:24]

        n.insert(2, '★')  # center free

        for row in range(5):
            bingo_grid.append([
                b[row],
                i[row],
                n[row],
                g[row],
                o[row],
            ])

    # ---------------- Picked numbers ----------------
    participants = BingoParticipant.objects.filter(game=ongoing_game)
    picked_participants = participants.filter(clicked_number__isnull=False)
    picked_numbers = {p.clicked_number: p.user.telegram_id for p in picked_participants}

    # ---------------- Winning calc ----------------
    player_count = picked_participants.count()
    total_pot = player_count * 10
    possible_winning = total_pot * 0.8

    # ---------------- Render ----------------
    return render(request, 'bingo_home.html', {
        'user_profile': user,
        'bingo_grid': bingo_grid,
        'bingo_numbers_range': range(1, 81),
        'clicked_number': participant.clicked_number,
        'picked_numbers': picked_numbers,
        'game_id': ongoing_game.game_id,
        'remaining_time': remaining_time,
        'success_message': success_message,
        'possible_winning': possible_winning,
        'player_count': player_count,
    })


from math import floor
from django.utils import timezone

def bingo_result(request, telegram_id, game_id, card_number):
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)
    game = get_object_or_404(BingoGame, game_id=game_id)
    drawn_numbers = game.drawn_numbers or []

    # Server-side reveal timing (sync across clients)
    reveal_interval = 3  # seconds per number
    reveal_start_time_ms = None
    server_now_ms = timezone.now().timestamp() * 1000

    if game.timer_start:
        reveal_start = game.timer_start + timedelta(seconds=game.timer_seconds)
        reveal_start_time_ms = reveal_start.timestamp() * 1000

        elapsed = (timezone.now() - reveal_start).total_seconds()
        if elapsed < 0:
            current_index = -1
        else:
            current_index = min(floor(elapsed / reveal_interval), len(drawn_numbers) - 1)
    else:
        current_index = -1

    participant = BingoParticipant.objects.filter(game=game, user=user, clicked_number=card_number).first()

    # Winner info (for overlay notification)
    winner_card_number = None
    winner_name = None
    if game.winner:
        winner_name = f"{game.winner.first_name} {game.winner.last_name}"
        winner_participant = BingoParticipant.objects.filter(game=game, user=game.winner).first()
        winner_card_number = winner_participant.clicked_number if winner_participant else None

    # Build user's card grid
    bingo_grid = []
    if participant and participant.card_numbers:
        numbers = participant.card_numbers.copy()
        idx = 0
        for row in range(5):
            row_list = []
            for col in range(5):
                if row == 2 and col == 2:
                    row_list.append('★')  # center free
                else:
                    row_list.append(numbers[idx])
                    idx += 1
            bingo_grid.append(row_list)
        
        # Transpose to make it column-major for BINGO structure
        bingo_grid = [list(row) for row in zip(*bingo_grid)]

    return render(request, 'bingo_result.html', {
        'user_profile': user,
        'game': game,
        'card_number': card_number,
        'drawn_numbers': drawn_numbers,
        'bingo_grid': bingo_grid,
        'numbers_range': range(1, 81),
        'current_index': current_index,
        'reveal_interval': reveal_interval,
        'reveal_start_time_ms': reveal_start_time_ms,
        'server_now_ms': server_now_ms,
        'winner_card_number': winner_card_number,
        'winner_name': winner_name,
        'is_user_winner': game.winner == user,
    })
# ---------------- Live Status View ----------------
def bingo_history(request, telegram_id):
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)
    
    # Get last 10 completed games (ALL games)
    past_games = BingoGame.objects.filter(winner__isnull=False).order_by('-created_at')[:10]
    
    game_history_by_date = []
    games_by_date = {}

    for game in past_games:
        drawn_numbers_list = game.drawn_numbers or []

        # Calculate total win (80% of pot) - need participants count for that game
        participants = BingoParticipant.objects.filter(game=game)
        selected_players_count = participants.filter(clicked_number__isnull=False).count()
        total_pot = selected_players_count * 10  # 10 ETB per player
        total_win = total_pot * 0.8  # 80% payout to winner

        winner_name = f"{game.winner.first_name} {game.winner.last_name} ({game.winner.telegram_id})" if game.winner else "No winner"

        game_entry = {
            'game_id': game.game_id,
            'drawn_numbers_list': drawn_numbers_list,
            'winner_name': winner_name,
            'total_win': round(total_win, 2),
            'player_count': selected_players_count,
            'created_at': game.created_at,
        }

        date_key = game.created_at.date()
        games_by_date.setdefault(date_key, []).append(game_entry)

    for date_key, games in games_by_date.items():
        game_history_by_date.append({
            'date': date_key,
            'games': games,
        })

    return render(request, 'bingo_history.html', {
        'user_profile': user,
        'game_history_grouped': game_history_by_date,
    })


def bingo_live_status(request, telegram_id):
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)
    ongoing_game = BingoGame.objects.filter(winner__isnull=True).order_by('-created_at').first()

    if not ongoing_game:
        return JsonResponse({'picked_numbers': {}, 'user_card': [], 'remaining_time': 0})

    # Calculate remaining time
    now = timezone.now()
    if ongoing_game.timer_start:
        elapsed = (now - ongoing_game.timer_start).total_seconds()
        remaining_time = max(int(ongoing_game.timer_seconds - elapsed), 0)
    else:
        remaining_time = ongoing_game.timer_seconds

    participant = BingoParticipant.objects.filter(game=ongoing_game, user=user).first()

    # If timer reached zero, finalize and redirect everyone to results
    redirect_url = None
    if remaining_time == 0 and ongoing_game.winner is None:
        finalize_bingo_game(ongoing_game)
        card_number = participant.clicked_number if participant and participant.clicked_number else 0
        redirect_url = f"/bingo/{telegram_id}/result/{ongoing_game.game_id}/{card_number}/"

    # Build 5x5 grid with center star
    card_grid = []
    flat_card = []
    if participant:
        numbers = participant.card_numbers.copy()
        idx = 0
        for row in range(5):
            row_list = []
            for col in range(5):
                if row == 2 and col == 2:
                    row_list.append('★')
                else:
                    # Guard against malformed/short templates
                    if idx < len(numbers):
                        row_list.append(numbers[idx])
                    else:
                        row_list.append('')
                    idx += 1
            card_grid.append(row_list)
        flat_card = [num for row in card_grid for num in row]

    # Build picked numbers only for users who selected a card number
    picked_participants = BingoParticipant.objects.filter(game=ongoing_game, clicked_number__isnull=False)
    picked_numbers = {p.clicked_number: p.user.telegram_id for p in picked_participants}

    # Calculate possible winning (only selected numbers count)
    player_count = picked_participants.count()
    total_pot = player_count * 10  # 10 ETB per player
    possible_winning = total_pot * 0.8  # 20% commission

    return JsonResponse({
        'picked_numbers': picked_numbers,
        'user_card': flat_card,
        'drawn_numbers': ongoing_game.drawn_numbers or [],
        'remaining_time': remaining_time,
        'redirect_url': redirect_url,
        'user_balance': user.balance,
        'possible_winning': possible_winning,
        'player_count': player_count,
    })



#withdrawal views






import uuid
@csrf_exempt
def initiate_transfer(request):
    logger.info("Initiate transfer request received.")

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid method"}, status=400)

    # Parse JSON body safely
    try:
        import json
        data = json.loads(request.body.decode())
    except Exception as e:
        logger.error("Failed to parse JSON body: %s", e, exc_info=True)
        return JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)

    telegram_id = data.get("telegram_id")
    amount = data.get("amount")
    full_name = data.get("full_name")
    phone_number = data.get("phone_number")
    method = data.get("method", "").lower()

    logger.info(
        "Request data: telegram_id=%s, amount=%s, full_name=%s, phone_number=%s, method=%s",
        telegram_id, amount, full_name, phone_number, method
    )

    # Validate input
    if not all([telegram_id, amount, full_name, phone_number, method]):
        return JsonResponse({"success": False, "error": "Missing parameters"}, status=400)

    if method not in BANK_CODES:
        return JsonResponse({"success": False, "error": f"Unsupported method: {method}"}, status=400)

    # Get user
    try:
        user = UserProfile.objects.get(telegram_id=telegram_id)
    except UserProfile.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found"}, status=404)

    try:
        amount = float(amount)
    except ValueError:
        return JsonResponse({"success": False, "error": "Invalid amount"}, status=400)

    if amount > user.balance:
        return JsonResponse({"success": False, "error": "Insufficient balance"}, status=400)

    # Deduct balance and hold
    user.balance -= amount
    user.hold_balance = getattr(user, "hold_balance", 0) + amount
    user.save()
    logger.info("User balance updated: balance=%s, hold_balance=%s", user.balance, user.hold_balance)

    # Prepare Chapa transfer payload
    reference = str(uuid.uuid4())
    payload = {
        "account_name": full_name,
        "account_number": phone_number,
        "amount": amount,
        "currency": "ETB",
        "reference": reference,
        "bank_code": BANK_CODES[method]
    }

    headers = {
        "Authorization": f"Bearer {CHAPA_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post("https://api.chapa.co/v1/transfers", json=payload, headers=headers, timeout=20)
        try:
            result = resp.json()
        except ValueError:
            # Rollback balance
            user.balance += amount
            user.hold_balance -= amount
            user.save()
            return JsonResponse({"success": False, "error": "Invalid response from Chapa API"}, status=500)

        logger.info("Chapa response: status_code=%s, response=%s", resp.status_code, result)

    except requests.RequestException as e:
        # Rollback balance
        user.balance += amount
        user.hold_balance -= amount
        user.save()
        return JsonResponse({"success": False, "error": "Failed to contact Chapa API"}, status=500)

    # Save withdrawal record
    withdrawal = Withdrawal.objects.create(
        user=user,
        telegram_id=telegram_id,
        amount=amount,
        method=method,
        phone_number=phone_number,
        full_name=full_name,
        reference=reference,
        status="pending"
    )
    logger.info("Withdrawal record created: withdraw_id=%s", withdrawal.withdraw_id)

    # Return success if Chapa API is OK
    if resp.status_code == 200 and result.get("status") in ["success", "pending"]:
        return JsonResponse({"success": True, "message": "Transfer initiated, amount on hold", "data": result})
    else:
        # Rollback balance
        user.balance += amount
        user.hold_balance -= amount
        user.save()
        return JsonResponse({"success": False, "error": result.get("message", "Transfer failed")}, status=400)   
        





# bot_dashboard/views.py
import json
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt

DEBUG = True  # Keep debug logging for testing
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
import json
import logging
from asgiref.sync import async_to_sync
from .utils import verify_chapa_transfer_and_alert

logger = logging.getLogger(__name__)
DEBUG = True
# ------------------ Configuration ------------------
@csrf_exempt
def transfer_approve(request):
    """
    Chapa webhook endpoint: verifies transfer and alerts the user via Telegram.
    Logs everything: headers, payload, raw body, IP.
    """
    if request.method != "POST":
        logger.warning(f"[transfer/approve] Method not allowed: {request.method}")
        return HttpResponse(status=405)

    try:
        # ---------------- Get client IP ----------------
        ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", ""))
        ip = ip.split(",")[0].strip()  # Take first IP if multiple
        logger.info(f"[transfer/approve] Incoming request from IP: {ip}")

        # ---------------- Log headers ----------------
        headers = {k: v for k, v in request.headers.items()}
        logger.info(f"[transfer/approve] Request headers:\n{json.dumps(headers, indent=2)}")

        # ---------------- Log raw body ----------------
        raw_body = request.body
        logger.info(f"[transfer/approve] Raw body bytes: {raw_body}")
        logger.info(f"[transfer/approve] Raw body hex: {raw_body.hex()}")

        # ---------------- Parse JSON payload ----------------
        try:
            payload = json.loads(raw_body.decode("utf-8"))
            logger.info(f"[transfer/approve] Parsed payload:\n{json.dumps(payload, indent=2)}")
        except Exception as e:
            logger.error(f"[transfer/approve] JSON parse error: {str(e)}")
            return JsonResponse({"status": "failed", "message": "Invalid JSON payload"}, status=400)

        # ---------------- Log payload fields ----------------
        if isinstance(payload, dict):
            for k, v in payload.items():
                logger.info(f"[transfer/approve] Field '{k}': type={type(v)}, value={v}")

        # ---------------- Extract key fields ----------------
        reference = payload.get("reference")
        if not reference:
            logger.error("[transfer/approve] Missing 'reference' in payload")
            return JsonResponse({"status": "failed", "message": "Missing reference"}, status=400)

        # ---------------- Fetch withdrawal ----------------
        try:
            withdrawal = Withdrawal.objects.get(reference=reference)
            telegram_id = withdrawal.telegram_id
        except Withdrawal.DoesNotExist:
            logger.error(f"[transfer/approve] Withdrawal not found for reference: {reference}")
            return JsonResponse({"status": "failed", "message": "Withdrawal not found"}, status=404)

        # ---------------- Call Verification Function ----------------
        logger.info(f"[transfer/approve] Calling verify_chapa_transfer_and_alert for reference: {reference}")
        async_to_sync(verify_chapa_transfer_and_alert)(reference, telegram_id)
        logger.info(f"[transfer/approve] Verification task completed for reference: {reference}")

        return JsonResponse({"status": "success", "message": "verification started"})

    except Exception as e:
        logger.exception(f"[transfer/approve] Exception occurred: {str(e)}")
        return HttpResponse("error", status=500)







#jackpot views

def guess_home(request, telegram_id):
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)

    submitted_key = f"guess_submitted_{telegram_id}"
    submitted = False
    profile_updated = False

    if request.method == "POST":
        if 'update_profile' in request.POST:
            # Handle profile update
            user.bio = request.POST.get('bio', '')
            user.favorite_club = request.POST.get('favorite_club', '')
            user.save()
            profile_updated = True
        else:
            # Handle guess submission
            submitted = True
            request.session[submitted_key] = True

    if request.session.get(submitted_key):
        submitted = True

    matches = list(Game.objects.filter(finished=False).order_by('game_datetime')[:10])

    # Update bet statuses for regular bets
    user_bets = Bet.objects.filter(user=user)
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

    # Calculate stats including jackpot bets
    total_bets = Bet.objects.filter(user=user).count() + JackpotBet.objects.filter(user=user).count()
    total_won = Bet.objects.filter(user=user, status='won').count()
    total_lost = Bet.objects.filter(user=user, status='lost').count()
    pending = Bet.objects.filter(user=user, status='pending').count() + JackpotBet.objects.filter(user=user, jackpot__status__in=['active', 'inactive']).count()

    # Count jackpot wins
    jackpot_wins = 0
    finished_jackpots = Jackpot.objects.filter(status='finished')
    for jackpot in finished_jackpots:
        jackpot_bets = JackpotBet.objects.filter(jackpot=jackpot).select_related('user')
        if not jackpot_bets:
            continue
        user_points = {}
        for jb in jackpot_bets:
            achieved_points = 0
            for match_id, sel in jb.selections.items():
                try:
                    game = GuessGame.objects.get(id=match_id)
                    if game.finished and is_jackpot_prediction_correct(game, sel.get('option')):
                        achieved_points += float(sel.get('points', 0))
                except GuessGame.DoesNotExist:
                    continue
            user_points[jb.user.id] = achieved_points
        if user_points:
            winner_id = max(user_points, key=user_points.get)
            if winner_id == user.id:
                jackpot_wins += 1
    total_won += jackpot_wins

    return render(request, "home_guess.html", {
        "user": user,
        "matches": matches,
        "submitted": submitted,
        "profile_updated": profile_updated,
        "total_bets": total_bets,
        "total_won": total_won,
        "total_lost": total_lost,
        "pending_bets": pending,
    })


def jackpot_home(request, telegram_id):
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)
    active_jackpots = Jackpot.objects.filter(status='active').order_by('start_time')

    option_data = [
        {"code": GuessGame.OPTION_HOME, "label": "Home", "points": GuessGame.OPTION_POINTS.get(GuessGame.OPTION_HOME, 0)},
        {"code": GuessGame.OPTION_DRAW, "label": "Draw", "points": GuessGame.OPTION_POINTS.get(GuessGame.OPTION_DRAW, 0)},
        {"code": GuessGame.OPTION_AWAY, "label": "Away", "points": GuessGame.OPTION_POINTS.get(GuessGame.OPTION_AWAY, 0)},
        {"code": GuessGame.OPTION_1X, "label": "1X", "points": GuessGame.OPTION_POINTS.get(GuessGame.OPTION_1X, 0)},
        {"code": GuessGame.OPTION_12, "label": "12", "points": GuessGame.OPTION_POINTS.get(GuessGame.OPTION_12, 0)},
        {"code": GuessGame.OPTION_X2, "label": "X2", "points": GuessGame.OPTION_POINTS.get(GuessGame.OPTION_X2, 0)},
        {"code": GuessGame.OPTION_OVER_1_5, "label": "Over 1.5", "points": GuessGame.OPTION_POINTS.get(GuessGame.OPTION_OVER_1_5, 0)},
        {"code": GuessGame.OPTION_UNDER_3_5, "label": "Under 3.5", "points": GuessGame.OPTION_POINTS.get(GuessGame.OPTION_UNDER_3_5, 0)},
    ]

    # Avoid template parser problems with JavaScript by pre-serializing JSON
    option_data_json = json.dumps(option_data)

    return render(request, "jackpot.html", {
        "user": user,
        "active_jackpots": active_jackpots,
        "option_data": option_data,
        "option_data_json": option_data_json,
    })


@csrf_exempt
def jackpot_submit(request, telegram_id):
    user = get_object_or_404(UserProfile, telegram_id=telegram_id)

    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "Only POST allowed"}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8')) if isinstance(request.body, bytes) else json.loads(request.body)
        selections = data.get('selections', {})
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    if not selections:
        return JsonResponse({"success": False, "error": "No selections provided"})

    # Get jackpot from first match
    first_match_id = list(selections.keys())[0]
    try:
        game = GuessGame.objects.get(id=first_match_id)
        jackpot = game.jackpot
    except GuessGame.DoesNotExist:
        return JsonResponse({"success": False, "error": "Invalid match ID"})

    # Check if user already submitted for this jackpot
    if JackpotBet.objects.filter(jackpot=jackpot, user=user).exists():
        return JsonResponse({"success": False, "error": "You have already submitted a prediction for this jackpot"})

    # Get all unfinished games in the jackpot
    unfinished_games = GuessGame.objects.filter(jackpot=jackpot, finished=False)
    unfinished_game_ids = set(str(g.id) for g in unfinished_games)

    # Check if all unfinished games are selected
    selected_game_ids = set(selections.keys())
    if selected_game_ids != unfinished_game_ids:
        return JsonResponse({"success": False, "error": "You must predict all matches in the jackpot"})

    # Validate that all selected games belong to the jackpot
    for match_id in selections:
        if match_id not in unfinished_game_ids:
            return JsonResponse({"success": False, "error": "Invalid match selection"})

    # Check if user has enough balance for entry fee
    if user.balance < jackpot.entry_fee:
        return JsonResponse({"success": False, "error": f"Insufficient balance. Entry fee is {jackpot.entry_fee} ETB"})

    # Calculate total points
    total_points = sum(s['points'] for s in selections.values())

    # Deduct entry fee from user balance
    user.balance -= jackpot.entry_fee
    user.save()

    # Save the bet
    bet = JackpotBet.objects.create(
        jackpot=jackpot,
        user=user,
        telegram_id=user.telegram_id,
        total_points=total_points,
        selections=selections
    )

    return JsonResponse({"success": True, "message": f"Bet submitted for {jackpot.title} with {total_points} points. Entry fee of {jackpot.entry_fee} ETB deducted. Bet ID: {bet.bet_id}"})





# ---------------- Bet History ----------------
def is_jackpot_prediction_correct(game, option):
    if not game.finished or game.score_home_team is None or game.score_away_team is None:
        return False
    home = game.score_home_team
    away = game.score_away_team
    if option == 'HOME':
        return home > away
    elif option == 'DRAW':
        return home == away
    elif option == 'AWAY':
        return home < away
    elif option == '1X':
        return home >= away
    elif option == '12':
        return home != away
    elif option == 'X2':
        return home <= away
    elif option == 'OVER1.5':
        return home + away > 1.5
    elif option == 'UNDER3.5':
        return home + away < 3.5
    return False

def history(request, telegram_id=None):
    if not telegram_id:
        return HttpResponse("Missing telegram_id", status=400)

    user_profile = get_object_or_404(UserProfile, telegram_id=telegram_id)

    # Always fetch bets
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

    # Always fetch transactions
    deposits = ChapaPayment.objects.filter(telegram_id=telegram_id).order_by('-created_at')
    withdrawals = Withdrawal.objects.filter(telegram_id=telegram_id).order_by('-created_at')

    transactions = []
    for dep in deposits:
        transactions.append({
            'type': 'deposit',
            'id': dep.tx_ref,
            'amount': dep.amount,
            'date': dep.created_at,
            'status': dep.status
        })
    for wd in withdrawals:
        transactions.append({
            'type': 'withdrawal',
            'id': wd.withdraw_id,
            'amount': wd.amount,
            'date': wd.created_at,
            'status': wd.status
        })
    # Sort transactions by date descending
    transactions.sort(key=lambda x: x['date'], reverse=True)

    # Fetch jackpot bets
    jackpot_bets = JackpotBet.objects.filter(user=user_profile).order_by('-created_at')
    jackpot_history = []
    for jb in jackpot_bets:
        enriched_selections = {}
        achieved_points = 0
        for match_id, sel in jb.selections.items():
            try:
                game = GuessGame.objects.get(id=match_id)
                result = 'win' if is_jackpot_prediction_correct(game, sel['option']) else 'loss'
                if result == 'win' and game.finished:
                    achieved_points += float(sel.get('points', 0))
                enriched_selections[match_id] = {
                    **sel,
                    'team_home': game.team_home,
                    'team_away': game.team_away,
                    'match_time': game.match_time,
                    'finished': game.finished,
                    'score_home_team': game.score_home_team,
                    'score_away_team': game.score_away_team,
                    'result': result,
                }
            except GuessGame.DoesNotExist:
                enriched_selections[match_id] = sel  # fallback
        jh = {
            'jackpot_id': jb.jackpot.jackpot_id,
            'status': jb.jackpot.status,
            'title': jb.jackpot.title,
            'total_points': jb.total_points,
            'achieved_points': achieved_points,
            'created_at': jb.created_at,
            'selections': enriched_selections
        }
        if jb.jackpot.status == 'finished':
            # Calculate full ranking for finished jackpots
            jackpot_bets_all = JackpotBet.objects.filter(jackpot=jb.jackpot).select_related('user')
            ranking = []
            for jba in jackpot_bets_all:
                achieved_points_a = 0
                for match_id, sel in jba.selections.items():
                    try:
                        game = GuessGame.objects.get(id=match_id)
                        if game.finished and is_jackpot_prediction_correct(game, sel.get('option')):
                            achieved_points_a += float(sel.get('points', 0))
                    except GuessGame.DoesNotExist:
                        continue
                ranking.append({
                    'telegram_id': jba.user.telegram_id,
                    'name': f"{jba.user.first_name} {jba.user.last_name}",
                    'total_points': jba.total_points,
                    'achieved_points': achieved_points_a,
                    'entry_fee': jb.jackpot.entry_fee,
                })
            ranking.sort(key=lambda x: x['achieved_points'], reverse=True)
            for i, item in enumerate(ranking, start=1):
                item['rank'] = i
                item['is_winner'] = i == 1
                if item['is_winner']:
                    item['win_amount'] = jb.jackpot.total_win
                else:
                    item['win_amount'] = 0
            jh['participants'] = ranking
        jackpot_history.append(jh)

    context = {
        'user': user_profile,
        'bets': bets_with_selections,
        'transactions': transactions,
        'jackpot_history': jackpot_history
    }

    return render(request, 'history_guess.html', context)


def rank_guess(request, telegram_id):
    type_param = request.GET.get('type', 'active')

    user_profile = None
    try:
        user_profile = UserProfile.objects.filter(telegram_id=telegram_id).first()
    except Exception:
        user_profile = None

    if type_param == 'active':
        # Find the current active jackpot (not finished)
        try:
            current_jackpot = Jackpot.objects.filter(status__in=['active', 'inactive']).first()
            if not current_jackpot:
                # No active jackpot, show empty ranking
                ranking = []
            else:
                # Get all bets for the current jackpot
                jackpot_bets = JackpotBet.objects.filter(jackpot=current_jackpot).select_related('user')
                
                # Check if all games have scores entered (not just finished)
                all_games_have_scores = current_jackpot.games.filter(
                    score_home_team__isnull=False, 
                    score_away_team__isnull=False
                ).count() == current_jackpot.games.count()
                show_winner = all_games_have_scores
                
                ranking = []
                for jb in jackpot_bets:
                    user = jb.user
                    total_prediction_points = jb.total_points
                    
                    # Calculate achieved points (points from correct predictions on finished games)
                    achieved_points = 0
                    total_wins = 0
                    total_matches = 0
                    
                    for match_id, sel in jb.selections.items():
                        try:
                            game = GuessGame.objects.get(id=match_id)
                            total_matches += 1
                            if game.finished:
                                if is_jackpot_prediction_correct(game, sel.get('option')):
                                    total_wins += 1
                                    achieved_points += float(sel.get('points', 0))
                        except GuessGame.DoesNotExist:
                            continue
                    
                    ranking.append({
                        'telegram_id': user.telegram_id,
                        'name': f"{user.first_name} {user.last_name}",
                        'total_points': total_prediction_points,
                        'achieved_points': achieved_points,
                        'wins': total_wins,
                        'matches': total_matches,
                    })
                
                # Sort by achieved points descending
                ranking.sort(key=lambda x: x['achieved_points'], reverse=True)
                
                # Assign ranks and mark winner
                for i, item in enumerate(ranking, start=1):
                    item['rank'] = i
                    item['is_winner'] = show_winner and i == 1
                
                # If we have a winner and the jackpot has just completed, credit the winner's wallet
                if show_winner and ranking and current_jackpot.status != 'finished':
                    winner_entry = ranking[0]
                    winner_user = UserProfile.objects.filter(telegram_id=winner_entry['telegram_id']).first()
                    if winner_user:
                        winner_amount = current_jackpot.total_win if current_jackpot.total_win else 0
                        if winner_amount > 0:
                            winner_user.balance += winner_amount
                            winner_user.save()
                    current_jackpot.status = 'finished'
                    current_jackpot.save()

        except Exception as e:
            ranking = []

        return render(request, 'rank_guess.html', {
            'ranking': ranking,
            'user': user_profile,
            'type': 'active',
        })

    elif type_param == 'finished':
        # Get finished jackpots with winners
        finished_jackpots = Jackpot.objects.filter(status='finished').order_by('-end_time')
        finished_data = []
        for jackpot in finished_jackpots:
            bets = JackpotBet.objects.filter(jackpot=jackpot).select_related('user')
            if not bets:
                continue
            user_points = {}
            for jb in bets:
                points = 0
                for match_id, sel in jb.selections.items():
                    try:
                        game = GuessGame.objects.get(id=match_id)
                        if game.finished and is_jackpot_prediction_correct(game, sel.get('option')):
                            points += float(sel.get('points', 0))
                    except GuessGame.DoesNotExist:
                        continue
                user_points[jb.user.id] = points
            if user_points:
                winner_id = max(user_points, key=user_points.get)
                winner = UserProfile.objects.get(id=winner_id)
                finished_data.append({
                    'jackpot_id': jackpot.jackpot_id,
                    'title': jackpot.title,
                    'entry_fee': jackpot.entry_fee,
                    'total_win': jackpot.total_win,
                    'winner_name': f"{winner.first_name} {winner.last_name}",
                    'winner_id': winner.telegram_id,
                })

        return render(request, 'rank_guess.html', {
            'finished_data': finished_data,
            'user': user_profile,
            'type': 'finished',
        })

    return render(request, 'rank_guess.html', {'ranking': [], 'user': user_profile, 'type': 'active'})
