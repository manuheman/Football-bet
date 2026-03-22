# bot_dashboard/create_bingo_templates.py

import os
import sys
import django
import random

# ---------------- Setup Django environment ----------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)  # add project root to path
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ethio_bet.settings')
django.setup()

from bot_dashboard.models import BingoCardTemplate

# ---------------- Helper to generate a bingo card ----------------
def generate_bingo_card():
    b_numbers = sorted(random.sample(range(1, 16), 5))
    i_numbers = sorted(random.sample(range(16, 31), 5))
    n_numbers = sorted(random.sample(range(31, 46), 4))
    g_numbers = sorted(random.sample(range(46, 61), 5))
    o_numbers = sorted(random.sample(range(61, 76), 5))
    return b_numbers + i_numbers + n_numbers + g_numbers + o_numbers

# ---------------- Main ----------------
def main():
    print("[INFO] Deleting existing BingoCardTemplate entries...")
    BingoCardTemplate.objects.all().delete()

    print("[INFO] Creating 80 new BingoCardTemplate entries...")
    for number in range(1, 81):
        card_numbers = generate_bingo_card()
        BingoCardTemplate.objects.create(number=number, card_numbers=card_numbers)
        print(f"[INFO] Created template {number}: {card_numbers}")

    print("[INFO] All templates created successfully!")

if __name__ == "__main__":
    main()