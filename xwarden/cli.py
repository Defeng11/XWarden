"""CLI entry point: python -m xwarden (or python run.py)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .config import Config
from .monitor_bb import (
    fetch_profile,
    _get_managed_chrome_pids,
    _kill_chrome_pids,
    _get_bb_browser_daemon_pids,
    _kill_bb_browser_daemon_pids,
)
from .notifier import make_notifiers, notify_all
from .storage import Storage

# 日志放到项目目录下 logs/ 子目录, 跟项目走 (不污染 home).
# .gitignore 已排除 logs/, 不会上传到 GitHub.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = str(_PROJECT_ROOT / "logs" / "xwarden.log")


class _Tee:
    """Tee stdout: write to both console and log file."""

    def __init__(self, *files):
        self.files = files

    def write(self, data):
        for f in self.files:
            f.write(data)

    def flush(self):
        for f in self.files:
            f.flush()

    @property
    def encoding(self):
        # Forward to the first wrapped stream (typically the real console)
        # so callers like `sys.stdout.encoding` still work after the swap.
        first = self.files[0] if self.files else None
        return getattr(first, "encoding", None) or "utf-8"


def main() -> int:
    # ── Logging setup ───────────────────────────────────────────────────
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    log_file = open(LOG_PATH, "w", encoding="utf-8")
    log_file.write(f"=== XWarden run at {__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
    log_file.flush()
    sys.stdout = _Tee(sys.__stdout__, log_file)

    try:
        return _run()
    finally:
        sys.stdout = sys.__stdout__
        log_file.close()


def _run() -> int:
    cfg = Config.load()

    if not cfg.active_channels:
        print("[!] No notify channel configured.")
        print("    Copy .env.example to .env and fill in BARK_KEY (iOS),")
        print("    TG_BOT_TOKEN (Telegram), or FEISHU_WEBHOOK (Feishu/Lark).")
        return 1

    print(f"[i] XWarden: watching @{cfg.user}")

    try:
        try:
            tweets = fetch_profile(cfg.user, cfg.limit)
        except Exception as e:
            print(f"[!] Fetch failed: {e}")
            return 2

        storage = Storage()
        new = [t for t in tweets if storage.is_new(t)]

        if not new:
            print(f"[i] No new tweets (scanned {len(tweets)}, all known).")
            return 0

        print(f"[!] {len(new)} new tweet(s)")
        notifiers = make_notifiers(cfg)
        texts = [t["text"] for t in new]
        urls = [t["url"] for t in new]
        notify_all(notifiers, cfg=cfg, raw_texts=texts, urls=urls)

        storage.add_many(new)
        storage.save()
        return 0
    finally:
        # 干掉 XWarden 启动的 managed Chrome + bb-browser daemon,
        # 不影响用户自己的 Chrome (不同 profile).
        # 连 daemon 一起杀是防止 daemon CDP 断开后成僵尸、在 Windows
        # 上撞 iphlpsvc 占用的 19824 端口 (bb-browser #217).
        chrome_pids = _get_managed_chrome_pids()
        if chrome_pids:
            print(f"[i] XWarden-managed Chrome PIDs (will kill): {sorted(chrome_pids)}")
            _kill_chrome_pids(chrome_pids)

        daemon_pids = _get_bb_browser_daemon_pids()
        if daemon_pids:
            print(f"[i] bb-browser daemon PIDs (will kill): {sorted(daemon_pids)}")
            _kill_bb_browser_daemon_pids(daemon_pids)


if __name__ == "__main__":
    sys.exit(main())
