"""NL2SQL 引擎（D3 核心交付物）。

端到端流程（与 PRD 7.1 架构一致）：
    用户问题
      │ ① 组装 Prompt（schema 摘要 + few-shot 示例 + 用户问题）
      ▼
    LLM 生成 SQL（DeepSeek API / Ollama，temperature=0）
      │ ② 提取并校验（只允许 SELECT，禁止写操作）
      ▼
    SQLite 只读执行（自动附加 LIMIT 200 + 15 秒超时保护）
      │ ③ 失败 → 携带数据库错误信息重试 1 次
      ▼
    返回 {sql, df, 耗时, 行数}

本模块只负责"问题 → 可执行 SQL → 结果表"，图表与结论生成（present.py）在 D5 实现。
"""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

import pandas as pd

from nl2sql.config import DB_PATH, LLM_TIMEOUT, get_llm_client

# 项目根目录（本文件位于 nl2sql/ 下，向上取一级）
ROOT = Path(__file__).resolve().parent.parent

# 生成 SQL 的最大尝试次数（首次失败后带错误信息再问 1 次，PRD FR-05）
MAX_ATTEMPTS = 2
# 查询结果默认最大行数（PRD FR-01：自动附加 LIMIT）
DEFAULT_LIMIT = 200
# SQL 执行超时（秒，PRD FR-02）
EXEC_TIMEOUT = 15


# ============ 1. Prompt 素材 ============

def build_schema_summary(schema_path: Path | None = None) -> str:
    """从 data/schema.md 解析出精简 schema 摘要，供 Prompt 使用。

    解析规则（schema.md 为固定表格格式，见 D2 交付物）：
        - "### 2.x 表名（中文名）" 标题下的字段表 → 表字段清单；
        - "### 1. 表间关联" 的关联表 → JOIN 键；
        - "## 4. 核心指标口径" 表 → 指标口径定义。
    优点：schema.md 一旦更新，摘要自动同步，避免两处维护漂移。
    """
    if schema_path is None:
        schema_path = ROOT / "data" / "schema.md"
    lines = schema_path.read_text(encoding="utf-8").splitlines()

    tables: dict[str, list[tuple[str, str, str]]] = {}
    links: list[str] = []
    metrics: list[str] = []
    section: str | None = None  # 当前所在区块: "table" / "links" / "metrics"
    current_table: str | None = None

    for raw in lines:
        s = raw.strip()
        # ① 区块标题：关联键表（## 1.）
        if s.startswith("## 1."):
            section = "links"
            continue
        # ② 区块标题：业务表（### 2.x / 3.x），如 "### 2.1 orders（订单主表）"
        m = re.match(r"^### [23]\.\d+\s+([a-z_]+)（", s)
        if m:
            section = "table"
            current_table = m.group(1)
            tables.setdefault(current_table, [])
            continue
        # ③ 区块标题：指标口径（## 4.）
        if s.startswith("## 4."):
            section = "metrics"
            continue
        # ④ 表格数据行：| a | b | c | ... |
        m = re.match(r"^\|(.+)\|$", s)
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        # 跳过表头行与分隔行（分隔行含 ---，表头首格为"字段"/"左表"）
        if any("---" in c for c in cells) or cells[0] in ("字段", "左表"):
            continue
        if section == "table" and len(cells) >= 3 and cells[0]:
            tables[current_table].append((cells[0], cells[1], cells[2]))
        elif section == "links" and len(cells) >= 5 and cells[0]:
            links.append(f"{cells[0]}.{cells[1]} = {cells[2]}.{cells[3]}")
        elif section == "metrics" and len(cells) >= 2 and cells[0]:
            metrics.append(f"- {cells[0]}：{cells[1]}")

    # 拼装摘要文本
    parts = ["【数据表】"]
    for name, cols in tables.items():
        parts.append(
            f"表 {name}: " + ", ".join(f"{c}({t} {d})" for c, t, d in cols)
        )
    parts.append("\n【表间关联】\n" + "\n".join(links))
    if metrics:
        parts.append("\n【指标口径】\n" + "\n".join(metrics))
    return "\n".join(parts)


# few-shot 示例：与 data/eval_set.json 金标准口径严格一致（优化于 D4 首轮评测后）
# 口径约定：总数不过滤 / 金额与趋势过滤 canceled / 支付、评价明细分布不过滤
FEW_SHOT_EXAMPLES: list[dict[str, str]] = [
    # 订单量（由 orders 驱动 → 排除 canceled）
    {"question": "一共有多少个订单？",
     "sql": "SELECT COUNT(DISTINCT o.order_id) AS order_count\n"
            "FROM orders o\n"
            "WHERE o.order_status != 'canceled';"},
    # 金额类（由 order_items 聚合 → 排除 canceled）
    {"question": "总 GMV 是多少？",
     "sql": "SELECT ROUND(SUM(oi.price), 2) AS gmv\nFROM order_items oi\n"
            "JOIN orders o ON oi.order_id = o.order_id\n"
            "WHERE o.order_status != 'canceled';"},
    # 支付方式明细分布（直接查原表；占比分母用标量子查询）
    {"question": "各支付方式的使用情况？",
     "sql": "SELECT payment_type,\n"
            "       COUNT(DISTINCT order_id) AS order_count,\n"
            "       ROUND(COUNT(DISTINCT order_id) * 100.0 /\n"
            "             (SELECT COUNT(DISTINCT order_id) FROM order_payments), 2) AS pct\n"
            "FROM order_payments\n"
            "GROUP BY payment_type\n"
            "ORDER BY order_count DESC;"},
    # 评价明细分布（直接查原表，不过滤）
    {"question": "订单评价按分数分布是怎样的？",
     "sql": "SELECT review_score,\n"
            "       COUNT(*) AS review_count\n"
            "FROM order_reviews\n"
            "GROUP BY review_score\n"
            "ORDER BY review_score;"},
    # 多表 JOIN + 排序 TOP（金额类，排除 canceled）
    {"question": "哪个品类销量最高？列出前 10",
     "sql": "SELECT t.product_category_name_english AS category,\n"
            "       SUM(oi.price) AS sales\n"
            "FROM order_items oi\n"
            "JOIN orders o ON oi.order_id = o.order_id\n"
            "JOIN products p ON oi.product_id = p.product_id\n"
            "JOIN product_category_name_translation t\n"
            "     ON p.product_category_name = t.product_category_name\n"
            "WHERE o.order_status != 'canceled'\n"
            "GROUP BY t.product_category_name_english\n"
            "ORDER BY sales DESC\n"
            "LIMIT 10;"},
    # 多表 JOIN + 分组（订单量分布，排除 canceled）
    {"question": "各州的订单数量分布？",
     "sql": "SELECT c.customer_state,\n"
            "       COUNT(DISTINCT o.order_id) AS order_count\n"
            "FROM orders o\n"
            "JOIN customers c ON o.customer_id = c.customer_id\n"
            "WHERE o.order_status != 'canceled'\n"
            "GROUP BY c.customer_state\n"
            "ORDER BY order_count DESC;"},
    # 时间范围 + 趋势（排除 canceled）
    {"question": "过去每月订单量趋势如何？",
     "sql": "SELECT strftime('%Y-%m', order_purchase_timestamp) AS month,\n"
            "       COUNT(DISTINCT order_id) AS order_count\n"
            "FROM orders\n"
            "WHERE order_status != 'canceled'\n"
            "GROUP BY month\n"
            "ORDER BY month;"},
    # 复购率（子查询口径：排除 canceled 与 unavailable）
    {"question": "客户的复购率是多少？",
     "sql": "SELECT ROUND(SUM(CASE WHEN buy_times >= 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)\n"
            "       AS repurchase_rate_pct\n"
            "FROM (SELECT c.customer_unique_id,\n"
            "             COUNT(DISTINCT o.order_id) AS buy_times\n"
            "      FROM customers c\n"
            "      JOIN orders o ON c.customer_id = o.customer_id\n"
            "      WHERE o.order_status NOT IN ('canceled', 'unavailable')\n"
            "      GROUP BY c.customer_unique_id);"},
]

# 系统指令：约束 LLM 只输出可执行 SELECT，杜绝幻觉字段
SYSTEM_PROMPT = (
    "你是电商数据库（巴西 Olist）SQL 专家。请根据给定的数据表 schema、指标口径和示例，"
    "将用户的中文问题改写为一条可执行的 SQLite SELECT 语句。\n"
    "规则：\n"
    "1. 只允许 SELECT 查询，禁止 INSERT/UPDATE/DELETE/DROP/ALTER 等写操作；\n"
    "2. 表名、列名必须严格来自给出的 schema，禁止臆造字段；\n"
    "3. 口径规则（重要，须与示例一致）：\n"
    "   - 统计订单量（含按年/月/州等分组）以及由 order_items 聚合的金额"
    "（GMV、客单价、总运费、平均单价、品类/商品/卖家销量）→ 统一 JOIN orders 并排除 order_status='canceled'；"
    "除非问句明确要\"包括取消的订单\"或统计某单一状态(canceled/shipped)；\n"
    "   - 支付方式分布、评价分数分布、平均评分、客户/卖家/商品数量等 → 直接对原表统计，不要 JOIN orders 过滤；\n"
    "   - 统计客户人数时按 customer_unique_id 去重（customers 表对每个订单各有一行）；\n"
    "   - 计算占比时分母用独立标量子查询，如 (SELECT COUNT(DISTINCT order_id) FROM order_payments)；\n"
    "   - 计算\"率/占比\"（如取消率、复购率）时：分子为满足条件的事件数"
    "（用 SUM(CASE WHEN 条件 THEN 1 ELSE 0 END)），分母为该分组总数（COUNT(*) 或 COUNT(DISTINCT ...)）；\n"
    "4. 日期用 strftime('%Y-%m', 字段) 提取年月，'%Y' 提取年份；\n"
    "5. 只选择回答问题必需的列，禁止输出额外辅助列（如明细列、多余计数列）；\n"
    "6. 问句为\"哪个/哪种/哪一位……最多/最高\"（单条答案）时排序后加 LIMIT 1，\"前 N\"则加 LIMIT N；\n"
    "7. 只输出 SQL 本身，不要输出解释、不要输出 markdown 代码块；\n"
    "8. 不需要 LIMIT 时不要加 LIMIT（系统会自动附加）。"
)


def build_prompt(question: str, schema_summary: str) -> str:
    """组装 user 侧 Prompt：schema 摘要 + few-shot 示例 + 用户问题。"""
    parts = [f"【数据表结构】\n{schema_summary}", "\n【示例问答】"]
    for ex in FEW_SHOT_EXAMPLES:
        parts.append(f"问：{ex['question']}\n答：\n{ex['sql']}")
    parts.append(f"\n【用户问题】\n{question}\n\n【SQL】")
    return "\n".join(parts)


# ============ 2. SQL 提取与校验 ============

def extract_sql(text: str) -> str:
    """从 LLM 返回文本中提取 SQL。

    兼容三种输出：```sql 代码块、``` 代码块、裸 SQL 文本。
    若整段都是解释性文字，则返回空串（由调用方判为"未生成 SQL"）。
    """
    text = text.strip()
    # 1) 优先取 ```sql ... ``` 代码块
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    if m:
        return m.group(1).strip()
    # 2) 无代码块：取第一个 SELECT/WITH 开头的语句（可能带少量前后缀文字）
    m = re.search(r"(?is)\b(SELECT|WITH)\b.*", text)
    if m:
        return m.group(0).strip()
    return ""


def validate_sql(sql: str) -> tuple[bool, str]:
    """只读校验（PRD FR-02）。

    策略：
        1. 仅允许单条语句，且以 SELECT / WITH 开头；
        2. 禁止写操作关键词（用词边界匹配，避免误伤列名里的子串）。
    返回 (是否通过, 错误信息)。
    """
    if not sql:
        return False, "未生成 SQL"
    # 去掉首尾空白与结尾分号后取首个 token
    first = re.sub(r";\s*$", "", sql.strip()).split()[0].upper()
    if first not in ("SELECT", "WITH"):
        return False, f"非只读语句: 仅允许 SELECT，收到 {first}"
    forbidden = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM)\b",
        re.I,
    )
    if forbidden.search(sql):
        return False, "包含被禁止的写操作关键词"
    return True, ""


# ============ 3. SQL 执行 ============

def _attach_limit(sql: str, limit: int = DEFAULT_LIMIT) -> str:
    """若 SQL 未含 LIMIT，则自动附加 LIMIT，防止返回海量数据（PRD FR-01）。"""
    sql = re.sub(r";\s*$", "", sql.strip())
    if not re.search(r"\bLIMIT\b", sql, re.I):
        sql += f"\nLIMIT {limit}"
    return sql


def execute_sql(sql: str, limit: int = DEFAULT_LIMIT) -> tuple[pd.DataFrame, float]:
    """以只读模式执行 SQL，返回 (DataFrame, 耗时秒)。

    安全措施：
        - 使用 URI 只读模式打开（sqlite3 层禁止任何写操作，与 validate_sql 双保险）；
        - set_progress_handler 实现超时保护（每 10 万条 VM 指令检查一次总耗时，
          超过 EXEC_TIMEOUT 秒则中断查询）；
        - 自动附加 LIMIT 限制结果规模。
    """
    sql = _attach_limit(sql, limit)
    start = time.time()
    # mode=ro：只读打开；file: 前缀必须配 uri=True
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=EXEC_TIMEOUT)

    def _timeout_check() -> int:
        # 返回非 0 即中断当前查询（sqlite3.set_progress_handler 约定）
        return 1 if time.time() - start > EXEC_TIMEOUT else 0

    conn.set_progress_handler(_timeout_check, 100_000)
    try:
        df = pd.read_sql_query(sql, conn)
    finally:
        conn.close()
    return df, time.time() - start


# ============ 4. LLM 调用 ============

def generate_sql(question: str, error_hint: str | None = None) -> str:
    """调用 LLM 生成 SQL；可选携带上轮执行错误信息（用于失败重试）。"""
    schema_summary = build_schema_summary()
    user_prompt = build_prompt(question, schema_summary)
    if error_hint:  # 重试时把错误回传给 LLM，要求修正（PRD FR-05）
        user_prompt += (
            f"\n\n【重要】上一次生成的 SQL 执行失败，错误信息如下：\n{error_hint}\n"
            "请修正 SQL 使其能正确执行，仍然只输出 SQL。"
        )
    client, model = get_llm_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,      # 降低随机性，SQL 生成要求稳定
        max_tokens=1000,
        timeout=LLM_TIMEOUT,
    )
    return extract_sql(resp.choices[0].message.content or "")


# ============ 5. 端到端主流程 ============

def answer(question: str) -> dict:
    """端到端入口：问题 → SQL → 结果。失败自动重试 1 次。

    返回字典结构（供 CLI / Streamlit 复用）：
        {question, sql, df, elapsed, row_count, attempts, error}
    """
    result = {"question": question, "sql": "", "df": None, "elapsed": 0.0,
              "row_count": 0, "attempts": 0, "error": ""}
    last_error = ""
    sql = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        result["attempts"] = attempt
        # ① 生成 SQL
        sql = generate_sql(question, error_hint=last_error or None)
        if not sql:
            last_error = "LLM 未返回 SQL（可能问题超出数据范围）"
            continue
        # ② 只读校验
        ok, msg = validate_sql(sql)
        if not ok:
            last_error = f"SQL 校验失败: {msg}"
            continue
        # ③ 执行
        try:
            df, elapsed = execute_sql(sql)
            result.update(sql=sql, df=df, elapsed=elapsed,
                          row_count=len(df), error="")
            return result
        except Exception as e:  # 执行失败 → 携带错误进入重试
            last_error = f"SQL 执行失败: {e}"

    # 两次尝试均失败：返回最后一条 SQL 与错误信息（PRD FR-05 展示给用户自查）
    result.update(sql=sql, error=last_error)
    return result
