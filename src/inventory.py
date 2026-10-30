"""Replay year 2 week by week under different service-level policies.

Policy (periodic review, order-up-to), recomputed every week from history only:
  forecast  = average weekly demand over the last 13 weeks
  sigma     = standard deviation of weekly demand over the last 52 weeks
  S         = 3 x forecast + z x sigma x sqrt(3)      (2-week lead time + 1-week review)
Lost sales, no backorders. Inventory and sales are valued at the SKU's year-1 median price.
Every SKU segmented in year 1 is included, including ones that stop selling in year 2:
a planner doesn't know in advance which items are about to die.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm

import config as C


def matrices(weekly, segments):
    w = weekly[weekly.stock_code.isin(segments.stock_code)]
    d = w.pivot(index="stock_code", columns="week_start", values="demand").loc[segments.stock_code]
    n_y1 = int((~weekly.drop_duplicates("week_start").is_year2).sum())
    return d.to_numpy(dtype=float), n_y1


def rolling_stats(d, n_y1):
    """Forecast and sigma known at the END of each week; column 0 = just before year 2 starts."""
    df = pd.DataFrame(d.T)
    mean = df.rolling(C.FORECAST_WINDOW_WEEKS, min_periods=1).mean().to_numpy().T
    std = df.rolling(52, min_periods=8).std().fillna(0).to_numpy().T
    return mean[:, n_y1 - 1:], std[:, n_y1 - 1:]


def simulate(d, n_y1, z, price, stats=None):
    """Returns value matrices (SKU x week): demand, sold, average on-hand inventory."""
    demand = d[:, n_y1:]
    n, T = demand.shape
    fc, sd = stats if stats is not None else rolling_stats(d, n_y1)
    L = C.PROTECTION_WEEKS
    ss = z[:, None] * sd * np.sqrt(L)
    target = L * fc + ss

    arrive = np.zeros((n, T + L))
    arrive[:, 1] = arrive[:, 2] = fc[:, 0]          # orders already in transit
    on_hand = fc[:, 0] + ss[:, 0]
    sold = np.zeros((n, T))
    inv = np.zeros((n, T))
    for t in range(T):
        on_hand = on_hand + arrive[:, t]
        start = on_hand.copy()
        sold[:, t] = np.minimum(on_hand, demand[:, t])
        on_hand = on_hand - sold[:, t]
        inv[:, t] = (start + on_hand) / 2
        position = on_hand + arrive[:, t + 1:t + L].sum(axis=1)
        arrive[:, t + L] += np.maximum(0, target[:, t + 1] - position)
    p = price[:, None]
    return {"demand": demand * p, "sold": sold * p, "inv": inv * p,
            "stockout": (sold < demand - 1e-9) & (demand > 0), "demand_week": demand > 0}


def summarize(res, rows=None, weeks=slice(None)):
    r = slice(None) if rows is None else rows
    dem, sold = res["demand"][r, weeks].sum(), res["sold"][r, weeks].sum()
    return {
        "revenue_fill_rate": sold / dem if dem else np.nan,
        "avg_inventory_value": res["inv"][r, weeks].sum(axis=0).mean(),
        "lost_sales_value": dem - sold,
        "in_stock_rate_on_demand_weeks": 1 - res["stockout"][r, weeks].sum() / max(res["demand_week"][r, weeks].sum(), 1),
    }


def frontier(points):
    """Interpolate inventory needed for a given fill rate along a policy's trade-off curve."""
    p = points.sort_values("revenue_fill_rate")
    return lambda f: float(np.interp(f, p.revenue_fill_rate, p.avg_inventory_value)) \
        if p.revenue_fill_rate.min() <= f <= p.revenue_fill_rate.max() else np.nan


def z_for(targets):
    return norm.ppf(np.asarray(targets, dtype=float))
