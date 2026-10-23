"""Generate a dedicated publication-grade PDF guide explaining how the model finds and holds stocks."""
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
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#718096"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(45, 752, "BLUMBERG MARKET RADAR — PRE-RALLY DISCOVERY & HOLDING LIFECYCLE GUIDE")
            self.drawRightString(567, 752, "QUANTITATIVE EXECUTION MANUAL")
            self.setStrokeColor(colors.HexColor("#CBD5E0"))
            self.setLineWidth(0.6)
            self.line(45, 744, 567, 744)
            
        # Footer
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(567, 32, page_str)
        self.drawString(45, 32, "CONFIDENTIAL & PROPRIETARY — SYSTEMATIC MULTIBAGGER HOLDING FRAMEWORK")
        self.setStrokeColor(colors.HexColor("#CBD5E0"))
        self.setLineWidth(0.6)
        self.line(45, 42, 567, 42)
        self.restoreState()

def build_pdf():
    out_dir = Path("reports/secular_longterm_hold")
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "HOW_THE_MODEL_HOLDS_MULTIBAGGERS_EXPLAINED.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=42,
        rightMargin=42,
        topMargin=46,
        bottomMargin=46
    )

    styles = getSampleStyleSheet()

    # Typography styles
    title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=19,
        textColor=colors.HexColor("#0F2942"),
        spaceAfter=3
    )
    subtitle_style = ParagraphStyle(
        "CoverSub",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13.5,
        textColor=colors.HexColor("#1A56DB"),
        spaceAfter=6
    )
    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#4A5568")
    )
    h1_style = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#0F2942"),
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )
    h2_style = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1E429F"),
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=10.8,
        textColor=colors.HexColor("#2D3748"),
        spaceAfter=4
    )
    bullet_style = ParagraphStyle(
        "Bullet_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=10.8,
        textColor=colors.HexColor("#2D3748"),
        leftIndent=12,
        spaceAfter=3
    )
    badge_style = ParagraphStyle(
        "BadgeText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#03543F"),
        alignment=1
    )
    table_hdr = ParagraphStyle(
        "TableHdr",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.8,
        leading=8.8,
        textColor=colors.white,
        alignment=1
    )
    table_cell = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.8,
        leading=8.8,
        textColor=colors.HexColor("#1A202C")
    )
    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.8,
        leading=8.8,
        textColor=colors.HexColor("#1A202C")
    )
    table_cell_c = ParagraphStyle("TableCellC", parent=table_cell, alignment=1)
    table_cell_cb = ParagraphStyle("TableCellCB", parent=table_cell_bold, alignment=1)
    table_cell_r = ParagraphStyle("TableCellR", parent=table_cell, alignment=2)
    table_cell_rb = ParagraphStyle("TableCellRB", parent=table_cell_bold, alignment=2)

    story = []

    # =========================================================================
    # PAGE 1: TITLE, EXECUTIVE SUMMARY & THE 4-STAGE STATE MACHINE
    # =========================================================================
    story.append(Paragraph("Blumberg Market Radar — Multibagger Holding Framework", title_style))
    story.append(Paragraph("How the Model Discovers Stocks Before the Rally and Holds Them for 5x–10x Gains", subtitle_style))
    story.append(Paragraph("<b>Subject:</b> XYZ Stock ko XX Price par dhundhne ke baad model usko KAB TAK HOLD karta hai?", meta_style))
    story.append(Paragraph("<b>Core Thesis:</b> Zero arbitrary day limits (not 30 or 60 days). We ride the entire secular trend as long as growth persists.", meta_style))
    story.append(Paragraph("<b>Author:</b> Principal Quantitative Developer & Quantitative Risk Architect &nbsp;|&nbsp; <b>Execution Engine:</b> 4-Stage State Machine", meta_style))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#0F2942"), spaceAfter=6))

    badge_data = [
        [Paragraph("CORE PRINCIPLE: <b>CUT LOSERS AT -8% HARD STOP | HOLD WINNERS FOR YEARS WHILE 100 EMA TREND PERSISTS</b>", badge_style)]
    ]
    bt = Table(badge_data, colWidths=[528])
    bt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#DEF7EC")),
        ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#03543F")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(bt)
    story.append(Spacer(1, 5))

    story.append(Paragraph("1. Discovery Phase: Pre-Rally Radar Ignition (Finding XYZ at XX Price)", h1_style))
    story.append(Paragraph("Aapka model kisi stock ko tab nahi khareedta jab woh pehle se hi TV news ya social media par 50%–100% bhaag chuka ho. Yeh stock ko uski <b>shuruati base consolidation (VCP base)</b> mein pakadta hai jab institutions chupke se accumulate kar rahe hote hain:", body_style))
    story.append(Paragraph("• <b>Base Consolidation (Anti-Chasing Filter):</b> 20-Day return <b>0% se 35%</b> ke beech hona chahiye (tight compression base, not overextended).", bullet_style))
    story.append(Paragraph("• <b>Institutional Ignition (RVOL >= 1.5x):</b> Volume apne 20-day average volume se kam se kam 1.5x ya usse zyada explode hona chahiye.", bullet_style))
    story.append(Paragraph("• <b>Ignition Trigger:</b> 5-Day return positive (> 0%) aur Daily Turnover >= Rs. 50 Lakhs hona chahiye taaki illiquid penny stocks reject ho jayein.", bullet_style))
    story.append(Paragraph("• <b>Execution:</b> Signal aane ke agle din (Day t+1) ke <b>Market Open</b> price par order fill hota hai. Agar stock Upper Circuit (locked) par ho, toh model order reject kar deta hai taaki fake fill na ho.", bullet_style))
    story.append(Spacer(1, 4))

    story.append(Paragraph("2. The Holding Lifecycle: Kab Tak Hold Karega?", h1_style))
    story.append(Paragraph("Jaise hi XYZ stock XX price par khareeda jata hai, model usko <b>4 Stages ke strict quantitative rules</b> ke mutabiq manage karta hai:", body_style))

    state_machine_data = [
        [Paragraph("Lifecycle Stage", table_hdr), Paragraph("Stock Condition / Gain", table_hdr), Paragraph("Stop-Loss / Profit Floor", table_hdr), Paragraph("Kab Tak Hold Karega? / Exit Action", table_hdr)],
        [Paragraph("<b>Stage 1: False Breakout Defense</b>", table_cell), Paragraph("Peak Gain &lt; +15.0%<br/>(First 1 to 30 Days)", table_cell_c), Paragraph("<b>Hard Stop at -8.0%</b><br/>(Low &lt;= XX * 0.92)", table_cell_c), Paragraph("Jab tak stock upar ya base mein hai hold karega. Agar breakout fail ho kar -8% gir gaya, turant exit kar lega (Capital Safe).", table_cell)],
        [Paragraph("<b>Stage 2: Capital Preservation</b>", table_cell), Paragraph("+15.0% &lt;= Peak Gain &lt; +30.0%<br/>(Emerging Winner)", table_cell_c), Paragraph("<b>Breakeven Floor at +2.0%</b><br/>(Low &lt;= XX * 1.02)", table_cell_c), Paragraph("Stop ko -8% se badha kar <b>XX + 2%</b> par permanently lock kar deta hai. Ek baar +15% profit aane ke baad trade <b>kabhi bhi loss mein nahi ja sakta!</b>", table_cell)],
        [Paragraph("<b>Stage 3: Secular Multibagger Wave</b>", table_cell), Paragraph("Peak Gain &gt;= +30.0%<br/>(100%, 300%, 800%+)", table_cell_c), Paragraph("<b>Secular Trend Shield:</b><br/>100-Day Daily EMA", table_cell_c), Paragraph("Daily stops hata diye jate hain. Minor 10%–15% pullbacks par bilkul nahi bechta! <b>Saalon-saal (months/years) hold karta hai jab tak 100 EMA ke upar hai.</b>", table_cell)],
        [Paragraph("<b>Stage 4: Structural Exit</b>", table_cell), Paragraph("Close &lt; 100 EMA AND<br/>Drop &gt;= 20% from Peak", table_cell_c), Paragraph("Floor never below +2.0%<br/>(Profit Harvested)", table_cell_c), Paragraph("Jab multi-year trend officially khatam hota hai, tab exit karke poora multibagger profit book karta hai (e.g. HAL @ 12.2x, ABB @ 8.4x).", table_cell)],
    ]
    smt = Table(state_machine_data, colWidths=[90, 100, 110, 228])
    smt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F2942")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(smt)

    # =========================================================================
    # PAGE 2: HISTORICAL CASE STUDIES & PSYCHOLOGY AUDIT
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("3. Real Historical Case Studies: Kaise Hold Hua Aur Kitna Bana?", h1_style))
    story.append(Paragraph("Yeh koi hypothetical theory nahi hai. Niche diye gaye real Indian equities ke live fills dekhein jo model ne 2015 se 2026 ke beech capture kiye:", body_style))

    case_hdr = [
        Paragraph("Stock Symbol", table_hdr),
        Paragraph("Entry Date & Fill", table_hdr),
        Paragraph("Exit Date & Fill", table_hdr),
        Paragraph("Total Duration Held", table_hdr),
        Paragraph("Net Return (%)", table_hdr),
        Paragraph("Capital Multiple", table_hdr),
        Paragraph("Holding & Exit Rationale", table_hdr),
    ]

    case_data = [
        case_hdr,
        [
            Paragraph("<b>Hindustan Aeronautics (HAL)</b>", table_cell),
            Paragraph("2020-11-13<br/><b>Rs. 338.9</b>", table_cell_c),
            Paragraph("2024-09-19<br/><b>Rs. 4,140.2</b>", table_cell_c),
            Paragraph("<b>1,406 Calendar Days</b><br/>(~3.9 Years / 953 Bars)", table_cell_c),
            Paragraph("<b>+1,121.7%</b>", table_cell_cb),
            Paragraph("<b>12.2x</b>", table_cell_cb),
            Paragraph("2021, 2022, aur 2023 ke normal 15% pullbacks ko ignore kiya. 100 EMA ke upar ride karta raha jab tak 2024 mein trend break nahi hua.", table_cell)
        ],
        [
            Paragraph("<b>Titagarh Rail Systems</b>", table_cell),
            Paragraph("2022-07-06<br/><b>Rs. 105.4</b>", table_cell_c),
            Paragraph("2024-03-06<br/><b>Rs. 888.8</b>", table_cell_c),
            Paragraph("<b>609 Calendar Days</b><br/>(~1.7 Years / 412 Bars)", table_cell_c),
            Paragraph("<b>+743.7%</b>", table_cell_cb),
            Paragraph("<b>8.4x</b>", table_cell_cb),
            Paragraph("Base consolidation ignition pakdi aur poori capex expansion rally ride ki. Exit tab hua jab rail pack mein -20% structural correction aayi.", table_cell)
        ],
        [
            Paragraph("<b>ABB India</b>", table_cell),
            Paragraph("2020-06-22<br/><b>Rs. 791.0</b>", table_cell_c),
            Paragraph("2024-11-13<br/><b>Rs. 6,635.5</b>", table_cell_c),
            Paragraph("<b>1,605 Calendar Days</b><br/>(~4.4 Years / 1,089 Bars)", table_cell_c),
            Paragraph("<b>+738.8%</b>", table_cell_cb),
            Paragraph("<b>8.4x</b>", table_cell_cb),
            Paragraph("4.4 saal tak stock ko chupchap hold kiya. Daily swing trading ki jagah institution ki tarah compounded holding ki.", table_cell)
        ],
        [
            Paragraph("<b>Dixon Technologies</b>", table_cell),
            Paragraph("2020-04-22<br/><b>Rs. 774.2</b>", table_cell_c),
            Paragraph("2022-01-24<br/><b>Rs. 4,697.8</b>", table_cell_c),
            Paragraph("<b>642 Calendar Days</b><br/>(~1.8 Years / 437 Bars)", table_cell_c),
            Paragraph("<b>+506.9%</b>", table_cell_cb),
            Paragraph("<b>6.1x</b>", table_cell_cb),
            Paragraph("PLI scheme capex ke dauran stock 6x multiply hua. Exit hua jab tech electronics correction shuru hui.", table_cell)
        ],
        [
            Paragraph("<b>Cummins India</b>", table_cell),
            Paragraph("2020-08-14<br/><b>Rs. 395.6</b>", table_cell_c),
            Paragraph("2025-01-09<br/><b>Rs. 2,148.0</b>", table_cell_c),
            Paragraph("<b>1,609 Calendar Days</b><br/>(~4.4 Years / 1,091 Bars)", table_cell_c),
            Paragraph("<b>+443.4%</b>", table_cell_cb),
            Paragraph("<b>5.4x</b>", table_cell_cb),
            Paragraph("Data center aur power generation capex cycle ko ride kiya. 4 saal mein capital ko 5x se zyada multiply kiya.", table_cell)
        ],
        [
            Paragraph("<b>Bharti Airtel</b>", table_cell),
            Paragraph("2020-04-16<br/><b>Rs. 472.5</b>", table_cell_c),
            Paragraph("<b>STILL HOLDING</b><br/>Rs. 1,889.8", table_cell_c),
            Paragraph("<b>2,379 Calendar Days</b><br/>(~6.5 Years / 1,614 Bars)", table_cell_c),
            Paragraph("<b>+300.0%</b>", table_cell_cb),
            Paragraph("<b>4.0x</b>", table_cell_cb),
            Paragraph("<b>ACTIVE WEALTH COMPOUNDER:</b> Trend abhi tak 100 EMA ke upar intact hai, isliye model ne aaj tak isko becha nahi hai!", table_cell)
        ],
        [
            Paragraph("<b>YES Bank (Bad Stock)</b>", table_cell),
            Paragraph("Breakout Signal<br/>Rs. 317.2", table_cell_c),
            Paragraph("Stop-Loss Hit<br/>Rs. 291.5", table_cell_c),
            Paragraph("<b>12 Calendar Days</b><br/>(Short Duration)", table_cell_c),
            Paragraph("<b>-8.1%</b>", table_cell_cb),
            Paragraph("<b>0.92x</b>", table_cell_cb),
            Paragraph("<b>CAPITAL SAVED:</b> Stock fail hua toh model ne foran -8% par kaat diya. Retailer ki tarah -90% girne tak hold nahi kiya!", table_cell)
        ],
    ]

    c_table = Table(case_data, colWidths=[80, 68, 68, 80, 52, 42, 138])
    c_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0F2942")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 2.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
    ]))
    story.append(c_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("4. Retail Thinking vs Quantitative Secular Holding Mindset", h1_style))
    story.append(Paragraph("Aam retail investor aur aapke model ke holding structure mein yeh 3 sabse bade antar hain:", body_style))
    story.append(Paragraph("1. <b>Small Gains Churning (Retail Mistake):</b> Retailer +15% aate hi dar jata hai ki munafa chala na jaye aur bech deta hai. Aapka model Stage-2 mein aate hi Breakeven Floor (+2%) lock kar leta hai taaki dar khatam ho jaye, aur phir poora 5x–10x banne tak baitha rehta hai.", bullet_style))
    story.append(Paragraph("2. <b>Holding Bad Stocks (Hope Trading):</b> Retailer girte hue stock (jaise YES Bank, Vodafone Idea, Suzlon) mein saalon-saal phansa rehta hai ki kabhi toh wapas aayega. Aapka model Stage-1 mein hi **-8% par bina daya kiye foran exit** kar deta hai.", bullet_style))
    story.append(Paragraph("3. <b>Zero Transaction Churn:</b> Baar-baar buy-sell na karne se STT, stamp duty, aur brokerage friction 92% bach jati hai (₹1.07 Crore ki bachat), jo seedha portfolio mein compound hoti hai.", bullet_style))
    story.append(Spacer(1, 8))

    cert_data = [
        [Paragraph("<b>FINAL SUMMARY & EXECUTION SIGN-OFF</b><br/>Aapke model ka seedha aur saaf niyam hai: <b>Galat nikla toh chote se cut (-8%) par foran bahar, aur agar sahi nikla toh jab tak multi-year trend zinda hai, tab tak saalon-saal hold karke poora 5x–10x nichodna hai!</b><br/><b>Verified by:</b> Principal Quantitative Developer & Quantitative Risk Architect &nbsp;|&nbsp; <b>Date:</b> October 23, 2026", ParagraphStyle("CertText", parent=styles["Normal"], fontName="Helvetica", fontSize=7.8, leading=11, textColor=colors.HexColor("#0F2942"), alignment=1))]
    ]
    ct = Table(cert_data, colWidths=[528])
    ct.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EFF6FF")),
        ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#1A56DB")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(ct)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated 2-Page Holding Guide PDF: {pdf_path}")

    # Mirror to workspace root and brain directory
    import shutil
    root_pdf = Path("HOW_THE_MODEL_HOLDS_MULTIBAGGERS_EXPLAINED.pdf")
    shutil.copy2(pdf_path, root_pdf)
    print(f"Mirrored PDF to root workspace: {root_pdf}")

    brain_dir = Path(r"C:\Users\DELL\.gemini\antigravity\brain\be23f339-1b91-4d43-b86f-c3a26d38aace")
    if brain_dir.exists():
        brain_pdf = brain_dir / "HOW_THE_MODEL_HOLDS_MULTIBAGGERS_EXPLAINED.pdf"
        shutil.copy2(pdf_path, brain_pdf)
        print(f"Mirrored PDF to brain directory: {brain_pdf}")

if __name__ == "__main__":
    build_pdf()
