-- ABC / XYZ segmentation on year 1 only.
--   ABC: rank SKUs by year-1 revenue. A = first 80% of cumulative revenue, B = next 15%, C = last 5%.
--   XYZ: coefficient of variation (std / mean) of weekly demand. X <= 0.5, Y <= 1.0, Z > 1.0.

CREATE OR REPLACE TABLE segments AS
WITH y1 AS (
    SELECT d.stock_code,
           SUM(d.demand)                     AS units,
           AVG(d.demand)                     AS mean_weekly,
           STDDEV_SAMP(d.demand)             AS std_weekly,
           AVG((d.demand = 0)::INT)          AS zero_week_share
    FROM weekly_demand d
    WHERE NOT d.is_year2
    GROUP BY d.stock_code
    HAVING SUM(d.demand) > 0
),
valued AS (
    SELECT y1.*, p.unit_price, p.description, y1.units * p.unit_price AS revenue
    FROM y1 JOIN sku_price p USING (stock_code)
),
ranked AS (
    SELECT *,
           SUM(revenue) OVER (ORDER BY revenue DESC, stock_code ROWS UNBOUNDED PRECEDING)
             / SUM(revenue) OVER () AS cum_share,
           std_weekly / mean_weekly AS cv
    FROM valued
)
SELECT
    *,
    CASE WHEN cum_share <= {ABC_A} THEN 'A' WHEN cum_share <= {ABC_B} THEN 'B' ELSE 'C' END AS abc,
    CASE WHEN cv <= {XYZ_X} THEN 'X' WHEN cv <= {XYZ_Y} THEN 'Y' ELSE 'Z' END             AS xyz
FROM ranked;

ALTER TABLE segments ADD COLUMN segment VARCHAR;
UPDATE segments SET segment = abc || xyz;

-- Segment matrix
CREATE OR REPLACE TABLE segment_matrix AS
SELECT abc, xyz, segment,
       COUNT(*)                                    AS skus,
       COUNT(*) / SUM(COUNT(*)) OVER ()            AS sku_share,
       SUM(revenue)                                AS revenue,
       SUM(revenue) / SUM(SUM(revenue)) OVER ()    AS revenue_share,
       MEDIAN(cv)                                  AS median_cv,
       AVG(zero_week_share)                        AS avg_zero_week_share
FROM segments
GROUP BY 1, 2, 3
ORDER BY 1, 2;
