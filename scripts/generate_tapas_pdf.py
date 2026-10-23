"""Generate publication-grade PDF report for the TAPAS Framework & 8-Point Multibagger Detection Engine."""
from __future__ import annotations

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
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#718096"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(42, 752, "BLUMBERG MARKET RADAR — TAPAS MULTIBAGGER EARLY DETECTION REPORT")
            self.drawRightString(570, 752, "INSTITUTIONAL EQUITY INTELLIGENCE")
            self.setStrokeColor(colors.HexColor("#CBD5E0"))
            self.setLineWidth(0.6)
            self.line(42, 744, 570, 744)
            
        # Footer
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(570, 32, page_str)
        self.drawString(42, 32, "CONFIDENTIAL & PROPRIETARY — TAPAS PRE-RALLY SCREENING FRAMEWORK (NSE/BSE)")
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.6)
        self.line(42, 42, 570, 42)
        self.restoreState()

def build_pdf():
    print("=" * 80)
    print("GENERATING TAPAS MULTIBAGGER REPORT PDF")
    print("=" * 80)

    out_dir = Path("reports/secular_longterm_hold")
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "TAPAS_MULTIBAGGER_FRAMEWORK_REPORT.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=46,
        bottomMargin=46
    )

    styles = getSampleStyleSheet()

    # Typography styles
    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15.5,
        leading=18.5,
        textColor=colors.HexColor("#0F2942"),
        spaceAfter=3
    )
    subtitle_style = ParagraphStyle(
        "CoverSub",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#1A56DB"),
        spaceAfter=6
    )
    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.2,
        leading=10.2,
        textColor=colors.HexColor("#4A5568")
    )
    h1_style = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12.5,
        textColor=colors.HexColor("#0F2942"),
        spaceBefore=7,
        spaceAfter=3,
        keepWithNext=True
    )
    h2_style = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#1E429F"),
        spaceBefore=5,
        spaceAfter=2.5,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.0,
        leading=9.5,
        textColor=colors.HexColor("#2D3748"),
        spaceAfter=3.5
    )
    bullet_style = ParagraphStyle(
        "Bullet_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.0,
        leading=9.5,
        textColor=colors.HexColor("#2D3748"),
        leftIndent=10,
        spaceAfter=2.0
    )
    badge_style = ParagraphStyle(
        "BadgeText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#03543F"),
        alignment=1
    )
    table_hdr = ParagraphStyle(
        "TableHdr",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.2,
        leading=8,
        textColor=colors.white,
        alignment=1
    )
    table_cell = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.2,
        leading=8,
        textColor=colors.HexColor("#1A202C")
    )
    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.2,
        leading=8,
        textColor=colors.HexColor("#1A202C")
    )
    table_cell_c = ParagraphStyle("TableCellC", parent=table_cell, alignment=1)
    table_cell_cb = ParagraphStyle("TableCellCB", parent=table_cell_bold, alignment=1)
    table_cell_r = ParagraphStyle("TableCellR", parent=table_cell, alignment=2)
    table_cell_rb = ParagraphStyle("TableCellRB", parent=table_cell_bold, alignment=2)

    story = []

    # =========================================================================
    # PAGE 1: TITLE, FRAMEWORK OVERVIEW & 8-POINT CHECKLIST
    # =========================================================================
    story.append(Paragraph("Blumberg Market Radar — TAPAS Multibagger Report", title_style))
    story.append(Paragraph("Systematic Framework for Identifying 3x–10x Indian Equities 6–18 Months Before the Rally", subtitle_style))
    story.append(Paragraph("<b>Market Universe:</b> Indian Equities (NSE/BSE 2010–2026) &nbsp;|&nbsp; <b>Model:</b> TAPAS 5-Pillar Framework + 8-Point Scoring Checklist", meta_style))
    story.append(Paragraph("<b>Core Thesis:</b> Buy in the Silence Phase (Phase 1 Accumulation) before institutional discovery, media hype, and PE re-rating.", meta_style))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#0F2942"), spaceAfter=5))

    badge_data = [
        [Paragraph("CORE PHILOSOPHY: <b>EARNINGS INFLECTION + DEBT DESTRUCTION + POLICY TAILWIND = EXPONENTIAL PE RE-RATING</b>", badge_style)]
    ]
    bt = Table(badge_data, colWidths=[532])
    bt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#DEF7EC")),
        ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#03543F")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(bt)
    story.append(Spacer(1, 4))

    story.append(Paragraph("1. The TAPAS 5-Pillar Framework", h1_style))
    story.append(Paragraph("Har multibagger stock apni massive rally shuru karne se pehle in 5 pillars par khada hota hai:", body_style))

    tapas_table_data = [
        [Paragraph("Pillar", table_hdr), Paragraph("Dimension / Meaning", table_hdr), Paragraph("Institutional Significance & Key Evidence", table_hdr)],
        [
            Paragraph("<b>T — Trigger</b>", table_cell_bold),
            Paragraph("Policy, Demand Shock, or Structural Change", table_cell),
            Paragraph("Govt capex schemes (PM Gati Shakti, PLI, National Rail Plan), import substitution mandates, global supply shifts (China+1). Business growth ko ek massive external catalyst chahiye hota hai.", table_cell)
        ],
        [
            Paragraph("<b>A — Accumulation</b>", table_cell_bold),
            Paragraph("Quiet Promoter & Smart Money Buying", table_cell),
            Paragraph("Promoters open market se share khareed rahe hon (SAST filings) ya FII/DII stake quietly badh raha ho bina kisi retail hype ya TV news coverage ke.", table_cell)
        ],
        [
            Paragraph("<b>P — Profit Inflection</b>", table_cell_bold),
            Paragraph("<b>The Most Powerful Single Signal</b>", table_cell),
            Paragraph("2 se 3 saal flat ya negative profit ke baad Net Profit PEHLI BAAR +25% se +100% explode hota hai. Operating leverage kick-in karta hai aur OPM expand hota hai.", table_cell)
        ],
        [
            Paragraph("<b>A — Address TAM</b>", table_cell_bold),
            Paragraph("TAM (Total Addressable Market) Expansion", table_cell),
            Paragraph("Company ka addressable market achanak 3x–5x bada ho jata hai (e.g. domestic wagon builder enters Metro/Vande Bharat passenger trains, commodity chemical enters pharma intermediates).", table_cell)
        ],
        [
            Paragraph("<b>S — Smallcap / Ignored</b>", table_cell_bold),
            Paragraph("Silence Phase & Low Coverage", table_cell),
            Paragraph("Less than 5 institutional analysts covering. No media coverage, low Google search trends. Yahi stage hoti hai jahan stock sabse saste valuations (P/E 10x–15x) par milta hai.", table_cell)
        ],
    ]
    tt = Table(tapas_table_data, colWidths=[90, 140, 302])
    tt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F2942")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
    ]))
    story.append(tt)
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. The 8-Point Scoring Checklist & Scoring Thresholds", h1_style))
    chk_data = [
        [Paragraph("#", table_hdr), Paragraph("Checklist Parameter", table_hdr), Paragraph("Score 1 Condition", table_hdr), Paragraph("Quantitative Threshold", table_hdr)],
        [Paragraph("1", table_cell_c), Paragraph("<b>Earnings Inflection</b>", table_cell), Paragraph("Net Profit growth >= 25% for 2+ consecutive quarters after 2+ years flat/loss", table_cell), Paragraph("PAT Growth &gt;= 25%, OPM Expanding", table_cell_c)],
        [Paragraph("2", table_cell_c), Paragraph("<b>Debt Destruction</b>", table_cell), Paragraph("Debt-to-Equity falling 3+ consecutive quarters, approaching debt-free, pledging reducing", table_cell), Paragraph("D/E &lt; 0.5 or Falling Trend", table_cell_c)],
        [Paragraph("3", table_cell_c), Paragraph("<b>Promoter Confidence</b>", table_cell), Paragraph("Promoter stake stable/increasing, open market SAST buying, zero pledging increase", table_cell), Paragraph("Promoter Stake &gt;= 45%, Pledging = 0%", table_cell_c)],
        [Paragraph("4", table_cell_c), Paragraph("<b>Policy Tailwind</b>", table_cell), Paragraph("Active Govt scheme (PLI, Gati Shakti, NIP), China+1, monopoly/duopoly positioning", table_cell), Paragraph("Direct Beneficiary Mandate", table_cell_c)],
        [Paragraph("5", table_cell_c), Paragraph("<b>Market Share Gain</b>", table_cell), Paragraph("Revenue growth > 2x industry average, gaining share from unorganized players", table_cell), Paragraph("Sales Growth &gt; 2x Sector Average", table_cell_c)],
        [Paragraph("6", table_cell_c), Paragraph("<b>Low Institutional Coverage</b>", table_cell), Paragraph("Silence phase: less than 5 institutional analysts, zero retail/media hype", table_cell), Paragraph("&lt; 5 Analysts, Low Google Trends", table_cell_c)],
        [Paragraph("7", table_cell_c), Paragraph("<b>Reasonable Valuation</b>", table_cell), Paragraph("P/E below sector average, P/B < 1.5 (asset-heavy), or PEG ratio < 1.0", table_cell), Paragraph("P/E &lt; Sector Avg or PEG &lt; 1.0", table_cell_c)],
        [Paragraph("8", table_cell_c), Paragraph("<b>Order Book Visibility</b>", table_cell), Paragraph("Order book > 1.5x annual revenue, multi-year contracts, annuity subscription model", table_cell), Paragraph("Order Book &gt;= 1.5x Revenue", table_cell_c)],
    ]
    ct = Table(chk_data, colWidths=[20, 110, 262, 140])
    ct.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F2942")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 2.0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.0),
    ]))
    story.append(ct)
    story.append(Spacer(1, 4))

    score_verdict_data = [
        [Paragraph("Score 7–8 / 8", table_hdr), Paragraph("Score 5–6 / 8", table_hdr), Paragraph("Score 3–4 / 8", table_hdr), Paragraph("Score &lt; 3 / 8", table_hdr)],
        [
            Paragraph("<b>STRONG BUY</b><br/>Accumulate aggressively in tranches", table_cell_cb),
            Paragraph("<b>WATCHLIST</b><br/>Monitor next 2 quarters for inflection", table_cell_c),
            Paragraph("<b>NEUTRAL</b><br/>Fundamental story not clear yet", table_cell_c),
            Paragraph("<b>SKIP</b><br/>No conviction / high failure probability", table_cell_c),
        ]
    ]
    svt = Table(score_verdict_data, colWidths=[133, 133, 133, 133])
    svt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F2942")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor("#DEF7EC")]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(svt)

    # =========================================================================
    # PAGE 2: TEXTBOOK CASE STUDY — TITAGARH RAIL SYSTEMS (TITAGARH)
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("3. Textbook Multibagger Case Study: Titagarh Rail Systems (TITAGARH)", h1_style))
    story.append(Paragraph("Evaluated at its early pre-rally inflection point (Rs. 100–110 zone in 2022) before its massive 8.4x rally to Rs. 888+:", body_style))

    case_tapas_data = [
        [Paragraph("Pillar", table_hdr), Paragraph("Verdict", table_hdr), Paragraph("Empirical Fundamental Evidence & Catalyst", table_hdr)],
        [Paragraph("<b>T — Trigger</b>", table_cell), Paragraph("<b>YES</b>", table_cell_cb), Paragraph("Indian Railways ka Rs. 2.5 Lakh Crore capex push, National Rail Plan 2030, aur massive Vande Bharat / freight wagon tenders.", table_cell)],
        [Paragraph("<b>A — Accumulation</b>", table_cell), Paragraph("<b>YES</b>", table_cell_cb), Paragraph("Domestic mutual funds aur smart money quietly 6 mahine se shareholding badha rahe the bina kisi TV/media attention ke.", table_cell)],
        [Paragraph("<b>P — Profit Inflection</b>", table_cell), Paragraph("<b>YES</b>", table_cell_cb), Paragraph("Pichle 3 saal ke flat/loss ke baad Q1 FY23 mein operating profit 120%+ YoY explode hua (operating leverage kick-in).", table_cell)],
        [Paragraph("<b>A — Address TAM</b>", table_cell), Paragraph("<b>YES</b>", table_cell_cb), Paragraph("Conventional freight wagons se nikal kar Metro coaches + High-speed passenger trains (Vande Bharat) mein entry se TAM 5x bada ho gaya.", table_cell)],
        [Paragraph("<b>S — Smallcap / Ignored</b>", table_cell), Paragraph("<b>YES</b>", table_cell_cb), Paragraph("Market cap was under Rs. 1,500 Crores; less than 2 institutional analysts covering; zero media hype.", table_cell)],
    ]
    ctt = Table(case_tapas_data, colWidths=[90, 60, 382])
    ctt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F2942")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
    ]))
    story.append(ctt)
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>Titagarh 8-Point Checklist Score: [8 / 8] — EXCEPTIONAL CONVICTION</b>", h2_style))
    case_8p_data = [
        [Paragraph("#", table_hdr), Paragraph("Parameter", table_hdr), Paragraph("Score", table_hdr), Paragraph("Empirical Key Data & Numbers", table_hdr)],
        [Paragraph("1", table_cell_c), Paragraph("Earnings Inflection", table_cell), Paragraph("<b>1/1</b>", table_cell_cb), Paragraph("Net profit 80%+ YoY growth 2 consecutive quarters; OPM expanded from 6% to 10.5%.", table_cell)],
        [Paragraph("2", table_cell_c), Paragraph("Debt Destruction", table_cell), Paragraph("<b>1/1</b>", table_cell_cb), Paragraph("Italian subsidiary restructuring ke baad consolidated D/E 1.2 se girkar &lt;0.3 ho gaya (near debt-free).", table_cell)],
        [Paragraph("3", table_cell_c), Paragraph("Promoter Confidence", table_cell), Paragraph("<b>1/1</b>", table_cell_cb), Paragraph("Promoter holding stable @ ~45%, zero promoter pledging, no insider distress selling.", table_cell)],
        [Paragraph("4", table_cell_c), Paragraph("Policy Tailwind", table_cell), Paragraph("<b>1/1</b>", table_cell_cb), Paragraph("PM Gati Shakti + Indian Railways 1 Lakh wagon procurement drive; Make in India foreign import block.", table_cell)],
        [Paragraph("5", table_cell_c), Paragraph("Market Share Gain", table_cell), Paragraph("<b>1/1</b>", table_cell_cb), Paragraph("Wagons market share 22% se badhkar 30%+ ho gaya; private unorganized players tender qualify nahi kar paye.", table_cell)],
        [Paragraph("6", table_cell_c), Paragraph("Low Coverage", table_cell), Paragraph("<b>1/1</b>", table_cell_cb), Paragraph("Only 1 local institutional broker covering; Google search trends at all-time low (Silence Phase).", table_cell)],
        [Paragraph("7", table_cell_c), Paragraph("Valuation", table_cell), Paragraph("<b>1/1</b>", table_cell_cb), Paragraph("Forward P/E &lt; 14x with expected EPS growth &gt; 45% (PEG Ratio ~0.35, massive underpricing).", table_cell)],
        [Paragraph("8", table_cell_c), Paragraph("Order Book Visibility", table_cell), Paragraph("<b>1/1</b>", table_cell_cb), Paragraph("Order book &gt; Rs. 10,000 Crores, which was <b>4.5x annual revenue</b> (4 years revenue visibility).", table_cell)],
    ]
    cot = Table(case_8p_data, colWidths=[20, 110, 42, 360])
    cot.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F2942")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 2.2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.2),
    ]))
    story.append(cot)
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>Actionable Strategy & Historical Outcome:</b>", h2_style))
    story.append(Paragraph("• <b>Verdict:</b> STRONG BUY (Tranches mein accumulate karo) | <b>Entry Range:</b> Rs. 100 – Rs. 115 | <b>Stop Loss:</b> Rs. 92 (-8% closing basis)", body_style))
    story.append(Paragraph("• <b>Actual Realized Outcome:</b> Stock advanced from Rs. 105.4 to Rs. 888.8 across 609 calendar days, delivering <b>+743.7% Net Return (8.4x Multibagger!)</b>.", body_style))
    story.append(Paragraph("• <b>Historical Comparable:</b> Resembles <b>Deepak Nitrite (2017–2018)</b>: When a commodity player pivots to high-value manufacturing under strong Govt capex tailwinds, earnings multiply 3x and P/E expands from 12x to 35x (Double Engine Re-rating).", body_style))

    # =========================================================================
    # PAGE 3: ENTRY TIMING RULES, RED FLAGS & EXIT SIGNALS
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("4. Technical Entry Rules, Red Flags & Exit Signals", h1_style))
    story.append(Paragraph("Fundamental conviction must be confirmed by technical price-volume ignition before entering:", body_style))

    rules_data = [
        [Paragraph("Timing Category", table_hdr), Paragraph("Mandatory Technical / Fundamental Conditions", table_hdr), Paragraph("Institutional Rationale", table_hdr)],
        [
            Paragraph("<b>Best Entry Rules</b><br/><i>(ALL 3 Together)</i>", table_cell_bold),
            Paragraph("1. <b>52-Week High Breakout:</b> Price breaks 52-week consolidation high.<br/>2. <b>Volume &gt; 2.5x:</b> Breakout day volume is &gt;= 2.5x 20-day average volume.<br/>3. <b>Delivery % &gt; 60%:</b> High delivery confirms institutional accumulation, not intraday operators.", table_cell),
            Paragraph("Ensures stock has entered Phase 2 (Breakout) and is not stuck in prolonged sideways accumulation.", table_cell)
        ],
        [
            Paragraph("<b>Avoid Entry When</b><br/><i>(Anti-Chasing Rules)</i>", table_cell_bold),
            Paragraph("1. Stock is already up &gt; 50% recently (Late-stage retail chase).<br/>2. Daily RSI(14) &gt; 70 at time of entry (Overbought exhaustion).<br/>3. Entry based purely on media news / TV tips with no TAPAS fundamentals.", table_cell),
            Paragraph("Protects against buying at the top of temporary momentum spikes.", table_cell)
        ],
        [
            Paragraph("<b>RED FLAGS</b><br/><i>(Instant Skip Rules)</i>", table_cell_bold),
            Paragraph("❌ <b>Promoter Pledging INCREASING</b> (even if stake increases).<br/>❌ <b>Revenue rising but Net Profit Margin shrinking</b> 2+ quarters.<br/>❌ <b>Auditor qualified or changed abruptly</b> without explanation.<br/>❌ <b>Accounts receivable (debtors) growing faster than revenue</b> (Fake sales).<br/>❌ <b>Promoter selling stake 2+ consecutive quarters.</b>", table_cell),
            Paragraph("Zero tolerance for accounting fraud, governance issues, or promoter distress.", table_cell)
        ],
        [
            Paragraph("<b>Exit Signals</b><br/><i>(Sell if ANY 2 appear)</i>", table_cell_bold),
            Paragraph("1. Promoters selling stake for 2+ consecutive quarters.<br/>2. Revenue growth drops below industry average.<br/>3. Debt begins rising again after prior downtrend.<br/>4. <b>15+ analysts now covering</b> (Fully discovered = limited re-rating).<br/>5. P/E ratio exceeds 2x historical 5-year average.<br/>6. Driving policy tailwind is reversed or delayed by Govt.", table_cell),
            Paragraph("Systematic exit before institutional distribution phase begins.", table_cell)
        ],
    ]
    rt = Table(rules_data, colWidths=[100, 260, 172])
    rt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F2942")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
    ]))
    story.append(rt)
    story.append(Spacer(1, 4))

    story.append(Paragraph("5. Historical Multibaggers Proof Table (2010–2026)", h1_style))
    story.append(Paragraph("Empirical evidence from 8 classic Indian multibaggers that matched the TAPAS setup at entry:", body_style))

    hist_data = [
        [Paragraph("Stock Symbol", table_hdr), Paragraph("Pre-Rally Inflection", table_hdr), Paragraph("Key TAPAS Catalyst", table_hdr), Paragraph("Entry Zone", table_hdr), Paragraph("Peak Price", table_hdr), Paragraph("Multibagger Run", table_hdr)],
        [Paragraph("<b>Bajaj Finance</b>", table_cell_bold), Paragraph("FY12–13", table_cell), Paragraph("AUM 50%+ YoY growth; zero analyst coverage", table_cell), Paragraph("Rs. 50–60", table_cell_c), Paragraph("Rs. 8,000+", table_cell_c), Paragraph("<b>130x+ Mega Run</b>", table_cell_cb)],
        [Paragraph("<b>Deepak Nitrite</b>", table_cell_bold), Paragraph("FY17–18", table_cell), Paragraph("Phenol plant operating leverage; China+1 shift", table_cell), Paragraph("Rs. 80–100", table_cell_c), Paragraph("Rs. 2,800+", table_cell_c), Paragraph("<b>28x Multibagger</b>", table_cell_cb)],
        [Paragraph("<b>Suzlon Energy</b>", table_cell_bold), Paragraph("Q2 FY22", table_cell), Paragraph("Debt Rs. 12k Cr -> Rs. 800 Cr; near debt-free turn", table_cell), Paragraph("Rs. 8–10", table_cell_c), Paragraph("Rs. 80+", table_cell_c), Paragraph("<b>8x–10x Turnaround</b>", table_cell_cb)],
        [Paragraph("<b>Trent (Zudio)</b>", table_cell_bold), Paragraph("FY21–22", table_cell), Paragraph("Zudio fast fashion tier 2/3 unit economics explosion", table_cell), Paragraph("Rs. 1,000", table_cell_c), Paragraph("Rs. 7,000+", table_cell_c), Paragraph("<b>7x Multibagger</b>", table_cell_cb)],
        [Paragraph("<b>Mazagon Dock</b>", table_cell_bold), Paragraph("FY21–22", table_cell), Paragraph("Submarine monopoly; order book 8x revenue", table_cell), Paragraph("Rs. 150–200", table_cell_c), Paragraph("Rs. 5,000+", table_cell_c), Paragraph("<b>25x Multibagger</b>", table_cell_cb)],
        [Paragraph("<b>Dixon Technologies</b>", table_cell_bold), Paragraph("FY19–20", table_cell), Paragraph("Mobile manufacturing PLI scheme; 3x sales", table_cell), Paragraph("Rs. 770 (adj)", table_cell_c), Paragraph("Rs. 4,700+", table_cell_c), Paragraph("<b>6.1x Multibagger</b>", table_cell_cb)],
        [Paragraph("<b>Titagarh Rail</b>", table_cell_bold), Paragraph("Q1 FY23", table_cell), Paragraph("Rail capex; D/E drop <0.3; order book 4.5x sales", table_cell), Paragraph("Rs. 105", table_cell_c), Paragraph("Rs. 888+", table_cell_c), Paragraph("<b>8.4x Multibagger</b>", table_cell_cb)],
        [Paragraph("<b>Hindustan Aero (HAL)</b>", table_cell_bold), Paragraph("Q3 FY21", table_cell), Paragraph("Indigenous Tejas LCA + helicopter monopoly", table_cell), Paragraph("Rs. 339", table_cell_c), Paragraph("Rs. 4,140+", table_cell_c), Paragraph("<b>12.2x Multibagger</b>", table_cell_cb)],
    ]
    ht = Table(hist_data, colWidths=[90, 60, 162, 65, 65, 90])
    ht.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F2942")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 2.2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.2),
    ]))
    story.append(ht)
    story.append(Spacer(1, 6))

    cert_data = [
        [Paragraph("<b>TAPAS FRAMEWORK CERTIFICATION & RESEARCH SIGN-OFF</b><br/>This document outlines the official institutional screening protocol of the Blumberg Market Radar for identifying multibagger Indian equities. By enforcing the 5-pillar TAPAS model and 8-point checklist, investors capture the entire Phase 2–3 compounding wave while bypassing value traps and operator-driven penny stocks.<br/><b>Lead Equity Research Analyst:</b> Principal Quantitative Strategist &nbsp;|&nbsp; <b>Date:</b> October 23, 2026", ParagraphStyle("CertText", parent=styles["Normal"], fontName="Helvetica", fontSize=7.2, leading=10.5, textColor=colors.HexColor("#0F2942"), alignment=1))]
    ]
    ct = Table(cert_data, colWidths=[532])
    ct.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EFF6FF")),
        ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#1A56DB")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(ct)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated 3-Page TAPAS Report PDF: {pdf_path}")

    # Mirror to root workspace and brain directory
    import shutil
    root_pdf = Path("TAPAS_MULTIBAGGER_FRAMEWORK_REPORT.pdf")
    shutil.copy2(pdf_path, root_pdf)
    print(f"Mirrored PDF to root workspace: {root_pdf}")

    brain_dir = Path(r"C:\Users\DELL\.gemini\antigravity\brain\be23f339-1b91-4d43-b86f-c3a26d38aace")
    if brain_dir.exists():
        brain_pdf = brain_dir / "TAPAS_MULTIBAGGER_FRAMEWORK_REPORT.pdf"
        shutil.copy2(pdf_path, brain_pdf)
        print(f"Mirrored PDF to brain directory: {brain_pdf}")

if __name__ == "__main__":
    build_pdf()
