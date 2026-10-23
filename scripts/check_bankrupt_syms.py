import pandas as pd
from pathlib import Path

df_raw = pd.read_parquet("data/cache/historical_2010_2026/market_bars_2010_2026.parquet")
print("Symbols containing YES:", [s for s in df_raw["symbol"].unique() if "YES" in s])
print("Symbols containing IDEA:", [s for s in df_raw["symbol"].unique() if "IDEA" in s])
print("Symbols containing JET:", [s for s in df_raw["symbol"].unique() if "JET" in s])
print("Symbols containing RCOM:", [s for s in df_raw["symbol"].unique() if "RCOM" in s])
print("Symbols containing UNITECH:", [s for s in df_raw["symbol"].unique() if "UNITECH" in s])
