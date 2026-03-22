import json
import hashlib
import hmac

# Sample request body from Chapa (replace with actual body)
body = '{"amount": "1.00", "reference": "af087f16-8dba-417d-b109-6c834ad7edaa", "bank": "telebirr", "account_name": "Zerihun", "account_number": "251927084146"}'

# Signature received from Chapa
received_signature = "9fef3d39ba4f9d16410d63023e7798bac7ebe9a707a4e1c14caa74c173952ee2"

# Candidate words (add all you can think of)
candidates = [
    "WeviewFootballViewer",
    "CHASECK-OtxJDfVcR7i3qTckDUbKFPK3ZIOLGjmA",
    "your_secret_here",
    "test123",
    "approval123",
    "mypassword"
]

found = False
for secret in candidates:
    expected = hmac.new(
        key=secret.encode('utf-8'),
        msg=body.encode('utf-8'),
        digestmod=hashlib.sha256
    ).hexdigest()
    
    if hmac.compare_digest(received_signature, expected):
        print(f"✅ Match found! Secret is likely: '{secret}'")
        found = True
        break
    else:
        print(f"Tested '{secret}' -> No match")

if not found:
    print("❌ None of the candidates matched. You need to try more possibilities or check Chapa dashboard for the exact secret.")