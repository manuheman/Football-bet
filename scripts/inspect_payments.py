import os, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ethio_bet.settings')

django.setup()

from bot_dashboard.models import ChapaPayment, UserProfile

print('payments:')
for p in ChapaPayment.objects.order_by('-created_at')[:20]:
    print(p.tx_ref, p.amount, p.status, p.telegram_id)

print('balances:')
for u in UserProfile.objects.all()[:20]:
    print(u.telegram_id, u.balance)
