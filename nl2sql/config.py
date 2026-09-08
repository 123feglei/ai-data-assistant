"""NL2SQL 引擎 · 统一配置加载模块（D3 前置）。

职责：
    1. 加载 .env 中的配置（DeepSeek API Key、模型名、数据库路径等）；
    2. 提供 LLM 客户端工厂函数 get_llm_client()；
    3. 配置缺失时给出友好报错，避免 D3 链路跑起来才暴露问题。

设计说明：
    - 优先级：环境变量 > .env 文件 > Streamlit Secrets > 默认值；
    - 兼容双环境：本地用 .env；Streamlit Community Cloud 用平台 Secrets
      （平台会注入环境变量，个别情况下也可经 st.secrets 读取，这里做双保险）；
    - 支持双 LLM 后端（DeepSeek API / 本地 Ollama），通过 LLM_BACKEND 切换，与 PRD 7.2 保持一致。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（本文件位于 nl2sql/ 下，向上取一级）
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # 读取项目根目录 .env（若已配置系统环境变量则优先）


def _get_config(key: str, default: str = "") -> str:
    """读取配置：环境变量优先；其次兼容 Streamlit Cloud 的 st.secrets。

    在无 Streamlit 运行时（CLI / 评测脚本）调用时不会报错：
    取不到值就返回默认值，由调用方给出友好提示。
    """
    value = os.getenv(key)
    if value is not None and value.strip():
        return value.strip()
    try:  # 云端双保险：Secrets 也可能只暴露在 st.secrets
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return default


# ---------- 配置项（全部可从 .env / Secrets 覆盖） ----------
# URL 类配置做字符清理：防复制时误带 markdown 反引号/引号（如 `https://...`）
def _clean_url(url: str) -> str:
    return url.strip().strip("`'\" ")


DEEPSEEK_API_KEY = _get_config("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = _clean_url(
    _get_config("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
DEEPSEEK_MODEL = _get_config("DEEPSEEK_MODEL", "deepseek-chat")

# 后端开关：api=DeepSeek 云 API；ollama=本地 Ollama（如 qwen2.5:7b）
LLM_BACKEND = _get_config("LLM_BACKEND", "api").lower()
OLLAMA_BASE_URL = _clean_url(
    _get_config("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
OLLAMA_MODEL = _get_config("OLLAMA_MODEL", "qwen2.5:7b")

# 数据库与请求超时
DB_PATH = _get_config("DB_PATH", str(ROOT / "data" / "ecommerce.db"))
LLM_TIMEOUT = int(_get_config("LLM_TIMEOUT", "60"))


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
            "未读取到 DEEPSEEK_API_KEY。请检查：\n"
            "1) 本地运行：在项目根目录 .env 中填入 "
            "https://platform.deepseek.com 创建的 Key（参考 .env.example）；\n"
            "2) Streamlit Cloud 部署：在 Dashboard → 应用 → Settings → Secrets 中配置\n"
            "   DEEPSEEK_API_KEY=sk-... 等三项，保存后重启应用。"
        )
    return OpenAI(base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY, timeout=LLM_TIMEOUT), DEEPSEEK_MODEL
