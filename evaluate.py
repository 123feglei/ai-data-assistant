"""D4 离线评测脚本（PRD FR-06）。

对评测集 data/eval_set.json 中每题运行完整 NL2SQL 链路（answer），将生成 SQL
的执行结果与金标准 SQL 的执行结果做语义对比，输出：
    1. 总准确率、各问题类别准确率、执行成功率、平均耗时、平均重试次数；
    2. 错误类型分布（表名幻觉 / 列名幻觉 / JOIN错误 / 语法错误 / 结果不一致等）；
    3. 逐题失败明细（生成 SQL vs 金标准 SQL），报告可导出为 Markdown。

用法：
    python evaluate.py                 # 评测全部题目，报告输出到 reports/
    python evaluate.py --limit 5       # 只评测前 5 题（冒烟测试）
    python evaluate.py --out x.md      # 指定报告路径

判定口径（结果对比法）：
    - 先比较列数；列名集合一致时按列名对齐后比较「排序后的行集合」；
    - 列名不一致（LLM 别名不同）时，若列数 ≤ 4 则尝试所有列排列，任一对齐
      使行集合相等即判对——兼顾"别名宽容"与"行列关联不丢失"；
    - 数值统一 round(·,3) 后再比较，避免浮点精度误判。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from itertools import combinations, permutations
from pathlib import Path

import pandas as pd

from nl2sql.engine import answer, execute_sql

ROOT = Path(__file__).resolve().parent  # evaluate.py 位于项目根目录
EVAL_SET = ROOT / "data" / "eval_set.json"
REPORT_DIR = ROOT / "reports"

# 类别中文名（用于报告）
CATEGORY_NAMES = {
    "simple": "简单单表查询",
    "agg": "聚合统计",
    "join": "多表JOIN",
    "time": "时间范围",
    "complex": "复杂组合",
}


# ============ 1. 结果判定 ============

def _norm_cell(v) -> tuple:
    """把单个单元格规范化为可安全排序/比较的元组（避免 Python3 混合类型比较报错）。"""
    if pd.isna(v):
        return ("z", None)  # NULL 统一放最后
    if isinstance(v, bool):
        return ("b", int(v))
    if isinstance(v, (int, float)):
        return ("f", round(float(v), 2))  # 数值统一 round 到 2 位（与金标准显示精度一致）
    return ("s", str(v))


def _sorted_rows(df: pd.DataFrame) -> list:
    """DataFrame → 排序后的行元组列表（每行内 cell 保持列序，整体按行排序）。"""
    return sorted(
        tuple(_norm_cell(x) for x in row) for row in df.itertuples(index=False)
    )


def frames_equivalent(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """判断两个查询结果是否语义等价（忽略列名、列序、行序差异）。

    容忍情形（业务友好）：
        - 生成 SQL 附带额外辅助列（如同时输出 total_orders、canceled_orders）；
        - LLM 起的列别名与金标准不同。
    实现：在"列名集合一致"或"gold 是 gen 列的子集"时对齐比较；否则当列数较少时
    枚举列排列/组合做值匹配（n≤4，成本可控）。
    """
    gold_cols = [str(c) for c in b.columns]
    gen_cols = [str(c) for c in a.columns]
    n = len(gold_cols)
    if len(gen_cols) < n:
        return False
    gold_rows = _sorted_rows(b)

    def match_subset(gen_col_indexes) -> bool:
        """按给定 gen 列索引投影后，尝试所有列排列与 gold 行集合比对。"""
        sub = a.iloc[:, gen_col_indexes]
        if len(gen_col_indexes) == n and len(set(gen_col_indexes)) == n:
            for perm in permutations(range(n)):
                if _sorted_rows(sub.iloc[:, list(perm)]) == gold_rows:
                    return True
            return False
        # gen 列多于 gold 列（多余辅助列）：直接比较投影行集合（顺序固定）
        return _sorted_rows(sub) == gold_rows

    # 情形 A：gold 列名是 gen 列名的子集 → 按名对齐比较
    if set(gold_cols) <= set(gen_cols):
        idx = [gen_cols.index(c) for c in gold_cols]
        return match_subset(idx)
    # 情形 B：列数相同但列名不一致 → 尝试所有列排列（兼容别名差异）
    if len(gen_cols) == n and n <= 4:
        return match_subset(list(range(n)))
    # 情形 C：gen 列更多且列名不重合 → 枚举 gen 列组合后做列排列匹配
    if len(gen_cols) <= 5 and n <= 4:
        for combo in combinations(range(len(gen_cols)), n):
            sub = a.iloc[:, list(combo)]
            for perm in permutations(range(n)):
                if _sorted_rows(sub.iloc[:, list(perm)]) == gold_rows:
                    return True
    return False


# ============ 2. 错误分类 ============

def classify_error(msg: str) -> str:
    """根据执行错误信息自动归类（PRD 9.2 错误类型：表/列名幻觉、JOIN、语法、语义等）。"""
    m = msg.lower()
    if "llm 未返回" in m or "未生成 sql" in m:
        return "未生成SQL(语义误解)"
    if "no such table" in m:
        return "表名幻觉"
    if "no such column" in m:
        return "列名幻觉"
    if "ambiguous" in m:
        return "JOIN/别名错误"
    if any(k in m for k in ("syntax error", "no such function", "misuse",
                            "incomplete input", "near \"")):
        return "语法错误"
    if "校验失败" in m or "非只读" in m:
        return "非只读SQL"
    return "其他执行错误"


# ============ 3. 主流程 ============

def run_question(item: dict) -> dict:
    """评测单题：跑链路 + 与金标准对比。返回明细记录。"""
    question, gold = item["question"], item["gold_sql"]
    t0 = time.time()
    res = answer(question)          # 完整 NL2SQL 链路（含自动重试）
    total_cost = time.time() - t0   # 端到端耗时（含 LLM 生成）
    gold_df, _ = execute_sql(gold)  # 执行金标准作为基准

    record = {
        "id": item["id"], "category": item["category"], "question": question,
        "gold_sql": gold, "gen_sql": res["sql"],
        "gen_df": res["df"], "gold_df": gold_df,
        "attempts": res["attempts"], "cost": total_cost, "status": "", "note": "",
    }
    if res["error"]:  # 链路失败（未生成 SQL / 校验失败 / 执行失败）
        record["status"] = "fail"
        record["note"] = classify_error(res["error"]) + ": " + res["error"]
        return record
    # 执行成功 → 与金标准结果对比
    if frames_equivalent(res["df"], gold_df):
        record["status"] = "pass"
    else:
        record["status"] = "fail"
        record["note"] = "结果不一致(语义/聚合差异,需人工复核)"
    return record


def render_report(records: list[dict], total: int) -> str:
    """生成 Markdown 评测报告文本。"""
    passed = [r for r in records if r["status"] == "pass"]
    n_pass = len(passed)
    acc = n_pass / total * 100 if total else 0
    # 执行成功率：生成 SQL 能成功执行（拿到结果）的比例（含执行成功但结果不一致）
    exec_fail = sum(1 for r in records if r["gen_df"] is None and r["status"] == "fail")
    exec_ok = total - exec_fail
    avg_cost = sum(r["cost"] for r in records) / total if total else 0
    avg_attempts = sum(r["attempts"] for r in records) / total if total else 0

    lines = [
        "# NL2SQL 评测报告",
        "",
        f"- 评测时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 评测题目：{total} 题",
        f"- 模型：deepseek-chat（temperature=0，失败自动重试 1 次）",
        "",
        "## 总览",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 总准确率 | {acc:.1f}% ({n_pass}/{total}) |",
        f"| 执行成功率 | {exec_ok}/{total} ({exec_ok / total * 100:.1f}%) |",
        f"| 平均端到端耗时 | {avg_cost:.2f}s/题 |",
        f"| 平均 LLM 调用次数 | {avg_attempts:.2f} 次/题 |",
        "",
        "## 各类别准确率",
        "",
        "| 类别 | 题数 | 通过 | 准确率 |",
        "|---|---|---|---|",
    ]
    for cat in CATEGORY_NAMES:
        recs = [r for r in records if r["category"] == cat]
        if not recs:  # 跳过无题目的类别（--limit 冒烟测试时可能为空）
            continue
        p = sum(1 for r in recs if r["status"] == "pass")
        lines.append(f"| {CATEGORY_NAMES[cat]} | {len(recs)} | {p} | {p / len(recs) * 100:.1f}% |")

    # 错误类型分布
    lines += ["", "## 错误类型分布", "", "| 错误类型 | 数量 |", "|---|---|"]
    err_counter: dict[str, int] = {}
    for r in records:
        if r["status"] != "pass":
            key = r["note"].split(":")[0]
            err_counter[key] = err_counter.get(key, 0) + 1
    for k, v in sorted(err_counter.items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v} |")

    # 失败明细
    fails = [r for r in records if r["status"] != "pass"]
    lines += ["", "## 失败明细（供人工复核与错误类型细分）", ""]
    if not fails:
        lines.append("全部通过 🎉")
    for r in fails:
        lines += [
            f"### {r['id']}. [{CATEGORY_NAMES[r['category']]}] {r['question']}",
            "",
            f"- 结论：❌ {r['note']}（耗时 {r['cost']:.2f}s，LLM 调用 {r['attempts']} 次）",
            "",
            "**生成的 SQL：**",
            "",
            "```sql",
            r["gen_sql"] or "（LLM 未生成 SQL）",
            "```",
            "",
            "**金标准 SQL：**",
            "",
            "```sql",
            r["gold_sql"],
            "```",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="NL2SQL 离线评测（PRD FR-06）")
    ap.add_argument("--limit", type=int, default=0, help="只评测前 N 题（默认全部）")
    ap.add_argument("--out", type=str, default="", help="报告输出路径（默认 reports/eval_report_时间.md）")
    args = ap.parse_args()

    data = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    questions = data["questions"]
    if args.limit > 0:
        questions = questions[: args.limit]

    print(f"开始评测 {len(questions)} 题 ...")
    records = []
    for i, item in enumerate(questions, 1):
        rec = run_question(item)
        records.append(rec)
        mark = "✅" if rec["status"] == "pass" else "❌"
        print(f"[{i}/{len(questions)}] {mark} #{rec['id']} [{rec['category']}] "
              f"{rec['question'][:24]} ... {rec['cost']:.1f}s")
        sys.stdout.flush()  # 逐题刷新，便于观察进度

    # 输出报告
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else REPORT_DIR / (
        f"eval_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md")
    out.write_text(render_report(records, len(questions)), encoding="utf-8")
    print(f"\n评测完成，报告已导出：{out}")


if __name__ == "__main__":
    main()
