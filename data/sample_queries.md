# 金标准 SQL 示例（few-shot 素材）

> 本文件提供 10 条「标准问法 → 金标准 SQL」示例，覆盖 PRD 6.3 核心业务指标与 6 类问题类型（单表查询 / 聚合统计 / 多表 JOIN / 时间范围 / 排序 TOP / 比较），供 NL2SQL 链路作为 few-shot 示例与评测基准。
>
> - 数据库：`data/ecommerce.db`（SQLite）
> - 口径说明：GMV 取 `order_items.price` 之和（不含运费与退款）；订单量按去重 `order_id` 计数。

| # | 类别 | 指标 | 标准问法 |
|---|---|---|---|
| 1 | 单表查询 | 订单量 | 一共有多少个订单？ |
| 2 | 聚合统计 | GMV | 总 GMV 是多少？ |
| 3 | 聚合统计 | 客单价 | 平均客单价是多少？ |
| 4 | 多表 JOIN | 各州订单分布 | 各州的订单数量分布？ |
| 5 | 多表 JOIN + 排序 TOP | 品类销量 TOP10 | 哪个品类销量最高？按销量列出前 10 |
| 6 | 聚合统计 | 支付方式分布 | 各支付方式的使用情况？ |
| 7 | 时间范围 | 月度订单量趋势 | 过去每月订单量趋势如何？ |
| 8 | 聚合统计 | 订单评分分布 | 订单评价分数分布是怎样的？ |
| 9 | 时间范围 + 计算 | 平均配送时长 | 平均配送时长是多少天？ |
| 10 | 多表 JOIN + 比较 | 复购率 | 客户的复购率是多少？ |

---

## 1. 订单量（单表查询）

**问法：** 一共有多少个订单？

```sql
SELECT COUNT(DISTINCT order_id) AS order_count
FROM orders;
```

## 2. GMV（聚合统计）

**问法：** 总 GMV 是多少？

```sql
SELECT ROUND(SUM(price), 2) AS gmv
FROM order_items;
```

## 3. 客单价（聚合统计）

**问法：** 平均客单价是多少？

```sql
SELECT ROUND(SUM(price) * 1.0 / COUNT(DISTINCT order_id), 2) AS avg_order_value
FROM order_items;
```

## 4. 各州订单分布（多表 JOIN + 分组）

**问法：** 各州的订单数量分布？

```sql
SELECT c.customer_state,
       COUNT(DISTINCT o.order_id) AS order_count
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
GROUP BY c.customer_state
ORDER BY order_count DESC;
```

## 5. 品类销量 TOP10（多表 JOIN + 排序 TOP）

**问法：** 哪个品类销量最高？按销量列出前 10

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

## 6. 支付方式分布（聚合统计）

**问法：** 各支付方式的使用情况？

```sql
SELECT payment_type,
       COUNT(DISTINCT order_id) AS order_count,
       ROUND(SUM(payment_value), 2) AS total_value
FROM order_payments
GROUP BY payment_type
ORDER BY order_count DESC;
```

## 7. 月度订单量趋势（时间范围）

**问法：** 过去每月订单量趋势如何？

```sql
SELECT strftime('%Y-%m', order_purchase_timestamp) AS month,
       COUNT(DISTINCT order_id) AS order_count
FROM orders
WHERE order_status != 'canceled'
GROUP BY month
ORDER BY month;
```

## 8. 订单评分分布（聚合统计）

**问法：** 订单评价分数分布是怎样的？

```sql
SELECT review_score,
       COUNT(*) AS review_count
FROM order_reviews
GROUP BY review_score
ORDER BY review_score;
```

## 9. 平均配送时长（时间范围 + 计算）

**问法：** 平均配送时长是多少天？

```sql
SELECT ROUND(AVG(julianday(order_delivered_customer_date)
              - julianday(order_purchase_timestamp)), 1) AS avg_delivery_days
FROM orders
WHERE order_status = 'delivered'
  AND order_delivered_customer_date IS NOT NULL;
```

## 10. 复购率（多表 JOIN + 比较）

**问法：** 客户的复购率是多少？

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

---

## 说明

- **表名**：`orders`、`order_items`、`customers`、`sellers`、`order_payments`、`order_reviews`、`products`、`product_category_name_translation`（`geolocation` 为辅助表，暂不参与指标计算）。
- **关联键**：`orders.order_id = order_items.order_id`、`orders.customer_id = customers.customer_id`、`order_items.product_id = products.product_id`、`products.product_category_name = product_category_name_translation.product_category_name`。
- 以上 SQL 已在 `data/ecommerce.db` 中逐条验证可执行，可作为 D4 评测集金标准的编写模板。
