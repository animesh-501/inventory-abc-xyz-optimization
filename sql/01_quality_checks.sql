-- Data quality checks on the raw transaction file.

-- 1. Coverage
SELECT COUNT(*) AS rows, COUNT(DISTINCT invoice) AS invoices, COUNT(DISTINCT stock_code) AS stock_codes,
       MIN(invoice_ts) AS first_ts, MAX(invoice_ts) AS last_ts
FROM raw_tx;

-- 2. The source was built from two yearly files that overlap on 1-9 Dec 2010.
--    Every row in that window appears twice; elsewhere exact duplicates are rare.
SELECT
    AVG(CASE WHEN n > 1 THEN 1 ELSE 0 END) FILTER (WHERE in_overlap)     AS dup_share_in_overlap,
    AVG(CASE WHEN n > 1 THEN 1 ELSE 0 END) FILTER (WHERE NOT in_overlap) AS dup_share_elsewhere
FROM (
    SELECT invoice_ts >= '2010-12-01' AND invoice_ts < '2010-12-10' AS in_overlap,
           COUNT(*) OVER (PARTITION BY invoice, stock_code, description, quantity, invoice_ts, price, customer_id, country) AS n
    FROM raw_tx
);

-- 3. Non-product codes (postage, fees, manual adjustments) and cancellations
SELECT
    SUM(CASE WHEN NOT REGEXP_MATCHES(stock_code, '^[0-9]{5}') THEN 1 ELSE 0 END) AS non_product_rows,
    SUM(CASE WHEN invoice LIKE 'C%' THEN 1 ELSE 0 END)                        AS cancellation_rows,
    SUM(CASE WHEN price <= 0 THEN 1 ELSE 0 END)                                AS zero_price_rows
FROM raw_tx;
