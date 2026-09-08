"""「问问数据」对话式数据分析助手 · Streamlit 主界面（D5 交付物）

一键启动：  streamlit run app.py

界面设计（QuickBI 风格）：
    - 顶部品牌渐变横幅 + 示例问题胶囊按钮
    - 每条分析结果展示为独立"结果卡片"，内部用栏目（Tabs）分区展示：
        📈 图表分析 / 📋 数据明细 / 🧾 SQL 语句
    - 卡片顶部为"智能洞察"高亮条（一句话结论），单值结果用品牌蓝色大数字卡片（KPI）
    - 配色：QuickBI 品牌蓝 #2166F3 + 数据色板，浅灰页面底 + 白色圆角卡片
"""
from __future__ import annotations

import sys
from pathlib import Path

# 保证从任意工作目录启动都能导入 nl2sql 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from nl2sql.engine import answer
from nl2sql.present import build_figure, generate_conclusion

# ============ 页面配置 ============
st.set_page_config(page_title="问问数据 · NL2SQL", page_icon="📊", layout="wide")

# ============ QuickBI 风格全局样式 ============
CUSTOM_CSS = """
<style>
/* 页面底色与主容器 */
.stApp { background-color: #F3F5F9; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stMainBlockContainer"] { padding-top: 1.2rem; max-width: 1180px; }

/* 品牌渐变横幅 */
.qb-brand {
  background: linear-gradient(115deg, #0E2A5C 0%, #16409E 45%, #2166F3 100%);
  border-radius: 16px; padding: 22px 30px; color: #fff; margin-bottom: 10px;
  box-shadow: 0 8px 20px rgba(18, 55, 150, 0.20);
}
.qb-brand .t1 { font-size: 25px; font-weight: 700; letter-spacing: .5px; }
.qb-brand .t2 { font-size: 13.5px; opacity: .82; margin-top: 7px; }

/* 通用白色圆角卡片 */
.qb-card {
  background: #fff; border: 1px solid #E7EAF0; border-radius: 14px;
  padding: 16px 20px; margin: 10px 0;
  box-shadow: 0 2px 10px rgba(15, 40, 90, 0.05);
}
.qb-card .qb-label { font-size: 13px; color: #86909C; }

/* 智能洞察高亮条 */
.qb-insight {
  background: linear-gradient(90deg, #EAF2FF, #F7FAFF);
  border-left: 4px solid #2166F3; border-radius: 8px;
  padding: 10px 14px; margin: 8px 0 4px 0;
  color: #1D2129; font-size: 15px; line-height: 1.6;
}

/* 示例问题：胶囊按钮 */
.stButton > button {
  border-radius: 999px; border: 1px solid #2166F3; color: #2166F3;
  background: #fff; font-weight: 500; transition: all .18s;
}
.stButton > button:hover { background: #2166F3; color: #fff; border-color: #2166F3; }

/* Tabs 激活色 */
.stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 6px 16px; }
.stTabs [aria-selected="true"] { background: #EAF2FF; color: #2166F3; font-weight: 600; }

/* KPI 大数字卡片 */
[data-testid="stMetric"] {
  background: linear-gradient(135deg, #2166F3, #3D8BFF); border-radius: 12px;
  padding: 12px 20px; box-shadow: 0 4px 14px rgba(33, 102, 243, 0.25);
}
[data-testid="stMetricLabel"] { color: #DCE8FF; font-size: 13px; }
[data-testid="stMetricValue"] { color: #fff; font-size: 26px; font-weight: 700; }

/* 输入框圆角 */
[data-testid="stChatInput"] { border-radius: 12px; }

/* 侧边栏说明卡片 */
.qb-sec {
  background: #fff; border: 1px solid #E7EAF0; border-radius: 10px;
  padding: 10px 13px; margin-bottom: 10px;
}
.qb-sec .h { font-weight: 700; color: #2166F3; font-size: 14px; margin-bottom: 6px; }
.qb-sec ul { margin: 0; padding-left: 17px; color: #4E5969; font-size: 13px; line-height: 1.9; }
.qb-sec p { margin: 0; color: #4E5969; font-size: 13px; line-height: 1.8; }
.qb-sec .highlight { color: #1D2129; font-weight: 600; }
.qb-sec .ok { color: #00B578; }
.qb-sec .no { color: #FF6B6B; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ============ 侧边栏：数据集 / 业务问题示例 / 技术边界 ============
def render_sidebar() -> None:
    """侧边栏说明：让用户了解"数据是什么、能问什么、系统边界在哪"。"""
    with st.sidebar:
        st.markdown("## 📊 问问数据")
        st.markdown(
            """
            <div class="qb-sec">
              <div class="h">📁 数据集简介</div>
              <p><span class="highlight">巴西电商 Olist</span>（Kaggle 公开数据集）
              —— 巴西最大电商平台 2016-2018 年的真实交易数据。</p>
              <ul>
                <li>有效订单 <span class="highlight">98,816</span> 单（已剔除取消单）</li>
                <li>客户 <span class="highlight">96,096</span> 位 · 卖家 3,095 家</li>
                <li>商品 32,951 种 · 覆盖 71 个品类</li>
                <li>时间范围：2016-09 ~ 2018-08</li>
                <li>核心表：订单 / 明细 / 客户 / 卖家 / 支付 / 评价 / 商品 / 品类</li>
              </ul>
            </div>

            <div class="qb-sec">
              <div class="h">🎯 业务问题示例（可以这样问）</div>
              <ul>
                <li><b>汇总指标：</b>总 GMV 多少？客单价？复购率？</li>
                <li><b>排行 TOP：</b>销量最高的品类/商品？高价值客户 TOP10？</li>
                <li><b>分布占比：</b>各州订单分布？支付方式占比？评价分数分布？</li>
                <li><b>时间趋势：</b>每月订单量趋势？2018 年各月 GMV？</li>
                <li><b>复杂分析：</b>各州客单价排名？订单取消率最高的州？</li>
              </ul>
            </div>

            <div class="qb-sec">
              <div class="h">⛔ 技术边界（查询范围）</div>
              <p><span class="ok">✔</span> 仅支持<b>只读 SELECT</b> 查询本数据集（写操作会被拦截）<br>
              <span class="ok">✔</span> 单次结果最多返回 <b>200</b> 行（超出可加条件缩小范围）<br>
              <span class="ok">✔</span> 支持单表 / 多表 JOIN / 聚合 / 时间范围 / 排序 TOP 等</p>
              <p><span class="no">✘</span> 不做预测、不回答与数据无关的问题<br>
              <span class="no">✘</span> 不支持多轮记忆、跨数据源、写入操作<br>
              <span class="no">✘</span> 数据为 2018-08 前的静态快照，不含实时数据</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

render_sidebar()

# ============ 顶部品牌横幅 ============
st.markdown(
    """
    <div class="qb-brand">
      <div class="t1">📊 问问数据 · 对话式数据分析助手</div>
      <div class="t2">输入业务问题（中文/英文）→ 自动生成 SQL 查询巴西电商 Olist 数据集 → 输出图表与一句话结论</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============ 示例问题（PRD FR-08） ============
EXAMPLE_QUESTIONS = [
    "总 GMV 是多少？",
    "哪个品类销量最高？列出前 5",
    "各州的订单数量分布是怎样的？",
    "过去每月的订单量趋势如何？",
    "消费金额最高的前 5 位客户是谁？",
    "各支付方式的订单占比是多少？",
]

# ============ 会话历史 ============
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


def ask(question: str) -> dict:
    """执行完整链路：NL2SQL → 自动选图 → 一句话结论。"""
    res = answer(question)
    if res["error"]:
        return {"question": question, "sql": res["sql"], "df": None,
                "error": res["error"], "conclusion": ""}
    conclusion = generate_conclusion(question, res["df"])
    return {"question": question, "sql": res["sql"], "df": res["df"],
            "elapsed": res["elapsed"], "row_count": res["row_count"],
            "error": "", "conclusion": conclusion}


def process(question: str) -> None:
    """提问入口：执行并把结果追加进历史，随后 rerun 渲染。"""
    with st.spinner("⏳ 分析中…（生成 SQL → 查询 → 出图 → 洞察）"):
        item = ask(question)
    st.session_state.messages.append({"role": "user", "content": question})
    st.session_state.messages.append({"role": "assistant", **item})
    st.rerun()


def render_assistant(item: dict) -> None:
    """把一条分析结果渲染为 QuickBI 风格"结果卡片"，内部用 Tabs 分区。"""
    # 结果卡片开标签
    st.markdown('<div class="qb-card">', unsafe_allow_html=True)

    if item.get("error"):
        st.error(f"❌ {item['error']}")
        if item.get("sql"):
            st.warning("系统生成的 SQL 如下，可自行检查：")
            st.code(item["sql"], language="sql")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    df = item["df"]
    elapsed = item.get("elapsed", 0)
    # 元信息：查询规模与耗时
    meta = f"📌 共 {item.get('row_count', 0)} 行结果"
    if df is not None and len(df) > 0:
        meta += f" · {len(df.columns)} 个字段"
    meta += f" · 执行耗时 {elapsed:.2f}s"
    st.markdown(f'<div class="qb-label">{meta}</div>', unsafe_allow_html=True)

    # 智能洞察：一句话结论高亮条（FR-04）
    if item.get("conclusion"):
        st.markdown(
            f'<div class="qb-insight">💡 <b>智能洞察</b>　{item["conclusion"]}</div>',
            unsafe_allow_html=True,
        )

    if df is None or df.empty:
        st.info("查询无数据，可换个问法试试。")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # 单值标量结果 → 品牌蓝 KPI 大数字卡片（比图表更直观）
    is_scalar = len(df.columns) == 1 and len(df) == 1
    if is_scalar:
        col_name, value = df.columns[0], df.iloc[0, 0]
        try:
            value = f"{float(value):,.2f}"
        except (TypeError, ValueError):
            value = str(value)
        st.metric(label=str(col_name), value=value)

    # 栏目（Tabs）分区展示：图表 / 数据明细 / SQL
    tab_chart, tab_data, tab_sql = st.tabs(["📈 图表分析", "📋 数据明细", "🧾 SQL 语句"])

    with tab_chart:
        fig = build_figure(df)
        if is_scalar:
            st.caption("标量结果已在上方 KPI 卡片高亮展示。")
        elif fig is not None:
            st.plotly_chart(fig, width="stretch")
        else:
            st.caption("当前结果暂不适合绘图，可查看下方数据明细。")
    with tab_data:
        st.dataframe(df, width="stretch", hide_index=True)
    with tab_sql:
        st.code(item["sql"], language="sql")

    # 结果卡片闭标签
    st.markdown("</div>", unsafe_allow_html=True)


# ============ 示例问题（胶囊按钮，2×3 网格） ============
st.markdown(
    '<div style="color:#1D2129;font-weight:600;font-size:15px;margin:6px 0 2px 0;">'
    "💡 试试这样问</div>",
    unsafe_allow_html=True,
)
grid = st.columns(3)
for i, q in enumerate(EXAMPLE_QUESTIONS):
    with grid[i % 3]:
        if st.button(q, key=f"btn_{i}", width="stretch"):
            st.session_state.pending_question = q

# ============ 历史对话渲染 ============
for msg in st.session_state.messages:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.write(msg["content"])
    else:
        with st.chat_message("assistant"):
            render_assistant(msg)

# ============ 输入与事件处理 ============
if st.session_state.pending_question:
    q = st.session_state.pending_question
    st.session_state.pending_question = None
    process(q)
else:
    q = st.chat_input("输入业务问题，例如：各州 2018 年的 GMV 是多少？")
    if q:
        process(q)
