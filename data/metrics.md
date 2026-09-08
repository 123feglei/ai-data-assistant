# 核心业务指标清单

> D2 交付物：覆盖 PRD 6.3 的全部 12 个核心业务指标，每个指标给出「指标口径 / 标准问法 / 金标准 SQL」。
> 该清单是 D4 评测集选题与 LLM few-shot 示例的来源。全部 SQL 已在 `data/ecommerce.db` 验证可执行。

| # | 指标 | 问题类型 | 状态 |
|---|---|---|---|
| 1 | GMV | 聚合统计 | ✅ |
| 2 | 订单量 | 单表查询 | ✅ |
| 3 | 客单价 | 聚合统计 | ✅ |
| 4 | 复购率 | 多表 JOIN + 子查询 | ✅ |
| 5 | 各州订单分布 | 多表 JOIN + 分组 | ✅ |
| 6 | 品类销量 TOP10 | 多表 JOIN + 排序 TOP | ✅ |
| 7 | 支付方式分布 | 聚合统计 | ✅ |
| 8 | 月度订单量趋势 | 时间范围 | ✅ |
| 9 | 订单评分分布 | 聚合统计 | ✅ |
| 10 | 平均配送时长 | 时间范围 + 计算 | ✅ |
| 11 | 高价值客户 TOP10 | 多表 JOIN + 排序 TOP | ✅ |
| 12 | 季度 GMV 对比 | 时间范围 + 比较 | ✅ |

---

## 1. GMV

- **口径**：Σ order_items.price（不含运费、不含 canceled）
- **问法**：总 GMV 是多少？

```sql
SELECT ROUND(SUM(price), 2) AS gmv
FROM order_items;
```

## 2. 订单量

- **口径**：COUNT(DISTINCT order_id)，不含 canceled
- **问法**：一共有多少个订单？

```sql
SELECT COUNT(DISTINCT o.order_id) AS order_count
FROM orders o
WHERE o.order_status != 'canceled';
```

## 3. 客单价

- **口径**：GMV ÷ 订单量
- **问法**：平均客单价是多少？

```sql
SELECT ROUND(SUM(oi.price) * 1.0 / COUNT(DISTINCT oi.order_id), 2) AS avg_order_value
FROM order_items oi;
```

## 4. 复购率

- **口径**：购买 ≥ 2 次的客户占比（按 customer_unique_id）
- **问法**：客户的复购率是多少？

```sql
SELECT ROUND(
         SUM(CASE WHEN buy_times >= 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
         2
       ) AS repurchase_rate_pct
FROM (
    SELECT c.customer_unique_id,
           COUNT(DISTINCT o.order_id) AS buy_times
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY c.customer_unique_id
);
```

## 5. 各州订单分布

- **口径**：按 customer_state 分组统计订单数
- **问法**：各州的订单数量分布？

```sql
SELECT c.customer_state,
       COUNT(DISTINCT o.order_id) AS order_count
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_status != 'canceled'
GROUP BY c.customer_state
ORDER BY order_count DESC;
```

## 6. 品类销量 TOP10

- **口径**：按英文品类名分组 Σ price
- **问法**：哪个品类销量最高？列出前 10

```sql
SELECT t.product_category_name_english AS category,
       SUM(oi.price) AS sales
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
JOIN product_category_name_translation t
     ON p.product_category_name = t.product_category_name
GROUP BY t.product_category_name_english
ORDER BY sales DESC
LIMIT 10;
```

## 7. 支付方式分布

- **口径**：按 payment_type 统计订单数与金额
- **问法**：各支付方式的使用情况？

```sql
SELECT payment_type,
       COUNT(DISTINCT order_id) AS order_count,
       ROUND(SUM(payment_value), 2) AS total_value
FROM order_payments
GROUP BY payment_type
ORDER BY order_count DESC;
```

## 8. 月度订单量趋势

- **口径**：按 strftime('%Y-%m') 分组，不含 canceled
- **问法**：过去每月订单量趋势如何？

```sql
SELECT strftime('%Y-%m', order_purchase_timestamp) AS month,
       COUNT(DISTINCT order_id) AS order_count
FROM orders
WHERE order_status != 'canceled'
GROUP BY month
ORDER BY month;
```

## 9. 订单评分分布

- **口径**：按 review_score 分组计数
- **问法**：订单评价分数分布是怎样的？

```sql
SELECT review_score,
       COUNT(*) AS review_count
FROM order_reviews
GROUP BY review_score
ORDER BY review_score;
```

## 10. 平均配送时长

- **口径**：AVG(送达时间 − 下单时间)，仅 delivered 且已送达
- **问法**：平均配送时长是多少天？

```sql
SELECT ROUND(AVG(julianday(order_delivered_customer_date)
              - julianday(order_purchase_timestamp)), 1) AS avg_delivery_days
FROM orders
WHERE order_status = 'delivered'
  AND order_delivered_customer_date IS NOT NULL;
```

## 11. 高价值客户 TOP10

- **口径**：按 customer_unique_id 汇总消费金额（Σ price）排序
- **问法**：消费金额最高的 TOP10 客户是谁？

```sql
SELECT c.customer_unique_id,
       ROUND(SUM(oi.price), 2) AS total_spent,
       COUNT(DISTINCT o.order_id) AS order_count
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status != 'canceled'
GROUP BY c.customer_unique_id
ORDER BY total_spent DESC
LIMIT 10;
```

## 12. 季度 GMV 对比

- **口径**：按 strftime('%Y-Qx') 季度分组 Σ price
- **问法**：各季度 GMV 对比？

```sql
SELECT strftime('%Y', o.order_purchase_timestamp) || '-Q' ||
       CAST((CAST(strftime('%m', o.order_purchase_timestamp) AS INT) + 2) / 3 AS INT) AS quarter,
       ROUND(SUM(oi.price), 2) AS gmv
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status != 'canceled'
GROUP BY quarter
ORDER BY quarter;
```

---

## 备注

- 指标 1~10 与 `data/sample_queries.md` 金标准一致；11、12 为本清单新增（覆盖 PRD 6.3 全量 12 个指标）。
- D4 评测集将基于本清单扩展为 30~50 题。
