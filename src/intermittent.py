"""Forecasts built for intermittent demand, tested in the same year-2 replay.

Classification (Syntetos-Boylan, on year 1):
  ADI  = weeks / weeks with a sale           (average interval between sales)
  CV2  = squared CV of the non-zero weekly quantities
  smooth: ADI <= 1.32 and CV2 <= 0.49 | erratic: ADI <= 1.32, CV2 > 0.49
  intermittent: ADI > 1.32, CV2 <= 0.49 | lumpy: ADI > 1.32, CV2 > 0.49

Forecasts (smoothing constant fixed at 0.1, a common textbook value; nothing is tuned here):
  SBA  Croston with the Syntetos-Boylan bias correction. Size and interval are updated only in
       weeks with a sale, so the forecast never decays while an item sits unsold.
  TSB  Teunter-Syntetos-Babai. Size is updated in weeks with a sale; the probability of a sale
       is updated every week, so the forecast decays when an item stops selling.

The new forecast replaces the 13-week average only on intermittent and lumpy SKUs; smooth and
erratic SKUs keep the 13-week average. Sigma stays the trailing 52-week standard deviation, so
the only thing that changes is the forecast. Each method is run across the same service targets
as the uniform policy and compared at equal fill rate on the full year 2.
"""
import warnings

import numpy as np
import pandas as pd

import config as C
import inventory as inv

ADI_CUT, CV2_CUT = 1.32, 0.49
ALPHA = 0.1


def classify(d, n_y1):
    """Syntetos-Boylan class per SKU from year-1 weekly demand."""
    y1 = d[:, :n_y1]
    nz = y1 > 0
    k = nz.sum(axis=1)
    adi = np.where(k > 0, n_y1 / np.maximum(k, 1), np.inf)
    sizes = np.where(nz, y1, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean_nz = np.nanmean(sizes, axis=1)
        std_nz = np.nanstd(sizes, axis=1, ddof=1)        # undefined (NaN) with one sale -> treated as 0
    cv2 = np.nan_to_num((std_nz / mean_nz) ** 2)
    cls = np.where(adi <= ADI_CUT, np.where(cv2 <= CV2_CUT, "smooth", "erratic"),
                   np.where(cv2 <= CV2_CUT, "intermittent", "lumpy"))
    return pd.DataFrame({"adi": adi, "cv2": cv2, "sales_weeks_y1": k, "sb_class": cls})


def croston_sba(d, alpha=ALPHA):
    """SBA forecast known at the end of each week (SKU x week). 0 until the first sale."""
    n, T = d.shape
    z = np.zeros(n); p = np.zeros(n); q = np.ones(n); seen = np.zeros(n, bool)
    out = np.zeros((n, T))
    for t in range(T):
        x = d[:, t]
        hit = x > 0
        first = hit & ~seen
        z[first], p[first] = x[first], q[first]
        upd = hit & seen
        z[upd] += alpha * (x[upd] - z[upd])
        p[upd] += alpha * (q[upd] - p[upd])
        seen |= hit
        q = np.where(hit, 1, q + 1)
        out[:, t] = np.where(seen, (1 - alpha / 2) * z / np.maximum(p, 1e-9), 0)
    return out


def tsb(d, alpha=ALPHA, beta=ALPHA):
    """TSB forecast known at the end of each week. Probability starts at the share of weeks with a sale
    seen so far until the first sale, then is smoothed every week."""
    n, T = d.shape
    z = np.zeros(n); pr = np.zeros(n); seen = np.zeros(n, bool)
    out = np.zeros((n, T))
    for t in range(T):
        x = d[:, t]
        hit = x > 0
        first = hit & ~seen
        z[first] = x[first]
        pr[first] = 1.0 / (t + 1)                         # one sale in t+1 weeks so far
        upd = seen.copy()
        z[upd & hit] += alpha * (x[upd & hit] - z[upd & hit])
        pr[upd] += beta * (hit[upd].astype(float) - pr[upd])
        seen |= hit
        out[:, t] = pr * z
    return out


def _sweep(d, n_y1, price, fc, sd, name):
    rows = []
    for lvl in C.UNIFORM_GRID:
        z = np.full(d.shape[0], inv.z_for(lvl))
        rows.append({"method": name, "target": lvl, **inv.summarize(inv.simulate(d, n_y1, z, price, (fc, sd)))})
    return rows


def _inventory_at_fill(d, n_y1, price, fc, sd, fill):
    g = pd.DataFrame(_sweep(d, n_y1, price, fc, sd, ""))
    return inv.frontier(g)(fill)


def run(weekly, segments, dormancy_weeks=8, alphas=(0.05, 0.1, 0.2, 0.3)):
    d, n_y1 = inv.matrices(weekly, segments)
    price = segments.unit_price.to_numpy()
    cls = classify(d, n_y1)
    lumpy = cls.sb_class.isin(["intermittent", "lumpy"]).to_numpy()

    fc13, sd = inv.rolling_stats(d, n_y1)
    sba = croston_sba(d)[:, n_y1 - 1:]
    tsb_fc = tsb(d)[:, n_y1 - 1:]
    methods = {
        "13-week average (current)": fc13,
        "SBA on intermittent/lumpy SKUs": np.where(lumpy[:, None], sba, fc13),
        "TSB on intermittent/lumpy SKUs": np.where(lumpy[:, None], tsb_fc, fc13),
    }

    # Dormancy rule on top of each forecast (same rule as optimize.dormancy_rule)
    dormant = pd.DataFrame(d.T).rolling(dormancy_weeks, min_periods=1).sum().to_numpy().T[:, n_y1 - 1:] == 0
    rows = []
    for name, fc in methods.items():
        rows += _sweep(d, n_y1, price, fc, sd, name)
        rows += _sweep(d, n_y1, price, np.where(dormant, 0, fc), np.where(dormant, 0, sd),
                       f"{name} + {dormancy_weeks}-week dormancy rule")
    curves = pd.DataFrame(rows)

    # Inventory each method needs at the current policy's fill rate (13-week average, 95% target)
    base = curves[(curves.method == "13-week average (current)") & (curves.target == C.UNIFORM_DEFAULT)].iloc[0]
    out = []
    for name, g in curves.groupby("method", sort=False):
        at95 = g[g.target == C.UNIFORM_DEFAULT].iloc[0]
        inv_same_fill = inv.frontier(g)(base.revenue_fill_rate)
        out.append({"method": name,
                    "fill_rate_at_95_target": at95.revenue_fill_rate,
                    "inventory_at_95_target": at95.avg_inventory_value,
                    "inventory_at_current_fill": inv_same_fill,
                    "inventory_vs_current_same_fill": inv_same_fill / base.avg_inventory_value - 1})
    comparison = pd.DataFrame(out)

    # Forecast accuracy on year 2, one week ahead, intermittent/lumpy SKUs only (valued at price).
    # Split the forecast between SKUs that never sold again in year 2 and ones that did.
    actual = d[:, n_y1:] * price[:, None]
    dead = d[:, n_y1:].sum(axis=1) == 0
    total = actual[lumpy].sum()
    acc = []
    for name, fc in methods.items():
        f = fc[:, :-1] * price[:, None]                  # forecast made at end of week t-1 for week t
        acc.append({"method": name,
                    "wape": np.abs(f - actual)[lumpy].sum() / total,
                    "bias": (f - actual)[lumpy].sum() / total,
                    "forecast_on_dead_skus": f[lumpy & dead].sum(),
                    "bias_on_live_skus": (f - actual)[lumpy & ~dead].sum() / actual[lumpy & ~dead].sum(),
                    "actual_demand": total})
    accuracy = pd.DataFrame(acc)

    # Sensitivity to the smoothing constant (all on the full year; reported as a range, not tuned)
    sens = []
    for a in alphas:
        for name, fc in [("SBA", croston_sba(d, a)), ("TSB", tsb(d, a, a))]:
            fc = np.where(lumpy[:, None], fc[:, n_y1 - 1:], fc13)
            sens.append({"method": name, "alpha": a, "inventory_vs_current_same_fill":
                         _inventory_at_fill(d, n_y1, price, fc, sd, base.revenue_fill_rate)
                         / base.avg_inventory_value - 1})
    sensitivity = pd.DataFrame(sens)

    cls.insert(0, "stock_code", segments.stock_code.to_numpy())
    cls["segment"] = segments.segment.to_numpy()
    cls["revenue_y1"] = segments.revenue.to_numpy()
    class_summary = (cls.groupby("sb_class")
                     .agg(skus=("stock_code", "size"), revenue_y1=("revenue_y1", "sum"),
                          median_adi=("adi", "median"), median_cv2=("cv2", "median"))
                     .reindex(["smooth", "erratic", "intermittent", "lumpy"]).fillna(0))
    class_summary["sku_share"] = class_summary.skus / class_summary.skus.sum()
    class_summary["revenue_share"] = class_summary.revenue_y1 / class_summary.revenue_y1.sum()
    xyz_cross = pd.crosstab(segments.xyz.to_numpy(), cls.sb_class, rownames=["xyz"], colnames=["sb_class"])
    return {"classes": cls, "class_summary": class_summary.reset_index(), "xyz_cross": xyz_cross,
            "curves": curves, "comparison": comparison, "accuracy": accuracy,
            "sensitivity": sensitivity, "current_fill": base.revenue_fill_rate,
            "lumpy_skus": int(lumpy.sum()), "lumpy_dead_skus": int((lumpy & dead).sum())}
