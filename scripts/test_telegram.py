"""Quick Test Script for Telegram Alerts."""
import os
import sys
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv()

def test_telegram(token: str | None = None, chat_id: str | None = None):
    token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("\n❌ Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing in .env!")
        print("Usage: python scripts/test_telegram.py <BOT_TOKEN> <CHAT_ID>\n")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "⚡ *Blumberg Market Radar* Test Alert: Telegram connected successfully! Daily EOD reports will arrive at 4:30 PM IST.",
        "parse_mode": "Markdown",
    }
    data = json.dumps(payload).encode("utf-8")

    print(f"Sending test alert to Telegram chat_id {chat_id}...")
    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "BlumbergMarketRadar/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            if res_json.get("ok"):
                print("✅ Test message successfully sent to your Telegram on your phone!")
                return True
            else:
                print("❌ Telegram API returned:", res_json)
                return False
    except Exception as e:
        print("❌ Failed to send:", e)
        return False

if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else None
    c = sys.argv[2] if len(sys.argv) > 2 else None
    test_telegram(t, c)
