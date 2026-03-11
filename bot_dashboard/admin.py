# bot_dashboard/admin.py

from django import forms
from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import redirect, get_object_or_404
from django.utils.html import format_html
from .models import UserProfile, Game, Bet, BetSelection, Withdrawal
import requests

# ---------------- Bot Token ----------------
BOT_TOKEN = "8661608966:AAFXphBOs9rgCzK9VJCrJtgPL_Vfe-M3cp0"

# ---------------- User Profile Admin ----------------
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'first_name', 'last_name', 'phone_number', 'balance', 'bonus')
    search_fields = ('telegram_id', 'first_name', 'last_name', 'phone_number')
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
    form = GameAdminForm
    list_display = (
        'team1', 'team2', 'country', 'league', 'flag_thumb',
        'win1', 'draw', 'win2',
        'double_1x', 'double_12', 'double_x2',
        'score_team1', 'score_team2', 'finished',
        'game_datetime', 'date_added'
    )
    list_filter = ('finished', 'date_added', 'country', 'league')
    search_fields = ('team1', 'team2', 'league')
    ordering = ('-date_added',)
    readonly_fields = ('date_added', 'flag_thumb')
    list_editable = ('score_team1', 'score_team2', 'finished')

    fieldsets = (
        ('Teams', {'fields': ('team1', 'team2')}),
        ('League Info', {'fields': ('country', 'league', 'game_datetime', 'country_flag')}),
        ('1X2 Odds', {'fields': ('win1', 'draw', 'win2')}),
        ('Double Chance Odds', {'fields': ('double_1x', 'double_12', 'double_x2')}),
        ('Match Result', {'fields': ('score_team1', 'score_team2', 'finished'),
                          'description': 'Enter the final score once the match is finished.'}),
        ('Meta', {'fields': ('date_added',)}),
    )

    def flag_thumb(self, obj):
        if obj.country_flag:
            return format_html('<img src="{}" width="24" height="16" />', obj.country_flag.url)
        return "-"
    flag_thumb.short_description = "Flag"

    class Media:
        js = ('admin/js/game_league_dynamic.js',)  # JS for dynamic league selection


# ---------------- Bet Admin ----------------
class BetSelectionInline(admin.TabularInline):
    model = BetSelection
    extra = 0
    readonly_fields = ('game', 'bet_type', 'odds', 'match_info', 'match_status')
    can_delete = False


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ('ticket_id', 'user', 'bet_amount', 'total_odds', 'potential_win', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('ticket_id', 'user__first_name', 'user__last_name', 'user__telegram_id')
    ordering = ('-created_at',)
    readonly_fields = ('ticket_id', 'created_at', 'total_odds', 'potential_win', 'telegram_id')
    inlines = [BetSelectionInline]


# ---------------- Withdrawal Admin ----------------
@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ('withdraw_id', 'user_display', 'amount', 'method', 'phone_number', 'status', 'created_at', 'approve_button')
    list_filter = ('status', 'created_at', 'method')
    search_fields = ('withdraw_id', 'telegram_id', 'full_name', 'phone_number')
    readonly_fields = ('withdraw_id', 'telegram_id', 'amount', 'method', 'phone_number', 'full_name', 'status', 'created_at')

    def user_display(self, obj):
        return f"{obj.full_name} ({obj.telegram_id})"
    user_display.short_description = "User"

    def approve_button(self, obj):
        if obj.status != "approved":
            return format_html('<a class="button" href="{}">Approve</a>', f'{obj.id}/approve/')
        return "✅ Approved"
    approve_button.short_description = "Approve Withdrawal"

    def send_telegram_message(self, telegram_id, text):
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": telegram_id, "text": text, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"Error sending Telegram message to {telegram_id}: {e}")

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:withdrawal_id>/approve/', self.admin_site.admin_view(self.approve_withdrawal_view), name='withdrawal-approve'),
        ]
        return custom_urls + urls

    def approve_withdrawal_view(self, request, withdrawal_id):
        withdrawal = get_object_or_404(Withdrawal, id=withdrawal_id)
        if withdrawal.status != "approved":
            withdrawal.status = "approved"
            withdrawal.save()
            self.send_telegram_message(
                withdrawal.telegram_id,
                f"💸 Your withdrawal request has been *approved*!\n\n"
                f"ID: {withdrawal.withdraw_id}\n"
                f"Amount: {withdrawal.amount:.2f} ETB\n"
                f"Method: {withdrawal.method.title()}\n"
                f"Status: Approved"
            )
            self.message_user(request, f"Withdrawal {withdrawal.withdraw_id} approved successfully.")
        else:
            self.message_user(request, "Withdrawal already approved.", level=messages.WARNING)
        return redirect('/admin/bot_dashboard/withdrawal/')

    actions = ["approve_selected_withdrawals"]

    def approve_selected_withdrawals(self, request, queryset):
        for withdrawal in queryset:
            if withdrawal.status != "approved":
                withdrawal.status = "approved"
                withdrawal.save()
                self.send_telegram_message(
                    withdrawal.telegram_id,
                    f"💸 Your withdrawal request has been *approved*!\n\n"
                    f"ID: {withdrawal.withdraw_id}\n"
                    f"Amount: {withdrawal.amount:.2f} ETB\n"
                    f"Method: {withdrawal.method.title()}\n"
                    f"Status: Approved"
                )
        self.message_user(request, "Selected withdrawals approved.")
    approve_selected_withdrawals.short_description = "Approve selected withdrawals"