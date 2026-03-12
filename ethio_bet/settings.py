"""
Django settings for ethio_bet project.

Optimized for local development with Telegram bot integration and public callback testing.
"""

from pathlib import Path
import os

# -----------------------------
# Base directory
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# -----------------------------
# Security
# -----------------------------
SECRET_KEY = 'django-insecure-t&x#*5q75lgh$-t&f$g1g904rqm_8tpr974$c-m#mjl-x#a81-'
DEBUG = True

# Local development with Cloudflare Tunnel / ngrok
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "*"]  # '*' allows public tunnel access

# -----------------------------
# Installed apps
# -----------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Your app
    'bot_dashboard',
]

# -----------------------------
# Middleware
# -----------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# -----------------------------
# URL configuration
# -----------------------------
ROOT_URLCONF = 'ethio_bet.urls'

# -----------------------------
# Templates
# -----------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],  # app templates
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# -----------------------------
# WSGI
# -----------------------------
WSGI_APPLICATION = 'ethio_bet.wsgi.application'

# -----------------------------
# Database
# -----------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# -----------------------------
# Password validators
# -----------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]

# -----------------------------
# Internationalization
# -----------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Addis_Ababa'  # Ethiopian time for local dev
USE_I18N = True
USE_TZ = True

# -----------------------------
# Static files
# -----------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# -----------------------------
# Media files
# -----------------------------
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# -----------------------------
# Default primary key field type
# -----------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -----------------------------
# Telegram bot token (local dev)
# -----------------------------
TELEGRAM_BOT_TOKEN = "8661608966:AAFXphBOs9rgCzK9VJCrJtgPL_Vfe-M3cp0"

# -----------------------------
# Public URL for callbacks (update to your tunnel URL)
# Example: https://edge-giant-liz-simulations.trycloudflare.com
# -----------------------------
PUBLIC_URL = "https://appliances-capability-sustainability-tool.trycloudflare.com"
# settings.py

# Chapa payment configuration
CHAPA_SECRET_KEY = "CHASECK-OtxJDfVcR7i3qTckDUbKFPK3ZIOLGjmA"
CHAPA_INIT_URL = "https://api.chapa.co/v1/transaction/initialize"
CHAPA_VERIFY_URL = "https://api.chapa.co/v1/transaction/verify/{}"
CALLBACK_URL = "https://yourdomain.com/chapa/callback/"  # Full public URL