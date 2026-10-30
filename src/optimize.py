"""Choose a service target per ABC/XYZ segment from data, then test it out of sample.

SKUs don't interact, so one simulation per service level gives every segment's result at that
level. Targets are chosen on the first 26 weeks of year 2 (fit) and judged on the last 26 (test).

Allocation is greedy marginal analysis: start every segment at the lowest level, then keep
raising the segment whose next step buys the most revenue per extra dollar of inventory.
That traces the best trade-off curve; we take the cheapest point on it that matches the uniform
95% policy's fit-period fill rate.
"""
import numpy as np
import pandas as pd

import config as C
import inventory as inv

LEVELS = sorted(set(C.UNIFORM_GRID) | set(C.SEGMENT_TARGETS.values()) | {0.50, 0.60, 0.70, 0.75, 0.995})


def run(weekly, segments):
    d, n_y1 = inv.matrices(weekly, segments)
    price = segments.unit_price.to_numpy()
    seg = segments.segment.to_numpy()
    segs = sorted(set(seg))
    stats = inv.rolling_stats(d, n_y1)
    T = d.shape[1] - n_y1
    fit, test = slice(0, T // 2), slice(T // 2, T)

    # cache[(segment, level, window)] = (sold, demand, inventory) totals
    cache, sims = {}, {}
    for lvl in LEVELS:
        res = inv.simulate(d, n_y1, np.full(len(seg), inv.z_for(lvl)), price, stats)
        sims[lvl] = res
        for s in segs:
            m = seg == s
            for wname, w in [("fit", fit), ("test", test), ("year", slice(None))]:
                cache[(s, lvl, wname)] = (res["sold"][m, w].sum(), res["demand"][m, w].sum(),
                                          res["inv"][m, w].sum(axis=0).mean())

    def total(alloc, window):
        sold = sum(cache[(s, alloc[s], window)][0] for s in segs)
        dem = sum(cache[(s, alloc[s], window)][1] for s in segs)
        stock = sum(cache[(s, alloc[s], window)][2] for s in segs)
        return {"revenue_fill_rate": sold / dem, "avg_inventory_value": stock, "lost_sales_value": dem - sold}

    # Greedy frontier on the fit window
    idx = {s: 0 for s in segs}
    path = [dict(idx)]
    while any(idx[s] < len(LEVELS) - 1 for s in segs):
        best, best_gain = None, -np.inf
        for s in segs:
            if idx[s] == len(LEVELS) - 1:
                continue
            a, b = cache[(s, LEVELS[idx[s]], "fit")], cache[(s, LEVELS[idx[s] + 1], "fit")]
            d_sold, d_inv = b[0] - a[0], b[2] - a[2]
            gain = np.inf if d_inv <= 0 else d_sold / d_inv
            if gain > best_gain:
                best, best_gain = s, gain
        idx[best] += 1
        path.append(dict(idx))
    allocs = [{s: LEVELS[i] for s, i in p.items()} for p in path]
    curve = pd.DataFrame([{**total(a, "fit"), **{f"test_{k}": v for k, v in total(a, "test").items()}}
                          for a in allocs])

    uniform = {lvl: {s: lvl for s in segs} for lvl in LEVELS}
    base = uniform[C.UNIFORM_DEFAULT]
    target_fill = total(base, "fit")["revenue_fill_rate"]
    ok = curve[curve.revenue_fill_rate >= target_fill]
    chosen = allocs[int(ok.avg_inventory_value.idxmin())]
    textbook = {s: C.SEGMENT_TARGETS[s] for s in segs}

    policies = {"Uniform 95%": base, "Textbook ABC/XYZ targets": textbook, "Optimized per segment": chosen}
    comparison = pd.DataFrame([{"policy": n, "window": w, **total(a, w)}
                               for n, a in policies.items() for w in ["fit", "test", "year"]])
    uniform_curve = pd.DataFrame([{"target": l, "window": w, **total(a, w)}
                                  for l, a in uniform.items() for w in ["fit", "test", "year"]])

    # Inventory a uniform policy would need to reach each policy's fill rate, in the same window
    curves = {w: inv.frontier(uniform_curve[uniform_curve.window == w]) for w in ["fit", "test", "year"]}
    comparison["uniform_inventory_for_same_fill"] = [curves[r.window](r.revenue_fill_rate)
                                                     for r in comparison.itertuples()]
    comparison["inventory_vs_uniform_same_fill"] = (comparison.avg_inventory_value
                                                    / comparison.uniform_inventory_for_same_fill - 1)

    by_segment = pd.DataFrame([
        {"segment": s, "skus": int((seg == s).sum()), "textbook_target": textbook[s], "optimized_target": chosen[s],
         **{f"{n}_{k}": v for n, a in [("uniform95", base), ("optimized", chosen)]
            for k, v in zip(["sold", "demand", "inventory"], cache[(s, a[s], "test")])}}
        for s in segs])
    by_segment["uniform95_fill"] = by_segment.uniform95_sold / by_segment.uniform95_demand
    by_segment["optimized_fill"] = by_segment.optimized_sold / by_segment.optimized_demand

    # Items that never sold again in year 2: what the default policy kept on the shelf for them
    dead = d[:, n_y1:].sum(axis=1) == 0
    res95 = sims[C.UNIFORM_DEFAULT]
    dead_stock = {
        "skus_not_sold_in_year2": int(dead.sum()),
        "share_of_skus": float(dead.mean()),
        "avg_inventory_value_on_them": float(res95["inv"][dead].sum(axis=0).mean()),
        "share_of_inventory": float(res95["inv"][dead].sum(axis=0).mean() / res95["inv"].sum(axis=0).mean()),
    }
    return {"comparison": comparison, "uniform_curve": uniform_curve, "greedy_curve": curve,
            "by_segment": by_segment, "dead_stock": dead_stock, "chosen": chosen}


def dormancy_rule(weekly, segments, windows=(8, 13, 17, 26)):
    """Stop reordering a SKU once it has gone N weeks without a sale (resume when it sells again).

    Stock already on hand stays until it sells. Uses the default uniform target for everything else,
    and is evaluated on the full year 2 (no parameter is fitted).
    """
    d, n_y1 = inv.matrices(weekly, segments)
    price = segments.unit_price.to_numpy()
    fc, sd = inv.rolling_stats(d, n_y1)
    z = np.full(len(segments), inv.z_for(C.UNIFORM_DEFAULT))
    base = inv.summarize(inv.simulate(d, n_y1, z, price, (fc, sd)))
    rows = [{"rule": "No rule (uniform 95%)", "weeks_without_sale": None, **base}]
    for n in windows:
        dormant = pd.DataFrame(d.T).rolling(n, min_periods=1).sum().to_numpy().T[:, n_y1 - 1:] == 0
        res = inv.summarize(inv.simulate(d, n_y1, z, price, (np.where(dormant, 0, fc), np.where(dormant, 0, sd))))
        rows.append({"rule": f"Stop after {n} weeks without a sale", "weeks_without_sale": n, **res})
    out = pd.DataFrame(rows)
    out["inventory_change"] = out.avg_inventory_value / base["avg_inventory_value"] - 1
    out["extra_lost_sales"] = out.lost_sales_value - base["lost_sales_value"]
    out["demand_value"] = (d[:, n_y1:] * price[:, None]).sum()
    return out
