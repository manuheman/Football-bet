# bot_dashboard/models.py

import uuid
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.crypto import get_random_string

# ---------------- User Profile ----------------
class UserProfile(models.Model):
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    balance = models.FloatField(default=0)
    bonus = models.FloatField(default=10)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.telegram_id})"


# ---------------- Game ----------------
class Game(models.Model):
    # ---------------- TEAMS ----------------
    team1 = models.CharField(max_length=50)
    team2 = models.CharField(max_length=50)

    # ---------------- ODDS ----------------
    win1 = models.FloatField()
    draw = models.FloatField()
    win2 = models.FloatField()
    double_1x = models.FloatField()
    double_12 = models.FloatField()
    double_x2 = models.FloatField()

    # ---------------- MATCH RESULT ----------------
    score_team1 = models.PositiveIntegerField(null=True, blank=True)
    score_team2 = models.PositiveIntegerField(null=True, blank=True)
    finished = models.BooleanField(default=False)  # True when scores are entered

    # ---------------- LEAGUE & COUNTRY ----------------
    COUNTRY_CHOICES = [
        ('england', 'England'),
        ('germany', 'Germany'),
        ('spain', 'Spain'),
        ('italy', 'Italy'),
        ('russia', 'Russia'),
        ('france', 'France'),
        ('netherlands', 'Netherlands'),
        ('portugal', 'Portugal'),
        ('switzerland', 'Switzerland'),
        ('saudi_arabia', 'Saudi Arabia'),
        ('ethiopia', 'Ethiopia'),
        ('scotland', 'Scotland'),
        ('ukraine', 'Ukraine'),
        ('south_africa', 'South Africa'),
    ]

    # Static mapping of leagues for each country
    LEAGUE_CHOICES = {
        'england': ['Premier League', 'FA Cup', 'Championship'],
        'germany': ['DFB Pocal', 'Bundesliga1', 'Bundesliga2'],
        'spain': ['La Liga', 'Segunda Division'],
        'italy': ['Coppa Italia', 'Serie A', 'Serie B'],
        'russia': ['Russia Cup', 'Russia Premier League'],
        'france': ['Coupe de France', 'France League 1'],
        'netherlands': ['Eredivisie'],
        'portugal': ['Premier League'],
        'switzerland': ['Super League'],
        'saudi_arabia': ['Professional League'],
        'ethiopia': ['Premier League'],
        'scotland': ['Premier League'],
        'ukraine': ['Premier League'],
        'south_africa': ['Premier League'],
    }

    country = models.CharField(max_length=50, choices=COUNTRY_CHOICES, default='england')
    league = models.CharField(max_length=100, blank=True)
    game_datetime = models.DateTimeField(null=True, blank=True)
    country_flag = models.ImageField(upload_to="flags/", null=True, blank=True)  # small country flag
    date_added = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.team1} vs {self.team2}"

    def save(self, *args, **kwargs):
        # Automatically mark finished if scores are entered
        if self.score_team1 is not None and self.score_team2 is not None:
            self.finished = True

        # Auto-set league to the first league in the list if empty
        if not self.league:
            leagues = self.LEAGUE_CHOICES.get(self.country, [])
            if leagues:
                self.league = leagues[0]

        # Auto-set country flag image if not provided
        if not self.country_flag:
            flag_path = f"flags/{self.country}.png"  # store your flags in MEDIA_ROOT/flags/
            self.country_flag.name = flag_path

        super().save(*args, **kwargs)


# ---------------- Bet ----------------
class Bet(models.Model):
    ticket_id = models.CharField(max_length=12, unique=True, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    telegram_id = models.BigIntegerField(null=True, blank=True, editable=False)
    games = models.ManyToManyField(Game, through='BetSelection')
    bet_amount = models.FloatField()
    total_odds = models.FloatField()
    potential_win = models.FloatField()
    status = models.CharField(max_length=20, default='pending')
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.ticket_id:
            self.ticket_id = str(uuid.uuid4()).replace('-', '')[:12].upper()
        if self.user:
            self.telegram_id = self.user.telegram_id
        super().save(*args, **kwargs)


# ---------------- Bet Selection ----------------
class BetSelection(models.Model):
    bet = models.ForeignKey(Bet, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    bet_type = models.CharField(max_length=20)
    odds = models.FloatField()
    match_info = models.CharField(max_length=200, editable=False, null=True, blank=True)
    match_status = models.CharField(max_length=50, default='Pending')

    def save(self, *args, **kwargs):
        if self.game:
            self.match_info = f"{self.game.team1} vs {self.game.team2}"
        else:
            self.match_info = "Unknown match"

        if self.game.finished:
            result = self.is_correct()
            if result is True:
                self.match_status = 'Finished ✔'
            elif result is False:
                self.match_status = 'Finished ✖'
        super().save(*args, **kwargs)

    def is_correct(self):
        if not self.game.finished or self.game.score_team1 is None or self.game.score_team2 is None:
            return None
        s1, s2 = self.game.score_team1, self.game.score_team2
        bt = self.bet_type
        if bt == 'win1':
            return s1 > s2
        elif bt == 'draw':
            return s1 == s2
        elif bt == 'win2':
            return s2 > s1
        elif bt == 'double_1x':
            return s1 >= s2
        elif bt == 'double_12':
            return s1 != s2
        elif bt == 'double_x2':
            return s2 >= s1
        return False

    def __str__(self):
        game_name = self.match_info if self.match_info else "Unknown match"
        return f"{self.bet.ticket_id} | {game_name} | {self.bet_type.upper()}"


# ---------------- Automatic Bet Status Update ----------------
@receiver(post_save, sender=BetSelection)
def update_bet_status(sender, instance, **kwargs):
    bet = instance.bet
    selections = BetSelection.objects.filter(bet=bet)
    if all(s.match_status.startswith('Finished') for s in selections):
        if all(s.match_status == 'Finished ✔' for s in selections):
            bet.status = 'won'
        else:
            bet.status = 'lost'
        bet.save()


# ---------------- Payment Transactions ----------------
class ChapaPayment(models.Model):
    telegram_id = models.BigIntegerField()
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    tx_ref = models.CharField(max_length=50, unique=True)
    amount = models.FloatField(default=0)
    status = models.CharField(max_length=20, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.tx_ref} | {self.telegram_id} | {self.status}"


# ---------------- Withdrawals ----------------
class Withdrawal(models.Model):
    WITHDRAW_METHODS = [
        ('telebirr', 'Telebirr'),
        ('mpesa', 'M-Pesa'),
        ('cbe_birr', 'CBE Birr'),
    ]

    withdraw_id = models.CharField(max_length=12, unique=True, editable=False)
    telegram_id = models.BigIntegerField()
    amount = models.FloatField()
    method = models.CharField(max_length=10, choices=WITHDRAW_METHODS)
    phone_number = models.CharField(max_length=20)
    full_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_processed = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.withdraw_id:
            self.withdraw_id = 'WDL' + get_random_string(8).upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.withdraw_id} - {self.telegram_id} - {self.status}"