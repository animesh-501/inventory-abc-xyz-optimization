-- Weekly net demand per SKU on a complete SKU x week grid (weeks with no sales = 0).

CREATE OR REPLACE TABLE weekly_demand AS
WITH weeks AS (
    SELECT CAST(range AS DATE) AS week_start
    FROM range(DATE '{YEAR1_START}', DATE '{YEAR2_END}', INTERVAL 7 DAY)
),
skus AS (
    SELECT DISTINCT stock_code FROM sales
    WHERE invoice_ts >= DATE '{YEAR1_START}' AND invoice_ts < DATE '{YEAR2_END}'
),
net AS (
    SELECT stock_code, week_start, SUM(quantity) AS net_units
    FROM sales
    GROUP BY 1, 2
)
SELECT
    s.stock_code,
    w.week_start,
    w.week_start >= DATE '{YEAR2_START}'      AS is_year2,
    GREATEST(COALESCE(n.net_units, 0), 0)     AS demand
FROM skus s
CROSS JOIN weeks w
LEFT JOIN net n USING (stock_code, week_start)
ORDER BY 1, 2;

-- Unit value per SKU: median selling price in year 1 (prices vary with order size)
CREATE OR REPLACE TABLE sku_price AS
SELECT stock_code, MEDIAN(price) AS unit_price, ANY_VALUE(description) AS description
FROM sales
WHERE NOT is_cancellation AND invoice_ts >= DATE '{YEAR1_START}' AND invoice_ts < DATE '{YEAR2_START}'
GROUP BY stock_code;
