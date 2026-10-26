"""Telegram Alert Dispatcher for Blumberg Market Radar via Official Telegram Bot API.

Official Telegram Bot Setup (Takes only 30 seconds):
1. Open Telegram on your phone and search: @BotFather
2. Send: /newbot
3. Give it a name (e.g. My Market Radar) and a username (e.g. my_market_radar_bot).
4. BotFather will instantly give you your HTTP API Token:
   e.g. 7123456789:AAHk...
5. Search your bot username on Telegram, click "Start" (or send /start).
6. To get your Chat ID:
   Open Telegram and search @userinfobot -> click Start -> it instantly replies with your Id (e.g. 123456789).
7. Put in .env:
   TELEGRAM_BOT_TOKEN="your_bot_token"
   TELEGRAM_CHAT_ID="your_chat_id"
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
import pandas as pd
from dotenv import load_dotenv

logger = logging.getLogger("telegram_alerts")
load_dotenv()


def format_telegram_digest(
    pipeline_df: pd.DataFrame,
    new_candidates_df: pd.DataFrame | None = None,
    sector_summary: dict[str, int] | None = None,
    available_slots: int | None = None,
) -> str:
    """Format daily EOD performance, stop-loss alerts, sector allocation, and new setups for Telegram."""
    today_str = pd.Timestamp.now().strftime("%d %b %Y")
    lines = [
        "⚡ *BLUMBERG MARKET RADAR — EOD DIGEST*",
        f"📅 *Date:* {today_str} (4:30 PM IST)",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # 1. Critical Alerts (Stop Loss / Exits)
    if not pipeline_df.empty and "status" in pipeline_df.columns:
        exits = pipeline_df[pipeline_df["status"].str.contains("STOP_LOSS|EXIT", case=False, na=False)]
        if not exits.empty:
            lines.append("🚨 *CRITICAL RISK ALERTS:*")
            for _, r in exits.iterrows():
                lines.append(f"⚠️ *{r['symbol']}*: `{r.get('current_gain_pct', 0.0):+.2f}%` ({r['status'][:24]})")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━")

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
            lines.append(f"{icon} *{sym}*: ₹{price:,.1f} (`{gain:+.2f}%`) | Day {days}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # 3. Sector Cluster Allocation (The Golden 5% Sizing + 25% Cluster Rule)
    if sector_summary:
        lines.append("🏛️ *SECTOR ALLOCATION (Max 5/Sector - 25% Cap):*")
        for sec, cnt in sorted(sector_summary.items(), key=lambda x: x[1], reverse=True)[:5]:
            lines.append(f"• {sec}: *{cnt}/5* ({cnt * 5}% Cap)")
        if available_slots is not None:
            lines.append(f"📦 *Slots Available:* {available_slots}/20 (5% each)")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    # 4. Fresh Breakout / Radar Setups
    if new_candidates_df is not None and not new_candidates_df.empty:
        lines.append("🎯 *TOP FRESH RADAR SETUPS (L1):*")
        top3 = new_candidates_df.head(3)
        for _, r in top3.iterrows():
            sym = r["symbol"]
            score = r.get("radar_score", 0.0)
            driver = r.get("primary_driver", "VCP Squeeze")[:20]
            lines.append(f"⭐ *{sym}* (Score {score:.1f}) | {driver}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    lines.append("👉 *Terminal:* `http://localhost:8501`")
    return "\n".join(lines)


def send_telegram_message(text: str, token: str | None = None, chat_id: str | None = None) -> bool:
    """Send text message to user's Telegram via official Bot API."""
    token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.warning("Telegram alerts not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.")
        print("\n[TELEGRAM PREVIEW (Not Sent - Missing .env Credentials)]:\n" + text + "\n")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    data = json.dumps(payload).encode("utf-8")

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "BlumbergMarketRadar/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            if res_json.get("ok"):
                logger.info(f"Telegram alert successfully sent to chat_id {chat_id}!")
                return True
            else:
                logger.warning(f"Telegram API response: {res_json}")
                return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False
