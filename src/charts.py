"""Static charts for the README."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mtick  # noqa: E402
import numpy as np  # noqa: E402

import config as C  # noqa: E402

INK, MUTED, ACCENT, LIGHT, GOOD, WARN = "#1f2328", "#656d76", "#1f6feb", "#afb8c1", "#2da44e", "#bf8700"

plt.rcParams.update({
    "figure.dpi": 150, "font.size": 10, "axes.edgecolor": "#d0d7de", "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titleweight": "bold", "axes.titlesize": 12, "axes.titlelocation": "left",
    "axes.grid": True, "grid.color": "#eaeef2", "grid.linewidth": 0.8, "legend.frameon": False,
})


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(C.CHART_DIR / name, bbox_inches="tight")
    plt.close(fig)


def segment_matrix(m):
    fig, ax = plt.subplots(figsize=(6.5, 4))
    grid = np.zeros((3, 3))
    for r in m.itertuples():
        grid["ABC".index(r.abc), "XYZ".index(r.xyz)] = r.revenue_share
    ax.imshow(grid, cmap="Blues", vmin=0, vmax=0.6)
    for r in m.itertuples():
        i, j = "ABC".index(r.abc), "XYZ".index(r.xyz)
        ax.text(j, i, f"{r.segment}\n{r.skus:,} SKUs ({r.sku_share:.0%})\n{r.revenue_share:.0%} of revenue",
                ha="center", va="center", fontsize=8.5, color="white" if r.revenue_share > 0.3 else INK)
    for i in range(3):
        for j in range(3):
            if grid[i, j] == 0:
                ax.text(j, i, f"{'ABC'[i]}{'XYZ'[j]}\nnone", ha="center", va="center", fontsize=8.5, color=MUTED)
    ax.set_xticks(range(3), ["X  (steady)", "Y  (variable)", "Z  (erratic)"])
    ax.set_yticks(range(3), ["A  (top 80% revenue)", "B  (next 15%)", "C  (last 5%)"])
    ax.grid(False)
    ax.set_title("ABC / XYZ segmentation, year 1")
    _save(fig, "01_segment_matrix.png")


def variability(seg):
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.hist(seg.cv.clip(upper=7), bins=60, color=ACCENT)
    for x in C.XYZ_CUTS:
        ax.axvline(x, color=INK, ls="--", lw=1)
    z = (seg.xyz == "Z").mean()
    ax.text(C.XYZ_CUTS[1] + 0.1, ax.get_ylim()[1] * 0.85, f"Z: {z:.0%} of SKUs", fontsize=9.5, color=INK)
    ax.set_xlabel("Coefficient of variation of weekly demand (std / mean; last bar = 7 or more)")
    ax.set_ylabel("SKUs")
    ax.set_title("Most SKUs sell in lumps, not a steady stream")
    _save(fig, "02_demand_variability.png")


def tradeoff(uniform_curve, comparison, dormancy):
    u = uniform_curve[uniform_curve.window == "year"].sort_values("avg_inventory_value")
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    ax.plot(u.avg_inventory_value / 1e6, u.revenue_fill_rate * 100, color=MUTED, marker="o", ms=3.5,
            label="Same target for every SKU (80% ... 99%)")
    yr = comparison[comparison.window == "year"].set_index("policy")
    for name, color, marker in [("Textbook ABC/XYZ targets", WARN, "s")]:
        ax.scatter(yr.loc[name, "avg_inventory_value"] / 1e6, yr.loc[name, "revenue_fill_rate"] * 100,
                   color=color, marker=marker, s=60, zorder=5, label=name)
    dz = dormancy.dropna(subset=["weeks_without_sale"])
    ax.scatter(dz.avg_inventory_value / 1e6, dz.revenue_fill_rate * 100, color=GOOD, s=60, zorder=5,
               label="95% target + stop reordering after N quiet weeks")
    for r in dz[dz.weeks_without_sale.isin([8, 26])].itertuples():
        ax.annotate(f"N={int(r.weeks_without_sale)}", (r.avg_inventory_value / 1e6, r.revenue_fill_rate * 100),
                    xytext=(0, 9), textcoords="offset points", fontsize=8.5, color=INK, ha="center")
    ax.set_xlim(0.95, 1.85)
    ax.set_ylim(82, 92.5)
    ax.set_xlabel("Average inventory value, $ millions (at selling price)")
    ax.set_ylabel("Revenue fill rate")
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.legend(loc="lower right", fontsize=8.5)
    ax.set_title("Year-2 replay: service vs. stock under each policy")
    _save(fig, "03_policy_tradeoff.png")


def dormancy_bars(dormancy):
    dz = dormancy.dropna(subset=["weeks_without_sale"])
    fig, ax = plt.subplots(figsize=(8, 2.8))
    labels = [f"{int(n)} weeks" for n in dz.weeks_without_sale]
    bars = ax.barh(labels, -dz.inventory_change * 100, color=GOOD)
    ax.bar_label(bars, labels=[f"-{-c:.1%} stock   (+${l:,.0f} lost sales)"
                               for c, l in zip(dz.inventory_change, dz.extra_lost_sales)],
                 padding=4, fontsize=9, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 20)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter())
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Average inventory removed")
    ax.set_title("Stop reordering after N weeks without a sale")
    _save(fig, "04_dormancy_rule.png")


def intermittent_forecasts(res):
    """Left: stock vs fill rate per forecast. Right: what each forecast expected from items that never sold again."""
    cur, sba, tsb = "13-week average (current)", "SBA on intermittent/lumpy SKUs", "TSB on intermittent/lumpy SKUs"
    style = {cur: (MUTED, "13-week average (current)"), sba: (WARN, "SBA (Croston, bias-corrected)"),
             tsb: (ACCENT, "TSB")}
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"width_ratios": [1.35, 1]})
    for m, (color, label) in style.items():
        g = res["curves"][res["curves"].method == m].sort_values("avg_inventory_value")
        ax.plot(g.avg_inventory_value / 1e6, g.revenue_fill_rate * 100, color=color, lw=2, marker="o", ms=3.5,
                label=label)
    ax.axhline(res["current_fill"] * 100, color=INK, lw=0.8, ls=":")
    ax.text(0.86, res["current_fill"] * 100 - 0.6, f"today's fill rate {res['current_fill']:.1%}", fontsize=8.5, color=MUTED)
    comp = res["comparison"].set_index("method")
    for m, offset, ha in [(sba, (8, -16), "left"), (tsb, (-8, 10), "right")]:
        x = comp.loc[m, "inventory_at_current_fill"]
        ax.scatter([x / 1e6], [res["current_fill"] * 100], color=style[m][0], s=40, zorder=5)
        ax.annotate(f"{style[m][1].split(' (')[0]}: {comp.loc[m, 'inventory_vs_current_same_fill']:+.1%} stock",
                    (x / 1e6, res["current_fill"] * 100), xytext=offset, textcoords="offset points",
                    fontsize=8.5, color=INK, ha=ha)
    ax.set_xlabel("Average inventory value, $ millions (at selling price)")
    ax.set_ylabel("Revenue fill rate")
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.legend(loc="lower right", fontsize=8.5)
    ax.set_title("Same service targets (80% ... 99%), three forecasts")

    acc = res["accuracy"].set_index("method").loc[[cur, sba, tsb]]
    bars = bx.barh([style[m][1] for m in acc.index], acc.forecast_on_dead_skus / 1e6,
                   color=[style[m][0] for m in acc.index], height=0.55)
    bx.set_axisbelow(True)
    bx.bar_label(bars, labels=[f"${v / 1e6:.2f}M" for v in acc.forecast_on_dead_skus], padding=4, fontsize=9, color=INK)
    bx.invert_yaxis()
    bx.set_xlim(0, acc.forecast_on_dead_skus.max() / 1e6 * 1.3)
    bx.grid(axis="y", visible=False)
    bx.set_xlabel("Year-2 forecast, $ millions (at selling price)")
    bx.set_title(f"Demand forecast for {res['lumpy_dead_skus']:,} items\nthat never sold again (actual: $0)", fontsize=11)
    _save(fig, "05_intermittent_forecasts.png")


def make_all(t, opt, dormancy, intermittent=None):
    segment_matrix(t["segment_matrix"])
    variability(t["segments"])
    tradeoff(opt["uniform_curve"], opt["comparison"], dormancy)
    dormancy_bars(dormancy)
    if intermittent is not None:
        intermittent_forecasts(intermittent)
