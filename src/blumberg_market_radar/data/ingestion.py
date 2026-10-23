"""Market data ingestion, caching, and synthetic fallback for Indian equities."""
from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Sequence
import urllib.request
import numpy as np
import pandas as pd
import yfinance as yf

from blumberg_market_radar.data.validation import validate_ohlcv

logger = logging.getLogger(__name__)

# Representative universe of 20 core Indian stocks across Large, Mid, and Momentum Small caps (Backward-compatible)
DEFAULT_INDIAN_UNIVERSE = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "TATAMOTORS.NS",
    "BHARTIARTL.NS",
    "LT.NS",
    "BEL.NS",
    "HAL.NS",
    "MAZDOCK.NS",
    "SUZLON.NS",
    "BSE.NS",
    "CDSL.NS",
    "TRENT.NS",
    "DIXON.NS",
    "POLYCAB.NS",
    "KALYANKJIL.NS",
    "COCHINSHIP.NS",
    "ZOMATO.NS",
]

# Official NIFTY 100 Largecap Constituents
NIFTY_100_LARGECAPS = {
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "BHARTIARTL", "TATAMOTORS", "LT",
    "SBIN", "BAJFINANCE", "HINDUNILVR", "ITC", "KOTAKBANK", "AXISBANK", "BEL", "HAL",
    "NTPC", "POWERGRID", "TITAN", "COALINDIA", "TATASTEEL", "ADANIENT", "ADANIPORTS",
    "ADANIGREEN", "BAJAJ-AUTO", "M&M", "MARUTI", "SUNPHARMA", "ULTRACEMCO", "ASIANPAINT",
    "ONGC", "JSWSTEEL", "SIEMENS", "ABB", "TRENT", "DMART", "ZOMATO", "VBL", "DLF",
    "IOC", "REC", "PFC", "NESTLEIND", "GRASIM", "HINDALCO", "INDUSINDBK", "TECHM",
    "WIPRO", "HCLTECH", "EICHERMOT", "DIVISLAB", "LTIM", "CIPLA", "APOLLOHOSP",
    "TATAPOWER", "BHEL", "VEDL", "CHOLAFIN", "BPCL", "SHRIRAMFIN", "HAVELLS",
    "PIDILITIND", "GAIL", "AMBUJACEM", "BANKBARODA", "PNB", "CANBK", "UNIONBANK",
    "IOB", "POLYCAB", "CUMMINSIND", "CGPOWER", "TVSMOTOR", "HEROMOTOCO", "BOSCHLTD",
    "MOTHERSON", "MAXHEALTH", "MANKIND", "TORNTPHARM", "LUPIN", "AUROPHARMA", "COLPAL",
    "MARICO", "DABUR", "GODREJCP", "BRITANNIA", "SRF", "PAGEIND", "MUTHOOTFIN",
    "SHREECEM", "ICICIPRULI", "HDFCLIFE", "SBILIFE", "ICICIGI", "NAUKRI", "PERSISTENT",
    "COFORGE", "MPHASIS",
}

# Official NIFTY Midcap 150 Constituents
NIFTY_MIDCAP_150 = {
    "MAZDOCK", "COCHINSHIP", "GRSE", "BDL", "RVNL", "IRFC", "SUZLON", "BSE", "CDSL",
    "DIXON", "KAYNES", "KALYANKJIL", "TITAGARH", "RAILTEL", "RITES", "IRB", "NCC",
    "INOXWIND", "IREDA", "BORORENEW", "SJVN", "SYRMA", "CYIENTDLM", "NETWEB", "KEI",
    "MCX", "ANGELONE", "CAMS", "TATAELXSI", "PBFINTECH", "THERMAX", "JSWENERGY",
    "TATACHEM", "TATACOMM", "ASHOKLEY", "FEDERALBNK", "GODREJPROP", "PRESTIGE",
    "OBEROIRLTY", "APOLLOTYRE", "MRF", "JINDALSTEL", "SAIL", "EXIDEIND", "GLENMARK",
    "IPCALAB", "NATCOPHARM", "ALKEM", "LAURUSLABS", "ASTRAL", "SUPREMEIND", "DEEPAKNTR",
    "ATUL", "GUJGASLTD", "IGL", "MGL", "PETRONET", "OIL", "CASTROLIND", "HUDCO",
    "LICHSGFIN", "ABCAPITAL", "POONAWALLA", "IDFCFIRSTB", "BANDHANBNK", "CENTRALBK",
    "BANKINDIA", "UCOBANK", "MAHABANK", "BATAINDIA", "DEVYANI", "JUBLFOOD", "WESTLIFE",
    "SAPPHIRE", "NYKAA", "PAYTM", "DELHIVERY", "STARHEALTH", "SUNDARMFIN", "FACT",
    "GNFC", "COROMANDEL", "PIIND", "UPL", "SUMICHEM", "TATAINVEST", "MOTILALOFS",
    "KIMS", "FORTIS", "ASTERDM", "NARAYANA", "GLAXO", "PFIZER", "SANOFI", "JBCHEPHARM",
    "AJANTPHARM", "ABFRL", "RAYMOND", "MANYAVAR", "CENTURYTEX", "FINCABLES", "RRKABEL",
    "APLAPOLLO", "JSL", "RATNAMANI", "WELCORP", "KEC", "KALPATPOWR", "VOLTAS",
    "BLUESTARCO", "WHIRLPOOL", "CROMPTON", "RADICO", "TIINDIA", "TIMKEN", "SCHAEFFLER",
    "SKFINDIA", "AIAENG", "ENDURANCE", "UNOMINDA", "SONACOMS", "BBL",
}

# 50 Prominent Indian growth & momentum equities across Defence, Infra, Railways, Renewable Energy, EMS, Capital Goods, IT, and Financials
NIFTY_MOMENTUM_UNIVERSE_50 = [
    # Core Largecap Growth Anchors
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "TATAMOTORS.NS",
    "BHARTIARTL.NS",
    # Defence & Aerospace
    "BEL.NS",
    "HAL.NS",
    "MAZDOCK.NS",
    "COCHINSHIP.NS",
    "BDL.NS",
    "GRSE.NS",
    "PARAS.NS",
    "DATAPATTNS.NS",
    # Railways & Infra
    "LT.NS",
    "RVNL.NS",
    "IRFC.NS",
    "TITAGARH.NS",
    "RAILTEL.NS",
    "RITES.NS",
    "IRB.NS",
    "NCC.NS",
    # Green Energy & Wind (Renewable Energy)
    "SUZLON.NS",
    "INOXWIND.NS",
    "IREDA.NS",
    "TATAPOWER.NS",
    "ADANIGREEN.NS",
    "BORORENEW.NS",
    "SJVN.NS",
    # EMS / Electronics & Technology
    "DIXON.NS",
    "KAYNES.NS",
    "SYRMA.NS",
    "CYIENTDLM.NS",
    "NETWEB.NS",
    "POLYCAB.NS",
    "KEI.NS",
    # Capital Goods & Heavy Engineering
    "BHEL.NS",
    "SIEMENS.NS",
    "ABB.NS",
    "CUMMINSIND.NS",
    "CGPOWER.NS",
    # Consumer & Retail & New Age Growth
    "TRENT.NS",
    "ZOMATO.NS",
    "KALYANKJIL.NS",
    "DMART.NS",
    # Financial Market Infrastructure & Fintech
    "BSE.NS",
    "CDSL.NS",
    # IT & Digital Transformation Leaders
    "KPITTECH.NS",
    "PERSISTENT.NS",
]

# Curated smallcap pre-rally candidates across Defence, EMS, Railways, Power, and Precision Engineering
NIFTY_SMALLCAP_GROWTH = [
    "KAYNES.NS",
    "CYIENTDLM.NS",
    "NETWEB.NS",
    "PARAS.NS",
    "BORORENEW.NS",
    "JWL.NS",
    "TEJASNET.NS",
    "HBLPOWER.NS",
    "ELECON.NS",
    "SHAKTIPUMP.NS",
    "KIRLOSENG.NS",
    "NEWGEN.NS",
    "DBL.NS",
    "GOKEX.NS",
    "MOTISONS.NS",
    "PPLPHARMA.NS",
    "GRAVITA.NS",
    "APARINDS.NS",
    "ACE.NS",
    "ZEN.NS",
    "AWHCL.NS",
    "ANANDRATHI.NS",
    "POONAWALLA.NS",
    "MARKSANS.NS",
    "KNRCON.NS",
]

# NIFTY 500 High-Beta Basket (100 Stocks) combining top momentum, smallcap leaders, and high-beta cyclicals
_EXTRA_HIGH_BETA_35 = [
    "MCX.NS",
    "ANGELONE.NS",
    "CAMS.NS",
    "COFORGE.NS",
    "TATAELXSI.NS",
    "NAUKRI.NS",
    "PBFINTECH.NS",
    "THERMAX.NS",
    "JSWENERGY.NS",
    "TATACHEM.NS",
    "VBL.NS",
    "TATACOMM.NS",
    "ASHOKLEY.NS",
    "FEDERALBNK.NS",
    "CANBK.NS",
    "REC.NS",
    "PFC.NS",
    "NTPC.NS",
    "COALINDIA.NS",
    "SAIL.NS",
    "TATASTEEL.NS",
    "JINDALSTEL.NS",
    "HINDALCO.NS",
    "DLF.NS",
    "GODREJPROP.NS",
    "PRESTIGE.NS",
    "OBEROIRLTY.NS",
    "APOLLOTYRE.NS",
    "MRF.NS",
    "AMBUJACEM.NS",
    "BAJAJ-AUTO.NS",
    "M&M.NS",
    "MARUTI.NS",
    "SBIN.NS",
    "AXISBANK.NS",
]

# Exact 100-stock unique high-beta basket
_all_combined = NIFTY_MOMENTUM_UNIVERSE_50 + NIFTY_SMALLCAP_GROWTH + _EXTRA_HIGH_BETA_35
_seen = set()
NIFTY_500_HIGH_BETA_100: list[str] = []
for _s in _all_combined:
    if _s not in _seen:
        _seen.add(_s)
        NIFTY_500_HIGH_BETA_100.append(_s)
    if len(NIFTY_500_HIGH_BETA_100) == 100:
        break

BENCHMARK_SYMBOL = "^NSEI"  # NIFTY 50

# NSE official Industry to Standardized Sector Theme Mapping
NSE_INDUSTRY_TO_SECTOR = {
    "Automobile and Auto Components": "Automotive & EV",
    "Capital Goods": "Capital Goods",
    "Chemicals": "Chemicals & Materials",
    "Construction": "Railways & Infra",
    "Construction Materials": "Railways & Infra",
    "Consumer Durables": "Consumer & Retail",
    "Consumer Services": "Consumer & Retail",
    "Diversified": "Diversified / General",
    "Fast Moving Consumer Goods": "Consumer & Retail",
    "Financial Services": "Banking & Financial Services",
    "Healthcare": "Healthcare & Pharma",
    "Information Technology": "IT & Digital Transformation",
    "Media Entertainment & Publication": "Consumer & Retail",
    "Metals & Mining": "Metals & Mining",
    "Oil Gas & Consumable Fuels": "Energy & Petrochemicals",
    "Power": "Power & Utilities",
    "Realty": "Real Estate & Construction",
    "Services": "Consumer & Retail",
    "Telecommunication": "Telecom & Space",
    "Textiles": "Consumer & Retail",
}

# High-precision curated thematic mapping for Indian growth/momentum equities
CURATED_THEMATIC_SECTOR_MAP = {
    # Defence & Aerospace
    "BEL": "Defence & Aerospace",
    "HAL": "Defence & Aerospace",
    "MAZDOCK": "Defence & Aerospace",
    "COCHINSHIP": "Defence & Aerospace",
    "BDL": "Defence & Aerospace",
    "GRSE": "Defence & Aerospace",
    "PARAS": "Defence & Aerospace",
    "DATAPATTNS": "Defence & Aerospace",
    "ZEN": "Defence & Aerospace",
    "ASTRAZEN": "Defence & Aerospace",
    # Railways & Infra
    "RVNL": "Railways & Infra",
    "IRFC": "Railways & Infra",
    "TITAGARH": "Railways & Infra",
    "RAILTEL": "Railways & Infra",
    "RITES": "Railways & Infra",
    "LT": "Railways & Infra",
    "IRB": "Railways & Infra",
    "NCC": "Railways & Infra",
    "KNRCON": "Railways & Infra",
    "JWL": "Railways & Infra",
    "DBL": "Railways & Infra",
    "PNCINFRA": "Railways & Infra",
    # Green Energy & Wind (Renewable Energy)
    "SUZLON": "Green Energy & Wind",
    "INOXWIND": "Green Energy & Wind",
    "IREDA": "Green Energy & Wind",
    "TATAPOWER": "Green Energy & Wind",
    "ADANIGREEN": "Green Energy & Wind",
    "BORORENEW": "Green Energy & Wind",
    "SJVN": "Green Energy & Wind",
    "WAAREEENER": "Green Energy & Wind",
    "PREMIERENE": "Green Energy & Wind",
    "JSWENERGY": "Green Energy & Wind",
    # EMS / Electronics & Technology
    "DIXON": "EMS & Technology",
    "KAYNES": "EMS & Technology",
    "SYRMA": "EMS & Technology",
    "CYIENTDLM": "EMS & Technology",
    "NETWEB": "EMS & Technology",
    "POLYCAB": "EMS & Technology",
    "KEI": "EMS & Technology",
    "TEJASNET": "EMS & Technology",
    "HBLPOWER": "EMS & Technology",
    "AVALON": "EMS & Technology",
    # Capital Goods & Heavy Engineering
    "BHEL": "Capital Goods",
    "SIEMENS": "Capital Goods",
    "ABB": "Capital Goods",
    "CUMMINSIND": "Capital Goods",
    "THERMAX": "Capital Goods",
    "CGPOWER": "Capital Goods",
    "ELECON": "Capital Goods",
    "SHAKTIPUMP": "Capital Goods",
    "KIRLOSENG": "Capital Goods",
    "APARINDS": "Capital Goods",
    "ACE": "Capital Goods",
    # Consumer & Retail & New Age Growth
    "TRENT": "Consumer & Retail",
    "ZOMATO": "Consumer & Retail",
    "KALYANKJIL": "Consumer & Retail",
    "DMART": "Consumer & Retail",
    "NAUKRI": "Consumer & Retail",
    "PBFINTECH": "Consumer & Retail",
    "NYKAA": "Consumer & Retail",
    "MOTISONS": "Consumer & Retail",
    "GOKEX": "Consumer & Retail",
    "VBL": "Consumer & Retail",
    "TITAN": "Consumer & Retail",
    # Financial Market Infrastructure & Fintech
    "BSE": "Financial Market Infrastructure",
    "CDSL": "Financial Market Infrastructure",
    "MCX": "Financial Market Infrastructure",
    "ANGELONE": "Financial Market Infrastructure",
    "CAMS": "Financial Market Infrastructure",
    "KFINTECH": "Financial Market Infrastructure",
    "ANANDRATHI": "Financial Market Infrastructure",
    "POONAWALLA": "Banking & Financial Services",
    # IT & Digital Transformation
    "KPITTECH": "IT & Digital Transformation",
    "PERSISTENT": "IT & Digital Transformation",
    "COFORGE": "IT & Digital Transformation",
    "TATAELXSI": "IT & Digital Transformation",
    "NEWGEN": "IT & Digital Transformation",
    "TCS": "IT & Digital Transformation",
    "INFY": "IT & Digital Transformation",
    "HCLTECH": "IT & Digital Transformation",
    "WIPRO": "IT & Digital Transformation",
    "TECHM": "IT & Digital Transformation",
    # Banking & Financial Services
    "HDFCBANK": "Banking & Financial Services",
    "ICICIBANK": "Banking & Financial Services",
    "SBIN": "Banking & Financial Services",
    "KOTAKBANK": "Banking & Financial Services",
    "AXISBANK": "Banking & Financial Services",
    "FEDERALBNK": "Banking & Financial Services",
    "CANBK": "Banking & Financial Services",
    "REC": "Banking & Financial Services",
    "PFC": "Banking & Financial Services",
    # Automotive & EV
    "TATAMOTORS": "Automotive & EV",
    "M&M": "Automotive & EV",
    "MARUTI": "Automotive & EV",
    "BAJAJ-AUTO": "Automotive & EV",
    "ASHOKLEY": "Automotive & EV",
    "APOLLOTYRE": "Automotive & EV",
    "MRF": "Automotive & EV",
    # Telecom & Space
    "BHARTIARTL": "Telecom & Space",
    "TATACOMM": "Telecom & Space",
    "IDEA": "Telecom & Space",
    # Energy & Petrochemicals
    "RELIANCE": "Energy & Petrochemicals",
    "ONGC": "Energy & Petrochemicals",
    "BPCL": "Energy & Petrochemicals",
    "IOC": "Energy & Petrochemicals",
    "COALINDIA": "Energy & Petrochemicals",
    # Metals & Mining
    "TATASTEEL": "Metals & Mining",
    "JINDALSTEL": "Metals & Mining",
    "SAIL": "Metals & Mining",
    "HINDALCO": "Metals & Mining",
    "VEDL": "Metals & Mining",
    # Real Estate & Construction
    "DLF": "Real Estate & Construction",
    "GODREJPROP": "Real Estate & Construction",
    "PRESTIGE": "Real Estate & Construction",
    "OBEROIRLTY": "Real Estate & Construction",
    # Healthcare & Pharma
    "PPLPHARMA": "Healthcare & Pharma",
    "MARKSANS": "Healthcare & Pharma",
    "SUNPHARMA": "Healthcare & Pharma",
    "CIPLA": "Healthcare & Pharma",
    "DRREDDY": "Healthcare & Pharma",
    # Chemicals & Materials
    "TATACHEM": "Chemicals & Materials",
    "GRAVITA": "Chemicals & Materials",
    "PIIND": "Chemicals & Materials",
    "DEEPAKNTR": "Chemicals & Materials",
}

# Base prices for realistic synthetic Indian equities generation (₹15 to ₹15,000)
BASE_PRICES = {
    # Penny / Micro / Low Tier (< ₹100)
    "MOTISONS": 28.0,
    "IRB": 65.0,
    "SUZLON": 75.0,
    # Mid-Tier Low (₹100 to ₹500)
    "SJVN": 125.0,
    "IRFC": 160.0,
    "MARKSANS": 180.0,
    "INOXWIND": 190.0,
    "PPLPHARMA": 210.0,
    "IREDA": 220.0,
    "NCC": 240.0,
    "ZOMATO": 265.0,
    "BHEL": 290.0,
    "BEL": 310.0,
    "KNRCON": 310.0,
    "RITES": 320.0,
    "POONAWALLA": 380.0,
    "RAILTEL": 390.0,
    "TATAPOWER": 420.0,
    "RVNL": 430.0,
    "SYRMA": 450.0,
    "BORORENEW": 460.0,
    "JWL": 480.0,
    "DBL": 490.0,
    # Mid-Tier High (₹500 to ₹2,000)
    "HBLPOWER": 540.0,
    "ELECON": 620.0,
    "CYIENTDLM": 680.0,
    "KALYANKJIL": 680.0,
    "CGPOWER": 710.0,
    "PARAS": 890.0,
    "GOKEX": 890.0,
    "KIRLOSENG": 920.0,
    "TATAMOTORS": 980.0,
    "NEWGEN": 1100.0,
    "TEJASNET": 1150.0,
    "BDL": 1200.0,
    "ICICIBANK": 1220.0,
    "ACE": 1280.0,
    "TITAGARH": 1350.0,
    "CDSL": 1500.0,
    "HDFCBANK": 1650.0,
    "BHARTIARTL": 1650.0,
    "GRSE": 1650.0,
    "KPITTECH": 1650.0,
    "PBFINTECH": 1680.0,
    "COCHINSHIP": 1750.0,
    "ADANIGREEN": 1750.0,
    "ZEN": 1800.0,
    "INFY": 1850.0,
    "GRAVITA": 1950.0,
    # Premium Tier (₹2,000 to ₹15,000)
    "NETWEB": 2400.0,
    "BSE": 2600.0,
    "ANGELONE": 2800.0,
    "RELIANCE": 2800.0,
    "DATAPATTNS": 2850.0,
    "LT": 3600.0,
    "CUMMINSIND": 3600.0,
    "ANANDRATHI": 3800.0,
    "TCS": 4100.0,
    "SHAKTIPUMP": 4100.0,
    "MAZDOCK": 4200.0,
    "KEI": 4200.0,
    "CAMS": 4200.0,
    "DMART": 4300.0,
    "HAL": 4800.0,
    "THERMAX": 4800.0,
    "KAYNES": 4900.0,
    "PERSISTENT": 5100.0,
    "MCX": 5800.0,
    "POLYCAB": 6800.0,
    "TATAELXSI": 6800.0,
    "SIEMENS": 6900.0,
    "NAUKRI": 7100.0,
    "TRENT": 7200.0,
    "COFORGE": 7400.0,
    "ABB": 7800.0,
    "APARINDS": 8900.0,
    "DIXON": 12500.0,
}


def _clean_symbol(symbol: str) -> str:
    """Normalize symbol to clean uppercase ticker without exchange suffix."""
    return str(symbol).strip().upper().replace(".NS", "").replace(".BO", "")


def _deterministic_base_price(sym: str) -> float:
    """Return realistic deterministic base price for any equity based on explicit map or symbol hash."""
    clean = _clean_symbol(sym)
    if clean in BASE_PRICES:
        return BASE_PRICES[clean]
    
    # Hash-based deterministic price spanning ₹18 to ₹11,600
    h = int(hashlib.md5(clean.encode("utf-8")).hexdigest(), 16)
    tier = h % 4
    if tier == 0:
        return float(18.0 + (h % 80))       # Small / Penny: ₹18 to ₹98
    elif tier == 1:
        return float(120.0 + (h % 550))     # Mid Tier: ₹120 to ₹670
    elif tier == 2:
        return float(750.0 + (h % 1800))    # Large Tier: ₹750 to ₹2,550
    else:
        return float(2600.0 + (h % 9000))   # Premium Tier: ₹2,600 to ₹11,600


def fetch_nifty500_symbol_list(
    cache_path: Path | str = "data/universe/nifty500.csv",
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Fetch official NSE Nifty 500 equity list, extracting symbols, company names, and industry sectors.
    
    Reads from local CSV cache when available, downloads from NSE archives when required,
    and falls back to built-in momentum & growth universe if offline.
    """
    cache_file = Path(cache_path)
    nse_url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"

    # 1. Try reading from cache
    if cache_file.exists() and not force_refresh:
        try:
            df = pd.read_csv(cache_file)
            if not df.empty and "Symbol" in df.columns:
                return _normalize_nifty500_dataframe(df)
        except Exception as exc:
            logger.warning(f"Error reading Nifty 500 cache {cache_file}: {exc}. Re-fetching.")

    # 2. Try fetching from official NSE repository
    try:
        req = urllib.request.Request(
            nse_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            raw_csv = response.read()
            df = pd.read_csv(io.BytesIO(raw_csv))
            if not df.empty and "Symbol" in df.columns:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_bytes(raw_csv)
                logger.info(f"Downloaded and cached {len(df)} NIFTY 500 equities to {cache_file}")
                return _normalize_nifty500_dataframe(df)
    except Exception as fetch_err:
        logger.warning(f"Failed to download Nifty 500 list from NSE: {fetch_err}.")

    # 3. Fallback: If cache exists even partially, use it
    if cache_file.exists():
        try:
            return _normalize_nifty500_dataframe(pd.read_csv(cache_file))
        except Exception:
            pass

    # 4. Fallback: Generate curated DataFrame from built-in universe
    logger.info("Using built-in Nifty momentum universe fallback list.")
    records = []
    for sym_full in NIFTY_500_HIGH_BETA_100:
        c = _clean_symbol(sym_full)
        sec = CURATED_THEMATIC_SECTOR_MAP.get(c, "Diversified / General")
        records.append({
            "symbol": c,
            "company_name": f"{c} India Ltd",
            "industry": sec,
            "sector": sec,
        })
    return pd.DataFrame(records)


def _normalize_nifty500_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names and sectors for NIFTY 500 DataFrame."""
    col_map = {c.strip().lower(): c for c in df.columns}
    sym_col = col_map.get("symbol", "Symbol")
    name_col = col_map.get("company name", col_map.get("company_name", "Company Name"))
    ind_col = col_map.get("industry", "Industry")

    clean_records = []
    for _, row in df.iterrows():
        sym_raw = str(row[sym_col]).strip().upper()
        if not sym_raw or sym_raw == "NAN":
            continue
        clean_sym = _clean_symbol(sym_raw)
        comp_name = str(row[name_col]).strip() if name_col in df.columns else f"{clean_sym} Ltd"
        industry_raw = str(row[ind_col]).strip() if ind_col in df.columns else "Diversified"
        
        # Check curated thematic map first, then general NSE industry map
        if clean_sym in CURATED_THEMATIC_SECTOR_MAP:
            sector = CURATED_THEMATIC_SECTOR_MAP[clean_sym]
        else:
            sector = NSE_INDUSTRY_TO_SECTOR.get(industry_raw, "Diversified / General")

        clean_records.append({
            "symbol": clean_sym,
            "company_name": comp_name,
            "industry": industry_raw,
            "sector": sector,
        })

    out = pd.DataFrame(clean_records).drop_duplicates(subset=["symbol"]).reset_index(drop=True)
    return out


def get_symbol_sector_map(include_nifty500: bool = True) -> dict[str, str]:
    """Map Indian symbols to their sectors (both clean symbols and .NS tickers).
    
    Returns a unified mapping covering:
    - Defence & Aerospace
    - Railways & Infra
    - Green Energy & Wind
    - EMS & Technology
    - Capital Goods
    - Consumer & Retail
    - Financial Market Infrastructure
    - IT & Digital Transformation
    - Banking & Financial Services
    - Automotive & EV
    - Power & Utilities, etc.
    """
    sector_map: dict[str, str] = {}

    # 1. Populate with NIFTY 500 if available
    if include_nifty500:
        try:
            nifty_df = fetch_nifty500_symbol_list()
            for _, r in nifty_df.iterrows():
                sym = r["symbol"]
                sec = r["sector"]
                sector_map[sym] = sec
                sector_map[f"{sym}.NS"] = sec
                sector_map[f"{sym}.BO"] = sec
        except Exception as exc:
            logger.debug(f"Could not load Nifty 500 for sector mapping: {exc}")

    # 2. Curated thematic sector mapping overrides with high-conviction thematic classifications
    for sym, sec in CURATED_THEMATIC_SECTOR_MAP.items():
        clean = _clean_symbol(sym)
        sector_map[clean] = sec
        sector_map[f"{clean}.NS"] = sec
        sector_map[f"{clean}.BO"] = sec

    return sector_map


def _get_universe_cache_path(symbols: Sequence[str], period: str) -> Path:
    """Generate a deterministic Parquet cache path for a given batch of symbols."""
    clean_syms = sorted({_clean_symbol(s) for s in symbols})
    batch_sig = hashlib.md5(",".join(clean_syms).encode("utf-8")).hexdigest()[:10]
    return Path("data/cache") / f"universe_{len(clean_syms)}_{batch_sig}_{period}.parquet"


def fetch_angel_one_ohlcv(
    symbols: Sequence[str] = DEFAULT_INDIAN_UNIVERSE,
    days: int = 300,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Fetch official historical bars using Angel One SmartAPI connector."""
    try:
        from blumberg_market_radar.connectors.angel_one import get_angel_connector
        conn = get_angel_connector()
        df = conn.fetch_bars_for_symbols(symbols, days=days, use_cache=use_cache)
        if not df.empty:
            return validate_ohlcv(df)
    except Exception as exc:
        logger.warning(f"Angel One fetch exception: {exc}")
    return pd.DataFrame()


def fetch_historical_ohlcv(
    symbols: Sequence[str] = DEFAULT_INDIAN_UNIVERSE,
    period: str = "2y",
    cache_path: Path | str | None = None,
    use_cache: bool = True,
    data_source: str = "yfinance",
    **kwargs,
) -> pd.DataFrame:
    """Fetch daily OHLCV bars for given Indian symbols using Angel One or Yahoo Finance with parquet caching.

    Falls back to a deterministic synthetic Indian market dataset if internet
    or provider is temporarily unavailable.
    """
    # 1. Angel One SmartAPI institutional feed if selected
    if data_source == "angel_one":
        angel_df = fetch_angel_one_ohlcv(symbols, days=300 if "1y" in period or "2y" in period else 120, use_cache=use_cache)
        if not angel_df.empty:
            logger.info(f"Loaded {len(angel_df)} bars for {angel_df['symbol'].nunique()} symbols via Angel One SmartAPI.")
            return angel_df

    # Determine cache file path
    if cache_path is not None:
        target_cache = Path(cache_path)
    else:
        target_cache = _get_universe_cache_path(symbols, period)

    if use_cache and target_cache.exists():
        try:
            cached_df = pd.read_parquet(target_cache)
            logger.info(f"Loaded {len(cached_df)} bars from cache {target_cache}")
            return validate_ohlcv(cached_df)
        except Exception as exc:
            logger.warning(f"Failed to read cache {target_cache}: {exc}. Re-fetching.")

    frames: list[pd.DataFrame] = []
    logger.info(f"Downloading historical data for {len(symbols)} symbols...")

    try:
        raw_data = yf.download(
            tickers=list(symbols),
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
        )

        for sym in symbols:
            try:
                sub_df = raw_data[sym] if len(symbols) > 1 else raw_data
                if sub_df is None or sub_df.empty:
                    continue

                sub_df = sub_df.reset_index()
                sub_df.columns = [str(c).lower().replace(" ", "_") for c in sub_df.columns]

                date_col = "date" if "date" in sub_df.columns else sub_df.columns[0]
                clean_sym = _clean_symbol(sym)

                renamed = pd.DataFrame({
                    "date": pd.to_datetime(sub_df[date_col], utc=True),
                    "symbol": clean_sym,
                    "open": pd.to_numeric(sub_df["open"], errors="coerce"),
                    "high": pd.to_numeric(sub_df["high"], errors="coerce"),
                    "low": pd.to_numeric(sub_df["low"], errors="coerce"),
                    "close": pd.to_numeric(sub_df["close"], errors="coerce"),
                    "volume": pd.to_numeric(sub_df["volume"], errors="coerce"),
                })
                renamed = renamed.dropna(subset=["close", "volume"])
                renamed = renamed[renamed["volume"] > 0]
                if not renamed.empty:
                    frames.append(renamed)
            except Exception as sym_err:
                logger.debug(f"Could not parse symbol {sym}: {sym_err}")

    except Exception as fetch_err:
        logger.warning(f"Live market data fetch encountered error: {fetch_err}. Using fallback.")

    if not frames:
        logger.info(f"Generating realistic synthetic Indian market dataset for {len(symbols)} equities.")
        synthetic_df = generate_synthetic_universe(symbols, num_days=300)
        if use_cache:
            try:
                target_cache.parent.mkdir(parents=True, exist_ok=True)
                synthetic_df.to_parquet(target_cache, index=False)
            except Exception as w_err:
                logger.debug(f"Could not write synthetic cache: {w_err}")
        return synthetic_df

    combined = pd.concat(frames, ignore_index=True)
    validated = validate_ohlcv(combined)

    if use_cache:
        try:
            target_cache.parent.mkdir(parents=True, exist_ok=True)
            validated.to_parquet(target_cache, index=False)
        except Exception as write_err:
            logger.warning(f"Failed to write parquet cache to {target_cache}: {write_err}")

    return validated


def fetch_benchmark(period: str = "2y", data_source: str = "yfinance", **kwargs) -> pd.DataFrame:
    """Fetch NIFTY 50 benchmark daily bars."""
    if data_source == "angel_one":
        try:
            from blumberg_market_radar.connectors.angel_one import get_angel_connector
            conn = get_angel_connector()
            days = 300 if "1y" in period or "2y" in period else 120
            bench = conn.fetch_nifty_benchmark(days=days)
            if not bench.empty:
                return validate_ohlcv(bench)
        except Exception as e:
            logger.warning(f"Angel One benchmark fetch failed: {e}. Falling back to default.")

    try:
        raw = yf.download(
            tickers=BENCHMARK_SYMBOL,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
        ).reset_index()

        raw.columns = [str(c).lower().replace(" ", "_") for c in raw.columns]
        date_col = "date" if "date" in raw.columns else raw.columns[0]
        bench = pd.DataFrame({
            "date": pd.to_datetime(raw[date_col], utc=True),
            "symbol": "NIFTY50",
            "open": pd.to_numeric(raw["open"], errors="coerce"),
            "high": pd.to_numeric(raw["high"], errors="coerce"),
            "low": pd.to_numeric(raw["low"], errors="coerce"),
            "close": pd.to_numeric(raw["close"], errors="coerce"),
            "volume": pd.to_numeric(raw["volume"], errors="coerce"),
        }).dropna()
        return validate_ohlcv(bench)
    except Exception:
        # Fallback synthetic benchmark
        dates = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=300, freq="B")
        prices = 22000.0 * np.exp(np.cumsum(np.random.normal(0.0004, 0.008, len(dates))))
        return pd.DataFrame({
            "date": dates,
            "symbol": "NIFTY50",
            "open": prices * 0.998,
            "high": prices * 1.005,
            "low": prices * 0.995,
            "close": prices,
            "volume": 200000000,
        })


def generate_synthetic_universe(
    symbols: Sequence[str] = DEFAULT_INDIAN_UNIVERSE,
    num_days: int = 300,
) -> pd.DataFrame:
    """Generate realistic, deterministic daily bars for Indian equities for offline testing.

    Seamlessly handles 50-100+ symbols spanning diverse prices (from ₹15 to ₹15,000)
    and sector-specific behaviors (Defence, Green Energy, Railways, EMS breakouts).
    """
    dates = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=num_days, freq="B")
    all_bars = []
    sector_map = get_symbol_sector_map(include_nifty500=False)

    # Breakout momentum stocks exhibiting volume explosion and stage-2 breakout
    breakout_leaders = {
        "BEL", "HAL", "MAZDOCK", "TRENT", "BSE", "SUZLON", "RVNL",
        "DIXON", "KAYNES", "TITAGARH", "IREDA", "INOXWIND", "PARAS", "BORORENEW"
    }

    for sym in symbols:
        clean = _clean_symbol(sym)
        start_p = _deterministic_base_price(clean)
        sector = sector_map.get(clean, "Diversified / General")

        # Independent deterministic RNG per symbol to ensure reproducibility
        sym_hash_int = int(hashlib.md5(clean.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(sym_hash_int)

        # Sector-specific momentum drift and volatility
        if sector in ["Defence & Aerospace", "Railways & Infra", "Green Energy & Wind", "EMS & Technology"]:
            daily_drift = 0.0009
            daily_vol = 0.022
        elif sector in ["Consumer & Retail", "Financial Market Infrastructure"]:
            daily_drift = 0.0007
            daily_vol = 0.019
        elif sector in ["IT & Digital Transformation", "Banking & Financial Services"]:
            daily_drift = 0.0004
            daily_vol = 0.014
        else:
            daily_drift = 0.0003
            daily_vol = 0.016

        # Higher volatility for high-beta / small-cap growth
        if clean in ["SUZLON", "MAZDOCK", "BSE", "RVNL", "INOXWIND", "IREDA", "BORORENEW", "PARAS", "MOTISONS"]:
            daily_vol = 0.026

        returns = rng.normal(daily_drift, daily_vol, num_days)

        # Introduce stage-1 pre-rally range compression base, then breakout acceleration
        is_breakout = clean in breakout_leaders
        if is_breakout:
            # Consolidation in sessions -30 to -11 (low volatility)
            if num_days >= 30:
                returns[-30:-10] *= 0.40
            # Sudden momentum surge in the last 10 sessions
            if num_days >= 10:
                returns[-10:] += rng.uniform(0.012, 0.022, min(10, num_days))

        price_series = start_p * np.exp(np.cumsum(returns))

        # Base volume inversely scaled with price to produce realistic daily turnover
        if start_p < 100:
            base_vol = 8_000_000
        elif start_p < 500:
            base_vol = 3_000_000
        elif start_p < 2000:
            base_vol = 800_000
        elif start_p < 5000:
            base_vol = 350_000
        else:
            base_vol = 120_000

        vol_noise = rng.lognormal(0.0, 0.35, num_days)
        if is_breakout and num_days >= 10:
            # Volume dry-up right before breakout (-20 to -10)
            if num_days >= 20:
                vol_noise[-20:-10] *= 0.55
            # Explosive institutional accumulation volume in last 10 days
            vol_noise[-10:] *= rng.uniform(2.5, 4.0, min(10, num_days))

        vols = np.maximum((base_vol * vol_noise).astype(int), 10_000)

        highs = price_series * (1.0 + np.abs(rng.normal(0.007, 0.004, num_days)))
        lows = price_series * (1.0 - np.abs(rng.normal(0.007, 0.004, num_days)))
        opens = price_series * (1.0 + rng.normal(0.001, 0.003, num_days))

        # Enforce strict OHLC consistency: high >= max(open, close), low <= min(open, close)
        highs = np.maximum(highs, np.maximum(opens, price_series)) + 0.1
        lows = np.maximum(np.minimum(lows, np.minimum(opens, price_series)) - 0.1, 0.5)

        df = pd.DataFrame({
            "date": dates,
            "symbol": clean,
            "open": np.round(opens, 2),
            "high": np.round(highs, 2),
            "low": np.round(lows, 2),
            "close": np.round(price_series, 2),
            "volume": vols,
        })
        all_bars.append(df)

    combined = pd.concat(all_bars, ignore_index=True)
    return validate_ohlcv(combined)
