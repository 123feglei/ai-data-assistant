"""NL2SQL 链路 CLI 测试入口（D3 交付物）。

用法：
    1) 单次查询：python scripts/cli_query.py "哪个品类的销量最高？"
    2) 交互模式：python scripts/cli_query.py
       （输入问题回车 → 显示 SQL/结果/耗时；输入 exit 退出）

输出说明：
    - SQL：LLM 生成的最终 SQL（含系统附加的 LIMIT）
    - 耗时：执行 SQL 耗时（不含 LLM 生成时间）
    - attempts：实际调用 LLM 的次数（正常 1，失败重试后为 2）
"""
import sys
from pathlib import Path

# 将项目根目录加入模块搜索路径，保证能从 scripts/ 下 import nl2sql 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nl2sql.engine import answer  # noqa: E402


def show_result(res: dict) -> None:
    """格式化打印一次查询结果。"""
    print("=" * 60)
    print(f"问题：{res['question']}")
    if res["error"]:
        print(f"❌ 失败（尝试 {res['attempts']} 次）：{res['error']}")
        if res["sql"]:
            print("最后生成的 SQL 如下，可自行检查：\n")
            print(res["sql"])
        return
    print(f"✅ 成功（尝试 {res['attempts']} 次，执行耗时 {res['elapsed']:.3f}s）")
    print("SQL：")
    print(res["sql"])
    print(f"\n结果（{res['row_count']} 行）：")
    print(res["df"].to_string(index=False, max_rows=20))


def main() -> None:
    # 单次查询模式：python scripts/cli_query.py "问题"
    if len(sys.argv) > 1:
        show_result(answer(sys.argv[1]))
        return
    # 交互模式
    print("NL2SQL 交互测试（输入 exit 退出）")
    while True:
        q = input("\n问题> ").strip()
        if q.lower() in ("exit", "quit", "退出"):
            break
        if not q:
            continue
        show_result(answer(q))


if __name__ == "__main__":
    main()
