# 问问数据（AskData）

**对话式数据分析助手**：用自然语言（中文/英文）向业务数据库提问，自动生成并执行 SQL，
返回「结果表格 + 自动图表 + 一句话结论」。

```
问：哪个品类销量最高？        →  SQL + 柱状图 + 智能结论
问：过去每月订单量趋势如何？  →  SQL + 折线图 + 智能结论
```

## 功能特性

- **NL2SQL**：自建 Prompt 链路（schema 摘要 + few-shot 示例 + 口径规则），LLM 生成 SQL
- **安全执行**：只读校验 + SQLite 只读连接 + 15s 超时 + 自动 LIMIT 200，失败自动带报错重试 1 次
- **自动可视化**：标量 → KPI 卡片；时间字段 → 折线图；占比字段 → 饼图；分类+数值 → 柱状图
- **智能结论**：基于查询结果生成含具体数字的一句话业务结论
- **评测闭环**：35 题 × 5 类评测集 + 执行结果对比判定，驱动口径与 Prompt 迭代
- **界面友好**：Streamlit 对话式界面，示例问题引导、SQL 可展开自查、数据说明侧边栏

## 技术栈

Python · SQLite · OpenAI SDK（DeepSeek API，兼容 Ollama）· Streamlit · Plotly

## 架构

```
Streamlit 界面 (app.py)
   │ 用户问题
   ▼
NL2SQL 引擎 (nl2sql/engine.py)
   ├─ 组装 Prompt：schema 摘要 + few-shot + 口径规则
   ├─ LLM 生成 SQL → 只读校验 → SQLite 执行（失败重试 1 次）
   ▼  DataFrame
结果处理 (nl2sql/present.py)：自动选图 + 一句话结论
   ▼
表格 / Plotly 图表 / 结论
```

## 快速开始

```bash
# 1. 安装依赖（Python 3.10+）
pip install -r requirements.txt

# 2. 配置 LLM（任选其一）
cp .env.example .env      # 填入 DEEPSEEK_API_KEY（https://platform.deepseek.com）
                          # 或使用本地 Ollama：设置 LLM_BACKEND=ollama

# 3. 启动
streamlit run app.py
```

> 仓库已内置精简版数据库 `data/ecommerce.db`（8 张业务表，约 65MB）。
> 如需用原始 CSV 重建：`python scripts/import_data.py`。

## 使用示例

点击页面示例问题，或直接输入：

| 问法 | 结果 |
|---|---|
| 总 GMV 是多少？ | 单值 KPI 卡片 |
| 各州的订单数量分布是怎样的？ | 分组柱状图 |
| 过去每月的订单量趋势如何？ | 时间折线图 |
| 各支付方式的订单占比是多少？ | 占比饼图 |
| 消费金额最高的前 5 位客户是谁？ | 明细表格 + 洞察 |

## 评测结果

内置离线评测（`python evaluate.py`）：35 题覆盖单表 / 聚合 / 多表 JOIN / 时间范围 / 复杂组合五类，
执行结果与金标准对比，准确率 97%+，平均端到端约 4 秒/题。

## 目录结构

```
app.py                      # Streamlit 界面
nl2sql/
  config.py                 # 配置（.env / Secrets 双保险）
  engine.py                 # NL2SQL 引擎：Prompt 组装 / 校验 / 执行 / 重试
  present.py                # 自动选图 + 结论生成
evaluate.py                 # 离线评测脚本
data/
  ecommerce.db              # SQLite 数据库（8 张业务表）
  schema.md                 # 表结构 / 字段 / 指标口径说明
  eval_set.json             # 评测集（35 题）
scripts/                    # 数据导入 / CLI / LLM 连通性等辅助脚本
```

## 相关文档

- `data/schema.md` — 数据表结构与指标口径
- `DEPLOY.md` — 部署指南（Community Cloud / 内网穿透 / 云服务器）

## License

MIT
