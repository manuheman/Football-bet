# bot_dashboard/management/commands/update_scores.py

import requests
import time
from django.core.management.base import BaseCommand
from bot_dashboard.models import Game
from datetime import timedelta

API_TOKEN = "41b134038f99400981d0bf23d26f3fa2"
BASE_URL = "https://api.football-data.org/v4/matches"

# Leagues you have access to in your subscription
COMPETITIONS = [
    "WC", "CL", "BL1", "DED", "BSA", "PD", "FL1", "ELC",
    "PPL", "EC", "SA", "PL"
]

# Map your Game.league field to API codes
LEAGUE_NAME_TO_CODE = {
    "Premier League": "PL",
    "Championship": "ELC",
    "Serie A": "SA",
    "Primera Division": "PD",
    "La Liga": "PD",
    "Eredivisie": "DED",
    "Bundesliga": "BL1",
    "Bundesliga 1": "BL1",
    "Primeira Liga": "PPL",
    "Ligue 1": "FL1",
    "Campeonato Brasileiro Série A": "BSA",
    "UEFA Champions League": "CL",
    "European Championship": "EC",
    "FIFA World Cup": "WC",
}


def normalize_team_name(name: str) -> str:
    """
    Normalize team names for better matching:
    - lowercase
    - remove dots, apostrophes
    - strip whitespace
    """
    return name.lower().replace(".", "").replace("'", "").strip()


class Command(BaseCommand):
    help = "Update scores for ongoing matches from football-data.org"

    def handle(self, *args, **kwargs):
        unfinished_games = Game.objects.filter(finished=False).order_by('game_datetime')
        headers = {"X-Auth-Token": API_TOKEN}

        if not unfinished_games.exists():
            self.stdout.write("No unfinished games to update.")
            return

        self.stdout.write(f"Updating scores for {unfinished_games.count()} games...")

        for game in unfinished_games:
            # Map league name to API code
            league_code = LEAGUE_NAME_TO_CODE.get(game.league)
            if not league_code or league_code not in COMPETITIONS:
                self.stdout.write(
                    f"Skipping {game.team1} vs {game.team2}: league '{game.league}' not in subscription."
                )
                continue

            # Expand date range ±1 day to account for timezone/UTC differences
            params = {
                "competitions": league_code,
                "dateFrom": (game.game_datetime.date() - timedelta(days=1)).isoformat(),
                "dateTo": (game.game_datetime.date() + timedelta(days=1)).isoformat(),
            }

            # Retry on rate limit or transient errors
            for attempt in range(3):
                try:
                    response = requests.get(BASE_URL, headers=headers, params=params, timeout=10)
                    response.raise_for_status()
                    break
                except requests.exceptions.HTTPError as e:
                    if response.status_code == 429:
                        self.stdout.write(
                            f"Rate limit hit for {game.team1} vs {game.team2}, retrying in 2 seconds..."
                        )
                        time.sleep(2)
                    else:
                        self.stdout.write(f"HTTP error for {game.team1} vs {game.team2}: {e}")
                        break
                except requests.RequestException as e:
                    self.stdout.write(f"Request error for {game.team1} vs {game.team2}: {e}")
                    break
            else:
                self.stdout.write(f"Skipping {game.team1} vs {game.team2} after 3 failed attempts.")
                continue

            data = response.json()
            matches = data.get("matches", [])

            # Match the game by normalized team names
            matched = False
            for match in matches:
                home_api = normalize_team_name(match["homeTeam"]["name"])
                away_api = normalize_team_name(match["awayTeam"]["name"])
                home_db = normalize_team_name(game.team1)
                away_db = normalize_team_name(game.team2)

                if home_api == home_db and away_api == away_db:
                    score = match.get("score", {}).get("fullTime", {})
                    home_score = score.get("home")
                    away_score = score.get("away")
                    status = match.get("status")

                    # Only update scores if the match has started
                    if status in ["FINISHED", "IN_PLAY"]:
                        game.score_team1 = home_score if home_score is not None else 0
                        game.score_team2 = away_score if away_score is not None else 0
                        game.finished = status == "FINISHED"
                        game.save()

                        self.stdout.write(
                            f"Updated {game.team1} vs {game.team2}: {game.score_team1}-{game.score_team2}, finished={game.finished}"
                        )
                    else:
                        # Scheduled, not yet started
                        self.stdout.write(f"{game.team1} vs {game.team2} has not started yet (status: {status}).")

                    matched = True
                    break

            if not matched:
                self.stdout.write(
                    f"No score update found for {game.team1} vs {game.team2} on API."
                )

            # Small delay to respect API rate limits
            time.sleep(1)

        self.stdout.write(self.style.SUCCESS("Score update complete!"))