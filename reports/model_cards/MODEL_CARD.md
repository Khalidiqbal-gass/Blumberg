# Model Card: Blumberg Early-Rally Learning-to-Rank Engine

**Phase 6 Acceptance Gate Specification**  
**Version:** `0.1.0-phase6`  
**Model Family:** Pairwise Learning-to-Rank (LambdaRank via LightGBM)  
**Evaluated On:** Out-of-Sample Walk-Forward Test Set with 20-Day Embargo Buffer  
**Status:** `GATE_PASSED — CANDIDATE READY FOR PAPER TRACKING`  

---

## 1. Model Details

- **Model Identifier:** `blumberg-ltr-lgbm-v0.1`
- **Architecture:** Gradient Boosted Decision Tree (GBDT) Ranker
- **Objective Function:** `lambdarank` (Direct pairwise optimization of Normalized Discounted Cumulative Gain)
- **Target Label:** 20-trading-day forward gross return:
  $$\text{Forward Return}_{i, t} = \frac{\text{Close}_{i, t+20}}{\text{Close}_{i, t}} - 1.0$$
- **Relevance Grades:** 4 discrete ordinal grades cross-sectionally ranked per query date:
  - `Grade 3`: Top quartile (Strong Early-Rally Candidate)
  - `Grade 2`: Upper-mid quartile (Moderate Outperformance)
  - `Grade 1`: Lower-mid quartile (Market In-Line)
  - `Grade 0`: Bottom quartile (Laggard / Underperformance)
- **Primary Framework:** LightGBM 4.x with fallback to Scikit-learn HistGradientBoosting
- **Training Date:** 2026-10-21

---

## 2. Intended Use & Governance Scope

### Primary Intended Use
- **Cross-Sectional Early Rally Ranking:** Ranks equities across the Indian universe (NSE/BSE) at each daily market close $t$ based on probability of 20-day momentum continuation.
- **Priority Signal Filter:** Provides systematic, objective ordering to replace or augment heuristic rule-based radar scores.
- **Watchlist Curation:** Surfaces Top-3 to Top-5 liquid high-probability momentum candidates for equity research analysts and discretionary execution.

### Out-of-Scope & Prohibited Uses
- **No Autonomous Direct Order Execution:** Must NOT be connected directly to broker execution gateways without human review (strictly complies with Phase 7 & 8 gates).
- **No Intraday High-Frequency Trading:** Not calibrated for sub-daily tick intervals or market-making.
- **No Illiquid / Micro-Cap Trading:** Ineffective on instruments with daily turnover $< \text{₹}1.0\text{ Cr}$ due to severe price-impact slippage and circuit restrictions.
- **No Derivative / Leverage Speculation:** Calibrated strictly on cash-market equities.

---

## 3. Training & Validation Data Partitioning

| Parameter | Specification | Purpose / Leakage Control |
| :--- | :--- | :--- |
| **Training Window** | `2025-08-28` to `2026-05-28` | Multi-month initial walk-forward regime |
| **Embargo Buffer** | **20 Trading Days** | **Strictly purges 20-day forward return overlap leakage between train and test** |
| **Out-of-Sample Test Window** | `2026-06-26` to `2026-09-23` | Untouched test window reflecting unseen market conditions |
| **Query Group Structure** | Date-based groups (`group = [N_stocks]_{t}`) | Pairwise comparison within the same market session |
| **Total Test Dates** | `64` dates | Out-of-sample sample size |
| **Total Test Observations** | `1280` stock-dates | Cross-sectional sample size |

---

## 4. Empirical Performance vs Rule-Based Baseline

Evaluated on the **untouched out-of-sample test window** after the 20-day embargo period:

| Evaluation Metric | ML Ranker (LightGBM) | Rule Baseline (`radar_score`) | Delta / Lift | Acceptance Criteria |
| :--- | :---: | :---: | :---: | :---: |
| **Spearman Rank Correlation (IC)** | **+0.0431** | +0.0377 | **+0.0053** | $\Delta \ge 0$ |
| **Top-3 Out-of-Sample Excess Return** | **+1.61%** | -0.69% | **+2.30%** | Outperform baseline |
| **Top-5 Out-of-Sample Excess Return** | **+0.95%** | +0.02% | **+0.92%** | Outperform baseline |
| **Top-3 Absolute Return** | **+2.50%** | +0.20% | **+2.30%** | Positive alpha |
| **NDCG@5** | **0.5453** | 0.4777 | **+0.0677** | High ranking fidelity |
| **Top-3 Win Rate vs Benchmark** | **71.9%** | 46.9% | **+25.0%** | $> 50\%$ win rate |
| **Information Ratio (IC / $\sigma_{IC}$)** | **0.24** | 0.12 | **+0.12** | Consistent alpha |

> **Key Finding:** The Machine Learning Ranker provides measurable outperformance over the rule-based radar heuristic across Spearman Rank Information Coefficient and Top-N forward returns on unseen out-of-sample data.

---

## 5. Feature Importances

Ranked contribution of multi-factor signals to the LambdaRank model:

| Rank | Feature Identifier | Split / Gain Importance | Relative Weight |
| :---: | :--- | :---: | :---: |
| 1 | `avg_turnover_20d_cr` | 589.00 | 19.6% |
| 2 | `return_60d` | 404.00 | 13.5% |
| 3 | `volatility_20d` | 398.00 | 13.3% |
| 4 | `dist_to_52w_high_pct` | 385.00 | 12.8% |
| 5 | `return_20d` | 357.00 | 11.9% |
| 6 | `atr_pct` | 326.00 | 10.9% |
| 7 | `return_5d` | 234.00 | 7.8% |
| 8 | `turnover_cr` | 198.00 | 6.6% |
| 9 | `relative_volume_20d` | 108.00 | 3.6% |
| 10 | `is_breakout_20d` | 1.00 | 0.0% |
| 11 | `rs_20d` | 0.00 | 0.0% |

---

## 6. Failure Modes, Edge Cases & Risk Mitigations

1. **Upper and Lower Circuit Freezes (Indian Equities):**
   - *Failure Mode:* An early-rally candidate may trigger a high ranking score while locked at the 5%, 10%, or 20% upper circuit limit, making execution impossible at the closing price.
   - *Mitigation:* The scanner flags locked stocks (`is_circuit_locked`); execution models enforce next-session market-open fill simulations.
2. **Severe Market Drawdowns / Macro Panics:**
   - *Failure Mode:* During widespread index-level drawdowns, positive momentum factors experience sharp reversals (momentum crash).
   - *Mitigation:* ATR% volatility filter and stop-loss risk controls (8% default threshold) must be active during live deployment.
3. **Turnover Decay and Liquidity Illusion:**
   - *Failure Mode:* Small-cap stocks displaying sudden 1-day volume spikes may exhibit negligible 20-day average liquidity.
   - *Mitigation:* Hard constraint requiring average daily traded value $\ge \text{₹}1.0\text{ Cr}$ (`turnover_cr` filter).
4. **Data Staleness & Corporate Action Distortions:**
   - *Failure Mode:* Unadjusted stock splits or bonus issues can falsely emulate a 50% drawdown or price collapse.
   - *Mitigation:* Ingestion pipeline enforces corporate action reconciliation and strict timestamp validation.

---

## 7. Phase 6 Gate Compliance Checklist

- [x] **Baseline First:** Rule-based heuristic (`radar_score`) benchmarked prior to ML evaluation.
- [x] **Defined Outcome Horizon:** Fixed 20-day forward return ($close_{t+20} / close_t - 1.0$) established before testing.
- [x] **Time-Aware Splitting:** Strictly forward temporal train/test split (no random shuffling).
- [x] **Leakage Prevention:** 20-day embargo buffer between train and test windows eliminates overlapping outcome windows.
- [x] **Untouched Test Windows:** Model hyperparameter tuning isolated from test evaluation window.
- [x] **Model Governance Card:** Comprehensive model card and failure mode documentation generated and versioned.

---

## 8. Governance Sign-Off

| Stakeholder Role | Verification Method | Status | Date |
| :--- | :--- | :---: | :---: |
| **Lead ML Ranking Engineer** | Out-of-sample walk-forward validation & NDCG verification | `APPROVED` | 2026-10-21 |
| **Quantitative Risk Officer** | Embargo buffer verification & circuit failure mode review | `APPROVED` | 2026-10-21 |
| **Product Governance Lead** | Phase 6 acceptance criteria compliance check | `APPROVED` | 2026-10-21 |
