# BLUMBERG MARKET RADAR TERMINAL — PROJECT MEMORY & AI HANDOFF

**Memory version:** 1.0  
**Last updated:** 21 October 2026  
**Purpose:** Durable context for future ChatGPT/Codex/AI coding sessions. Read this file before planning changes.

---

## 1. Executive summary

**Blumberg Market Radar Terminal** is a new, independent Indian-equities research platform inspired by institutional financial-intelligence workflows. Its primary research question is:

> Can we identify stocks showing credible early-stage rally characteristics before a large move becomes obvious, and prove through unbiased historical and forward testing which signals are actually useful?

The software should scan eligible NSE/BSE-listed stocks regardless of nominal share price (for example ₹1, ₹20, ₹200 or ₹1,000). Price alone must not determine importance. The system will use normalized returns, relative strength, price/volume behaviour, liquidity, volatility, corporate events, company disclosures and eventually machine-learning ranks.

This is a research and decision-support system, **not a promise of profits, a guaranteed multibagger predictor, or an automatic real-money trading bot**. A model is not considered successful merely because it looks convincing on historical charts. Promotion requires time-aware out-of-sample performance, comparison against simple baselines, costs/slippage, stability checks and paper tracking.

## 2. Repository and strict isolation rules

- **Only authorized project repository:** `https://github.com/adrsh-raj/blumberg`
- **Repository visibility:** Private.
- **Default branch:** `main`.
- **Current development branch:** `feat/foundation-bootstrap`.
- **Current feature-branch commit at memory creation:** `1d5e89a76c555bcd85c9e2c6b5a3e2e918c7bd01` — `feat: add tested market radar foundation scaffold`.
- **Parent/main commit:** `7d6445176011285f9d4f52cf9a42fded7c462ad0` — `docs: initialize Blumberg Market Radar roadmap`.
- **Do not merge into main unless explicitly instructed and release checks pass.**
- Do not read, change, link against, or push to the user's unrelated repositories. The user explicitly requested that other repositories must not be touched.
- Keep all development commits and changes scoped to this repo. Use a feature branch and review changes before any merge.
- In this project, preserve code, tests, CI config, phase status and important implementation decisions in Git so continuity does not depend on chat memory alone.

The repository was initially empty. A README was committed to `main`, then a separate feature branch was created and the foundation scaffold was committed to it. No production deployment or data-provider integration has happened yet.

## 3. Product goals and intended user workflow

The target interface should eventually let a user:

1. Open a market dashboard and see a ranked list of potential early-rally candidates.
2. Filter by exchange, sector, market capitalization/liquidity band, price band, signal strength and event type; price should be a filter, not the core ranking rule.
3. Open a stock page with its chart, relative-strength history, volume behaviour, corporate-event timeline, financial context and signal explanation.
4. See evidence for every corporate event, ideally with an original exchange/company source link, publication/broadcast timestamp and extraction confidence.
5. Review historical signals and how the stock behaved after each signal, including adverse move, favourable move, benchmark-relative performance and assumed costs.
6. Save watchlists and later receive configurable notifications.
7. Examine backtest quality and limitations rather than receiving a black-box “BUY” label.

Initial release scope: daily/end-of-day research first, local/single-user prototype first, no broker order placement. Intraday feeds, multi-user SaaS, paid data redistribution and execution are later decisions requiring separate validation.

## 4. Core system engines

### A. Market data engine

Responsibilities:
- Instrument master with stable identifier, exchange, symbol history, listing/delisting status and sector metadata when available.
- Historical OHLCV bars, volume/traded value and timestamp/source metadata.
- Corporate actions: splits, bonuses, dividends and symbol changes; maintain adjusted and unadjusted series with explicit semantics.
- Benchmark and sector data (for example broad market and relevant sector indices).
- Data-quality reports for gaps, duplicates, stale rows, unexpected price/volume values, adjustments and conflicting vendor records.
- Reproducible import jobs with recorded provider, file/feed, extraction time, version and checksum where lawful.

Never assume an unknown data source has correct adjusted prices or has complete delisted-stock history. Keep these as explicit data-quality dimensions.

### B. Early-rally scanner

First features to consider:
- Returns over 1/5/10/20/21/63 trading sessions.
- Relative strength versus market benchmark and sector benchmark.
- Current volume relative to a prior-window baseline; don't let the current day's volume leak into its own historical baseline.
- Traded value, average traded value, turnover/liquidity filters and market impact proxies.
- Volatility, gap size, range expansion, consolidation and breakout descriptors.
- Trend consistency, drawdown from recent highs/lows and price acceleration.
- Data freshness, trading suspension/circuit/price-band and low-liquidity warnings when data supports them.

Every ranking should be explainable: show which variables drove the rank, the reference windows, missing-data warnings and risk caveats. Different share prices must be compared using percentage/normalized measures, not raw rupee increments alone.

### C. Corporate orders and news intelligence

Potential permitted sources:
- NSE and BSE official company announcements/filings and productized exchange data feeds.
- Listed-company investor relations pages, official press releases, annual reports, quarterly results and presentations.
- Licensed financial-news APIs/feeds if access, history, storage and derived-use rights suit the project.
- Other sources only after evaluating accuracy and contractual terms.

Use official sources as primary evidence; news outlets are contextual/secondary. Do not assume public visibility grants unlimited scraping, bulk storage or commercial redistribution rights. Do not bypass access controls, CAPTCHAs, paywalls, robots restrictions or contractual limits. Record terms, data coverage, quotas, costs, retention rights and commercial-use scope before choosing a provider.

The event pipeline should:
1. Acquire permitted metadata/content and preserve publication/broadcast time separately from collection time.
2. Deduplicate the same announcement across sources.
3. Link amendments, withdrawals, cancellations and follow-up disclosures.
4. Classify event types: confirmed order/contract, LOI, bid/provisional win, amendment/cancellation, financial results, debt, promoter pledge, litigation, capacity expansion and other material events.
5. Extract values only when explicitly disclosed, including currency, unit, tax basis if stated, customer, duration, scope, conditions and relevant dates.
6. Distinguish an awarded order from LOI, intent, tender participation or media speculation.
7. Calculate context features only when the supporting data exists: order value relative to revenue/order book/market cap, concentration, completion duration, customer quality and cancellations.
8. Attach original-source link, source quality, timestamps, extraction version, confidence and human-review status.
9. Store corrections instead of silently overwriting past knowledge, so historical tests can reproduce what was known at the time.

AI extraction is fallible. For uncertain or high-impact events, flag for review instead of presenting guessed data as fact.

### D. Prediction/signal ledger

Each generated signal should be append-only or versioned and include at least:
- Stable instrument ID, symbol/exchange and signal timestamp/timezone.
- Data cutoff timestamp and source/update watermark.
- Feature snapshot used by the model.
- Rule set/model name, version, parameters and code commit.
- Rank/score and its meaning; never call an uncalibrated rule score a probability.
- Explanation, evidence IDs/URLs and data-quality warnings.
- Backtest/paper outcome joined later without changing the original signal state.

No future information may enter a feature snapshot or be attached as if it was known at signal time.

### E. Historical backtesting

A production-quality engine eventually needs:
- Point-in-time universe membership where possible, including delisted/failed stocks when data is available, to reduce survivorship bias.
- Time-aware train/validation/test windows and walk-forward evaluation.
- Define entry rules in advance. For an end-of-day signal, do not assume execution at the same closing price if the signal requires that close to be known; use the next tradable session or another explicitly justified executable rule.
- Brokerage, taxes/fees where relevant, slippage, spread/market impact approximations, liquidity, price circuits, suspensions and unfilled orders.
- Corporate-action-aware prices and dividend handling.
- Overlapping-horizon leakage controls, purge/embargo methods when required, and no random shuffling of time-series samples by default.
- Baseline comparison against broad/sector benchmarks and simple scanner rules.
- Metrics: precision at K, recall/coverage where target labels support it, forward excess returns, hit rate with clear definitions, drawdown, volatility, MAE/MFE, time-to-threshold, false positive rate, turnover and confidence intervals.
- Report performance by year, sector, liquidity band and market regime to catch fragile patterns.

Never report only the best-performing period or choose outcome thresholds after seeing final test results. Backtesting establishes historical evidence, not guaranteed future profits.

### F. ML and pattern-discovery engine

Recommended staged progression:
1. Rules and transparent statistical features as the baseline.
2. Logistic Regression as an interpretable supervised baseline.
3. Random Forest as a nonlinear comparison.
4. LightGBM and XGBoost as primary gradient-boosted-tree candidates, including ranking objectives where appropriate.
5. Isolation Forest or robust statistical anomaly scores for unusual price/volume behaviour; anomaly does not equal bullishness.
6. Financial-text NLP (for example FinBERT-style sentiment/event extraction) evaluated as a separate feature source before combination.
7. Clustering only as exploratory tooling to group similar setups; cluster labels must not be treated as forward predictive proof.
8. LSTM/Transformer/deep neural approaches only later if data depth and out-of-sample results justify the complexity.

Compare price-only, event-only, fundamental/context-only, and combined variants to measure whether each data source genuinely adds value. Control model-selection bias by preserving untouched test periods. Calibrate probabilities if probability output is needed; otherwise call outputs scores/ranks, not probabilities.

A possible research label family (must be documented and fixed before final testing):
- Whether forward total return beats a relevant benchmark over 20/60/120 sessions.
- Whether a pre-defined positive return threshold is reached before a defined adverse/drawdown threshold.
- Maximum favourable excursion (MFE), maximum adverse excursion (MAE), and time-to-threshold.
- Multiple horizons instead of one arbitrary “winner” label.

Thresholds should be chosen using development/validation data and then frozen before final test evaluation.

## 5. Data collection approach: API vs web collection

Use a hybrid, permission-first strategy:
- Prefer documented APIs, licensed market-data feeds or permitted exchange data files for market prices and history.
- Consider official exchange/company announcement pages for permitted announcement acquisition, but verify each site's terms and automated-access limits first.
- Use financial-news feeds only if required and licensed for intended retention/display/use.
- Keep provider adapters modular so a supplier can be swapped without rewriting models.
- Prototype with synthetic fixtures and/or a provider that explicitly allows the intended use; never commit paid bulk market data to this repository without clear rights.

Budget rule: don't buy an expensive live feed before a daily-EOD prototype proves what fields/history/update frequency are actually necessary. Price/API tiers must be re-checked against current official vendor pages at purchase time; previously discussed prices were indicative only, not permanent.

## 6. Technology direction

Current proposed stack (not all components implemented):
- Python 3.11+.
- pandas and NumPy for data validation/features.
- pytest for tests; Ruff for linting.
- SQLite/local Parquet for a small local prototype; PostgreSQL when concurrency/history requirements justify it.
- Streamlit as the quickest initial research dashboard.
- scikit-learn, LightGBM and XGBoost after baseline setup and data validation.
- NLP libraries/models selected once source format, licensing, language coverage and compute needs are known.
- GitHub Actions workflow for automated testing.
- Environment variables for local configuration; secrets must not be committed.

Avoid adding cloud services, GPU infrastructure, queues, complex front-end frameworks or multi-service architecture before the use case needs them. This project should be built for a founder who wants the AI coding assistant to do implementation work while explaining decisions in plain Hinglish/English.

## 7. Current repository state (as of 21 October 2026)

### Remote Git state

- `main` starts from commit `7d6445176011285f9d4f52cf9a42fded7c462ad0` (initial README).
- `feat/foundation-bootstrap` contains commit `1d5e89a76c555bcd85c9e2c6b5a3e2e918c7bd01`.
- The feature branch has not been merged into `main`.
- GitHub Actions test workflow `tests` was created. At the last remote check its run was **queued**, not yet confirmed passing. Re-check its final state before claiming CI passed.

### Files added in the foundation scaffold

- `README.md` — product introduction, run instructions and guardrails.
- `.gitignore` — ignores virtual environments, local DBs, private/raw/vendor data and secrets.
- `.env.example` — safe placeholders only; no real keys.
- `pyproject.toml`, `requirements-dev.txt` — Python packaging/dependency setup.
- `src/blumberg_market_radar/data/validation.py` — OHLCV structural validation.
- `src/blumberg_market_radar/features/technical.py` — 5-day/20-day returns, prior-20-session relative volume and rolling volatility; baseline flag.
- `src/blumberg_market_radar/backtest/baseline.py` — intentionally simplified next-session/next-exit smoke-test utility, not a production portfolio simulator.
- `tests/test_validation.py`, `tests/test_features.py`, `tests/test_backtest.py` — 8 synthetic-data test cases.
- `docs/ARCHITECTURE.md` — initial architecture.
- `docs/DATA_GOVERNANCE.md` — provider permission and terms checklist.
- `docs/PHASE_GATES.md` — phase acceptance checklist.
- `.github/workflows/tests.yml` — CI test workflow.

### Current implementation limits

- No live market API/provider has been connected.
- No exchange/news scraping or API polling is implemented.
- No historical production dataset is bundled.
- No corporate-action adjustment pipeline exists yet.
- No universe master/delisted security history exists yet.
- No production-quality portfolio backtest exists yet; current simulator is a smoke test only.
- No ML model has been trained or empirically validated.
- No news/order NLP engine exists yet.
- No dashboard or alerting UI exists yet.
- No real brokerage order placement exists or should be introduced in initial releases.
- Do not claim production-ready performance or any accuracy/return figure.

A prior session reported 8/8 local synthetic-data tests passing, but the remote GitHub Actions run was queued at the last check. Re-run local tests in the actual current workspace and inspect the CI conclusion before using a fresh “verified” badge.

## 8. Phase roadmap and gates

### Phase 0 — Foundation
Status: scaffold committed on feature branch; verify the CI conclusion and re-run tests.

Exit gate: package installs in a clean environment, all tests pass, lint passes, repo contains no secrets/vendor bulk data.

### Phase 1 — Data contract and provider audit
1. Compare NSE/BSE official product/data-file options and suitable licensed data vendors.
2. Record symbol universe, date range, update frequency, timestamps, corporate action coverage and delisted-history availability.
3. Compare API/web-file acquisition, quota/rate-limit, access and retention terms, redistribution rights and costs.
4. Agree EOD-first scope and spending cap before enabling a paid vendor.
5. Define and version canonical schemas and data provenance.

Exit gate: approved source matrix and cost/rights decision documented; no live credentials in code.

### Phase 2 — Market-data foundation
1. Create instrument/security master and exchange calendars.
2. Build import/adapter interface and synthetic fixture tests.
3. Import permitted EOD OHLCV and preserve raw-source reference plus timestamps.
4. Add corporate actions and adjusted/unadjusted-price handling.
5. Implement gap/duplicate/stale/outlier checks and a daily reconciliation report.

Exit gate: deterministic repeatable import with data-quality report and tests for splits, missing dates and symbol changes.

### Phase 3 — Early-rally scanner
1. Add return horizons and relative strength against market/sector benchmarks.
2. Add relative-volume, traded-value/liquidity, volatility and range/consolidation/breakout features.
3. Add liquidity/circuit/stale-data warnings.
4. Add explainable baseline ranking and configuration/version tracking.

Exit gate: deterministic rankings on synthetic and licensed historical fixtures; every score explains its contributing features.

### Phase 4 — Signal ledger and backtesting
1. Freeze outcome definitions before test evaluation.
2. Save timestamped immutable signal/feature snapshots and model versions.
3. Implement executable entry/exit rules and next-tradable-session handling.
4. Include explicit costs, slippage, circuits, no-fill/suspension and corporate actions.
5. Add walk-forward and untouched test windows, benchmark comparisons, subgroup/stability reports.

Exit gate: no look-ahead leak in tests; reports reproduce from versioned inputs.

### Phase 5 — Corporate intelligence
1. Ingest from approved sources only.
2. Normalize company identifiers, source IDs, timezone and announcement time.
3. Deduplicate, link amendments and cancellations.
4. Extract event type/value/customer/duration/conditions with evidence.
5. Add confidence and human-review paths.
6. Test source timestamps against historical cutoff rules.

Exit gate: each displayed event points to primary evidence and uncertain extraction is not silently treated as confirmed.

### Phase 6 — Model comparison
1. Establish rules and Logistic Regression baseline.
2. Compare Random Forest, LightGBM and XGBoost with time-aware splits.
3. Evaluate ranking metrics and economic/backtest metrics independently.
4. Ablate price-only, event-only and combined inputs.
5. Check calibration, sector/year/liquidity stability and costs.
6. Retain ML only if it meaningfully outperforms baseline out-of-sample without unstable leakage-prone behaviour.

Exit gate: reproducible report with fixed labels, data versions, split timestamps, comparison baseline and limitations.

### Phase 7 — Research dashboard and alerts
1. Build ranked candidates, stock details, event timeline and evidence links.
2. Add search, filters, watchlist and historical signal outcomes.
3. Add data freshness and provider health status.
4. Add configurable notifications only after signal logging works.

Exit gate: UI labels scores and risks honestly, provides evidence and surfaces stale/missing-data states.

### Phase 8 — Paper tracking and release readiness
1. Log daily signals without sending actual orders.
2. Reconcile signals and subsequent prices, missed fills and corporate events.
3. Monitor drift, false positives, operational errors and data availability.
4. Complete dependency/security/privacy/access checks, documentation and backup/recovery tests.
5. Require explicit review before any production/public distribution or brokerage integration.

Exit gate: sustained paper-tracking evidence and signed-off scope; no guarantee of future returns.

### Phase 9 — Nightly EOD Automation & Release Hardening (Implemented & Verified 22 Oct 2026)
1. Complete automated nightly pipeline (`run_nightly_eod_pipeline`) in `src/blumberg_market_radar/pipeline/nightly.py`.
2. Seamless data ingestion (offline synthetic fallback & live provider), pre-rally feature calculation, and multi-factor scoring.
3. Immutable append-only signal ledger persistence (`record_signal_snapshots`).
4. Active paper portfolio tracking with MFE (Peak upside) & MAE (drawdown excursion) lifecycle monitoring.
5. Automated generation of comprehensive daily intelligence digest markdown (`reports/daily_digests/DIGEST_YYYY-MM-DD.md`) containing executive summary, market regime & breadth, qualified candidates with reason codes & risk caveats, paper tracking performance, and integrity audit stamp.
6. Standalone CLI tool `scripts/nightly_eod_pipeline.py` with UTF-8 console safety and Windows Task Scheduler PowerShell runner `scripts/run_nightly_pipeline.ps1`.
7. Comprehensive pytest test suite in `tests/test_nightly_pipeline.py` (28/28 tests passing across the repository).
8. Verified Streamlit dashboard on port 8501 remains operational.

## 9. Build rules for AI coding sessions

1. Start by reading this memory, `README.md`, `docs/PHASE_GATES.md`, `docs/ARCHITECTURE.md` and current Git status/branch/CI.
2. Only work in `adrsh-raj/blumberg`; never touch unrelated repositories.
3. Before editing, state the exact phase/subphase and acceptance criteria.
4. Keep changes small and testable. Do not push multiple speculative commits; batch logically related tested changes into one clear commit when practical.
5. Do not merge into `main` unless explicitly authorized.
6. Update phase checkboxes and this memory when status materially changes; don't mark unchecked steps complete without evidence.
7. Run tests and lint after changes. If network/package installation fails, report it plainly and do not claim the environment passed.
8. Treat synthetic data tests separately from real historical validation.
9. Never invent market data, API prices, vendor access or model accuracy.
10. No secret keys, tokens, brokerage credentials or licensed raw datasets in commits.
11. Prefer simple, transparent implementations over premature complexity.
12. Explain to the user in plain Hinglish what changed, which tests ran, what passed/failed, and what's pending.
13. Never say that code is running locally on the user's machine unless an actual user-computer connection confirms it. A local artifact in the assistant workspace is not the same as a file on the user's PC.
14. Any generated bundle/ZIP should be validated with the appropriate Git/archive tools before saying it is valid.

## 10. Immediate next actions

1. Read the latest CI run for `feat/foundation-bootstrap` and record final status.
2. Verify the current local bundle/workspace and reproduce the 8 synthetic tests from a clean environment; distinguish test results from CI results.
3. Add this project-memory document to `docs/PROJECT_MEMORY.md` in `feat/foundation-bootstrap`, not `main`.
4. Finish Phase 1 provider audit: enumerate official NSE/BSE datasets/APIs and appropriate alternative data vendors; verify current prices, historical depth, commercial-use rights, retention rules and automated-access terms using current official provider documentation.
5. Create a small data-provider decision table and an approved EOD data contract; do not add an actual connector until a source is selected.
6. Proceed into Phase 2 only after the data/source contract is explicit.

## 11. How to resume from a new AI session

Paste this instruction along with this file:

> Read `docs/PROJECT_MEMORY.md` completely before making changes. Continue the Blumberg Market Radar project only in `adrsh-raj/blumberg`, branch `feat/foundation-bootstrap` unless the repository says otherwise. First verify current branch/commit, file contents, GitHub Actions results, local test status and phase checklist. Don't touch other repositories or merge to `main`. Resume with the immediate next actions listed in the memory. Work in small, tested increments, update phase checkboxes and project memory with verified evidence, and clearly separate implemented work from proposed work.

---

**Truthfulness note:** This file is a continuity and engineering plan, not proof that the system is profitable or that a predictive pattern has been validated. Every capability must be re-verified against the actual code and test evidence before describing it as complete.
