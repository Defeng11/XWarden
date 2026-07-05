<p align="right">
  <a href="README.md">🇬🇧 English</a>
  |
  <a href="README.zh-CN.md">🇨🇳 中文</a>
</p>

# XWarden 🦞

> Watch an X/Twitter account — auto LLM translate — push to your phone.

**XWarden** is a lightweight, self-hosted tool that watches a specified X (Twitter) user's new tweets, translates them from English to your language via LLM, and pushes them to your device through Bark (iOS), Telegram, or Feishu/Lark. Each run is one-shot: fetch, translate, notify, exit. Designed for scheduled execution (cron / Task Scheduler).

---

## How It Works

```
[X/Twitter] ──bb-browser──→ [User Tweets API]
       │                          │
       │                   ┌──────┘
       │                   ▼
       │          [Dedup: SHA-1]
       │                   │
       │            (new tweets?)
       │                   │
       │                   ▼
       │          [LLM Translation]
       │          minimax / deepseek
       │                   │
       │                   ▼
       │     ┌─────────────────────┐
       │     Bark  Telegram  Feishu
       ▼     └─────────────────────┘
    Your Phone
```

**Key decisions:**

1. **bb-browser over Playwright/nodriver** — X blocks headless browsers with Cloudflare. `bb-browser` uses a real Chrome via CDP and bypasses anti-bot detection.
2. **LLM translation over Google Translate scraper** — Google's free scraper loses context when splitting long text into chunks. LLM (MiniMax / DeepSeek) keeps full context, handles financial jargon and slang correctly.
3. **Dual-backend auto-fallback** — If the primary translation provider hits rate limits or quota exhaustion, the secondary provider takes over automatically.

---

## Directory Structure

```
XWarden/
├── README.md                 # This file (English)
├── README_CN.md              # Chinese version
├── requirements.txt          # Python dependencies
├── .env.example              # Configuration template
├── .env                      # Your config (gitignored)
├── .gitignore
├── LICENSE
├── run.py                    # Entry point
└── xwarden/
    ├── __init__.py
    ├── cli.py                # Main orchestration
    ├── config.py             # Environment config loader
    ├── monitor_bb.py         # X fetch via bb-browser
    ├── notifier.py           # Translation + notification
    └── storage.py            # SHA-1 dedup persistence
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for bb-browser)
- An API key for at least one supported LLM provider (MiniMax or DeepSeek)
- A notification channel: Bark app (iOS), Telegram Bot, or Feishu webhook

### 1. Install

```bash
# Python environment
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
.venv\Scripts\activate          # Windows

pip install -r requirements.txt

# Fetch engine (global)
npm install -g bb-browser
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your keys and preferences
```

Required fields:
- At least one notification channel (`BARK_KEY` / `TG_BOT_TOKEN` / `FEISHU_WEBHOOK`)
- At least one LLM API key (`MINIMAX_API_KEY` or `DEEPSEEK_API_KEY`)

### 3. First Run

```bash
python run.py
```

bb-browser will launch Chrome. **Log into X manually** when the browser window appears. Subsequent runs use the saved session cookie (stored in `~/.bb-browser/`).

### 4. Schedule

Run every 15 minutes:

**Windows (PowerShell as Admin):**
```powershell
$Action = New-ScheduledTaskAction -Execute "D:\path\to\.venv\Scripts\python.exe" -Argument "D:\path\to\run.py"
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 365)
Register-ScheduledTask -TaskName "XWarden-monitor" -Action $Action -Trigger $Trigger
```

**Linux / macOS (crontab):**
```bash
*/15 * * * * cd /path/to/XWarden && .venv/bin/python run.py >> /tmp/xwarden.log 2>&1
```

---

## Translation

### Backend Comparison

| Provider | Model | Cost | Quality |
|----------|-------|------|---------|
| MiniMax | M2.7-highspeed | Token Plan subscription | ✅ |
| DeepSeek | deepseek-v4-flash | ~¥0.0012/tweet (pay-as-you-go) | ✅ |

### Switching Backends

Edit `.env`:

```bash
# minimax (default) / deepseek
TRANSLATE_MODEL=deepseek
```

**Auto-fallback**: When the primary provider hits rate limits or quota exhaustion, the system automatically falls back to the secondary provider. No interruption.

---

## Changing the Target User

Edit `XWARDEN_USER` in `.env`:

```bash
XWARDEN_USER=elonmusk
```

No other changes needed. The system works for any public X account.

---

## Project Status

This is a personal tool that works reliably for its intended use case. It is not a library or framework — contributions are welcome but the project is maintained on a best-effort basis.

---

## License

MIT
