"""结果处理模块（D5 交付物）：表格数据的自动选图 + 一句话自然语言结论。

设计（对应 PRD FR-03 / FR-04）：
    - build_figure(df)：根据结果字段特征自动选择图表——
        ① 含时间字段（date/month/year 等）→ 折线图（时间趋势）；
        ② 含占比字段（pct/rate/ratio/占比）→ 饼图；
        ③ 分类列 + 数值列 → 柱状图；
        ④ 纯标量（单行单列）→ 返回 None（用数字卡片展示，不画图）；
        ⑤ 无图数据 → 返回 None（页面显示占位提示）。
    - generate_conclusion(question, df)：把"结果前若干行"喂给 LLM，
      生成一句包含具体数字的中文结论（不编造数据）。

图表类型判断的优先级即 ①→②→③，保证"时间序列出折线、占比出饼图、
分组出柱状"（PRD FR-03 验收标准）。
"""
from __future__ import annotations

import re

import pandas as pd
import plotly.graph_objects as go

from nl2sql.config import LLM_TIMEOUT, get_llm_client

# 判断时间字段用的列名关键词（含子串即命中）
_TIME_COL_KEYWORDS = ("date", "time", "month", "year", "timestamp")
# 判断占比字段用的列名关键词
_PCT_COL_KEYWORDS = ("pct", "rate", "ratio", "share", "占比", "率")
# 结论生成时喂给 LLM 的最大行数（控制 token 与成本）
CONCLUSION_MAX_ROWS = 8

# QuickBI 风格配色：品牌蓝 + 数据色板（柱/线/饼共用，保证整套界面视觉统一）
QUICKBI_PRIMARY = "#2166F3"
QUICKBI_COLORS = [
    "#2166F3", "#00B578", "#F6BD16", "#FF6B7A", "#855AF1",
    "#13C2C2", "#FF9F43", "#5B8FF9", "#FFC53D", "#00C2A8",
]


def _style_figure(fig: go.Figure, title: str) -> go.Figure:
    """统一 QuickBI 视觉样式：白底、浅网格、无边框、顶部图例、品牌字体色板。"""
    fig.update_layout(
        title=dict(text=title, x=0.01, font=dict(size=16, color="#1D2129")),
        template="none",
        colorway=QUICKBI_COLORS,
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family='"PingFang SC", "Microsoft YaHei", sans-serif', color="#4E5969"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=48, b=30, l=40, r=20),
        hovermode="x unified",
        xaxis=dict(gridcolor="#F0F2F5", zeroline=False, linecolor="#E5E6EB"),
        yaxis=dict(gridcolor="#F0F2F5", zeroline=False, linecolor="#E5E6EB"),
    )
    return fig


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    """返回可转为数值的列名列表（列中非缺失值 ≥90% 可转数值则视为数值列）。"""
    nums = []
    for col in df.columns:
        s = df[col]
        if s.empty:
            continue
        converted = pd.to_numeric(s, errors="coerce")
        if converted.notna().sum() / len(s) >= 0.9:
            nums.append(col)
    return nums


def _find_time_column(df: pd.DataFrame) -> str | None:
    """寻找时间列：优先列名含日期关键词，其次检查取值形如 YYYY-MM / YYYY。"""
    for col in df.columns:
        low = str(col).lower()
        if any(k in low for k in _TIME_COL_KEYWORDS):
            return col
    # 兜底：检查首列取值是否匹配日期模式（如 strftime 产出的 '2017-11'）
    first = df.columns[0]
    sample = df[first].astype(str).head(5)
    if sample.str.fullmatch(r"\d{4}-\d{2}(-\d{2}( \d{2}:\d{2}:\d{2})?)?|"
                            r"\d{4}-\d{1,2}-\d{1,2}.*").all():
        return first
    return None


def _find_category_column(df: pd.DataFrame, num_cols: list[str]) -> str | None:
    """返回第一个非数值列（作为图表分类轴 / 饼图扇区）。"""
    for col in df.columns:
        if col not in num_cols:
            return col
    return None


def build_figure(df: pd.DataFrame | None) -> go.Figure | None:
    """根据字段特征自动生成 plotly 图表；不适合画图时返回 None。"""
    if df is None or df.empty:
        return None
    num_cols = _numeric_columns(df)
    # ① 纯标量结果（1 行 1 列数值，如总 GMV）→ 不做图，用数字卡片
    if len(num_cols) == 1 and len(df.columns) == 1 and len(df) == 1:
        return None
    # ② 时间序列 → 折线图
    time_col = _find_time_column(df)
    if time_col and num_cols:
        fig = go.Figure()
        for i, y in enumerate(num_cols):
            fig.add_trace(go.Scatter(
                x=df[time_col], y=df[y], mode="lines+markers", name=y,
                line=dict(width=2.5, color=QUICKBI_COLORS[i % len(QUICKBI_COLORS)])))
        return _style_figure(fig, "时间趋势")
    # ③ 含占比列 → 饼图
    pct_col = next((c for c in df.columns
                    if any(k in str(c).lower() for k in _PCT_COL_KEYWORDS)), None)
    cat = _find_category_column(df, num_cols)
    if pct_col and cat:
        fig = go.Figure(go.Pie(
            labels=df[cat], values=df[pct_col], hole=0.35,
            marker=dict(colors=QUICKBI_COLORS[:len(df)]),
            textinfo="label+percent", insidetextorientation="horizontal"))
        return _style_figure(fig, "占比分布")
    # ④ 分类 + 数值 → 柱状图
    if cat and num_cols:
        fig = go.Figure()
        for i, y in enumerate(num_cols):
            fig.add_trace(go.Bar(
                x=df[cat], y=df[y], name=y,
                marker=dict(color=QUICKBI_COLORS[i % len(QUICKBI_COLORS)])))
        return _style_figure(fig, cat)
    return None


def generate_conclusion(question: str, df: pd.DataFrame | None) -> str:
    """调用 LLM 生成一句话中文结论（PRD FR-04）。

    为避免编造，只把结果前 N 行喂给 LLM，并要求结论必须使用结果中出现的数字。
    """
    if df is None or df.empty:
        return "查询无数据，暂无结论。可换个问法试试。"
    # 结果压缩成紧凑文本：保留前若干行（过长时截断提示）
    sample = df.head(CONCLUSION_MAX_ROWS).to_string(index=False)
    if len(df) > CONCLUSION_MAX_ROWS:
        sample += f"\n……（共 {len(df)} 行）"
    prompt = (
        "你是电商业务数据分析师。请根据下面的查询结果，用一句话给出中文业务结论。\n"
        "要求：\n"
        "1. 必须包含结果中出现的关键具体数字（如金额、数量、占比、排名）；\n"
        "2. 若结果含排名/占比，指出第一名及其数值；若为时间趋势，指出最高点月份与数值；\n"
        "3. 禁止编造结果中没有的数字；总字数不超过 80 字。\n\n"
        f"【问题】{question}\n\n【查询结果】\n{sample}\n\n【一句话结论】"
    )
    client, model = get_llm_client()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system",
                 "content": "你只输出一句包含具体数字的中文业务结论，不要任何解释。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,   # 结论生成可略开放，让语言自然
            max_tokens=200,
            timeout=LLM_TIMEOUT,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:  # 结论生成失败不应阻塞主流程
        return f"（结论生成失败：{e}）"
