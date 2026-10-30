-- Clean product movements.
--  * Removes the second copy of the 1-9 Dec 2010 overlap (keeps half of each identical group there).
--  * Keeps product codes only (5-digit codes), drops postage, fees and adjustments.
--  * Keeps cancellations as negative quantities, so an order and its cancellation net out
--    (e.g. one 80,995-unit order was cancelled the same day).

CREATE OR REPLACE TABLE sales AS
WITH tagged AS (
    SELECT *,
           invoice_ts >= '2010-12-01' AND invoice_ts < '2010-12-10' AS in_overlap,
           ROW_NUMBER() OVER w AS copy_no,
           COUNT(*) OVER w     AS copies
    FROM raw_tx
    WINDOW w AS (PARTITION BY invoice, stock_code, description, quantity, invoice_ts, price, customer_id, country)
)
SELECT
    invoice,
    stock_code,
    description,
    quantity,
    price,
    invoice_ts,
    CAST(DATE_TRUNC('week', invoice_ts) AS DATE) AS week_start,
    invoice LIKE 'C%'                            AS is_cancellation
FROM tagged
WHERE (NOT in_overlap OR copy_no <= copies / 2)
  AND REGEXP_MATCHES(stock_code, '^[0-9]{5}')
  AND price > 0;
