# bot_dashboard/admin.py

import os
from dotenv import load_dotenv
from django import forms
from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import redirect, get_object_or_404
from django.utils.html import format_html
from .models import UserProfile, Game, Jackpot, GuessGame, Bet, BetSelection, BingoGame, BingoParticipant, BingoCardTemplate, BingoNumberPick, JackpotBet
import requests
from django.conf import settings
from django.utils import timezone

# Load environment variables
load_dotenv()

# ---------------- Bot Token ----------------
BOT_TOKEN = os.environ.get('ADMIN_BOT_TOKEN_2')

# ---------------- User Profile Admin ----------------
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'first_name', 'last_name', 'phone_number', 'balance', 'bonus', 'favorite_club')
    search_fields = ('telegram_id', 'first_name', 'last_name', 'phone_number', 'favorite_club')
    list_filter = ('balance', 'bonus')


# ---------------- Game Admin Form ----------------
class GameAdminForm(forms.ModelForm):
    league = forms.ChoiceField(choices=[], required=False, label="League")

    class Meta:
        model = Game
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Collect all leagues across all countries to allow any league value
        all_leagues = []
        for leagues in Game.LEAGUE_CHOICES.values():
            all_leagues.extend(leagues)
        all_leagues = list(sorted(set(all_leagues)))

        # Include current instance league if editing
        if self.instance and self.instance.league and self.instance.league not in all_leagues:
            all_leagues.append(self.instance.league)

        # Set choices to all leagues to avoid validation errors
        self.fields['league'].choices = [(l, l) for l in all_leagues]

# ---------------- Game Admin ----------------
@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        'team1', 'team2', 'country', 'league', 'flag_thumb',
        'win1', 'draw', 'win2',
        'double_1x', 'double_12', 'double_x2',
        'score_team1', 'score_team2', 'finished',
        'game_datetime', 'date_added'
    )
    list_filter = ('finished', 'date_added', 'country', 'league')
    search_fields = ('team1', 'team2', 'league')
    ordering = ('-game_datetime',)
    readonly_fields = ('team1', 'team2', 'country', 'league', 'game_datetime', 'flag_thumb', 'date_added')
    list_editable = ('win1', 'draw', 'win2', 'double_1x', 'double_12', 'double_x2', 'score_team1', 'score_team2', 'finished')
    date_hierarchy = 'game_datetime'

    class Media:
        js = ('admin/js/game_date_separator.js',)

    def flag_thumb(self, obj):
        if obj.country_flag:
            return format_html('<img src="{}" width="24" height="16" />', obj.country_flag.url)
        return "-"
    flag_thumb.short_description = "Flag"


@admin.register(Jackpot)
class JackpotAdmin(admin.ModelAdmin):
    list_display = ('jackpot_id', 'title', 'entry_fee', 'total_win', 'status', 'start_time', 'end_time', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at')
    search_fields = ('jackpot_id', 'title')
    list_editable = ('jackpot_id', 'entry_fee', 'total_win', 'status')
    list_display_links = None
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    class GuessGameInline(admin.TabularInline):
        model = GuessGame
        extra = 0
        readonly_fields = ('created_at', 'updated_at')

    class JackpotBetInline(admin.TabularInline):
        model = JackpotBet
        extra = 0
        readonly_fields = ('created_at',)

    inlines = [GuessGameInline, JackpotBetInline]


@admin.register(GuessGame)
class GuessGameAdmin(admin.ModelAdmin):
    list_display = (
        'jackpot', 'team_home', 'team_away', 'score_home_team', 'score_away_team',
        'match_time', 'finished', 'created_at', 'updated_at'
    )
    list_filter = ('finished', 'match_time', 'created_at', 'jackpot')
    search_fields = ('team_home', 'team_away', 'jackpot__title')
    ordering = ('-match_time',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': (
                'jackpot', 'team_home', 'team_away', 'match_time',
                'score_home_team', 'score_away_team', 'finished'
            )
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ('created_at', 'updated_at')
        return ()

# ---------------- Bet Admin ----------------
class BetSelectionInline(admin.TabularInline):
    model = BetSelection
    extra = 0
    readonly_fields = ('game', 'bet_type', 'odds', 'match_info', 'match_status')
    can_delete = False


@admin.register(JackpotBet)
class JackpotBetAdmin(admin.ModelAdmin):
    list_display = ('bet_id', 'user', 'jackpot', 'total_points', 'created_at')
    list_filter = ('jackpot', 'created_at')
    search_fields = ('bet_id', 'user__telegram_id', 'user__first_name', 'jackpot__title')
    readonly_fields = ('bet_id', 'created_at')
    date_hierarchy = 'created_at'


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ('ticket_id', 'user', 'bet_amount', 'total_odds', 'potential_win', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('ticket_id', 'user__first_name', 'user__last_name', 'user__telegram_id')
    ordering = ('-created_at',)
    readonly_fields = ('ticket_id', 'created_at', 'total_odds', 'potential_win', 'telegram_id')
    inlines = [BetSelectionInline]
    date_hierarchy = 'created_at'
    list_per_page = 50


# ---------------- Bingo Admin ----------------
@admin.register(BingoGame)
class BingoGameAdmin(admin.ModelAdmin):
    list_display = ('game_id', 'winner', 'created_at', 'timer_start', 'timer_seconds', 'drawn_numbers')
    search_fields = ('game_id', 'winner__telegram_id', 'winner__first_name', 'winner__last_name')
    list_filter = ('created_at', 'winner')
    readonly_fields = ('game_id', 'created_at', 'timer_start', 'timer_seconds', 'drawn_numbers')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)


@admin.register(BingoParticipant)
class BingoParticipantAdmin(admin.ModelAdmin):
    list_display = ('game', 'user', 'clicked_number', 'card_numbers')
    search_fields = ('game__game_id', 'user__telegram_id', 'user__first_name', 'user__last_name')
    list_filter = ('game',)
    ordering = ('-game__created_at',)


@admin.register(BingoCardTemplate)
class BingoCardTemplateAdmin(admin.ModelAdmin):
    list_display = ('number', 'display_card_numbers', 'created_at')
    search_fields = ('number',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = ('number', 'card_numbers', 'created_at')

    def display_card_numbers(self, obj):
        if obj.card_numbers:
            # Group into rows of 5 for better display
            rows = []
            for i in range(0, len(obj.card_numbers), 5):
                row = obj.card_numbers[i:i+5]
                rows.append(', '.join(map(str, row)))
            return format_html('<div style="font-size: 10px; line-height: 1.2;">{}</div>', '<br>'.join(rows))
        return '-'
    display_card_numbers.short_description = 'Card Numbers (24)'


@admin.register(BingoNumberPick)
class BingoNumberPickAdmin(admin.ModelAdmin):
    list_display = ('bingo_number', 'picked_by', 'clicked_at')
    search_fields = ('bingo_number', 'picked_by__telegram_id', 'picked_by__first_name', 'picked_by__last_name')
    date_hierarchy = 'clicked_at'
    ordering = ('-clicked_at',)
