"""WhatsApp Alert Dispatcher for Blumberg Market Radar via CallMeBot API.

Sends clean EOD summaries and critical stop-loss alerts directly to user's WhatsApp.
Setup instructions (10 seconds, 100% Free):
1. Add phone number +34 644 44 48 48 to your WhatsApp contacts (CallMeBot).
2. Send WhatsApp message: "I allow callmebot to send me messages"
3. CallMeBot will reply with your personal API Key.
4. Add to .env:
   WHATSAPP_PHONE="+91XXXXXXXXXX"
   WHATSAPP_APIKEY="your_api_key_here"
"""
from __future__ import annotations

import logging
import os
import urllib.parse
import urllib.request
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

logger = logging.getLogger("whatsapp_alerts")
load_dotenv()


def format_whatsapp_digest(pipeline_df: pd.DataFrame, new_candidates_df: pd.DataFrame | None = None) -> str:
    """Format daily EOD performance, stop-loss alerts, and new setups for WhatsApp."""
    today_str = pd.Timestamp.now().strftime("%d %b %Y")
    lines = [
        "⚡ *BLUMBERG MARKET RADAR — EOD DIGEST*",
        f"📅 *Date:* {today_str} (4:30 PM IST)",
        "────────────────────────",
    ]

    # 1. Critical Alerts (Stop Loss / Exits)
    if not pipeline_df.empty and "status" in pipeline_df.columns:
        exits = pipeline_df[pipeline_df["status"].str.contains("STOP_LOSS|EXIT", case=False, na=False)]
        if not exits.empty:
            lines.append("🚨 *CRITICAL RISK ALERTS:*")
            for _, r in exits.iterrows():
                lines.append(f"⚠️ *{r['symbol']}*: {r.get('current_gain_pct', 0.0):+.2f}% ({r['status'][:24]})")
            lines.append("────────────────────────")

    # 2. Incubating Holdings Performance
    if not pipeline_df.empty:
        lines.append("📊 *ACTIVE PIPELINE HOLDINGS:*")
        active = pipeline_df[~pipeline_df["status"].str.contains("STOP_LOSS|DROPPED", case=False, na=False)].head(8)
        for _, r in active.iterrows():
            sym = r["symbol"]
            gain = r.get("current_gain_pct", 0.0)
            price = r.get("current_price", 0.0)
            days = r.get("days_in_pipeline", 0)
            icon = "🟢" if gain > 0 else "🔴" if gain < -3.0 else "⚪"
            lines.append(f"{icon} *{sym}*: ₹{price:,.1f} ({gain:+.2f}%) | Day {days}")
        lines.append("────────────────────────")

    # 3. Fresh Breakout / Radar Setups
    if new_candidates_df is not None and not new_candidates_df.empty:
        lines.append("🎯 *TOP FRESH RADAR SETUPS (L1):*")
        top3 = new_candidates_df.head(3)
        for _, r in top3.iterrows():
            sym = r["symbol"]
            score = r.get("radar_score", 0.0)
            driver = r.get("primary_driver", "VCP Squeeze")[:20]
            lines.append(f"⭐ *{sym}* (Score {score:.1f}) | {driver}")
        lines.append("────────────────────────")

    lines.append("👉 View Full Terminal: http://localhost:8501")
    return "\n".join(lines)


def send_whatsapp_message(text: str, phone: str | None = None, apikey: str | None = None) -> bool:
    """Send text message to user's WhatsApp via CallMeBot API."""
    phone = phone or os.getenv("WHATSAPP_PHONE")
    apikey = apikey or os.getenv("WHATSAPP_APIKEY")

    if not phone or not apikey:
        logger.warning(
            "WhatsApp alerts not configured. To enable, set WHATSAPP_PHONE and WHATSAPP_APIKEY in .env. "
            "Get free key by sending 'I allow callmebot to send me messages' to +34 644 44 48 48 on WhatsApp."
        )
        print("\n[WHATSAPP PREVIEW (Not Sent - Missing .env Credentials)]:\n" + text + "\n")
        return False

    encoded_text = urllib.parse.quote(text)
    clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")
    url = f"https://api.callmebot.com/whatsapp.php?phone={clean_phone}&text={encoded_text}&apikey={apikey}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            if "Message queued" in content or "success" in content.lower() or resp.status == 200:
                logger.info(f"WhatsApp alert successfully delivered to {clean_phone}!")
                return True
            else:
                logger.warning(f"CallMeBot response: {content}")
                return False
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message via CallMeBot: {e}")
        return False
