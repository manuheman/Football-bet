from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # User dashboard (detail page)
    path(
        "users/telegram_id/<int:telegram_id>/",
        views.user_detail,
        name="user_detail"
    ),

    # User bet history page
    path(
        "users/telegram_id/<int:telegram_id>/history/",
        views.history,
        name="history"
    ),

    # Place a bet via AJAX
    path(
        "place_bet/",
        views.place_bet,
        name="place_bet"
    ),

    # Chapa webhook callback
    path(
        "chapa-callback/",
        views.chapa_callback,
        name="chapa_callback"
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)