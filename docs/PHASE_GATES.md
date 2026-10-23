# Phase and acceptance gates

## Phase 0 — Repository foundation
- [x] Python package and isolated repository structure.
- [x] Data validation, deterministic features, baseline signal and smoke-test backtest helper.
- [x] Automated tests and secrets/data ignore rules.
- [ ] Confirm tests in CI after branch publication.

## Phase 1 — Data contract and provider audit
- [ ] Compare official exchange, company disclosure and licensed provider options.
- [ ] Default to daily end-of-day (EOD) data for the first prototype.
- [ ] Approve legal/contract scope, data budget, update schedule and symbol coverage.
- [ ] Version provider contracts and canonical schema before implementing connectors.

## Phase 2 — Data foundation
- [ ] Instrument master with stable IDs, symbol history and listing status.
- [ ] Historical OHLCV import with source and import timestamp.
- [ ] Corporate actions, adjusted/unadjusted prices and benchmark calendars.
- [ ] Reconciliation, gap, duplicate, outlier and stale-data reports.

## Phase 3 — Early-rally scanner
- [ ] Multi-horizon returns and benchmark/sector relative strength.
- [ ] Relative volume, traded value, volatility, consolidation and breakout features.
- [ ] Explicit liquidity, circuit and stale-data flags.
- [ ] Explainable rule scores with versioned thresholds.

## Phase 4 — Backtesting
- [ ] Immutable signal ledger with feature snapshot and model version.
- [ ] Next-tradable-session entry rules, slippage, fees, unfilled orders and circuits.
- [ ] Time-aware walk-forward evaluation and benchmark comparisons.
- [ ] Ranking quality, excess returns, drawdown, MAE/MFE and confidence intervals.

## Phase 5 — Corporate intelligence
- [ ] Permitted source ingestion and announcement timestamp normalization.
- [ ] Duplicate detection, amendments and cancellation linkage.
- [ ] Event classification and extraction of disclosed value, customer, duration and conditions.
- [ ] Evidence link, source quality, confidence and human review for uncertain extraction.

## Phase 6 — Model comparison
- [ ] Baseline first; then Logistic Regression, Random Forest and LightGBM/XGBoost.
- [ ] Define outcome horizons and labels before examining results.
- [ ] Time-aware splits and leakage controls for overlapping labels.
- [ ] Compare price-only, event-only and combined variants on untouched test windows.
- [ ] Promote no model unless it beats baseline after costs and passes stability checks.

## Phase 7 — Dashboard and alerts
- [ ] Ranked watchlist with evidence and signal explanation.
- [ ] Filters, saved views, run health and data-freshness indicators.
- [ ] Clear uncertainty labels; no automatic order placement.

## Phase 8 — Paper tracking and release
- [ ] Append-only live signal log and daily reconciliation.
- [ ] Paper-tracking period and independent review of drift/false positives.
- [ ] Security, privacy, observability, dependency and recovery checks.
- [ ] Explicit release review before any brokerage integration.
