"""D2：生成并执行 notebooks/eda.ipynb（EDA 分析交付物）。

工作方式：
    1. 先连接 data/ecommerce.db 做一轮真实统计分析，收集关键数字；
    2. 用这些真实数字动态拼装「结论小结」markdown 单元格（保证不编造数据）；
    3. 用 nbformat 构建 notebook，nbclient 执行所有代码单元格；
    4. 输出到 notebooks/eda.ipynb（已含执行结果，可直接打开查看）。

用法：
    python scripts/build_eda.py
"""
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

# ---------- 项目路径 ----------
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "ecommerce.db"
NOTEBOOK_PATH = ROOT / "notebooks" / "eda.ipynb"
NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------- 第一步：真实数据分析（用于拼装结论） ----------
import sqlite3

import pandas as pd

conn = sqlite3.connect(DB_PATH)


def q(sql: str) -> pd.DataFrame:
    """执行 SQL 并返回 DataFrame（notebook 内共用的小工具函数）。"""
    return pd.read_sql_query(sql, conn)


# 整体指标
orders = q("SELECT COUNT(DISTINCT order_id) n FROM orders").iloc[0, 0]
gmv = q("SELECT ROUND(SUM(price),2) v FROM order_items").iloc[0, 0]
aov = q("SELECT ROUND(SUM(price)*1.0/COUNT(DISTINCT order_id),2) v FROM order_items").iloc[0, 0]
repurchase = q(
    """
    SELECT ROUND(SUM(CASE WHEN buy_times>=2 THEN 1 ELSE 0 END)*100.0/COUNT(*),2) v
    FROM (SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) buy_times
          FROM customers c JOIN orders o ON c.customer_id=o.customer_id
          WHERE o.order_status NOT IN ('canceled','unavailable')
          GROUP BY c.customer_unique_id)
    """
).iloc[0, 0]
avg_delivery = q(
    """
    SELECT ROUND(AVG(julianday(order_delivered_customer_date)-julianday(order_purchase_timestamp)),1) v
    FROM orders WHERE order_status='delivered' AND order_delivered_customer_date IS NOT NULL
    """
).iloc[0, 0]
n_states = q("SELECT COUNT(DISTINCT customer_state) n FROM customers").iloc[0, 0]
n_cats = q(
    "SELECT COUNT(DISTINCT product_category_name_english) n "
    "FROM product_category_name_translation"
).iloc[0, 0]
top_state = q(
    """SELECT c.customer_state s, COUNT(DISTINCT o.order_id) c
       FROM orders o JOIN customers c ON o.customer_id=c.customer_id
       GROUP BY s ORDER BY c DESC LIMIT 1"""
).iloc[0]
top_cat = q(
    """SELECT t.product_category_name_english s, SUM(oi.price) v
       FROM order_items oi JOIN products p ON oi.product_id=p.product_id
       JOIN product_category_name_translation t
            ON p.product_category_name=t.product_category_name
       GROUP BY s ORDER BY v DESC LIMIT 1"""
).iloc[0]
top_pay = q(
    """SELECT payment_type s, COUNT(DISTINCT order_id) c
       FROM order_payments GROUP BY s ORDER BY c DESC LIMIT 1"""
).iloc[0]
n_reviews = q("SELECT COUNT(*) n FROM order_reviews").iloc[0, 0]
avg_score = q("SELECT ROUND(AVG(review_score),2) v FROM order_reviews").iloc[0, 0]
date_range = q(
    "SELECT MIN(order_purchase_timestamp) lo, MAX(order_purchase_timestamp) hi FROM orders"
).iloc[0]
n_payments = q("SELECT COUNT(*) n FROM order_payments").iloc[0, 0]
n_items = q("SELECT COUNT(*) n FROM order_items").iloc[0, 0]
n_products = q("SELECT COUNT(*) n FROM products").iloc[0, 0]
n_customers = q("SELECT COUNT(*) n FROM customers").iloc[0, 0]
n_sellers = q("SELECT COUNT(*) n FROM sellers").iloc[0, 0]
n_geoloc = q("SELECT COUNT(*) n FROM geolocation").iloc[0, 0]

# 状态分布
status_df = q(
    "SELECT order_status, COUNT(*) n FROM orders GROUP BY order_status ORDER BY n DESC"
)
top_status = status_df.iloc[0]

conn.close()

# ---------- 第二步：用真实数字拼装结论小结 ----------
summary = f"""## 8. 核心结论（由脚本真实计算生成）

**总体规模**
- 订单数 **{orders:,}**，订单明细 {n_items:,} 行；覆盖 **{n_states} 个州**、{n_cats} 个品类；
- GMV **{gmv:,.2f}**（= Σ order_items.price），客单价 **{aov}**；
- 客户 {n_customers:,} 人、卖家 {n_sellers:,} 家、商品 {n_products:,} 件、评价 {n_reviews:,} 条、支付记录 {n_payments:,} 条（另有地理定位 {n_geoloc:,} 条）；
- 数据时间范围：{date_range['lo']} ~ {date_range['hi']}。

**业务发现**
- 订单状态以 **{top_status['order_status']}** 为主（{top_status['n']:,} 单，占比 {top_status['n']/orders*100:.1f}%）；
- 订单集中州：**{top_state['s']}**（{top_state['c']:,} 单）；
- 销量最高品类：**{top_cat['s']}**（GMV {top_cat['v']:,.2f}）；
- 首选支付方式：**{top_pay['s']}**（{top_pay['c']:,} 单）；
- 平均配送时长 **{avg_delivery} 天**；复购率 **{repurchase}%**；
- 平均评价分 **{avg_score}**（满分 5）。

> 以上数字为 D2 快照，供 NL2SQL 评测与口径校准使用。
"""

# ---------- 第三步：构建 notebook ----------
# 每个单元格用字典描述：type=markdown/code，source=内容
cells = []
c = cells.append


def md(src: str):
    c(nbf.v4.new_markdown_cell(src))


def code(src: str):
    c(nbf.v4.new_code_cell(src))


md("# 智能数据分析助手 · D2 数据探索（EDA）\n\n"
   "数据源：巴西电商 Olist（8 张业务表 + geolocation 辅助表），数据库：`data/ecommerce.db`。\n\n"
   "目的：① 验证数据质量与口径；② 为 `data/schema.md`（字段中文说明）与 `data/metrics.md`（指标清单）提供依据。")

code(
    "import sqlite3\n"
    "from pathlib import Path\n\n"
    "import pandas as pd\n"
    "import plotly.express as px\n\n"
    "# 定位项目根目录（本 notebook 位于 notebooks/ 下，兼容从根目录或 notebooks/ 启动）\n"
    "PROJECT_ROOT = Path.cwd()\n"
    "if not (PROJECT_ROOT / 'data' / 'ecommerce.db').exists():\n"
    "    PROJECT_ROOT = PROJECT_ROOT.parent\n"
    "DB_PATH = PROJECT_ROOT / 'data' / 'ecommerce.db'\n\n"
    "conn = sqlite3.connect(DB_PATH)\n\n"
    "def q(sql: str) -> pd.DataFrame:\n"
    "    '''执行 SQL 返回 DataFrame'''\n"
    "    return pd.read_sql_query(sql, conn)\n\n"
    "print('数据库:', DB_PATH)"
)

md("## 1. 数据概览：9 张表")

code(
    "tables = q(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\")\n"
    "rows = []\n"
    "for t in tables['name']:\n"
    "    n = q(f'SELECT COUNT(*) n FROM \"{t}\"').iloc[0, 0]\n"
    "    cols = q(f'SELECT * FROM \"{t}\" LIMIT 0').columns.tolist()\n"
    "    rows.append({'表名': t, '行数': int(n), '列数': len(cols), '字段': ', '.join(cols)})\n"
    "overview = pd.DataFrame(rows)\n"
    "overview"
)

md("## 2. 订单状态分布（数据质量）")

code(
    "status_df = q(\"SELECT order_status, COUNT(*) n FROM orders \"\n"
    "              \"GROUP BY order_status ORDER BY n DESC\")\n"
    "status_df['占比%'] = (status_df['n'] / status_df['n'].sum() * 100).round(2)\n"
    "px.bar(status_df, x='order_status', y='n', text='n',\n"
    "       title='订单状态分布', labels={'order_status': '状态', 'n': '订单数'})"
)

md("## 3. 整体业务指标（GMV / 客单价 / 复购率 / 配送）")

code(
    "# 在 notebook 内重新计算整体指标（供后续单元使用，与构建脚本同一口径）\n"
    "orders = int(q('SELECT COUNT(DISTINCT order_id) n FROM orders').iloc[0, 0])\n"
    "gmv = float(q('SELECT ROUND(SUM(price),2) v FROM order_items').iloc[0, 0])\n"
    "aov = float(q('SELECT ROUND(SUM(price)*1.0/COUNT(DISTINCT order_id),2) v '\n"
    "              'FROM order_items').iloc[0, 0])\n"
    "repurchase = float(q(\"\"\"SELECT ROUND(\n"
    "                       SUM(CASE WHEN buy_times>=2 THEN 1 ELSE 0 END)*100.0/COUNT(*),2) v\n"
    "                   FROM (SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) buy_times\n"
    "                         FROM customers c JOIN orders o ON c.customer_id=o.customer_id\n"
    "                         WHERE o.order_status NOT IN ('canceled','unavailable')\n"
    "                         GROUP BY c.customer_unique_id)\"\"\").iloc[0, 0])\n"
    "avg_delivery = float(q(\"\"\"SELECT ROUND(AVG(julianday(order_delivered_customer_date)\n"
    "                          - julianday(order_purchase_timestamp)),1) v\n"
    "                      FROM orders\n"
    "                      WHERE order_status='delivered' AND order_delivered_customer_date IS NOT NULL\"\"\").iloc[0, 0])\n"
    "date_range = q('SELECT MIN(order_purchase_timestamp) lo, '\n"
    "               'MAX(order_purchase_timestamp) hi FROM orders').iloc[0]\n"
    "print(f'总订单数: {orders:,}')\n"
    "print(f'GMV: {gmv:,.2f}')\n"
    "print(f'客单价: {aov}')\n"
    "print(f'复购率: {repurchase}%')\n"
    "print(f'平均配送时长: {avg_delivery} 天')\n"
    "print(f'数据范围: {date_range[\"lo\"]} ~ {date_range[\"hi\"]}')"
)

md("## 4. 各州订单分布（地理）")

code(
    "state_df = q(\"\"\"SELECT c.customer_state s, COUNT(DISTINCT o.order_id) n\n"
    "               FROM orders o JOIN customers c ON o.customer_id=c.customer_id\n"
    "               GROUP BY s ORDER BY n DESC\"\"\")\n"
    "px.bar(state_df.head(10), x='s', y='n', text='n',\n"
    "       title='订单量 TOP10 州', labels={'s': '州', 'n': '订单数'})"
)

md("## 5. 品类销量 TOP10")

code(
    "cat_df = q(\"\"\"SELECT t.product_category_name_english cat, SUM(oi.price) v\n"
    "             FROM order_items oi\n"
    "             JOIN products p ON oi.product_id=p.product_id\n"
    "             JOIN product_category_name_translation t\n"
    "                  ON p.product_category_name=t.product_category_name\n"
    "             GROUP BY cat ORDER BY v DESC LIMIT 10\"\"\")\n"
    "px.bar(cat_df, x='cat', y='v', text='v',\n"
    "       title='品类销量 TOP10', labels={'cat': '品类', 'v': '销量(GMV)'})"
)

md("## 6. 支付方式分布")

code(
    "pay_df = q(\"\"\"SELECT payment_type s, COUNT(DISTINCT order_id) n,\n"
    "                 ROUND(SUM(payment_value),2) v\n"
    "             FROM order_payments GROUP BY s ORDER BY n DESC\"\"\")\n"
    "px.pie(pay_df, names='s', values='n', title='支付方式订单占比',\n"
    "       labels={'s': '支付方式', 'n': '订单数'})"
)

md("## 7. 月度订单量趋势（时间序列）")

code(
    "month_df = q(\"\"\"SELECT strftime('%Y-%m', order_purchase_timestamp) m,\n"
    "                  COUNT(DISTINCT order_id) n\n"
    "              FROM orders WHERE order_status != 'canceled'\n"
    "              GROUP BY m ORDER BY m\"\"\")\n"
    "px.line(month_df, x='m', y='n', markers=True,\n"
    "       title='月度订单量趋势', labels={'m': '月份', 'n': '订单数'})"
)

md("## 8. 评分与配送时长分布")

code(
    "score_df = q(\"SELECT review_score, COUNT(*) n FROM order_reviews \"\n"
    "             \"GROUP BY review_score ORDER BY review_score\")\n"
    "px.bar(score_df, x='review_score', y='n', text='n',\n"
    "       title='订单评分分布', labels={'review_score': '评分', 'n': '数量'})"
)

code(
    "deliv_df = q(\"\"\"SELECT CAST(julianday(order_delivered_customer_date)\n"
    "                    - julianday(order_purchase_timestamp) AS INT) days\n"
    "              FROM orders\n"
    "              WHERE order_status='delivered' AND order_delivered_customer_date IS NOT NULL\"\"\")\n"
    "px.histogram(deliv_df, x='days', nbins=30, title='配送时长分布（天）',\n"
    "            labels={'days': '配送天数'})"
)

md("## 9. 数据质量：空值检查")

code(
    "quality = []\n"
    "for t in tables['name']:\n"
    "    for col in q(f'SELECT * FROM \"{t}\" LIMIT 0').columns:\n"
    "        nulls = q(f'SELECT COUNT(*) FROM \"{t}\" WHERE \"{col}\" IS NULL OR \"{col}\" = \\'\\'').iloc[0, 0]\n"
    "        if nulls > 0:\n"
    "            quality.append({'表': t, '字段': col, '空值数': int(nulls)})\n"
    "quality_df = pd.DataFrame(quality).sort_values('空值数', ascending=False)\n"
    "print(f'发现 {len(quality_df)} 个含空值的字段：')\n"
    "quality_df.head(20)"
)

md(summary)

nb = nbf.v4.new_notebook()
nb["cells"] = cells
nb["metadata"]["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nb["metadata"]["language_info"] = {"name": "python"}

# ---------- 第四步：执行并保存 ----------
client = NotebookClient(nb, timeout=600, kernel_name="python3")
client.execute(cwd=str(ROOT))
nbf.write(nb, NOTEBOOK_PATH)
print(f"已生成并执行: {NOTEBOOK_PATH}")
print("关键数字：订单", orders, "| GMV", gmv, "| 客单价", aov, "| 复购率", repurchase, "% | 配送", avg_delivery, "天")
