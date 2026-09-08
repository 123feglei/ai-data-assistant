"""LLM 连通性测试脚本：验证 DeepSeek API 配置是否可用。

用法：
    python scripts/test_llm.py

预期输出：
    ✅ DeepSeek API 连接成功，模型返回：...
若报错，请检查 .env 中的 DEEPSEEK_API_KEY 是否正确、账户是否已充值。
"""
import sys
from pathlib import Path

# 将项目根目录加入模块搜索路径，保证能从 scripts/ 下 import nl2sql 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nl2sql.config import LLM_BACKEND, get_llm_client


def main() -> None:
    print(f"后端: {LLM_BACKEND}")
    client, model = get_llm_client()
    print(f"模型: {model}")

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "请只回复两个字：正常"}],
        max_tokens=10,
        temperature=0,
    )
    print(f"✅ API 连接成功，模型返回：{resp.choices[0].message.content}")


if __name__ == "__main__":
    main()
