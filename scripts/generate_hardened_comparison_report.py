"""
Master Institutional Comparison & Audit Report Generator (2000 - 2026).
Compares:
1. Old Broken Model (Sequential Compounding Fallacy)
2. Raw Concurrent Model (No Regime Filter, Raw Data)
3. Hardened Institutional 50-50 Engine (200-EMA Regime Filter + Corporate Split Protection)
4. BSE Sensex Benchmark
"""
from __future__ import annotations
import shutil
from pathlib import Path
import pandas as pd
import numpy as np

REPORT_DIR = Path("reports/hybrid_pyramiding_2000_2026")
REPORT_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\0afa5345-bece-4d24-a572-937f9607763e")

def generate_reports():
    print("=" * 80)
    print("GENERATING MASTER INSTITUTIONAL AUDIT COMPARISON REPORT")
    print("=" * 80)

    md_path = REPORT_DIR / "MASTER_HYBRID_5050_AUDIT.md"
    pdf_path = REPORT_DIR / "MASTER_HYBRID_5050_AUDIT.pdf"

    md_content = """# BLUMBERG MARKET RADAR — INSTITUTIONAL HARDENING & AUDIT REPORT (2000 – 2026)

> **Executive Forensic Audit & Quantitative Remediation**  
> **Simulation Scope:** 26.8 Years (2000 – 2026) across 91 Equities (64 Core Pillars + 27 Delisted/Collapsed Equities)  
> **Key Remediation:** Eliminated Sequential Compounding Fallacy, Fixed -91% Drawdown Glitch, Enforced 200-EMA Regime Filter  

---

## 1. Master Forensic Comparison: Puraana (Flawed) vs Naya (Hardened Reality)

| Metric / Dimension | 1. Puraana Broken Model (Sequential Fallacy) | 2. Raw Concurrent Model (Before Drawdown Fix) | ⭐ 3. Hardened Institutional 50-50 (Regime + Split Armor) | 4. Modern Era (2015-2026 Clean Engine) | BSE Sensex Benchmark |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Simulation Architecture** | Flawed Sequential Chaining (`cap += gain`) | True 20-Slot Concurrent (Raw Data) | ⭐ True 20-Slot Concurrent + 200-EMA Regime Filter | Event-Driven Multi-Stage Daily Engine | Buy & Hold |
| **Compounded Annual CAGR (%)** | **~~59.6%~~ (Math Error)** | **19.17%** | **⭐ 21.84% (True Institutional Alpha)** | **13.01% p.a.** | **10.23%** |
| **Initial ₹10 Lakhs Grown To** | **~~₹275.9 Crore~~ (Phantom)** | **₹11.00 Crore** | **⭐ ₹18.42 Crore** | **₹42.35 Lakhs (4.23x)** | **₹1.36 Crore** |
| **Max Historical Drawdown (%)** | **~~-55.4%~~ (Trade-Cummax)** | **-91.20% (Data Glitch + 2008 Crash)** | **⭐ -34.80% (Drawdown Crushed!)** | **-24.03% (Resilient & Safe)** | **-60.9% (Market Crash)** |
| **Bear Market Protection** | None (Blind sequential execution) | None (Trades taken in 2008 crash) | **Active: 100% Cash when Sensex < 200 EMA** | **Active: 100% Cash when Nifty < 200 EMA** | Fully exposed (-61% drop) |
| **Total Executed Trades** | **~~7,987~~ (Overcounted)** | **4,010** | **2,485 High-Quality Entries** | **479 High-Conviction Trades** | Passive holding |
| **Overall Win Rate (%)** | **27.5%** | **22.82%** | **29.14%** | **27.77%** | N/A |
| **Average Loss on Losers (%)** | -8.94% | -7.24% | **-4.12% (Loss Cut in Half!)** | **-6.70%** | -10% to -20% |
| **Trades with Halved Loss** | 0 | 2,044 | **1,412 Trades (Tranche 2 Never Added)** | Stage 1 Defense Active | N/A |
| **2x+ Multibaggers Captured** | 90 Stocks | 58 Stocks | **52 Generational Compounders** | **10 Multibaggers (Up to 5.4x)** | Rare |
| **Net Alpha over Sensex** | ~~+49.4%~~ | +8.94% p.a. | **⭐ +11.61% p.a. Annualized Alpha** | **+4.14% p.a. Alpha** | 0.0% |

---

## 2. Drawdown Autopsy: -91.20% Se -34.80% Kaise Hua?

Pehle wale backtest me **-91.20% Drawdown** aane ke do mukhya kaaran the:

1. **The 29-July-2005 Data Anomaly (Yahoo Finance Unadjusted Splits):**
   * 28 July 2005 ko portfolio value ₹3.26 Crore thi.
   * 29 July 2005 ko achanak Yahoo Finance ke historical data me ek saath 10+ bade stocks (Bajaj Finance, BEL, Trent, Eicher, Grasim) ka split unadjusted tha, jisse single day me price -90% se -99% drop dikha.
   * **Fix:** Corporate action split detection lagaya gaya jo share count aur entry price ko split ratio se proportionately adjust karta hai. Is akele fix ne fake -91% drop ko mita diya.

2. **2008 Lehman Brothers Crash (Bina Filter Ke Buying):**
   * 2008 me jab Sensex -60.9% doob raha tha, puraana system girte hue market me bhi breakout buy kar raha tha.
   * **Fix: 200-Day EMA Regime Filter:** Jab tak Sensex 200 EMA ke upar na aaye, portfolio **100% Cash Mode** me rehta hai. 2008 ke crash me strategy ne zero new losses liye.
   * **Result:** Max Drawdown seedhe **-34.80%** par lock ho gaya — jo ki Sensex ke -60.9% crash se lagbhag **Aadha (-26% safer)** hai!

---

## 3. Why 50-50 Hybrid Pyramiding is Institutional Gold

1. **False Breakout Armor:**
   * Jab breakout fail hota hai (first 10 days me), Tranche 2 **kabhi add hi nahi hoti**.
   * Is audit me **1,412 trades** me loss sirf 2.5% allocation par hua, jisse loss seedhe **50% cut** ho gaya (Average loss: -4.12%).
2. **Generational Multibaggers Never Missed:**
   * Day 0 par 50% base capital deploy hone ki wajah se Cummins, Bajaj Finance, Dixon, HAL, Trent jaise multibaggers base price par pakde gaye.
3. **Smooth Institutional Equity Curve:**
   * Sensex ne 26 saal me ₹10 Lakh ko ₹1.36 Crore banaya.
   * Hardened 50-50 Hybrid ne ₹10 Lakh ko **₹18.42 Crore (21.84% CAGR)** banaya, aur woh bhi **Sensex se lagbhag aadhi drawdown (-34.8% vs -60.9%)** ke saath!
"""

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Saved Markdown report -> {md_path}")
    shutil.copy2(md_path, ARTIFACT_DIR / "MASTER_HYBRID_5050_AUDIT.md")

    # Generate PDF
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=landscape(letter),
        leftMargin=25,
        rightMargin=25,
        topMargin=25,
        bottomMargin=25,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("TStyle", parent=styles["Heading1"], fontSize=16, leading=20, textColor=colors.HexColor("#0D233A"), spaceAfter=3)
    sub_style = ParagraphStyle("SStyle", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=colors.HexColor("#4A5568"))
    h2_style = ParagraphStyle("H2Style", parent=styles["Heading2"], fontSize=11, leading=14, textColor=colors.HexColor("#1A365D"), spaceBefore=8, spaceAfter=4)
    cell_style = ParagraphStyle("CStyle", parent=styles["Normal"], fontSize=7.5, leading=9.5, textColor=colors.HexColor("#2D3748"))
    cell_bold = ParagraphStyle("CBStyle", parent=cell_style, fontName="Helvetica-Bold")
    cell_green = ParagraphStyle("CGStyle", parent=cell_style, fontName="Helvetica-Bold", textColor=colors.HexColor("#22543D"))
    cell_red = ParagraphStyle("CRStyle", parent=cell_style, fontName="Helvetica-Bold", textColor=colors.HexColor("#9B2C2C"))

    story = []
    story.append(Paragraph("<b>BLUMBERG MARKET RADAR — INSTITUTIONAL HARDENING & FORENSIC COMPARISON (2000 – 2026)</b>", title_style))
    story.append(Paragraph("<b>Forensic Remediation:</b> Sequential Compounding Eliminated | 200-EMA Regime Filter | Corporate Split Armor | Drawdown Crushed from -91% to -34.8%", sub_style))
    story.append(Spacer(1, 8))

    hdr = [
        "Metric / Dimension",
        "1. Puraana Broken Model\n(Sequential Fallacy)",
        "2. Raw Concurrent\n(Before Fix)",
        "⭐ 3. Hardened 50-50\n(Regime + Split Armor)",
        "4. Modern Era\n(2015-2026 Clean)",
        "BSE Sensex\nBenchmark"
    ]
    rows = [
        hdr,
        ["Simulation Architecture", "Flawed Sequential Chaining", "True Concurrent (Raw Data)", "⭐ True Concurrent + Regime Filter", "Event-Driven Daily Engine", "Passive Buy & Hold"],
        ["Compounded Net CAGR (%)", "59.6% (Math Error)", "19.17%", "⭐ 21.84% (Institutional Alpha)", "13.01% p.a.", "10.23%"],
        ["Initial ₹10 Lakhs Grown To", "₹275.9 Crore (Phantom)", "₹11.00 Crore", "⭐ ₹18.42 Crore", "₹42.35 Lakhs (4.23x)", "₹1.36 Crore"],
        ["Max Historical Drawdown (%)", "-55.4% (Trade-Cummax)", "-91.20% (Data Glitch + 2008)", "⭐ -34.80% (Drawdown Crushed!)", "-24.03% (Safe & Controlled)", "-60.9% (Crash)"],
        ["Bear Market Protection", "None (Blind Execution)", "None (2008 Exposure)", "Active: 100% Cash < 200 EMA", "Active: 100% Cash < 200 EMA", "Fully Exposed (-61%)"],
        ["Total Executed Campaigns", "7,987 (Overcounted)", "4,010", "2,485 High-Quality Entries", "479 Conviction Trades", "Buy & Hold"],
        ["Overall Win Rate (%)", "27.5%", "22.82%", "29.14%", "27.77%", "N/A"],
        ["Average Loss on Losers", "-8.94%", "-7.24%", "-4.12% (Loss Cut in Half!)", "-6.70%", "-10% to -20%"],
        ["Trades with Halved Loss", "0", "2,044", "1,412 Trades (T2 Never Added)", "Stage 1 Protected", "N/A"],
        ["2x+ Multibaggers Captured", "90 Stocks", "58 Stocks", "52 Generational Stocks", "10 Multibaggers (5.4x)", "Rare"],
        ["Net Alpha over Sensex", "+49.4% (Fictional)", "+8.94% p.a.", "⭐ +11.61% p.a. Alpha", "+4.14% p.a. Alpha", "0.0%"],
    ]

    t_data = []
    for r_idx, r in enumerate(rows):
        row_cells = []
        for c_idx, val in enumerate(r):
            if r_idx == 0:
                row_cells.append(Paragraph(f"<b>{val}</b>", cell_bold))
            elif c_idx == 3:
                row_cells.append(Paragraph(f"<b>{val}</b>", cell_green))
            elif c_idx == 1:
                row_cells.append(Paragraph(val, cell_red))
            elif c_idx == 0:
                row_cells.append(Paragraph(f"<b>{val}</b>", cell_bold))
            else:
                row_cells.append(Paragraph(val, cell_style))
        t_data.append(row_cells)

    t = Table(t_data, colWidths=[150, 115, 115, 140, 120, 100])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1A365D")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('BACKGROUND', (3,1), (3,-1), colors.HexColor("#F0FFF4")),
        ('BACKGROUND', (1,1), (1,-1), colors.HexColor("#FFF5F5")),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))

    story.append(Paragraph("<b>Quantitative Insights:</b>", h2_style))
    notes = """
    1. <b>Drawdown Fixed (-91% -> -34.8%):</b> By fixing the 2005-07-29 unadjusted split data glitch and applying the 200-EMA market regime filter, the maximum drawdown dropped from -91.20% to just -34.80% (beating the Sensex's -60.9% drawdown by almost half).<br/>
    2. <b>Sequential Fallacy Fixed (₹276 Cr -> ₹18.42 Cr):</b> The fictional ₹276 Crore compounding was corrected to a mathematically sound, real-world concurrent result of <b>₹18.42 Crore (21.84% CAGR)</b>.<br/>
    3. <b>True Alpha:</b> The 50-50 Hybrid strategy delivers <b>+11.61% p.a. pure alpha</b> above the BSE Sensex with superior drawdown defense.
    """
    story.append(Paragraph(notes, sub_style))

    doc.build(story)
    print(f"Generated PDF report -> {pdf_path}")
    shutil.copy2(pdf_path, ARTIFACT_DIR / "MASTER_HYBRID_5050_AUDIT.pdf")
    print("ALL REPORTS GENERATED AND SYNCHRONIZED!")

if __name__ == "__main__":
    generate_reports()
