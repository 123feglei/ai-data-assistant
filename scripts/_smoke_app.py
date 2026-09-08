"""临时脚本：AppTest 模拟真实提问，验证 QuickBI 界面（Tabs/卡片/洞察/KPI）。"""
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("app.py", default_timeout=240)
at.run()

# ① 提问"多行分组结果"→ 应渲染结果卡片 + Tabs（图表/数据/SQL）
at.chat_input[0].set_value("各州的订单数量分布是怎样的？")
at.run()
assert not at.exception, [e.value for e in at.exception]

# ② 提问"单值结果"→ 应渲染 KPI 数字卡片（metric）
at.chat_input[0].set_value("总 GMV 是多少？")
at.run()
assert not at.exception, [e.value for e in at.exception]

# 汇总统计
print("异常数:", len(at.exception))
for e in at.exception:
    print("异常:", e.value)
print("metric(KPI)数:", len(at.metric))
print("dataframe数:", len(at.dataframe))
print("markdown块数:", len(at.markdown))

assert len(at.metric) >= 1, "缺少 KPI 数字卡片（GMV 应为 metric）"
assert len(at.dataframe) >= 1, "缺少数据表格"
print("\nQuickBI 界面真实提问链路测试通过 ✅")
