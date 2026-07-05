"""Storage: persist seen-tweet signatures to detect new content.

Uses SHA-1 of tweet text. Survives script restarts.

Path is locked to ~/.xwarden/tweets_seen.json so the same state survives
regardless of cwd (important when invoked from Task Scheduler).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Iterable

DEFAULT_PATH = os.path.expanduser("~/.xwarden/tweets_seen.json")


def _sig(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


class Storage:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self.seen: set[str] = (
            set(json.load(open(path, encoding="utf-8"))) if os.path.exists(path) else set()
        )

    def is_new(self, tweet: dict) -> bool:
        return _sig(tweet["text"]) not in self.seen

    def add_many(self, tweets: Iterable[dict]) -> None:
        for t in tweets:
            self.seen.add(_sig(t["text"]))

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        json.dump(sorted(self.seen), open(self.path, "w", encoding="utf-8"), indent=2)
