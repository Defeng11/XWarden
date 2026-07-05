"""CLI entry point: python -m xwarden (or python run.py)."""

from __future__ import annotations

import sys

from .config import Config
from .monitor_bb import fetch_profile
from .notifier import make_notifiers, notify_all
from .storage import Storage


def main() -> int:
    cfg = Config.load()

    if not cfg.active_channels:
        print("[!] No notify channel configured.")
        print("    Copy .env.example to .env and fill in BARK_KEY (iOS),")
        print("    TG_BOT_TOKEN (Telegram), or FEISHU_WEBHOOK (Feishu/Lark).")
        return 1

    print(f"[i] XWarden: watching @{cfg.user}")

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


if __name__ == "__main__":
    sys.exit(main())
