"""Quick Test Script for CallMeBot WhatsApp Alerts."""
import os
import sys
import urllib.parse
import urllib.request
from dotenv import load_dotenv

load_dotenv()

def test_whatsapp(phone: str | None = None, apikey: str | None = None):
    phone = phone or os.getenv("WHATSAPP_PHONE")
    apikey = apikey or os.getenv("WHATSAPP_APIKEY")

    if not phone or not apikey:
        print("\n❌ Error: WHATSAPP_PHONE or WHATSAPP_APIKEY missing in .env!")
        print("Please set them in .env or pass as arguments:")
        print("python scripts/test_whatsapp.py +91XXXXXXXXXX <APIKEY>\n")
        return False

    clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")
    message = "⚡ *Blumberg Market Radar* Test Alert: WhatsApp connected successfully! Daily EOD reports will arrive at 4:30 PM IST."
    encoded = urllib.parse.quote(message)
    url = f"https://api.callmebot.com/whatsapp.php?phone={clean_phone}&text={encoded}&apikey={apikey}"

    print(f"Sending test alert to {clean_phone}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            print("Response from WhatsApp Gateway:", content)
            print("✅ Test message successfully sent to your WhatsApp!")
            return True
    except Exception as e:
        print("❌ Failed to send:", e)
        return False

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else None
    k = sys.argv[2] if len(sys.argv) > 2 else None
    test_whatsapp(p, k)
