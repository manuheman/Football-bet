import os
from pyngrok import ngrok

# set Django settings
os.environ["DJANGO_SETTINGS_MODULE"] = "ethio_bet.settings"

# Open ngrok tunnel
public_url = ngrok.connect(8000)
print(" * Ngrok public URL:", public_url)

# Start Django dev server
os.system("python manage.py runserver 8000")