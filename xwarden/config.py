"""Load configuration from .env."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    user: str
    limit: int
    tg_token: str | None
    tg_chat: str | None
    bark_key: str | None
    feishu_webhook: str | None
    # Translation
    translate_enabled: bool
    translate_target: str | None
    # LLM translation backend: "minimax" (default) or "deepseek"
    translate_model: str
    # MiniMax
    minimax_api_key: str | None
    minimax_model: str
    # DeepSeek
    deepseek_api_key: str | None
    deepseek_model: str

    @classmethod
    def load(cls) -> "Config":
        enabled = os.getenv("TRANSLATE_ENABLED", "true").strip().lower()
        target = os.getenv("TRANSLATE_TARGET", "zh-CN").strip() or None
        return cls(
            user=os.getenv("XWARDEN_USER", "aleabitoreddit").strip().lstrip("@"),
            limit=int(os.getenv("XWARDEN_LIMIT", "5")),
            tg_token=os.getenv("TG_BOT_TOKEN") or None,
            tg_chat=os.getenv("TG_CHAT_ID") or None,
            bark_key=os.getenv("BARK_KEY") or None,
            feishu_webhook=os.getenv("FEISHU_WEBHOOK") or None,
            translate_enabled=enabled in ("1", "true", "yes", "on"),
            translate_target=target,
            translate_model=(os.getenv("TRANSLATE_MODEL", "minimax").strip().lower()),
            minimax_api_key=os.getenv("MINIMAX_API_KEY") or None,
            minimax_model=os.getenv("MINIMAX_MODEL", "MiniMax-M2.7-highspeed"),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        )

    @property
    def active_channels(self) -> list[str]:
        chans = []
        if self.tg_token and self.tg_chat:
            chans.append("telegram")
        if self.bark_key:
            chans.append("bark")
        if self.feishu_webhook:
            chans.append("feishu")
        return chans
