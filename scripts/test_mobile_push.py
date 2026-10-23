"""
Quick test script for Mobile Push Notifications via ntfy.sh
"""
import sys
from blumberg_market_radar.alerts.mobile_push import (
    send_mobile_push_notification,
    format_radar_mobile_push_message,
)

def main():
    topic = "blumberg-adarsh-radar"
    sample_report = {
        "as_of": "2026-10-23",
        "synced_bars": 8103,
        "summary": {
            "active_candidates": 3,
            "in_profit_count": 2,
            "average_gain_pct": 1.45,
        },
        "top_picks": [
            {"symbol": "TATAELXSI", "gain_pct": 3.80, "holding_days": 2, "layer": 1},
            {"symbol": "POLYCAB", "gain_pct": 1.10, "holding_days": 2, "layer": 1},
            {"symbol": "DIXON", "gain_pct": -0.55, "holding_days": 2, "layer": 1},
        ],
    }

    body = format_radar_mobile_push_message(sample_report)
    print(f"Sending test mobile push to topic: '{topic}'...")
    success = send_mobile_push_notification(
        topic=topic,
        message=body,
        title="📈 Blumberg Radar EOD Daily Update",
        priority="high",
        tags=["chart_with_upwards_trend", "rocket"],
    )

    if success:
        print(" SUCCESS! Mobile notification successfully posted to ntfy.sh!")
        print(f"Anyone subscribed to topic '{topic}' in the free 'ntfy' app will receive this immediately.")
    else:
        print(" Failed to send mobile notification.")

if __name__ == "__main__":
    main()
