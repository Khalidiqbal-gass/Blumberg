"""
Mobile Push Notification Dispatcher (via ntfy.sh)
-------------------------------------------------
Free, open-source, zero-signup instant push notifications to Android and iOS devices.
Works silently in the background:
- High priority sound / banner notification
- Rich Markdown formatting with stock tables and gainers/losers
- Click action to view radar or attachments
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

NTFY_DEFAULT_SERVER = "https://ntfy.sh"


def send_mobile_push_notification(
    topic: str,
    message: str,
    title: str = "📈 Blumberg Market Radar",
    priority: str = "high",  # min, low, default, high, urgent
    tags: Optional[list[str]] = None,
    click_url: Optional[str] = None,
    server_url: str = NTFY_DEFAULT_SERVER,
) -> bool:
    """
    Sends an instant push notification to any mobile device subscribed to `topic`.
    
    Parameters
    ----------
    topic : str
        The unique topic name subscribed on the user's mobile app (e.g., 'blumberg-adarsh-radar').
    message : str
        The notification body.
    title : str
        The notification header title.
    priority : str
        Notification importance: 'urgent', 'high', 'default', 'low', 'min'.
    tags : list[str], optional
        Emojis or tags (e.g. ['chart_with_upwards_trend', 'moneybag']).
    click_url : str, optional
        URL to open when the notification is tapped.
    server_url : str
        The ntfy server (defaults to public ntfy.sh).
        
    Returns
    -------
    bool
        True if the notification was delivered successfully, False otherwise.
    """
    endpoint = f"{server_url.rstrip('/')}/{topic.strip()}"
    headers = {
        "Title": title.encode("utf-8").decode("latin-1", errors="ignore"),
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = ",".join(tags)
    if click_url:
        headers["Click"] = click_url

    try:
        data = message.encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info(f"Mobile push delivered to topic '{topic}'.")
                return True
            logger.warning(f"Unexpected response status: {response.status}")
            return False
    except urllib.error.URLError as e:
        logger.error(f"Failed to send mobile push notification to topic '{topic}': {e}")
        return False
    except Exception as e:
        logger.error(f"Mobile push exception: {e}")
        return False


def format_radar_mobile_push_message(report: Dict[str, Any]) -> str:
    """
    Formats the daily radar metrics into a clean mobile notification body.
    """
    summary = report.get("summary", {})
    synced_bars = report.get("synced_bars", 0)
    top_picks = report.get("top_picks", [])
    
    total_active = summary.get("active_candidates", 0)
    avg_gain = summary.get("average_gain_pct", 0.0)
    in_profit = summary.get("in_profit_count", 0)

    lines = [
        f"📅 EOD Daily Update Completed ({report.get('as_of', 'Today')})",
        f"• Synced: {synced_bars:,} bars",
        f"• Active Pipeline: {total_active} stocks ({in_profit} in profit, Avg: {avg_gain:+.2f}%)",
        "",
        "🏆 Top Active Setups:"
    ]

    if top_picks:
        for p in top_picks[:5]:
            sym = p.get("symbol", "")
            gain = p.get("gain_pct", 0.0)
            hold = p.get("holding_days", 0)
            layer = p.get("layer", 1)
            icon = "🟢" if gain >= 0 else "🔴"
            lines.append(f"{icon} {sym}: {gain:+.2f}% (Day {hold}, L{layer})")
    else:
        lines.append("• No active stocks today.")

    lines.append("\nTap to open Streamlit Dashboard.")
    return "\n".join(lines)
