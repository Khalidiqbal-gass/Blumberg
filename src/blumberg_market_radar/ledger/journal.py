"""Signal Ledger & Journal: Immutable point-in-time snapshot of pre-rally candidate signals."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import pandas as pd


@dataclass
class SignalSnapshot:
    signal_id: str
    symbol: str
    signal_timestamp: str
    price_at_signal: float
    radar_score: float
    range_compression: float
    relative_volume: float
    rs_20d_pct: float
    primary_reason: str
    reasons: list[str]
    risk_flags: list[str]
    model_version: str
    code_commit: str
    related_corporate_event: str | None = None


DEFAULT_LEDGER_PATH = Path("data/signal_ledger.jsonl")


def record_signal_snapshots(
    scored_candidates: pd.DataFrame,
    ledger_path: Path | str = DEFAULT_LEDGER_PATH,
    model_version: str = "v1.0-pre-rally",
    code_commit: str = "main",
) -> list[SignalSnapshot]:
    """Append-only snapshot writer preserving exactly what the radar observed at signal time."""
    target_file = Path(ledger_path)
    target_file.parent.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(timezone.utc).isoformat()
    snapshots: list[SignalSnapshot] = []

    with open(target_file, "a", encoding="utf-8") as f:
        for idx, row in scored_candidates.iterrows():
            sym = str(row["symbol"])
            sig_id = f"SIG-{sym}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{idx}"
            snap = SignalSnapshot(
                signal_id=sig_id,
                symbol=sym,
                signal_timestamp=now_utc,
                price_at_signal=float(row["close"]),
                radar_score=float(row["radar_score"]),
                range_compression=float(row.get("compression_ratio", 0.0)),
                relative_volume=float(row.get("relative_volume", 1.0)),
                rs_20d_pct=float(row.get("rs_20d_pct", 0.0)),
                primary_reason=str(row.get("primary_driver", "Base Consolidation")),
                reasons=list(row.get("reason_codes", [])),
                risk_flags=list(row.get("risk_flags", [])),
                model_version=model_version,
                code_commit=code_commit,
                related_corporate_event=str(row.get("catalyst_summary", "")) or None,
            )
            f.write(json.dumps(asdict(snap)) + "\n")
            snapshots.append(snap)

    return snapshots


def load_signal_ledger(ledger_path: Path | str = DEFAULT_LEDGER_PATH) -> pd.DataFrame:
    """Load historical signal snapshots from the immutable append-only ledger."""
    target_file = Path(ledger_path)
    if not target_file.exists():
        return pd.DataFrame()

    records = []
    with open(target_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["signal_timestamp"] = pd.to_datetime(df["signal_timestamp"], utc=True)
    return df.sort_values("signal_timestamp", ascending=False).reset_index(drop=True)
