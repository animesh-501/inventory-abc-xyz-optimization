"""Load raw transactions into DuckDB and run the SQL layer."""
import duckdb

import config as C


def _statements(path):
    lines = [ln for ln in path.read_text().splitlines() if not ln.strip().startswith("--")]
    sql = "\n".join(lines)
    subs = {"YEAR1_START": C.YEAR1_START, "YEAR2_START": C.YEAR2_START, "YEAR2_END": C.YEAR2_END,
            "ABC_A": C.ABC_CUTS[0], "ABC_B": C.ABC_CUTS[1], "XYZ_X": C.XYZ_CUTS[0], "XYZ_Y": C.XYZ_CUTS[1]}
    for k, v in subs.items():
        sql = sql.replace("{" + k + "}", str(v))
    return [s.strip() for s in sql.split(";") if s.strip()]


def build():
    con = duckdb.connect()
    con.execute(f"""
        CREATE TABLE raw_tx AS
        SELECT "Invoice" AS invoice, "StockCode" AS stock_code, "Description" AS description,
               "Quantity" AS quantity, "InvoiceDate" AS invoice_ts, "Price" AS price,
               "Customer ID" AS customer_id, "Country" AS country
        FROM read_csv('{C.RAW_FILE.as_posix()}', header=true,
                      types={{'Invoice': 'VARCHAR', 'StockCode': 'VARCHAR', 'Customer ID': 'VARCHAR'}})
    """)
    print("Data quality checks")
    for stmt in _statements(C.SQL_DIR / "01_quality_checks.sql"):
        print("  ", con.execute(stmt).df().to_dict("records")[0])
    for name in ["02_clean_sales.sql", "03_weekly_demand.sql", "04_segmentation.sql"]:
        for stmt in _statements(C.SQL_DIR / name):
            con.execute(stmt)
    out = {t: con.execute(f"SELECT * FROM {t}").df() for t in ["weekly_demand", "segments", "segment_matrix"]}
    print("   rows after cleaning:", con.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
          "| SKUs segmented:", len(out["segments"]))
    return out
