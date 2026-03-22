from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from bot_dashboard.views import transfer_approve

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
   
    path('search_ticket/<str:ticket_id>/', views.search_ticket, name='search_ticket'),

    path('chapa/initiate_transfer/', views.initiate_transfer, name='initiate_transfer'),

   # urls.py
    # urls.py
    path('api/transfer/approve/', views.transfer_approve, name='transfer-approve'),



    # Dama home page
    path('dama/<int:telegram_id>/', views.dama_home, name='dama_home'),

    # Dama create room
    path('dama/<int:telegram_id>/create/', views.create_dama_room, name='create_dama_room'),

    # Dama join room
    path('dama/<int:telegram_id>/join/<str:game_id>/', views.join_dama_room, name='join_dama_room'),

    path('dama/<int:telegram_id>/game_id/<str:game_id>/', views.dama_game, name='dama_game'),





    #bingo urls

     # Bingo home page (user selects a number, shows their 5x5 card)
    path('bingo/<int:telegram_id>/', views.bingo_home, name='bingo_home'),

    # Bingo result page
    path('bingo/<int:telegram_id>/result/<str:game_id>/<int:card_number>/', views.bingo_result, name='bingo_result'),

    # Bingo history page
    path('bingo/<int:telegram_id>/history/', views.bingo_history, name='bingo_history'),
    
    # Live status endpoint for AJAX updates
    path('bingo_live_status/<int:telegram_id>/', views.bingo_live_status, name='bingo_live_status'),
]

# ---------------- Serve media files in DEBUG ----------------
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)