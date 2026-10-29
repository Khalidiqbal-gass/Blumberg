"""Daily EOD Automation Task: Syncs Market, Advances Pipeline, Checks Stops & Sends WhatsApp Alert."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
import pandas as pd

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from blumberg_market_radar.pipeline.staged_tracker import (
    load_staged_pipeline,
    update_pipeline_with_bars,
    add_candidates_to_pipeline,
)
from blumberg_market_radar.alerts.whatsapp import format_whatsapp_digest, send_whatsapp_message
from blumberg_market_radar.alerts.telegram import format_telegram_digest, send_telegram_message
from blumberg_market_radar.alerts.mobile_push import send_mobile_push_notification
from blumberg_market_radar.scanner.radar import (
    compute_pre_rally_features,
    score_pre_rally_candidates,
    apply_sector_cluster_guardrail,
)
from blumberg_market_radar.data.ingestion import fetch_benchmark
from blumberg_market_radar.corporate_intel.events import get_corporate_events

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("daily_eod_automation")


def run_daily_automation():
    print("=" * 80)
    print("⚡ BLUMBERG MARKET RADAR — DAILY EOD AUTOMATION RUNNER")
    print("=" * 80)

    # 1. Sync latest candles into parquet cache & advance existing positions
    from scripts.sync_today_pipeline_bars import sync_today
    updated_pipe_df = sync_today()

    # 2. Score fresh candidates & apply Golden 5% Sizing + 25% Sector Cluster Guardrail
    cache_path = Path("data/cache/market_eod_all_equities.parquet")
    new_cands = None
    sector_summary: dict[str, int] = {}
    available_slots: int = 20

    if cache_path.exists():
        bars_df = pd.read_parquet(cache_path)
        bench_df = fetch_benchmark(period="1y", data_source="angel_one")
        events_df = get_corporate_events()
        features_df = compute_pre_rally_features(bars_df, bench_df)
        ranked = score_pre_rally_candidates(features_df, events_df, min_turnover_cr=1.5)

        # Enforce Golden Sweet Spot Guardrail:
        # - 5% per position -> Max 20 portfolio positions
        # - Max 25% per sector -> Max 5 stocks per Sector Cluster
        approved_cands, sector_summary, available_slots = apply_sector_cluster_guardrail(
            ranked,
            updated_pipe_df,
            max_stocks_per_sector=2,
            max_portfolio_slots=8,
        )
        new_cands = approved_cands.head(min(5, available_slots)) if available_slots > 0 else approved_cands.head(0)
        print(f"⚡ Sector Cluster Allocation Status: {sector_summary} | Available Slots: {available_slots}/8")

    # 3. Format and Dispatch Alerts
    tg_text = format_telegram_digest(updated_pipe_df, new_cands, sector_summary, available_slots)
    print("\n--- FORMATTED EOD DIGEST ---")
    print(tg_text)
    print("----------------------------\n")

    # Mobile Push Notification (ntfy.sh - Instant phone sound & notification)
    push_sent = send_mobile_push_notification(
        topic="blumberg-khalid-radar",
        message=tg_text,
        title="📈 Blumberg Market Radar: Daily EOD Summary",
        priority="high",
        tags=["chart_with_upwards_trend", "bell"],
    )
    if push_sent:
        print("✅ Daily Mobile Push Notification successfully delivered to phone!")

    tg_sent = send_telegram_message(tg_text)
    if tg_sent:
        print("✅ Daily Telegram Digest successfully delivered to mobile!")

    wa_text = format_whatsapp_digest(updated_pipe_df, new_cands, sector_summary, available_slots)
    wa_sent = send_whatsapp_message(wa_text)
    if wa_sent:
        print("✅ Daily WhatsApp Digest successfully delivered to mobile!")

    print("=" * 80)
    print("DAILY AUTOMATION COMPLETED SUCCESSFULLY")
    print("=" * 80)
    return updated_pipe_df


if __name__ == "__main__":
    run_daily_automation()
