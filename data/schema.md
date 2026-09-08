# 数据库 Schema 说明（中文版）

> 本文档供 NL2SQL 链路使用：LLM 根据此处的字段说明、表间关联与指标口径生成 SQL。
> 数据库：`data/ecommerce.db`（SQLite）。所有字段以文本/原始值存储，日期为 `YYYY-MM-DD HH:MM:SS` 字符串，需用 SQLite 的 `strftime` / `julianday` 处理。

## 0. 使用约定（写进 Prompt 的关键规则）

1. **只允许 SELECT 查询**；禁止 INSERT / UPDATE / DELETE / DROP 等写操作。
2. 表名、列名必须严格使用下方给出的名称，**禁止臆造字段**。
3. 日期比较统一使用 ISO 字符串（如 `'2018-01-01'`）或 `strftime('%Y-%m', 字段)` 提取年月。
4. 统计类问题默认排除 `order_status = 'canceled'` 的订单（GMV、订单量、趋势等）。
5. 单表可完成的问题不要 JOIN；需要跨表时使用下方「表间关联」给出的键。

## 1. 表间关联（JOIN 键汇总）

| 左表 | 关联字段 | 右表 | 关联字段 | 语义 |
|---|---|---|---|---|
| orders | order_id | order_items | order_id | 订单 → 明细（1:N） |
| orders | order_id | order_payments | order_id | 订单 → 支付（1:N） |
| orders | order_id | order_reviews | order_id | 订单 → 评价（1:N，部分订单无评价） |
| orders | customer_id | customers | customer_id | 订单 → 客户（N:1） |
| order_items | product_id | products | product_id | 明细 → 商品（N:1） |
| order_items | seller_id | sellers | seller_id | 明细 → 卖家（N:1） |
| products | product_category_name | product_category_name_translation | product_category_name | 商品 → 品类英文名 |

## 2. 核心业务表（8 张，参与指标计算）

### 2.1 orders（订单主表）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| order_id | TEXT | 订单唯一 ID |
| customer_id | TEXT | 下单客户 ID（关联 customers） |
| order_status | TEXT | 订单状态：delivered（已送达）/ shipped（已发货）/ canceled（已取消）等 |
| order_purchase_timestamp | TEXT | 下单时间 |
| order_approved_at | TEXT | 支付审批通过时间 |
| order_delivered_carrier_date | TEXT | 交给物流商（发货）时间 |
| order_delivered_customer_date | TEXT | 送达客户时间 |
| order_estimated_delivery_date | TEXT | 预计送达时间 |

### 2.2 order_items（订单明细表）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| order_id | TEXT | 订单 ID（关联 orders） |
| order_item_id | INTEGER | 订单内商品行号（从 1 开始） |
| product_id | TEXT | 商品 ID（关联 products） |
| seller_id | TEXT | 卖家 ID（关联 sellers） |
| shipping_limit_date | TEXT | 卖家最晚发货截止时间 |
| price | REAL | 商品单价（不含运费）→ **GMV 口径来源** |
| freight_value | REAL | 运费 |

### 2.3 customers（客户表）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| customer_id | TEXT | 客户 ID（每个订单一条记录） |
| customer_unique_id | TEXT | 客户唯一标识（同一人多次购买时相同）→ **复购率口径来源** |
| customer_zip_code_prefix | TEXT | 邮编前缀（文本，勿转数字） |
| customer_city | TEXT | 城市 |
| customer_state | TEXT | 州（两字母缩写，如 SP / RJ / MG） |

### 2.4 sellers（卖家表）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| seller_id | TEXT | 卖家 ID |
| seller_zip_code_prefix | TEXT | 邮编前缀 |
| seller_city | TEXT | 城市 |
| seller_state | TEXT | 州 |

### 2.5 order_payments（支付表）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| order_id | TEXT | 订单 ID（关联 orders） |
| payment_sequential | INTEGER | 该订单的第几次支付（1 起） |
| payment_type | TEXT | 支付方式：credit_card（信用卡）/ boleto（银行票据）/ voucher（优惠券）/ debit_card（借记卡）/ not_defined |
| payment_installments | INTEGER | 分期数 |
| payment_value | REAL | 本次支付金额（同一订单多次支付时需聚合） |

### 2.6 order_reviews（评价表）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| review_id | TEXT | 评价 ID |
| order_id | TEXT | 订单 ID（关联 orders） |
| review_score | INTEGER | 评分 1~5 |
| review_comment_title | TEXT | 评论标题（可能为空） |
| review_comment_message | TEXT | 评论正文（可能为空） |
| review_creation_date | TEXT | 评论创建时间 |
| review_answer_timestamp | TEXT | 卖家回复时间 |

### 2.7 products（商品表）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| product_id | TEXT | 商品 ID |
| product_category_name | TEXT | 品类名（葡萄牙语，关联翻译表） |
| product_name_lenght | INTEGER | 商品名字符数（注意：Olist 原字段拼写即为 lenght，非笔误） |
| product_description_lenght | INTEGER | 商品描述字符数 |
| product_photos_qty | INTEGER | 商品图片数量 |
| product_weight_g | REAL | 商品重量（克） |
| product_length_cm | REAL | 长（厘米） |
| product_height_cm | REAL | 高（厘米） |
| product_width_cm | REAL | 宽（厘米） |

### 2.8 product_category_name_translation（品类翻译表）

| 字段 | 类型 | 中文含义 |
|---|---|---|
| product_category_name | TEXT | 品类名（葡萄牙语） |
| product_category_name_english | TEXT | 品类名（英语，推荐用于展示） |

## 3. 辅助表说明

- **geolocation（地理定位，可选扩展）**：`brazilian-ecommerce/olist_geolocation_dataset.csv`
  约 100 万行邮编级经纬度。默认数据库**不含**该表（体积约 130MB，超出 GitHub 单文件限制，
  不利于仓库托管/线上部署）。如需使用，用
  `python scripts/import_data.py --with-geolocation` 重建数据库即可。
  字段：geolocation_zip_code_prefix（邮编前缀）、geolocation_lat（纬度）、
  geolocation_lng（经度）、geolocation_city（城市）、geolocation_state（州）。
  **生成 SQL 时默认不要使用该表。**

## 4. 核心指标口径（重要，评测与生成 SQL 必须一致）

| 指标 | 口径定义 |
|---|---|
| GMV | Σ order_items.price（不含运费、不含 canceled） |
| 订单量 | COUNT(DISTINCT order_id)（默认不含 canceled） |
| 客单价 | GMV ÷ 订单量 |
| 复购率 | 购买次数 ≥ 2 的 customer_unique_id 数 ÷ 总 customer_unique_id 数 × 100% |
| 平均配送时长 | AVG(送达时间 − 下单时间)，仅 delivered 且已送达订单 |
| 销量（品类/商品） | Σ order_items.price 或 Σ 数量（order_items 无数量列，用 price 汇总） |
