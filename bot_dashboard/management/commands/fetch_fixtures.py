# bot_dashboard/management/commands/fetch_fixtures.py

import requests
import time
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from bot_dashboard.models import Game

# ---------------- Football-data.org API ----------------
API_TOKEN = "41b134038f99400981d0bf23d26f3fa2"  # replace with your token
BASE_URL = "https://api.football-data.org/v4/matches"

# Map league codes to country names
LEAGUE_MAP = {
    # England
    "PL": "england", "FAC": "england", "ELC": "england", "CH": "england", "L2": "england",
    # Germany
    "BL1": "germany", "BL2": "germany", "3BL": "germany", "DFB": "germany",
    # Spain
    "PD": "spain", "SD": "spain", "CDR": "spain",
    # Italy
    "SA": "italy", "SB": "italy", "CI": "italy", "SC": "italy",
    # France
    "FL1": "france", "FL2": "france", "CF": "france", "SCF": "france",
    # Netherlands
    "DED": "netherlands", "D2": "netherlands",
    # Portugal
    "PPL": "portugal", "TAC": "portugal",
    # Russia
    "RPL": "russia", "FNL": "russia", "RC": "russia",
    # Europe / UEFA
    "CL": "europe", "EL": "europe", "EC": "europe",
    # Scotland
    "SPL": "scotland", "SC": "scotland", "SCUP": "scotland", "SLC": "scotland",
    # Turkey
    "TBL": "turkey", "TC": "turkey",
    # Belgium
    "JPL": "belgium", "BC": "belgium",
    # USA
    "MLS": "usa", "USOC": "usa",
    # Argentina
    "LPF": "argentina", "CP": "argentina",
    # Brazil
    "BRA1": "brazil", "BRA2": "brazil", "CB": "brazil",
    # Mexico
    "MEX1": "mexico", "MC": "mexico",
}

# fallback competition mapping if code doesn't work with /matches?competitions=...
COMPETITION_CODE_FALLBACK = {
    "PL": "2021",
    "BL1": "2002",
    "BL2": "2003",
    "SA": "2019",
    "PD": "2014",
    "FL1": "2015",
    "CL": "2001",
    "EL": "2003",
    "SPL": "771",  # Scottish Premiership
    # Add IDs for other leagues as needed
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
        week_later = today + timedelta(days=14)  # fetch for next 14 days

        headers = {"X-Auth-Token": API_TOKEN}
        total_created = 0

        self.stdout.write(self.style.NOTICE(f"Fetching fixtures from {today} to {week_later}..."))

        for league_code, country in LEAGUE_MAP.items():
            endpoint = f"https://api.football-data.org/v4/competitions/{league_code}/matches"
            params = {
                "dateFrom": today.isoformat(),
                "dateTo": week_later.isoformat(),
                "status": "SCHEDULED",  # only scheduled matches
            }

            matches = []
            try:
                response = requests.get(endpoint, headers=headers, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                matches = data.get("matches", [])

                if not matches:
                    self.stdout.write(f"[{league_code}] No scheduled matches found in competitions endpoint.")

            except requests.HTTPError as e:
                self.stdout.write(self.style.WARNING(f"[{league_code}] competitions endpoint failed: {e}; trying fallback /matches."))
                # fallback to generic matches endpoint + filter by code (avoid 400 if comps code unsupported)
                try:
                    fallback_params = {
                        "dateFrom": today.isoformat(),
                        "dateTo": week_later.isoformat(),
                        "status": "SCHEDULED",
                    }
                    fallback_resp = requests.get(BASE_URL, headers=headers, params=fallback_params, timeout=10)
                    fallback_resp.raise_for_status()
                    fallback_data = fallback_resp.json()
                    all_matches = fallback_data.get("matches", [])
                    matches = [m for m in all_matches if m.get("competition", {}).get("code") == league_code]

                    if not matches:
                        self.stdout.write(self.style.WARNING(f"[{league_code}] Fallback /matches returned no games for code {league_code}."))

                except requests.RequestException as e2:
                    self.stdout.write(self.style.ERROR(f"[{league_code}] Fallback /matches failed: {e2}"))
                    time.sleep(6)
                    continue

            except requests.RequestException as e:
                self.stdout.write(self.style.ERROR(f"[{league_code}] Error fetching: {e}"))
                time.sleep(6)
                continue

            if not matches:
                time.sleep(6)
                continue

            for match in matches:
                team1 = match["homeTeam"]["name"]
                team2 = match["awayTeam"]["name"]
                game_datetime = match.get("utcDate")
                league_name = match.get("competition", {}).get("name", league_code)

                # Skip duplicate matches
                if Game.objects.filter(team1=team1, team2=team2, game_datetime=game_datetime).exists():
                    continue

                # Create new game
                Game.objects.create(
                    team1=team1,
                    team2=team2,
                    country=country,
                    league=league_name,
                    game_datetime=game_datetime,
                    **DEFAULT_ODDS,
                )
                total_created += 1
                self.stdout.write(self.style.SUCCESS(f"Created match: {team1} vs {team2}"))

            # Pause between requests to avoid 429 rate limit
            time.sleep(6)

        self.stdout.write(self.style.SUCCESS(f"Fixtures fetched successfully! Total new matches: {total_created}"))