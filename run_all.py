"""Run the full analysis: SQL clean-up and segmentation -> year-2 policy replays -> charts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd  # noqa: E402

import charts  # noqa: E402
import config as C  # noqa: E402
import data  # noqa: E402
import intermittent  # noqa: E402
import optimize  # noqa: E402

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)


def main():
    C.OUT_DIR.mkdir(exist_ok=True)
    C.CHART_DIR.mkdir(exist_ok=True)

    t = data.build()
    seg = t["segments"]
    print("\nSegment matrix (year 1)\n", t["segment_matrix"].round(3).to_string(index=False))

    opt = optimize.run(t["weekly_demand"], seg)
    print("\nPolicy comparison (fit = first 26 weeks of year 2, test = last 26, year = all 52)\n",
          opt["comparison"].round(4).to_string(index=False))
    print("\nTargets per segment\n", opt["by_segment"].round(3).to_string(index=False))

    dormancy = optimize.dormancy_rule(t["weekly_demand"], seg)
    print("\nDormancy rule, full year 2\n", dormancy.round(4).to_string(index=False))
    print("\nItems that never sold in year 2\n", opt["dead_stock"])

    im = intermittent.run(t["weekly_demand"], seg)
    print("\nSyntetos-Boylan demand classes (year 1)\n", im["class_summary"].round(3).to_string(index=False))
    print("\nXYZ class vs Syntetos-Boylan class (SKUs)\n", im["xyz_cross"].to_string())
    print("\nIntermittent-demand forecasts, full year 2 (compared at the current policy's fill rate)\n",
          im["comparison"].round(4).to_string(index=False))
    print("\nForecast accuracy, intermittent/lumpy SKUs, one week ahead\n", im["accuracy"].round(4).to_string(index=False))
    print("\nSensitivity to the smoothing constant\n", im["sensitivity"].round(4).to_string(index=False))

    comp = opt["comparison"].set_index(["policy", "window"])
    best = dormancy.iloc[1]
    summary = {
        "skus_segmented": len(seg),
        "share_skus_Z": (seg.xyz == "Z").mean(),
        "share_revenue_Z": seg.loc[seg.xyz == "Z", "revenue"].sum() / seg.revenue.sum(),
        "share_skus_A": (seg.abc == "A").mean(),
        "year2_demand_value": dormancy.demand_value.iloc[0],
        "uniform95_fill_rate": dormancy.revenue_fill_rate.iloc[0],
        "uniform95_avg_inventory": dormancy.avg_inventory_value.iloc[0],
        "textbook_vs_uniform_same_fill_year": comp.loc[("Textbook ABC/XYZ targets", "year"), "inventory_vs_uniform_same_fill"],
        "textbook_vs_uniform_same_fill_test": comp.loc[("Textbook ABC/XYZ targets", "test"), "inventory_vs_uniform_same_fill"],
        "optimized_vs_uniform_same_fill_fit": comp.loc[("Optimized per segment", "fit"), "inventory_vs_uniform_same_fill"],
        "optimized_vs_uniform_same_fill_test": comp.loc[("Optimized per segment", "test"), "inventory_vs_uniform_same_fill"],
        **{f"dead_{k}": v for k, v in opt["dead_stock"].items()},
        "dormancy8_inventory_change": best.inventory_change,
        "dormancy8_extra_lost_sales": best.extra_lost_sales,
        "dormancy8_fill_rate": best.revenue_fill_rate,
        "intermittent_or_lumpy_skus": im["lumpy_skus"],
        "intermittent_or_lumpy_dead_skus": im["lumpy_dead_skus"],
        **{f"{k}_vs_current_same_fill": im["comparison"].set_index("method").loc[m, "inventory_vs_current_same_fill"]
           for k, m in [("sba", "SBA on intermittent/lumpy SKUs"), ("tsb", "TSB on intermittent/lumpy SKUs"),
                        ("dormancy8", "13-week average (current) + 8-week dormancy rule"),
                        ("tsb_dormancy8", "TSB on intermittent/lumpy SKUs + 8-week dormancy rule")]},
        **{f"{k}_forecast_on_dead_skus": im["accuracy"].set_index("method").loc[m, "forecast_on_dead_skus"]
           for k, m in [("ma13", "13-week average (current)"), ("sba", "SBA on intermittent/lumpy SKUs"),
                        ("tsb", "TSB on intermittent/lumpy SKUs")]},
    }
    print("\nSummary\n", pd.Series(summary).to_string())

    t["segment_matrix"].to_csv(C.OUT_DIR / "segment_matrix.csv", index=False)
    seg[["stock_code", "description", "abc", "xyz", "segment", "revenue", "unit_price", "mean_weekly",
         "std_weekly", "cv", "zero_week_share"]].to_csv(C.OUT_DIR / "sku_segments.csv", index=False)
    opt["comparison"].to_csv(C.OUT_DIR / "policy_comparison.csv", index=False)
    opt["uniform_curve"].to_csv(C.OUT_DIR / "uniform_tradeoff.csv", index=False)
    opt["by_segment"].to_csv(C.OUT_DIR / "targets_by_segment.csv", index=False)
    dormancy.to_csv(C.OUT_DIR / "dormancy_rule.csv", index=False)
    im["classes"].to_csv(C.OUT_DIR / "demand_classes.csv", index=False)
    im["comparison"].to_csv(C.OUT_DIR / "intermittent_comparison.csv", index=False)
    im["curves"].to_csv(C.OUT_DIR / "intermittent_tradeoff.csv", index=False)
    im["accuracy"].to_csv(C.OUT_DIR / "intermittent_accuracy.csv", index=False)
    im["sensitivity"].to_csv(C.OUT_DIR / "intermittent_sensitivity.csv", index=False)
    pd.Series(summary).to_csv(C.OUT_DIR / "summary.csv", header=["value"])

    charts.make_all(t, opt, dormancy, im)
    print("\nOutputs written to outputs and charts")


if __name__ == "__main__":
    main()
