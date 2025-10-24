-- sql/basic_analytics.sql
-- Basic Analytics for Iteration 1 (PostgreSQL)
-- These queries assume three tables: customers, products, transactions.

-- 1) Top 10 customers by total spending
--    Total spending = sum(quantity * price) across all their transactions.
WITH line_revenue AS (
  SELECT
    t.id AS transaction_id,
    t.customer_id,
    (t.quantity * p.price) AS revenue
  FROM transactions t
  JOIN products p ON p.id = t.product_id
)
SELECT
  c.id AS customer_id,
  c.name AS customer_name,
  c.email,
  c.country,
  ROUND(SUM(lr.revenue)::numeric, 2) AS total_spent
FROM line_revenue lr
JOIN customers c ON c.id = lr.customer_id
GROUP BY c.id, c.name, c.email, c.country
ORDER BY total_spent DESC
LIMIT 10;

-- 2) Best-selling products by category (by units sold)
--    Uses a window function to pick the #1 per category.
WITH product_units AS (
  SELECT
    p.category,
    p.id AS product_id,
    p.name AS product_name,
    SUM(t.quantity) AS units_sold
  FROM transactions t
  JOIN products p ON p.id = t.product_id
  GROUP BY p.category, p.id, p.name
),
ranked AS (
  SELECT
    category,
    product_id,
    product_name,
    units_sold,
    RANK() OVER (PARTITION BY category ORDER BY units_sold DESC, product_name ASC) AS rnk
  FROM product_units
)
SELECT category, product_id, product_name, units_sold
FROM ranked
WHERE rnk = 1
ORDER BY category;

-- If you want “top N per category”, change WHERE rnk = 1 to WHERE rnk <= N.

-- 3) Monthly revenue trends
--    Buckets by month using date_trunc and sums revenue.
SELECT
  date_trunc('month', t.timestamp) AS month,
  ROUND(SUM(t.quantity * p.price)::numeric, 2) AS revenue
FROM transactions t
JOIN products p ON p.id = t.product_id
GROUP BY 1
ORDER BY 1;

-- 4) Average order value (AOV) by country
--    AOV = total revenue / number of orders.
--    Here we treat each row in `transactions` as a separate order id (t.id).
WITH orders AS (
  SELECT
    t.id AS order_id,
    c.country,
    SUM(t.quantity * p.price) AS order_revenue
  FROM transactions t
  JOIN products p ON p.id = t.product_id
  JOIN customers c ON c.id = t.customer_id
  GROUP BY t.id, c.country
)
SELECT
  country,
  ROUND(AVG(order_revenue)::numeric, 2) AS average_order_value,
  COUNT(*) AS num_orders,
  ROUND(SUM(order_revenue)::numeric, 2) AS total_revenue
FROM orders
GROUP BY country
ORDER BY average_order_value DESC;
