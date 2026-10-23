# Blumberg — Market Radar Terminal

An independent research platform for Indian equities, using transparent early-rally signals, corporate-event intelligence, historical backtesting, and carefully validated machine learning.

## Current status

**Foundation scaffold.** This increment includes OHLCV validation, deterministic technical features, a transparent baseline signal, a simplified backtest smoke-test utility, and automated tests. It does not yet connect to exchanges or brokers, ingest licensed data, or provide investment advice.

## First run

Python 3.11+ is recommended.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

Tests use synthetic data and require no market-data credentials.

## Delivery phases

1. Repository foundation and data permissions.
2. Market-data schema, instrument master, historical OHLCV and corporate actions.
3. Explainable early-rally scanner.
4. Signal ledger and realistic walk-forward backtesting.
5. Corporate orders and news intelligence.
6. Out-of-sample model comparison.
7. Research dashboard and alerts.
8. Paper tracking, hardening and release gates.

## Guardrails

- No guaranteed-return or multibagger claims; signals are research hypotheses.
- No automatic real-money trading in the initial release.
- Preserve event/publication/collection timestamps, source evidence, feature snapshots and model versions.
- Prevent look-ahead bias and unrealistic fills; account for survivorship limitations where data permits.
- Verify provider terms before automated collection, storage or redistribution.
- Never commit credentials, private personal data or unlicensed bulk datasets.

See `docs/` for architecture, data governance and phase acceptance criteria.
