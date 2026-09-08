"""NL2SQL 引擎 · 统一配置加载模块（D3 前置）。

职责：
    1. 加载 .env 中的配置（DeepSeek API Key、模型名、数据库路径等）；
    2. 提供 LLM 客户端工厂函数 get_llm_client()；
    3. 配置缺失时给出友好报错，避免 D3 链路跑起来才暴露问题。

设计说明：
    - 优先级：环境变量 > .env 文件 > 默认值（python-dotenv 默认不覆盖已存在的环境变量）；
    - 支持双 LLM 后端（DeepSeek API / 本地 Ollama），通过 LLM_BACKEND 切换，与 PRD 7.2 保持一致。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（本文件位于 nl2sql/ 下，向上取一级）
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # 读取项目根目录 .env（若已配置系统环境变量则优先）

# ---------- 配置项（全部可从 .env 覆盖） ----------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 后端开关：api=DeepSeek 云 API；ollama=本地 Ollama（如 qwen2.5:7b）
LLM_BACKEND = os.getenv("LLM_BACKEND", "api").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# 数据库与请求超时
DB_PATH = os.getenv("DB_PATH", str(ROOT / "data" / "ecommerce.db"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))


def get_llm_client():
    """创建 LLM 客户端（openai SDK 兼容）。

    返回 (client, model_name)：
        - api 后端：指向 DeepSeek 官方兼容端点；
        - ollama 后端：指向本地 Ollama 的 OpenAI 兼容端点。
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "缺少 openai 依赖，请先执行: pip install -r requirements.txt"
        )

    if LLM_BACKEND == "ollama":
        return OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama"), OLLAMA_MODEL

    if not DEEPSEEK_API_KEY:
        raise RuntimeError(
            "未配置 DEEPSEEK_API_KEY。请打开项目根目录 .env 文件，"
            "填入 https://platform.deepseek.com 创建的 API Key（参考 .env.example）。"
        )
    return OpenAI(base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY, timeout=LLM_TIMEOUT), DEEPSEEK_MODEL
