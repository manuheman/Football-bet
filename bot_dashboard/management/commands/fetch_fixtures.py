# bot_dashboard/management/commands/fetch_fixtures.py

import requests
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from bot_dashboard.models import Game

# ---------------- Football-data.org API ----------------
API_TOKEN = "41b134038f99400981d0bf23d26f3fa2"  # your token
BASE_URL = "https://api.football-data.org/v4/matches"

# Map league codes to country names
LEAGUE_MAP = {
    # England
    "PL": "england",      # Premier League
    "FAC": "england",     # FA Cup
    "ELC": "england",     # EFL Cup / League Cup
    "CH": "england",      # Championship
    # Germany
    "BL1": "germany",     # Bundesliga 1
    "BL2": "germany",     # Bundesliga 2
    "DFB": "germany",     # DFB Pokal
    # Spain
    "PD": "spain",        # La Liga
    "SD": "spain",        # Segunda Division
    # Italy
    "SA": "italy",        # Serie A
    "SB": "italy",        # Serie B
    "CI": "italy",        # Coppa Italia
    # France
    "FL1": "france",      # Ligue 1
    "FL2": "france",      # Ligue 2
    "CF": "france",       # Coupe de France
    # Netherlands
    "DED": "netherlands", # Eredivisie
    # Portugal
    "PPL": "portugal",    # Primeira Liga
    # Russia
    "RPL": "russia",      # Russian Premier League
    # UEFA
    "CL": "europe",       # Champions League
    "EL": "europe",       # Europa League
    "EC": "europe",       # Europa Conference League
    # Add more leagues as needed
}

# Default odds for new matches
DEFAULT_ODDS = {
    "win1": 1.0,
    "draw": 1.0,
    "win2": 1.0,
    "double_1x": 1.0,
    "double_12": 1.0,
    "double_x2": 1.0,
}

class Command(BaseCommand):
    help = "Fetch upcoming fixtures from football-data.org and save to Game model"

    def handle(self, *args, **kwargs):
        today = date.today()
        week_later = today + timedelta(days=7)

        headers = {"X-Auth-Token": API_TOKEN}

        total_created = 0

        # Loop through each league
        for league_code, country in LEAGUE_MAP.items():
            params = {
                "competitions": league_code,
                "dateFrom": today.isoformat(),
                "dateTo": week_later.isoformat(),
                "status": "SCHEDULED",
            }

            try:
                response = requests.get(BASE_URL, headers=headers, params=params, timeout=10)
                response.raise_for_status()
            except requests.RequestException as e:
                self.stdout.write(self.style.ERROR(f"Error fetching {league_code}: {e}"))
                continue

            data = response.json()
            matches = data.get("matches", [])

            if not matches:
                self.stdout.write(f"No scheduled matches found for {league_code}.")
                continue

            for match in matches:
                team1 = match["homeTeam"]["name"]
                team2 = match["awayTeam"]["name"]
                game_datetime = match.get("utcDate")
                league_name = match["competition"]["name"]

                # Skip duplicate matches
                if Game.objects.filter(team1=team1, team2=team2, game_datetime=game_datetime).exists():
                    continue

                # Create new game
                game = Game.objects.create(
                    team1=team1,
                    team2=team2,
                    country=country,
                    league=league_name,
                    game_datetime=game_datetime,
                    **DEFAULT_ODDS,
                )
                total_created += 1
                self.stdout.write(self.style.SUCCESS(f"Created match: {team1} vs {team2}"))

        self.stdout.write(self.style.SUCCESS(f"Fixtures fetched successfully! Total new matches: {total_created}"))