# 「问问数据」部署指南

> 三种方式从"本地可跑"到"别人能访问"，按需选择。
> 本仓库当前默认数据为 8 张业务表精简库 `data/ecommerce.db`（65MB，已纳入 Git，
> 无 geolocation；如需地理表用 `--with-geolocation` 重建，体积会增至 ~130MB）。

---

## 0. 部署前置检查

| 项 | 要求 |
|---|---|
| Python | 3.10+ |
| 依赖 | `pip install -r requirements.txt`（openai 已锁定 <2） |
| 敏感配置 | `.env` 只放本地，**绝不提交**（已被 .gitignore 排除）；线上用平台 Secrets |
| 数据库 | `data/ecommerce.db` 已随仓库提交（8 表，直接可用） |
| 一键启动 | `python -m streamlit run app.py` |

**为什么线上安全**：DeepSeek API Key 只在**后端 Python** 里调用（nl2sql/config.py），
不会下发到浏览器；只要不把 .env 提交到公开仓库，访客无法获取你的 Key。

---

## 方案 A：Streamlit Community Cloud（推荐 · 免费 · 长期在线）

适合：作品长期挂在简历上、随时给面试官发链接。
费用：0 元。限制：无鉴权（链接即访问）、约半天无人访问会休眠、国内访问可能不稳。

### A.1 把代码推到 GitHub
```powershell
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin master
```

### A.2 在 Streamlit 上部署
1. 打开 https://streamlit.io/cloud ，用 **GitHub 账号**登录；
2. 点击 **New app** → 选择刚推送的仓库与分支 → **Main file** 填 `app.py`；
3. 先别点 Deploy，展开 **Advanced settings** → **Secrets**，粘贴：
   ```toml
   DEEPSEEK_API_KEY = "sk-你的key"
   DEEPSEEK_BASE_URL = "https://api.deepseek.com"
   DEEPSEEK_MODEL = "deepseek-chat"
   ```
   （社区云会把 Secrets 注入为进程环境变量，config.py 的 `os.getenv` 自动读到，无需改代码）
4. 点击 **Deploy**，等待 2~3 分钟构建；
5. 完成后得到公网地址 `https://<app名>.streamlit.app`，直接分享即可。

### A.3 日常更新与维护
- 代码更新：`git push` 后平台自动重新部署（无需手动操作）；
- 修改 Secrets：Streamlit Dashboard → 应用 → Settings → Secrets；
- 长时间没访问会"休眠"：打开链接会有 30~60 秒冷启动，属正常。

### A.4 常见问题
| 现象 | 原因与处理 |
|---|---|
| 首次打开很慢 | 应用休眠冷启动；常访问或接受等待即可（免费层特性） |
| 国内访问慢/超时 | `*.streamlit.app` 海外节点；面向国内访客建议方案 C |
| 构建失败 | 看部署日志；多为依赖问题，本项目依赖已在 requirements.txt 固定 |
| 提问报"未配置 Key" | Secrets 未填或未生效，回 Dashboard 检查 |
| 访客提问消耗我额度 | 是，单次约几厘钱；介意可后续加访问口令或限额 |

---

## 方案 B：本地运行 + 内网穿透（免费 · 临时分享）

适合：电脑开着、临时把 Demo 发链接给面试官/朋友（10 分钟内可完成）。
只需映射 `localhost:8501` 到公网临时域名。

### B.1 先启动应用
```powershell
python -m streamlit run app.py --server.headless true
```

### B.2 任选一个隧道工具
**cpolar（国内节点，速度更好）**
```powershell
# 官网 https://www.cpolar.com 注册下载
cpolar authtoken <你的token>
cpolar http 8501
# 终端输出 https://xxxx.cpolar.top 即为公网地址
```
**ngrok（海外节点）**
```powershell
ngrok config add-authtoken <你的token>
ngrok http 8501
```

> 局限：电脑关机/隧道退出后链接失效；免费版域名会变。

---

## 方案 C：国内轻量云服务器（约 ¥30~100/月 · 国内稳定长期）

适合：需要国内稳定访问、长期 24h 在线。

### C.1 服务器准备（腾讯云/阿里云轻量 2C2G 及以上）
```bash
sudo apt update && sudo apt install -y python3.10-venv git
git clone <你的仓库> app && cd app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 配置环境变量
echo "DEEPSEEK_API_KEY=sk-xxx" >> .env
```

### C.2 常驻运行（systemd 示例）
```ini
# /etc/systemd/system/askdata.service
[Unit]
Description=AskData Streamlit
After=network.target

[Service]
WorkingDirectory=/home/user/app
ExecStart=/home/user/app/.venv/bin/python -m streamlit run app.py --server.port 8501 --server.headless true
Restart=always

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now askdata
```

### C.3 反向代理（可选）
- 直接访问 `http://服务器IP:8501` 即可；
- 若要域名 + HTTPS：caddy 自动签发证书，`Caddyfile` 反向代理 8501 端口
  （Streamlit 是 WebSocket，caddy/nginx 需开启 Upgrade 头，caddy 默认已支持）。

---

## 附：命令速查

```powershell
# 本地启动界面
python -m streamlit run app.py

# 无界面验证 NL2SQL 链路
python scripts/cli_query.py "哪个品类销量最高？"

# 跑评测（--limit N 只测前 N 题）
python evaluate.py

# 重建数据库（8 表精简版；加 --with-geolocation 可含地理表）
python scripts/import_data.py

# 验证 DeepSeek 连通性
python scripts/test_llm.py
```

---

*部署前建议先在本地完整跑通一遍；线上遇到问题把平台构建日志/报错贴回即可定位。*
