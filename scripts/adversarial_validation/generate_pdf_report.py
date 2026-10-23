"""Generate comprehensive, multi-page professional institutional PDF report for Adversarial Model Validation."""
import sys
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super(NumberedCanvas, self).showPage()
        super(NumberedCanvas, self).save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#718096"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 750, "Blumberg Market Radar — Adversarial Validation & Stress Audit (2015–2026)")
            self.setStrokeColor(colors.HexColor("#CBD5E0"))
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)
            
        # Footer
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 36, page_str)
        self.drawString(54, 36, "CONFIDENTIAL — BLUMBERG MARKET RADAR INDEPENDENT MODEL AUDIT")
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.5)
        self.line(54, 48, 558, 48)
        self.restoreState()

def build_pdf():
    out_dir = Path("reports/adversarial_validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "MASTER_ADVERSARIAL_VALIDATION_REPORT.pdf"
    
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    
    # Custom Typography Styles
    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        "CoverSub",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#2B6CB0"),
        spaceAfter=10
    )
    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11.5,
        textColor=colors.HexColor("#4A5568")
    )
    h1_style = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#1A365D"),
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )
    h2_style = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#2C5282"),
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11.5,
        textColor=colors.HexColor("#2D3748"),
        spaceAfter=5
    )
    bullet_style = ParagraphStyle(
        "Bullet_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11.5,
        textColor=colors.HexColor("#2D3748"),
        leftIndent=12,
        spaceAfter=3
    )
    verdict_badge_style = ParagraphStyle(
        "VerdictBadge",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#22543D"),
        alignment=1
    )
    table_hdr = ParagraphStyle(
        "TableHdr",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.white,
        alignment=1
    )
    table_cell = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#1A202C")
    )
    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#1A202C")
    )
    table_cell_c = ParagraphStyle(
        "TableCellC",
        parent=table_cell,
        alignment=1
    )
    table_cell_cb = ParagraphStyle(
        "TableCellCB",
        parent=table_cell_bold,
        alignment=1
    )

    story = []

    # =========================================================================
    # PAGE 1: TITLE, VERDICT & TOP 5 EMPIRICAL REASONS
    # =========================================================================
    story.append(Paragraph("Blumberg Market Radar — Master Adversarial Validation Brief", title_style))
    story.append(Paragraph("Systematic Bias, Loophole and Stress-Test Audit Protocol (2015–2026)", subtitle_style))
    story.append(Paragraph("<b>Audit Period:</b> 2015-01-01 to 2026-04-30 (11.3 Years / 2,796 Trading Days) &nbsp;|&nbsp; <b>Evaluation Protocol:</b> T0–T18 & F1–F13", meta_style))
    story.append(Paragraph("<b>Universe Reference:</b> 52 Primary Equities + 5 Catastrophic Bankrupt Injections (139,978 Daily Bars) &nbsp;|&nbsp; <b>Trades:</b> 1,757 Closed Positions", meta_style))
    story.append(Paragraph("<b>Auditor:</b> Quantitative Risk & Model Validation Desk &nbsp;|&nbsp; <b>Environment:</b> Python 3.12.10, NumPy, Pandas, ReportLab", meta_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1A365D"), spaceAfter=10))

    story.append(Paragraph("1. Executive Verdict & Decision Rule", h1_style))
    
    verdict_table_data = [
        [Paragraph("OFFICIAL AUDIT DETERMINATION: <b>CREDIBLE (MODERATED)</b>", verdict_badge_style)]
    ]
    vt = Table(verdict_table_data, colWidths=[504])
    vt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#C6F6D5")),
        ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor("#22543D")),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(vt)
    story.append(Spacer(1, 6))

    story.append(Paragraph("Applying the Section 5 Decision Rule strictly without bias, marketing narratives, or rationalization: The raw headline claim of '+11,353% cumulative alpha' was an unconstrained scalar sum of 1,757 non-concurrent trade returns, and the 52-stock pool suffered from ex-post selection bias. <b>However, when tested under extreme adversarial conditions, genuine and statistically significant quantitative alpha is conclusively confirmed.</b>", body_style))
    story.append(Paragraph("When subjected to a realistic capital-constrained ₹10 Lakh portfolio simulation, statutory Indian delivery costs (105.2 bps), penny-stock exclusion, catastrophic bankruptcies (YES Bank, Jet Airways, RCOM), 1-day execution delays, and 1,000 Monte Carlo random-entry null draws:", body_style))
    
    story.append(Paragraph("• <b>1. True Capital-Constrained Portfolio Net Alpha (+12.60% / year):</b> A 10-slot portfolio compounded ₹10 Lakhs to <b>₹99,20,407</b> (+892.0% total return, <b>+21.47% CAGR</b> vs NIFTY 50's <b>+8.87%</b>). Sharpe is <b>0.81</b>, Sortino is <b>1.79</b>, and Calmar is <b>1.10</b>.", bullet_style))
    story.append(Paragraph("• <b>2. Downside Risk Strictly Halved (-19.46% vs -38.40%):</b> Maximum drawdown is cut by 49.3% compared to NIFTY 50 (-19.46% vs -38.40%), providing robust capital preservation across the 2020 Covid crash and 2018 midcap bear market.", bullet_style))
    story.append(Paragraph("• <b>3. Signal Outperforms Random Chance (p = 0.0020):</b> In 1,000 Monte Carlo random-entry draws on the same price series and exit engine, the mean null Profit Factor was 2.11 vs Strategy <b>2.54</b> (<b>p = 0.0020</b>). Breakout timing adds <b>+2.03% net return per trade</b>.", bullet_style))
    story.append(Paragraph("• <b>4. Resilience to Catastrophic Bankruptcies:</b> Injected failures (YESBANK, IDEA, JETAIRWAYS, UNITECH, RCOM — 281 trades) were stopped out at -8% on 68.3% of entries, preserving a combined Profit Factor of <b>2.35</b> and average net return of <b>+5.92%</b>.", bullet_style))
    story.append(Paragraph("• <b>5. Zero Look-Ahead Leaks & Monotonic Layer Separation:</b> 50 point-in-time truncation scans confirmed 0 leaks; conditional forward PF expands monotonically from <b>2.54</b> (Layer 1) to <b>4.57</b> (Layer 2) to <b>8.11</b> (Layer 3) to <b>16.49</b> (Layer 4).", bullet_style))

    story.append(Spacer(1, 8))

    # Section 2: Headline Metrics Correction Table
    story.append(Paragraph("2. Corrected Headline Metrics: Marketing Claim vs Real Economic Truth", h1_style))
    
    metrics_data = [
        [Paragraph("Metric", table_hdr), Paragraph("Raw Claims (Unconstrained)", table_hdr), Paragraph("Audited (10-Slot Portfolio)", table_hdr), Paragraph("Benchmark (NIFTY 50)", table_hdr), Paragraph("Audit Determination", table_hdr)],
        [Paragraph("<b>Cumulative Return</b>", table_cell), Paragraph("+11,353% (Sum)", table_cell_c), Paragraph("<b>+892.0% (Compounded)</b>", table_cell_cb), Paragraph("+169.8%", table_cell_c), Paragraph("Misleading scalar sum replaced", table_cell)],
        [Paragraph("<b>Annualized CAGR</b>", table_cell), Paragraph("N/A (Scalar sum)", table_cell_c), Paragraph("<b>+21.47%</b>", table_cell_cb), Paragraph("+8.87%", table_cell_c), Paragraph("<b>+12.60% Annualized Net Alpha</b>", table_cell)],
        [Paragraph("<b>Max Drawdown</b>", table_cell), Paragraph("Not Reported", table_cell_c), Paragraph("<b>-19.46%</b>", table_cell_cb), Paragraph("-38.40%", table_cell_c), Paragraph("Portfolio drawdown cut by 49.3%", table_cell)],
        [Paragraph("<b>Sharpe Ratio (Rf=6.5%)</b>", table_cell), Paragraph("1.15 (Trade-level)", table_cell_c), Paragraph("<b>0.81</b>", table_cell_cb), Paragraph("0.25", table_cell_c), Paragraph("Strong risk-adjusted excess return", table_cell)],
        [Paragraph("<b>Sortino Ratio</b>", table_cell), Paragraph("2.45 (Trade-level)", table_cell_c), Paragraph("<b>1.79</b>", table_cell_cb), Paragraph("0.34", table_cell_c), Paragraph("5.2x higher downside efficiency", table_cell)],
        [Paragraph("<b>Calmar Ratio</b>", table_cell), Paragraph("Not Reported", table_cell_c), Paragraph("<b>1.10</b>", table_cell_cb), Paragraph("0.23", table_cell_c), Paragraph("4.8x higher return-to-drawdown", table_cell)],
        [Paragraph("<b>Profit Factor</b>", table_cell), Paragraph("2.54", table_cell_c), Paragraph("<b>2.19</b> (Post-105 bps fee)", table_cell_cb), Paragraph("N/A", table_cell_c), Paragraph("Survives full Indian statutory friction", table_cell)],
        [Paragraph("<b>Average Net Return</b>", table_cell), Paragraph("+6.46%", table_cell_c), Paragraph("<b>+5.62%</b> (Post-105 bps fee)", table_cell_cb), Paragraph("N/A", table_cell_c), Paragraph("Positive net expectancy per trade", table_cell)],
        [Paragraph("<b>Market Beta (β)</b>", table_cell), Paragraph("N/A", table_cell_c), Paragraph("<b>0.11</b>", table_cell_cb), Paragraph("1.00", table_cell_c), Paragraph("Uncorrelated idiosyncratic alpha", table_cell)],
    ]
    mt = Table(metrics_data, colWidths=[105, 95, 105, 75, 124])
    mt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1A365D")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F7FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(mt)

    # =========================================================================
    # PAGE 2: COMPLETE T0-T18 TEST MATRIX
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("3. Adversarial Test Results Matrix (T0 to T18)", h1_style))
    story.append(Paragraph("Complete empirical verification across all 19 adversarial tests specified in the brief:", body_style))
    
    t_table_data = [
        [Paragraph("Test ID & Name", table_hdr), Paragraph("Vulnerability Audited", table_hdr), Paragraph("Metric Before Audit", table_hdr), Paragraph("Metric After Adversarial Audit", table_hdr), Paragraph("Status", table_hdr)],
        [Paragraph("<b>T0: Data Integrity</b>", table_cell), Paragraph("Bad ticks, negative prices, splits", table_cell), Paragraph("Assumed clean", table_cell_c), Paragraph("0 bad ticks. Found VEDL unadjusted split drop", table_cell), Paragraph("<b>FRAGILE</b>", table_cell_c)],
        [Paragraph("<b>T1: Spec-Code Audit</b>", table_cell), Paragraph("Loop off-by-one, stop logic", table_cell), Paragraph("Matches spec", table_cell_c), Paragraph("Confirmed range(n-1) bug & stop asymmetry", table_cell), Paragraph("<b>BUG CONFIRMED</b>", table_cell_c)],
        [Paragraph("<b>T2: Look-ahead Leak</b>", table_cell), Paragraph("Future bar leakage, bfill", table_cell), Paragraph("Point-in-time", table_cell_c), Paragraph("0 leaks across 50 point-in-time truncation tests", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T3: Cost Truth</b>", table_cell), Paragraph("Understated friction (30 bps)", table_cell), Paragraph("PF = 2.54", table_cell_c), Paragraph("PF = <b>2.19</b>, Avg Net = <b>+5.62%</b> (105.2 bps statutory)", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T4: Execution Feas.</b>", table_cell), Paragraph("Penny stocks (< ₹20), illiquidity", table_cell), Paragraph("All executed", table_cell_c), Paragraph("1,682 trades (95.7%) retained, PF = <b>2.23</b>", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T5: Survivorship Bias</b>", table_cell), Paragraph("Selecting past multibaggers only", table_cell), Paragraph("52 winners", table_cell_c), Paragraph("Injected 5 bankruptcies (YES, IDEA). PF = <b>2.35</b>", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T6: Random Null Test</b>", table_cell), Paragraph("Entry timing vs lucky price trends", table_cell), Paragraph("Undifferentiated", table_cell_c), Paragraph("Null PF = 2.11 vs Real <b>2.54</b> (<b>p = 0.0020</b>)", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T7: Component Abl.</b>", table_cell), Paragraph("Disentangle signal vs exit engine", table_cell), Paragraph("Single score", table_cell_c), Paragraph("Signal adds <b>+2.03% net ret</b> & <b>+0.43 PF</b>", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T8: Capital Sim.</b>", table_cell), Paragraph("Stacking concurrent trades", table_cell), Paragraph("+11,353% sum", table_cell_c), Paragraph("10-Slot Portfolio: <b>+21.47% CAGR</b>, MaxDD <b>-19.5%</b>", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T9: Outlier Removal</b>", table_cell), Paragraph("Dependency on mega-winners", table_cell), Paragraph("PF = 2.54", table_cell_c), Paragraph("Drop top 10: PF = <b>1.97</b>; Drop 2020 & 2023: PF = <b>1.56</b>", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T10: Bootstrap CI</b>", table_cell), Paragraph("Sample variance across clusters", table_cell), Paragraph("Point estimates", table_cell_c), Paragraph("1,000 draws: 95% CI PF = <b>[2.16, 2.99]</b>", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T11: Parameter Grid</b>", table_cell), Paragraph("Knife-edge parameter cliff", table_cell), Paragraph("Fixed params", table_cell_c), Paragraph("Smooth plateau across +/-20% grid (no cliff)", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T12: Walk-Forward</b>", table_cell), Paragraph("In-sample vs Out-of-sample drop", table_cell), Paragraph("Unified period", table_cell_c), Paragraph("IS (2015-19): PF = <b>1.21</b>; OOS (2020-26): PF = <b>3.53</b>", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T13: Cross-Universe</b>", table_cell), Paragraph("Overfitting to specific universe", table_cell), Paragraph("52 pooled", table_cell_c), Paragraph("Sub-Universe A: PF = <b>2.60</b>; Sub-Universe B: PF = <b>2.50</b>", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T14: Beta Regression</b>", table_cell), Paragraph("Market Beta disguised as alpha", table_cell), Paragraph("Unknown beta", table_cell_c), Paragraph("Beta = <b>0.11</b>, Annual Alpha = <b>+16.34%</b> (p<0.05)", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T15: Honest Layer-Lift</b>", table_cell), Paragraph("Day-0 hindsight vs forward lift", table_cell), Paragraph("Day-0 return", table_cell_c), Paragraph("Conditional forward PF: L1:2.54 -> L2:4.57 -> L4:16.49", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T16: Live Book Audit</b>", table_cell), Paragraph("Stale marks & loop execution", table_cell), Paragraph("29 open trades", table_cell_c), Paragraph("Loop bug fixed, Siemens exit & live marks aligned", table_cell), Paragraph("<b>BUG CONFIRMED</b>", table_cell_c)],
        [Paragraph("<b>T17: Slippage Stress</b>", table_cell), Paragraph("1-day entry delay & 2x friction", table_cell), Paragraph("Day t+1 fill", table_cell_c), Paragraph("Day t+2 fill + 210 bps friction: PF = <b>1.95</b>", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
        [Paragraph("<b>T18: Reconciliation</b>", table_cell), Paragraph("Reviewer 1,897 vs 1,757 count", table_cell), Paragraph("Report conflict", table_cell_c), Paragraph("Reviewer double-counted reasons + brackets (1757+140)", table_cell), Paragraph("<b>PASS</b>", table_cell_c)],
    ]
    tt = Table(t_table_data, colWidths=[85, 95, 75, 185, 64])
    tt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1A365D")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F7FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 2.2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.2),
    ]))
    story.append(tt)

    # =========================================================================
    # PAGE 3: ADJUDICATION OF THE 13 DESK REVIEW RED FLAGS (F1 to F13)
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("4. Adjudication of the 13 Desk Review Red Flags (F1 to F13)", h1_style))
    story.append(Paragraph("Detailed adjudication and empirical resolution of all desk review questions:", body_style))

    story.append(Paragraph("• <b>F1: Ex-Post Hindsight Universe Selection:</b> <i>Confirmed but Mitigated.</i> The 52-stock pool was selected ex-post from well-known multibaggers. However, in Test T5, injecting 5 catastrophic collapses (YESBANK, IDEA, Jet Airways, Unitech, RCOM) demonstrated that the -8% hard stop truncated downside, yielding a resilient 2.35 PF. In Test T13, splitting the universe symmetrically yielded identical performance (PF 2.60 vs 2.50).", body_style))
    story.append(Paragraph("• <b>F2: The '+11,353%' Summation Illusion:</b> <i>Confirmed and Officially Corrected.</i> Linearly adding 1,757 non-concurrent trade returns is an unphysical marketing number. In Test T8, this was replaced by a capital-constrained ₹10 Lakh portfolio simulation, which delivered an actual compounded equity of <b>₹99.20 Lakhs (+21.47% CAGR)</b>.", body_style))
    story.append(Paragraph("• <b>F3: Friction and Cost Invisibility:</b> <i>Refuted as Fatal; Upgraded to Full Statutory Costs.</i> The original trade table printed net execution prices after 30 bps friction. Under full statutory Indian delivery costs (STT 0.1% buy + 0.1% sell, GST, stamp duty, exchange, SEBI turnover) + tiered slippage (105.2 bps round trip), the system retains a strong <b>Profit Factor of 2.19</b>.", body_style))
    story.append(Paragraph("• <b>F4: Look-Ahead Leaks:</b> <i>Refuted.</i> Point-in-time truncation scans across 50 randomly sampled trading dates revealed 0 signal mismatches. Entries execute strictly on Day t+1 Open with zero future data leakage.", body_style))
    story.append(Paragraph("• <b>F5: Survivorship Bias:</b> <i>Confirmed in Universe; Defended by Stop Architecture.</i> Historical failures were not in the primary 52 list. However, empirical injection of bankruptcies in T5 confirmed that the strategy's risk rules successfully prevented catastrophic capital destruction.", body_style))
    story.append(Paragraph("• <b>F6: Signal-vs-Exit Conflation:</b> <i>Partially Confirmed; Disentangled via T6 & T7.</i> Trailing stops do provide substantial edge, but 1,000 Monte Carlo random-entry simulations confirmed that the radar breakout signal adds <b>+2.03% net return per trade</b> with statistical significance (<b>p = 0.0020</b>).", body_style))
    story.append(Paragraph("• <b>F7: Outlier Dependency:</b> <i>Refuted.</i> Removing Cummins India (+855%), the top 5, top 10 trades, or removing both the 2020 and 2023 bull runs leaves the strategy solidly profitable with Profit Factors between <b>1.56 and 2.43</b>.", body_style))
    story.append(Paragraph("• <b>F8: Arithmetic Inconsistencies:</b> <i>Resolved (Desk Review Error).</i> The desk review's count of 1,897 trades was an arithmetic error created by adding 3 exit reasons (1,757) to 4 return brackets (140). The real count is exactly 1,757.", body_style))
    story.append(Paragraph("• <b>F9: Live Book Final-Day Loop Bug:</b> <i>Confirmed and Fixed.</i> Simulation loop `range(n - 1)` stopped on the second-to-last bar, skipping 2026-04-30. Siemens trailing stop and peak prices on TCS, WIPRO, and HCLTECH were corrected in Test T16.", body_style))
    story.append(Paragraph("• <b>F10: Asymmetric Stop Evaluation (Low vs Close):</b> <i>Confirmed in System Specification.</i> Initial hard stops evaluate against intraday Low (`low <= entry * 0.92`), whereas trailing stops evaluate against daily Close. Formalized in documentation.", body_style))
    story.append(Paragraph("• <b>F11: Dormant Trailing Zone (+15% to +25%):</b> <i>Confirmed in System Specification.</i> Between +15% and +25%, the stop is set to breakeven, and trailing stop percentages activate only after +25% gain is reached.", body_style))
    story.append(Paragraph("• <b>F12: Layer Conditioning (Day 0 vs Forward Return):</b> <i>Validated and Proven Monotonic.</i> Conditional forward returns confirm that graduation across Layer 1 to Layer 4 expands unconditional win rates from 32.7% to 60.5% and Profit Factor from 2.54 to 16.49.", body_style))
    story.append(Paragraph("• <b>F13: Unadjusted Corporate Action Drop (Vedanta):</b> <i>Confirmed (Data Vendor Anomaly).</i> Yahoo Finance unadjusted drop in VEDL on 2026-04-30 noted. Production implementation must utilize corporate-action adjusted NSE Bhavcopy data.", body_style))

    # =========================================================================
    # PAGE 4: PORTFOLIO PERFORMANCE, BUGS, & INSTITUTIONAL SIGN-OFF
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("5. Detailed Capital-Constrained Portfolio Simulation Results (Test T8)", h1_style))
    story.append(Paragraph("Simulating a ₹10,00,000 (₹10 Lakhs) portfolio with 10 slots (10% allocation per trade) across 2015–2026:", body_style))

    eq_table_data = [
        [Paragraph("Year", table_hdr), Paragraph("Start Capital (₹)", table_hdr), Paragraph("End Capital (₹)", table_hdr), Paragraph("Strategy Return (%)", table_hdr), Paragraph("NIFTY 50 Return (%)", table_hdr), Paragraph("Annual Net Alpha (%)", table_hdr)],
        [Paragraph("2015", table_cell_c), Paragraph("10,00,000", table_cell_c), Paragraph("10,95,420", table_cell_c), Paragraph("+9.54%", table_cell_cb), Paragraph("-4.06%", table_cell_c), Paragraph("+13.60%", table_cell_cb)],
        [Paragraph("2016", table_cell_c), Paragraph("10,95,420", table_cell_c), Paragraph("12,38,110", table_cell_c), Paragraph("+13.03%", table_cell_cb), Paragraph("+3.01%", table_cell_c), Paragraph("+10.02%", table_cell_cb)],
        [Paragraph("2017", table_cell_c), Paragraph("12,38,110", table_cell_c), Paragraph("16,84,300", table_cell_c), Paragraph("+36.04%", table_cell_cb), Paragraph("+28.65%", table_cell_c), Paragraph("+7.39%", table_cell_cb)],
        [Paragraph("2018", table_cell_c), Paragraph("16,84,300", table_cell_c), Paragraph("16,12,500", table_cell_c), Paragraph("-4.26%", table_cell_cb), Paragraph("+3.15%", table_cell_c), Paragraph("-7.41%", table_cell_c)],
        [Paragraph("2019", table_cell_c), Paragraph("16,12,500", table_cell_c), Paragraph("17,85,400", table_cell_c), Paragraph("+10.72%", table_cell_cb), Paragraph("+12.02%", table_cell_c), Paragraph("-1.30%", table_cell_c)],
        [Paragraph("2020", table_cell_c), Paragraph("17,85,400", table_cell_c), Paragraph("28,42,100", table_cell_c), Paragraph("+59.19%", table_cell_cb), Paragraph("+14.90%", table_cell_c), Paragraph("+44.29%", table_cell_cb)],
        [Paragraph("2021", table_cell_c), Paragraph("28,42,100", table_cell_c), Paragraph("41,85,600", table_cell_c), Paragraph("+47.27%", table_cell_cb), Paragraph("+24.12%", table_cell_c), Paragraph("+23.15%", table_cell_cb)],
        [Paragraph("2022", table_cell_c), Paragraph("41,85,600", table_cell_c), Paragraph("43,65,200", table_cell_c), Paragraph("+4.29%", table_cell_cb), Paragraph("+4.32%", table_cell_c), Paragraph("-0.03%", table_cell_c)],
        [Paragraph("2023", table_cell_c), Paragraph("43,65,200", table_cell_c), Paragraph("68,92,400", table_cell_c), Paragraph("+57.89%", table_cell_cb), Paragraph("+19.42%", table_cell_c), Paragraph("+38.47%", table_cell_cb)],
        [Paragraph("2024", table_cell_c), Paragraph("68,92,400", table_cell_c), Paragraph("88,40,100", table_cell_c), Paragraph("+28.26%", table_cell_cb), Paragraph("+20.10%", table_cell_c), Paragraph("+8.16%", table_cell_cb)],
        [Paragraph("2025", table_cell_c), Paragraph("88,40,100", table_cell_c), Paragraph("96,15,300", table_cell_c), Paragraph("+8.77%", table_cell_cb), Paragraph("+7.50%", table_cell_c), Paragraph("+1.27%", table_cell_cb)],
        [Paragraph("2026 (YTD)", table_cell_c), Paragraph("96,15,300", table_cell_c), Paragraph("99,20,407", table_cell_c), Paragraph("+3.17%", table_cell_cb), Paragraph("+1.20%", table_cell_c), Paragraph("+1.97%", table_cell_cb)],
        [Paragraph("<b>Total (2015–26)</b>", table_cell_c), Paragraph("<b>10,00,000</b>", table_cell_c), Paragraph("<b>99,20,407</b>", table_cell_cb), Paragraph("<b>+21.47% CAGR</b>", table_cell_cb), Paragraph("<b>+8.87% CAGR</b>", table_cell_c), Paragraph("<b>+12.60% Annual Alpha</b>", table_cell_cb)],
    ]
    et = Table(eq_table_data, colWidths=[65, 85, 85, 95, 85, 89])
    et.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1A365D")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor("#F7FAFC")]),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#EDF2F7")),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(et)
    story.append(Spacer(1, 8))

    story.append(Paragraph("6. Code Bugs Identified & Institutional Remediation", h1_style))
    story.append(Paragraph("• <b>Bug 1: Off-by-One Loop Index Skipping Final Bar (T1, T16):</b> `range(entry_idx, n - 1)` stopped at bar `n - 2`, leaving 2026-04-30 un-evaluated. Siemens missed its trailing stop exit, and peak prices lagged on TCS and WIPRO. Remediation: Changed to `range(entry_idx, n)`. Verified clean trailing exit for Siemens at ₹3,024.10.", body_style))
    story.append(Paragraph("• <b>Bug 2: Stop Loss Asymmetry (T1, F10):</b> Initial stops evaluate against intraday Low, while trailing stops evaluate against daily Close. Formalized in strategy parameter definitions.", body_style))
    story.append(Spacer(1, 6))

    story.append(Paragraph("7. Institutional Deployment Recommendations & Audit Certificate", h1_style))
    story.append(Paragraph("1. <b>Retire Marketing Metric:</b> Formally eliminate '+11,353%' from all collateral; quote verified <b>+21.47% CAGR</b> and <b>+12.60% Annualized Net Alpha</b>.", bullet_style))
    story.append(Paragraph("2. <b>Point-in-Time Universe:</b> Transition scanner from static 52-stock list to active <b>NIFTY 500 point-in-time universe</b> to eliminate selection bias completely in live deployment.", bullet_style))
    story.append(Paragraph("3. <b>Execution Protocols:</b> Use Market-on-Open (MOO) smart order routing on Day t+1 to execute within statutory slippage budgets.", bullet_style))
    story.append(Spacer(1, 8))

    cert_data = [
        [Paragraph("<b>FINAL AUDIT DETERMINATION: CREDIBLE (MODERATED)</b><br/>The quantitative strategy demonstrates verified statistical edge, robust downside convexity, and genuine outperformance in the Indian equity markets.<br/><b>Signed:</b> Quantitative Risk & Model Validation Desk &nbsp;|&nbsp; <b>Date:</b> October 22, 2026", ParagraphStyle("CertText", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=12, textColor=colors.HexColor("#1A365D"), alignment=1))]
    ]
    ct = Table(cert_data, colWidths=[504])
    ct.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EBF8FF")),
        ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor("#2B6CB0")),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(ct)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated comprehensive multi-page institutional PDF report: {pdf_path}")

if __name__ == "__main__":
    build_pdf()
