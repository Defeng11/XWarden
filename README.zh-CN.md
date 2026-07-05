<p align="right">
  <a href="README.md">🇬🇧 English</a>
  |
  <a href="README.zh-CN.md">🇨🇳 中文</a>
</p>

# XWarden 🦞

> 监控 X/Twitter 账号 — 自动 LLM 翻译 — 推送到手机。

**XWarden** 是一个轻量级、自托管的工具：监控指定 X (Twitter) 用户的新推文，通过 LLM 翻译成中文，然后推送到你的 Bark（iOS）、Telegram 或飞书。每次运行是一次性的：抓取、翻译、通知、退出。非常适合定时任务（cron / Task Scheduler）。

---

## 工作原理

```
[X/Twitter] ──bb-browser──→ [用户推文 API]
       │                          │
       │                   ┌──────┘
       │                   ▼
       │          [去重: SHA-1]
       │                   │
       │            (有新推文?)
       │                   │
       │                   ▼
       │          [LLM 翻译]
       │          minimax / deepseek
       │                   │
       │                   ▼
       │     ┌─────────────────────┐
       │     Bark  Telegram  飞书
       ▼     └─────────────────────┘
    你的手机
```

**关键技术决策：**

1. **bb-browser 替代 Playwright/nodriver** — X 用 Cloudflare 拦截无头浏览器。`bb-browser` 通过 CDP 连接真实 Chrome，绕过反爬检测。
2. **LLM 翻译替代 Google 爬虫** — Google 免费翻译将长文本切段后丢失上下文。LLM（MiniMax / DeepSeek）保留完整语义，金融术语和俚语翻译准确。
3. **双后端自动降级** — 主翻译提供商标额用尽或被限流时，自动切换到备用后端，不中断服务。

---

## 目录结构

```
XWarden/
├── README.md                 # 英文文档
├── README_CN.md              # 中文文档（本文）
├── requirements.txt          # Python 依赖
├── .env.example              # 配置模板
├── .env                      # 你的配置（已 gitignore）
├── .gitignore
├── LICENSE
├── run.py                    # 入口文件
└── xwarden/
    ├── __init__.py
    ├── cli.py                # 主流程编排
    ├── config.py             # 环境配置加载
    ├── monitor_bb.py         # X 抓取引擎（bb-browser）
    ├── notifier.py           # 翻译 + 多渠道推送
    └── storage.py            # SHA-1 去重持久化
```

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（bb-browser 需要）
- 至少一个 LLM 提供商的 API Key（MiniMax 或 DeepSeek）
- 至少一个推送渠道：Bark iOS App、Telegram Bot 或飞书 Webhook

### 1. 安装

```bash
# Python 虚拟环境
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
.venv\Scripts\activate          # Windows

pip install -r requirements.txt

# 抓取引擎（全局安装）
npm install -g bb-browser
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key 和推送渠道
```

必填项：
- 至少一个推送渠道（`BARK_KEY` / `TG_BOT_TOKEN` / `FEISHU_WEBHOOK`）
- 至少一个 LLM API Key（`MINIMAX_API_KEY` 或 `DEEPSEEK_API_KEY`）

### 3. 首次运行

```bash
python run.py
```

bb-browser 会自动打开 Chrome 窗口。**在弹出的浏览器中手动登录 X**。之后每次运行都会复用保存的会话 Cookie（存储在 `~/.bb-browser/`）。

### 4. 设定定时任务

建议每 15 分钟运行一次：

**Windows（管理员 PowerShell）：**
```powershell
$Action = New-ScheduledTaskAction -Execute "D:\path\to\.venv\Scripts\python.exe" -Argument "D:\path\to\run.py"
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 365)
Register-ScheduledTask -TaskName "XWarden-monitor" -Action $Action -Trigger $Trigger
```

**Linux / macOS（crontab）：**
```bash
*/15 * * * * cd /path/to/XWarden && .venv/bin/python run.py >> /tmp/xwarden.log 2>&1
```

---

## 翻译

### 后端对比

| 后端 | 模型 | 费用 | 翻译质量 |
|------|------|------|---------|
| MiniMax | M2.7-highspeed | Token Plan 余额 | ✅ |
| DeepSeek | deepseek-v4-flash | ~¥0.0012/条 (按量) | ✅ |

### 切换后端

修改 `.env`：

```bash
# minimax（默认）/ deepseek
TRANSLATE_MODEL=deepseek
```

**自动降级**：主后端触达限流或额度用尽时，自动切换到备用后端，无需人工干预。

---

## 更换监控用户

修改 `.env` 中的 `XWARDEN_USER`：

```bash
XWARDEN_USER=elonmusk
```

无需其他改动，适用于任何公开 X 账号。

---

## 项目状态

本工具是针对个人使用场景开发的生产级工具，已稳定运行。并非库或框架。欢迎提交 Issue 和 PR，但项目维护遵循尽力而为的原则。

---

## 协议

MIT
