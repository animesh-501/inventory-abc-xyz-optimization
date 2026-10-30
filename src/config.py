"""Paths, time windows and policy settings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = ROOT / "data" / "raw" / "online_retail_II.csv"
SQL_DIR = ROOT / "sql"
OUT_DIR = ROOT / "outputs"
CHART_DIR = ROOT / "charts"

# Year 1 classifies SKUs; year 2 tests the policies on demand the classification never saw.
YEAR1_START, YEAR2_START, YEAR2_END = "2009-12-07", "2010-12-06", "2011-12-05"   # Mondays, 52 weeks each

# ABC on year-1 revenue (cumulative share), XYZ on coefficient of variation of weekly demand
ABC_CUTS = (0.80, 0.95)
XYZ_CUTS = (0.5, 1.0)

# Replenishment
LEAD_TIME_WEEKS = 2
REVIEW_WEEKS = 1
PROTECTION_WEEKS = LEAD_TIME_WEEKS + REVIEW_WEEKS
FORECAST_WINDOW_WEEKS = 13      # forecast = trailing 13-week average demand

# Cycle service targets. Uniform policy uses one target for every SKU; the segmented policy
# protects high-value, predictable SKUs most and accepts lower service on low-value, erratic ones.
UNIFORM_GRID = [0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99]
UNIFORM_DEFAULT = 0.95
SEGMENT_TARGETS = {
    "AX": 0.98, "AY": 0.97, "AZ": 0.95,
    "BX": 0.96, "BY": 0.95, "BZ": 0.92,
    "CX": 0.93, "CY": 0.90, "CZ": 0.85,
}
