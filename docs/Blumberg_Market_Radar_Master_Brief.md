# BLUMBERG MARKET RADAR TERMINAL
## Master Product Brief & AI Handoff Specification
Version 1.0 | Updated 22 October 2026

## 1. One-sentence definition
Blumberg Market Radar Terminal is an Indian-equities research and market-intelligence platform designed to scan eligible NSE/BSE stocks, detect and explain possible early-stage rally setups, connect them with verified corporate events/news, and rigorously backtest whether the signals have historically provided useful benchmark-relative outcomes.

This is a research product, not a guaranteed-return system, not a promise to find multibaggers, and not initially an automated trading bot.

## 2. Mission and problem to solve
The software should answer:
1. Which eligible Indian stocks are beginning to show unusual, potentially meaningful strength?
2. What observable evidence triggered each candidate signal?
3. Is the signal supported by price/volume behaviour, a verified corporate event, both, or neither?
4. What risks or data-quality issues could make it misleading?
5. How did comparable signals perform historically under realistic assumptions?
6. How early did a signal occur before a later move, and how often did similar setups fail?

The goal is to test whether early signals can be identified consistently and without look-ahead bias—not merely find stocks after they have already risen.

## 3. Scope and non-goals
### In scope
- Indian listed equities, limited to coverage provided by permitted data sources.
- Nominal price is not the eligibility rule: ₹1, ₹20, ₹200 or ₹1,000 stocks may qualify if liquidity, data quality and risk checks pass.
- Daily/end-of-day (EOD) research first; intraday is a later option.
- Historical OHLCV, market/sector benchmarks, corporate actions, official filings and permitted news sources.
- Explainable candidate ranking, signal ledger, backtesting, research dashboard and later alerts.
- AI-assisted implementation, tests, documentation and phase tracking.

### Not initially in scope
- Guaranteed multibagger prediction or guaranteed profit.
- Automatic real-money order placement.
- Treating rumours or headlines as confirmed facts.
- Buying expensive tick-level feeds before proving their need.
- Redistributing exchange/vendor data without rights.
- Claiming model accuracy before out-of-sample evaluation.
- Modifying unrelated GitHub repositories.

## 4. End-to-end workflow
1. Collect permitted data: daily prices/volume, security master, benchmarks, corporate actions, official filings and permitted news.
2. Validate timestamps, gaps, duplicates, impossible candles, stale data, symbol changes, splits and bonuses.
3. Build point-in-time features using only information available at that moment.
4. Generate candidate signals using transparent rules and later validated ML models.
5. Enrich candidates with verified corporate events and original evidence.
6. Save immutable signal snapshots, timestamps, evidence, model/rule version and code version.
7. Backtest with realistic entry assumptions, costs, slippage, benchmarks and walk-forward splits.
8. Display candidates, explanations, risks and historical evidence.
9. Paper-track live signals before considering any execution capability.

## 5. Market Data Engine
### Required data
- Stable security ID, exchange, symbol history, listing/delisting status and available sector metadata.
- Daily OHLCV: open, high, low, close, volume; traded value if available.
- Broad-market and sector benchmark series, exchange calendar/holidays.
- Corporate actions: splits, bonuses, dividends, rights issues and symbol changes.
- Provider/source, source timestamp, import timestamp, price-adjustment status and data-quality status.
- Historical universe membership, including delisted/failing stocks where reliable data exists.

### Validation
- Reject/quarantine duplicate symbol-date rows, invalid dates, non-positive prices, negative volume and inconsistent candles.
- Report missing sessions, stale prices, outliers, zero-volume cases and provider conflicts.
- Keep raw and adjusted prices distinct where permitted.
- Do not assume every source has complete delisted-stock or corporate-action history.
- Keep provider adapters modular so vendors can change without rewriting the scanner.

## 6. Early Rally Scanner
Candidate feature groups:
- Returns/momentum: 1/5/10/20/21/63-session returns where available.
- Relative strength against market and sector benchmarks.
- Relative volume: current volume versus a baseline built from prior sessions only.
- Liquidity: traded value, average traded value and ability to enter/exit.
- Risk: rolling volatility, range expansion, gaps, drawdown and unstable price action.
- Structure: consolidation, range breakout, trend consistency and failed-breakout markers.
- Context: market/sector regime, corporate events, earnings dates, source quality and data freshness.
- Eligibility flags: illiquidity, stale data, suspension/circuit constraints and corporate-action uncertainty where data supports them.

Use normalized percentages, ratios and ranks so nominal share prices are comparable. Tune thresholds on development/validation data, not the final test set. Explain why each stock scored highly. A high score is a research candidate, not a buy instruction.

## 7. Corporate Order & News Intelligence
### Source hierarchy
1. Official NSE/BSE announcements/filings and attachments where use is permitted.
2. Company investor-relations pages, official press releases, results, annual reports and presentations.
3. Licensed financial news feeds/APIs if cost, history, coverage and rights fit.
4. Secondary news for context only; it does not automatically override an official filing.

### Event types
Confirmed order/contract; LOI; provisional/conditional award; tender/bid outcome; amendment/cancellation/delay; financial results; guidance/business update; debt/fundraising; promoter pledge; rating action; litigation/regulatory event; other material disclosure.

### Extracted fields
Company/security ID, event type, disclosed value/currency/unit, customer if disclosed, duration, scope, conditions, announcement time, source URL/document ID, capture time, confirmation status, confidence, extraction version, duplicate group, review status and evidence location. Only extract details supported by the source.

### Reliability and legal controls
- Link every claim to original evidence.
- Distinguish confirmed contracts from LOIs, bids, rumours and generic coverage.
- Link amendments and cancellations to the original event.
- Keep publication, collection and effective timestamps separate.
- Public visibility does not grant unlimited scraping, bulk storage, commercial-use or redistribution rights. Check terms, quotas, rate limits and licences; never bypass paywalls, access controls or CAPTCHAs.
- Uncertain extraction must remain uncertain or go to human review.

## 8. AI and algorithm strategy
Use a staged model portfolio; no algorithm is presumed profitable.

### Stage A — Transparent baseline
Rule-based score using normalized returns, relative strength, prior-window relative volume, liquidity and volatility. This is the benchmark every complex model must beat.

### Stage B — Supervised tabular models
- Logistic Regression: interpretable baseline; calibrate if displaying probabilities.
- Random Forest: nonlinear comparison.
- LightGBM and XGBoost: primary boosted-tree candidates for ranking/classification/regression.
- Treat outputs as ranks/scores unless probability calibration is validated.

### Stage C — Anomaly and exploratory patterns
- Isolation Forest/statistical anomaly detection flags unusual behaviour; unusual does not mean bullish.
- Clustering groups similar setups for exploration; clusters alone do not prove predictive value.

### Stage D — News NLP
A FinBERT-style financial NLP model may help with sentiment/event classification, but extracted facts must remain evidence-grounded. Compare price-only, event-only and combined models. Keep NLP only if it improves out-of-sample performance and reliability.

### Later
LSTM/Transformer/deep learning only if data depth and honest tests justify complexity. Do not choose an algorithm just because it sounds advanced.

## 9. Targets and outcome labels
Define targets before final evaluation:
- Benchmark-relative returns at 20/60/120 sessions.
- Whether a predefined upside threshold is reached before a predefined adverse-move threshold.
- Maximum favourable excursion (MFE), maximum adverse excursion (MAE), and time to threshold.
- Ranking quality: whether top-ranked candidates outperform lower-ranked candidates and benchmarks.

Freeze target thresholds on development/validation data before evaluating untouched later periods. Report horizons separately. Never define “winner” after seeing test results.

## 10. Backtesting — mandatory safeguards
- Time-aware walk-forward splits; never randomly shuffle time-series data.
- At signal time t, use only information actually available by its cutoff.
- For a signal using the closing price, do not assume a fill at that same close unless realistically executable; default to next tradable session.
- Prevent label overlap/leakage with purge/embargo where relevant.
- Model fees, brokerage, slippage, spread/market impact, liquidity, circuits, suspensions and unfilled trades.
- Handle corporate actions and document adjusted/unadjusted price basis.
- Use point-in-time universe membership and delisted/failing names where history exists; disclose survivorship limitations.
- Compare market/sector benchmarks and a simple baseline.
- Report signal count/coverage, precision-at-K/ranking metrics, defined hit rate, excess returns, drawdown, volatility, turnover, MAE/MFE, time-to-threshold, false positives and uncertainty intervals.
- Break results down by year, sector, liquidity and market regime.
- Never claim success based on one cherry-picked period or metric.

## 11. Signal Ledger
For every signal preserve instrument ID, exchange/symbol, timestamp/timezone, data cutoff, source watermark, feature snapshot, rank/score meaning, explanation, rule/model version, parameters, training window, code commit, related event IDs, source evidence and data-quality warnings. Store later outcomes separately. Use append-only/versioned records so corrections do not silently rewrite what was known at signal time.

## 12. Dashboard and UX
Initial dashboard pages:
1. Market Overview: market/sector regime and data freshness.
2. Early Rally Candidates: ranked stocks, filters, score explanation and risk flags.
3. Stock Detail: price/volume, features, events, source evidence and comparable historical cases.
4. Corporate Intelligence: event timeline, confirmation status and source links.
5. Backtest Lab: assumptions, test period, benchmark, performance, failures and subgroup results.
6. Signal Journal: past signals and later outcomes.
7. Watchlists/Alerts: later phase, configurable and evidence-based.
8. System Health: missing data, failed imports, stale feeds and last successful run.

Never hide missing data, uncertainty or downside risk. Do not present a model score as a guaranteed probability or personal investment advice.

## 13. Data providers, APIs, scraping and budget
Start with EOD data. Evaluate official exchange files/APIs, company disclosures and suitable licensed vendors. Compare coverage, historical depth, timestamp semantics, corporate-action/delisted coverage, update frequency, rate limits, support, cost, retention, commercial use and redistribution rights. Use permitted retrieval only. Scraping is not automatically free or licensed. Record current official quotations and date before purchase. Keep secrets in environment variables; never commit API keys or bulk vendor data.

## 14. Technology stack
- Python 3.11+
- pandas/NumPy
- pytest/Ruff
- SQLite/local Parquet initially; PostgreSQL if concurrency/history requires it
- Streamlit initial dashboard
- scikit-learn, LightGBM, XGBoost after baseline pipeline is stable
- GitHub Actions CI
- Environment-based secrets/configuration
Prefer a modular monolith over premature microservices. No GPU/cloud spend is necessary for the first rules/tabular-model prototype.

## 15. Repository and current status
**Only authorized repository:** https://github.com/adrsh-raj/blumberg (private).  
**Development branch:** `feat/foundation-bootstrap`.  
**Do not merge to `main` without explicit permission. Do not touch other repositories.**

Known commits at last check:
- Main baseline: `7d6445176011285f9d4f52cf9a42fded7c462ad0`
- Foundation scaffold: `1d5e89a76c555bcd85c9e2c6b5a3e2e918c7bd01`
- Project memory: `2935ada54cffc14fcbc65abc94365992876f64cf`

Scaffold includes README, .gitignore, .env.example, pyproject.toml, requirements-dev.txt, OHLCV validation, technical features, a simplified next-bar smoke-test helper, 8 synthetic-data tests, architecture/data-governance/phase-gate docs and a GitHub Actions workflow.

Previously reported local result: 8/8 synthetic tests passed. Last recorded GitHub Actions status was queued, so re-check live CI and rerun tests before claiming current verification.

### Not implemented yet
No production market-data connector/dataset, no complete point-in-time universe, no production corporate-action adjustment, no production-grade backtester, no trained/validated ML, no news/order NLP, no dashboard, no alerts, no brokerage execution, and no demonstrated profitability. Never describe planned work as completed.

## 16. Phased roadmap and exit criteria
**Phase 0 — Foundation:** verify clean install, tests, lint and CI; keep secrets/data out of Git.

**Phase 1 — Source/data contract:** compare official/licensed sources; document rights, coverage, history, timestamps, cost, rate limits and retention. Agree EOD source/schema and spending cap before connectors.

**Phase 2 — Market data:** security master, symbol history, permitted OHLCV imports, provenance, calendars/benchmarks, corporate actions, adjusted/unadjusted semantics, reconciliation and data-quality reports.

**Phase 3 — Scanner:** normalized returns, benchmark/sector strength, prior-window volume, liquidity, volatility, breakout features, risk flags and explainable/versioned ranking.

**Phase 4 — Ledger/backtest:** immutable snapshots, frozen labels, executable entry assumptions, costs/slippage/circuits, walk-forward validation, benchmarks and subgroup reports.

**Phase 5 — Corporate intelligence:** approved ingestion, timestamp normalization, event classification/extraction, evidence links, deduplication, amendment/cancellation links and human review.

**Phase 6 — Model comparison:** baseline, Logistic Regression, Random Forest, LightGBM, XGBoost; time-aware tests, ablation, calibration, stability and after-cost comparisons.

**Phase 7 — Dashboard/alerts:** candidate ranking, explanations, risks, events/evidence, filters/watchlists, historical performance and system health.

**Phase 8 — Paper tracking/release:** log signals without real orders, reconcile outcomes, monitor drift/false positives, and complete security/recovery/data-rights review.

A phase is complete only when code, tests, documented evidence and acceptance criteria are verified.

## 17. Rules for every AI coding session
1. Read this brief and repository `docs/PROJECT_MEMORY.md`, `docs/ARCHITECTURE.md`, `docs/DATA_GOVERNANCE.md`, `docs/PHASE_GATES.md`.
2. First inspect live branch/head, status/diff, files and CI; live repo overrides stale memory.
3. Work only in `adrsh-raj/blumberg`; never touch another repo.
4. Do not merge to main without explicit approval.
5. State phase/subphase, planned changes and acceptance tests before coding.
6. Make small cohesive changes; test/lint before commit; report network/package blockers honestly.
7. Update roadmap/memory only after verified work.
8. Separate synthetic tests from historical backtest and live paper evidence.
9. Never invent test results, provider costs/rights, data, model accuracy or profitability.
10. Never commit secrets, credentials, private data or unlicensed datasets.
11. Never claim code ran on the user's PC unless that environment was actually accessed.
12. Report in plain Hinglish: changed files, evidence, branch/commit, blockers and next step.

## 18. Immediate next steps
1. Check latest GitHub Actions result and rerun 8 synthetic tests in a clean environment.
2. Confirm this brief and `docs/PROJECT_MEMORY.md` match live repo.
3. Complete Phase 1 source/provider audit with current official information and licensing notes.
4. Agree the first EOD source and spending cap.
5. Start Phase 2 only after the data contract is explicit.

## 19. Copy/paste resume prompt for another AI
You are continuing Blumberg Market Radar Terminal. Read this complete Master Product Brief and `docs/PROJECT_MEMORY.md` before responding or editing. First inspect the live repository `adrsh-raj/blumberg`, current branch/head, git status, files and GitHub Actions. Work only on `feat/foundation-bootstrap` unless explicitly told otherwise. Never touch another repository or merge to `main` without explicit approval. Resume from Immediate next steps. Make small tested changes, update phase status/memory only with verified evidence, and distinguish planned features from implemented work. The objective is an evidence-driven Indian-equities early-rally research and backtesting platform—not guaranteed stock predictions.

## Final principle
Every signal must be explainable, every event must have traceable evidence, every historical result must respect what was knowable at the time, and every claim of model quality must be backed by out-of-sample tests.
