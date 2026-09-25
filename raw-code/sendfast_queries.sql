-- SendFast Q1 2024 analysis: SQL queries
-- Copied from notebooks/SendFast_Analysis.ipynb, where they run against an in-memory SQLite database
-- built from data/transactions.csv (table: transactions) and data/users.csv (table: users).
-- All data is synthetic; SendFast is a fictional company.

-- 1. Base health: monthly active senders, transfers and value (Jan-Mar 2024)
SELECT STRFTIME('%Y-%m', date)            AS month,
       COUNT(DISTINCT user_id)            AS active_senders,
       COUNT(id)                          AS transfers,
       SUM(base_amount_cad)               AS value_cad,
       ROUND(AVG(base_amount_cad), 0)     AS avg_transfer_cad
FROM transactions
WHERE date >= '2024-01-01' AND user_id IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- 2. Month-to-month retention
WITH act AS (SELECT DISTINCT user_id, STRFTIME('%Y-%m', date) m FROM transactions
             WHERE user_id IS NOT NULL AND date >= '2024-01-01')
SELECT a.m AS from_month, COUNT(a.user_id) AS senders,
       COUNT(b.user_id) AS retained,
       ROUND(COUNT(b.user_id) * 100.0 / COUNT(a.user_id), 1) AS retention_pct
FROM act a
LEFT JOIN act b ON a.user_id = b.user_id AND b.m = STRFTIME('%Y-%m', DATE(a.m || '-01', '+1 month'))
WHERE a.m < '2024-03'
GROUP BY 1;

-- 3. Week-to-week retention (weeks start Monday)
WITH act AS (SELECT DISTINCT user_id, DATE(date, 'weekday 0', '-6 days') w FROM transactions
             WHERE user_id IS NOT NULL AND date >= '2024-01-01')
SELECT a.w AS week, COUNT(a.user_id) AS senders, COUNT(b.user_id) AS retained,
       ROUND(COUNT(b.user_id) * 100.0 / COUNT(a.user_id), 1) AS retention_pct
FROM act a LEFT JOIN act b ON a.user_id = b.user_id AND b.w = DATE(a.w, '+7 days')
WHERE a.w < (SELECT MAX(w) FROM act)
GROUP BY 1 ORDER BY 1;

-- 4. Average transfer size and NGN/CAD rate by month, main corridors
SELECT STRFTIME('%Y-%m', date) AS month, corridor,
       ROUND(AVG(base_amount_cad), 0) AS avg_transfer_cad,
       COUNT(DISTINCT user_id)        AS senders,
       COUNT(id)                      AS transfers,
       ROUND(AVG(CASE WHEN corridor = 'CAD→NGN' THEN rate END), 0) AS avg_ngn_per_cad
FROM transactions
WHERE date >= '2024-01-01' AND corridor IN ('CAD→NGN', 'NGN→CAD')
GROUP BY 1, 2 ORDER BY 2, 1;

-- 5. Corridor share of transfers and value (remittances only)
SELECT corridor,
       COUNT(id)                                   AS transfers,
       COUNT(DISTINCT user_id)                     AS senders,
       SUM(base_amount_cad)                        AS value_cad,
       ROUND(AVG(base_amount_cad), 0)              AS avg_transfer_cad
FROM transactions WHERE is_remittance = 1
GROUP BY 1 ORDER BY value_cad DESC;

-- 6. Transfer purpose by corridor
SELECT corridor, narration, COUNT(*) AS n FROM transactions
WHERE corridor IN ('CAD→NGN', 'NGN→CAD') GROUP BY 1, 2;

-- 7. Customer value concentration (total CAD value per sender)
SELECT user_id, SUM(base_amount_cad) v FROM transactions WHERE user_id IS NOT NULL GROUP BY 1 ORDER BY v DESC;

-- 8. Signup funnel, Dec-Feb signup cohort
WITH s AS (
  SELECT u.*, (SELECT 1 FROM transactions t WHERE t.user_id = u.user_id LIMIT 1) IS NOT NULL AS transacted
  FROM users u WHERE signup_date < '2024-03-01')
SELECT 1 stage, 'Signed up' AS step, COUNT(*) users FROM s
UNION ALL SELECT 2, 'Completed profile', SUM(completed_profile) FROM s
UNION ALL SELECT 3, 'Started KYC', SUM(kyc_status <> 'NOT_STARTED') FROM s
UNION ALL SELECT 4, 'KYC passed', SUM(kyc_status = 'PASSED') FROM s
UNION ALL SELECT 5, 'Transacted', SUM(transacted) FROM s
ORDER BY stage;

-- 9. KYC progress and conversion by country, Dec-Feb cohort
WITH s AS (
  SELECT u.*, EXISTS (SELECT 1 FROM transactions t WHERE t.user_id = u.user_id) AS transacted
  FROM users u WHERE signup_date < '2024-03-01' AND country IN ('Canada', 'Nigeria'))
SELECT country, COUNT(*) AS signups,
       ROUND(AVG(kyc_status = 'NOT_STARTED') * 100, 1) AS never_started_kyc_pct,
       ROUND(AVG(kyc_status = 'PASSED') * 100, 1)      AS kyc_passed_pct,
       ROUND(AVG(transacted) * 100, 1)                 AS conversion_pct
FROM s GROUP BY 1;

-- 10. Referral vs non-referral within country, Dec-Feb cohort
WITH s AS (
  SELECT u.*, EXISTS (SELECT 1 FROM transactions t WHERE t.user_id = u.user_id) AS transacted
  FROM users u WHERE signup_date < '2024-03-01' AND country IN ('Canada', 'Nigeria'))
SELECT country,
       CASE WHEN referred_by IS NOT NULL THEN 'Referred' ELSE 'Not referred' END AS grp,
       COUNT(*)                                        AS signups,
       ROUND(AVG(kyc_status <> 'NOT_STARTED') * 100, 1) AS started_kyc_pct,
       ROUND(AVG(kyc_status = 'PASSED') * 100, 1)       AS kyc_passed_pct,
       ROUND(AVG(transacted) * 100, 1)                 AS conversion_pct
FROM s GROUP BY 1, 2 ORDER BY 1, 2;

-- 11. Referral share of signups by month
SELECT STRFTIME('%Y-%m', signup_date) AS signup_month, COUNT(*) AS signups,
       ROUND(AVG(referred_by IS NOT NULL) * 100, 1) AS referred_share_pct
FROM users GROUP BY 1 ORDER BY 1;
