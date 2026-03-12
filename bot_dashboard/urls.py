from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # ---------------- User Dashboard ----------------
    path(
        "users/telegram_id/<int:telegram_id>/",
        views.user_detail,
        name="user_detail"
    ),

    # ---------------- Bet History ----------------
    path(
        "users/telegram_id/<int:telegram_id>/history/",
        views.history,
        name="history"
    ),

    # ---------------- AJAX Place Bet ----------------
    path(
        "place_bet/",
        views.place_bet,
        name="place_bet"
    ),

    # ---------------- Chapa Deposit ----------------
    path(
        "chapa/init_deposit/",
        views.init_deposit,
        name="init_deposit"
    ),
    path(
        "chapa/callback/",
        views.chapa_callback,
        name="chapa_callback"
    ),
]

# ---------------- Serve media files in DEBUG ----------------
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)