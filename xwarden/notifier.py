"""Notification: batch all new tweets into 1 combined push (split if over limit).

Translation backends (LLM):
  - minimax (default)  → MiniMax-M2.7-highspeed (Token Plan, no extra cost)
  - deepseek           → deepseek-v4-flash (¥0.0012/条, 按量计费)

Switch by changing TRANSLATE_MODEL in .env.
"""

from __future__ import annotations

from typing import Sequence
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

from .config import Config

_SESSION = requests.Session()
_SESSION.mount("https://", HTTPAdapter(max_retries=1, pool_connections=4, pool_maxsize=8))
_TIMEOUT = 30

# Bark GET URL path: key/title/body?group=... URL length ~2000 max.
# Safe limit: 600 bytes for the body segment after encoding + overhead.
BARK_URL_MAX = 600


# ── LLM Translation ──────────────────────────────────────────────────────────

_PROVIDERS = {
    # MiniMax M2.7 uses OpenAI-compatible /v1/chat/completions
    "minimax": {
        "url": "https://api.minimaxi.com/v1/chat/completions",
    },
    "deepseek": {
        "url": "https://api.deepseek.com/v1/chat/completions",
    },
}

# Cache: one translator session per target language
_LLM_CACHE: dict[str, "LLMTranslator"] = {}


class LLMTranslator:
    """Translate English → target language via LLM chat completion.

    Both MiniMax and DeepSeek use OpenAI-compatible request/response format.
    """

    def __init__(self, target_lang: str, api_key: str, base_url: str, model: str, provider: str):
        self.target_lang = target_lang
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.provider = provider
        self._session = _SESSION

    def translate(self, text: str) -> str:
        # Build system prompt
        lang_map = {
            "zh-CN": "Simplified Chinese",
            "zh-TW": "Traditional Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "en": "English",
        }
        lang_name = lang_map.get(self.target_lang, self.target_lang)

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are a professional translator. Translate the following English text "
                        f"to {lang_name}. Observe these rules:\n"
                        f"1. Translate ONLY what is written — do NOT add details, names, or facts not present in the source.\n"
                        f"2. Preserve financial/technical jargon, tickers ($TSLA, etc.), numbers, percentages, and URLs exactly as-is.\n"
                        f"3. If the source text contains garbled/unreadable characters, translate the readable parts and mark unreadable parts as [原文乱码].\n"
                        f"4. Never invent company names, contract details, or specific figures.\n"
                        f"5. Return ONLY the translation, no explanations, no greetings, no markdown formatting."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        resp = self._session.post(
            self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=_TIMEOUT,
        )

        # Check MiniMax business status code BEFORE raise_for_status
        # (some errors like 2056 quota come with HTTP 200 but choices=null)
        data = resp.json()
        if "base_resp" in data:
            br = data["base_resp"]
            sc = br.get("status_code", 0)
            if sc == 2056:
                raise RuntimeError(f"quota exhausted: {br.get('status_msg', '')}")
            if sc == 2058 or sc == 2013:
                raise RuntimeError(f"rate limit / server error (code {sc})")
        # Also check for 429 HTTP status
        if resp.status_code == 429:
            raise RuntimeError(f"rate limit (HTTP 429)")
        resp.raise_for_status()

        # Both providers return OpenAI-compatible response
        content = data["choices"][0]["message"]["content"].strip()
        return content


def _make_translator(cfg: Config) -> tuple[LLMTranslator | None, LLMTranslator | None]:
    """Create (primary, fallback) LLM translators based on config.

    Returns (translator, fallback). If the primary (e.g. MiniMax) hits a quota
    error, ``_maybe_translate`` will automatically retry with fallback.
    """
    def _build(provider: str) -> LLMTranslator | None:
        if provider not in _PROVIDERS:
            return None
        info = _PROVIDERS[provider]
        if provider == "minimax":
            api_key = cfg.minimax_api_key
            model = cfg.minimax_model
        elif provider == "deepseek":
            api_key = cfg.deepseek_api_key
            model = cfg.deepseek_model
        else:
            return None
        if not api_key:
            return None
        cache_key = f"{provider}/{cfg.translate_target}"
        if cache_key not in _LLM_CACHE:
            _LLM_CACHE[cache_key] = LLMTranslator(
                target_lang=cfg.translate_target,
                api_key=api_key,
                base_url=info["url"],
                model=model,
                provider=provider,
            )
        return _LLM_CACHE[cache_key]

    if not cfg.translate_enabled or not cfg.translate_target:
        return None, None

    primary_provider = cfg.translate_model
    if primary_provider not in _PROVIDERS:
        print(f"  [!] Unknown translate_model '{primary_provider}', defaulting to minimax")
        primary_provider = "minimax"

    primary = _build(primary_provider)

    # Build fallback from the other provider
    fallback_provider = "deepseek" if primary_provider == "minimax" else "minimax"
    fallback = _build(fallback_provider)

    if primary:
        print(f"  [i] Translation: {primary.provider} ({primary.model}) → {cfg.translate_target}")
    if fallback and primary_provider != "deepseek":
        print(f"  [i] Fallback: {fallback.provider} ({fallback.model}) (auto if quota exhausted)")

    return primary, fallback


def _maybe_translate(text: str, translator: LLMTranslator | None, fallback: LLMTranslator | None = None) -> str:
    """Translate text if a translator is available, otherwise return as-is.

    If the primary translator hits a quota error, tries ``fallback``.
    """
    if translator is None:
        return text

    def _do_translate(t: LLMTranslator) -> str:
        if len(text) <= 4000:
            return t.translate(text)
        chunks: list[str] = []
        buf = ""
        for line in text.split("\n"):
            if buf and len(buf) + len(line) + 1 > 3500:
                chunks.append(buf)
                buf = line
            else:
                buf = buf + ("\n" if buf else "") + line
        if buf:
            chunks.append(buf)
        return "\n\n".join(t.translate(c) for c in chunks)

    try:
        return _do_translate(translator)
    except Exception as e:
        err_msg = str(e).lower()
        # Fallback triggers: quota exhausted, rate limited, 429, 2056
        should_fallback = any(kw in err_msg for kw in ["quota", "rate limit", "429", "too many", "2056"])
        if fallback is not None and should_fallback:
            print(f"  [!] {translator.provider} quota/rate-limited, falling back to {fallback.provider}")
            try:
                return _do_translate(fallback)
            except Exception as e2:
                print(f"  [!] Fallback also failed: {e2}")
                return f"{text}\n\n[翻译失败: {e2}]"
        print(f"  [!] Translation failed ({translator.provider}): {e}")
        return f"{text}\n\n[翻译失败: {e}]"


# ── Notification logic (unchanged structure) ─────────────────────────────────


def _title_for(cfg, batch_total: int, batch_index: int, batch_count: int) -> str:
    """Fixed title: Serenity@user"""
    return f"Serenity@{cfg.user}"


def _compact_entry(text: str, url: str, translated: str, show_original: bool = False) -> str:
    """One tweet entry: translated text + link (no original in batch mode)."""
    t = translated if translated else text
    lines = [t]
    if show_original and translated and translated != text:
        lines.append(f"[原文摘要] {text[:200]}")
    if url:
        lines.append(url)
    return "\n".join(lines)


def _chunk_entries(entries: list[str], max_bytes: int) -> list[list[str]]:
    """Split entries into chunks so each chunk body ≤ max_bytes (UTF-8)."""
    if not entries:
        return []
    chunks: list[list[str]] = []
    cur: list[str] = []
    cur_bytes = 0
    sep = "\n\n" + ("─" * 20) + "\n\n"
    for e in entries:
        e_b = len(e.encode("utf-8")) + (len(sep.encode("utf-8")) if cur else 0)
        if cur and cur_bytes + e_b > max_bytes and len(cur) < len(entries):
            chunks.append(cur)
            cur = []
            cur_bytes = 0
        cur.append(e)
        cur_bytes += e_b
    if cur:
        chunks.append(cur)
    return chunks


_BARK_SEP = "\n\n---\n\n"


def _build_bark_bodies(texts: list[str], urls: list[str], trans: list[str]) -> list[str]:
    """Build Bark body chunks — only translation text + link, no numbering, no original."""
    URL_MAX = 3500
    entries = []
    for rt, tr, url in zip(texts, trans, urls):
        body = (tr if tr else rt)[:300]
        entries.append(f"{body}\n{url}")

    def _url_b(body: str, title: str = "x") -> int:
        q = "?group=m&level=a&icon=i"
        return len(f"https://api.day.app/k/{quote(title)}/{quote(body)}{q}".encode("utf-8"))

    full = _BARK_SEP.join(entries)
    if _url_b(full) <= URL_MAX:
        return [full]
    result, cur = [], []
    for e in entries:
        test = _BARK_SEP.join(cur + [e]) if cur else e
        if cur and _url_b(test) > URL_MAX:
            result.append(_BARK_SEP.join(cur))
            cur = [e]
        else:
            cur.append(e)
    if cur:
        result.append(_BARK_SEP.join(cur))
    return result


class Telegram:
    def __init__(self, token: str, chat: str):
        self.token = token
        self.chat = chat

    def send_batch(self, *, cfg, raw_texts: Sequence[str], urls: Sequence[str], translator: LLMTranslator | None, fallback: LLMTranslator | None = None) -> bool:
        ok = True
        for rt, url in zip(raw_texts, urls):
            translated = _maybe_translate(rt, translator, fallback)
            msg = f"🐦 @{cfg.user}\n\n{_compact_entry(rt, url, translated)}"
            r = _SESSION.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True},
                timeout=_TIMEOUT,
            )
            if not r.ok:
                ok = False
        return ok


class Bark:
    """Bark push via GET URL path (POST JSON body doesn't display content on iOS)."""

    def __init__(self, key: str):
        self.key = key

    def send_batch(self, *, cfg, raw_texts: Sequence[str], urls: Sequence[str], translator: LLMTranslator | None, fallback: LLMTranslator | None = None) -> bool:
        translated = [
            _maybe_translate(rt, translator, fallback) for rt in raw_texts
        ]
        bodies = _build_bark_bodies(raw_texts, urls, translated)
        ok = True
        for idx, body in enumerate(bodies):
            title = _title_for(cfg, len(raw_texts), idx, len(bodies))
            enc_title = quote(title, safe="")
            enc_body = quote(body, safe="")
            icon = quote("https://n.uguu.se/QzdgYEYe.jpg", safe="")
            url = (
                f"https://api.day.app/{self.key}/{enc_title}/{enc_body}"
                f"?group=Serenity@{cfg.user}&level=active&icon={icon}"
            )
            url_len = len(url.encode("utf-8"))
            r = _SESSION.get(url, timeout=_TIMEOUT)
            if not r.ok:
                print(f"  Bark chunk {idx+1}/{len(bodies)}: HTTP {r.status_code} (url {url_len}B)")
                ok = False
            else:
                print(f"  Bark chunk {idx+1}/{len(bodies)}: √ ({url_len}B url)")
        return ok


class Feishu:
    def __init__(self, webhook: str):
        self.webhook = webhook

    def send_batch(self, *, cfg, raw_texts: Sequence[str], urls: Sequence[str], translator: LLMTranslator | None, fallback: LLMTranslator | None = None) -> bool:
        ok = True
        for rt, url in zip(raw_texts, urls):
            translated = _maybe_translate(rt, translator, fallback)
            msg = f"🐦 @{cfg.user}\n\n{_compact_entry(rt, url, translated)}"
            r = _SESSION.post(self.webhook, json={"msg_type": "text", "content": {"text": msg}}, timeout=_TIMEOUT)
            if not r.ok:
                ok = False
        return ok


# ── Public API ───────────────────────────────────────────────────────────────


def make_notifiers(cfg) -> list:
    notifiers = []
    if cfg.tg_token and cfg.tg_chat:
        notifiers.append(Telegram(cfg.tg_token, cfg.tg_chat))
    if cfg.bark_key:
        notifiers.append(Bark(cfg.bark_key))
    if cfg.feishu_webhook:
        notifiers.append(Feishu(cfg.feishu_webhook))
    return notifiers


def notify_all(notifiers, *, cfg: Config, raw_texts: Sequence[str], urls: Sequence[str]) -> bool:
    """Send ALL new tweets as a combined batch (or split if over limit)."""
    if not notifiers or not raw_texts:
        return False

    translator, fallback = _make_translator(cfg)

    any_ok = False
    for n in notifiers:
        name = type(n).__name__
        try:
            ok = n.send_batch(cfg=cfg, raw_texts=raw_texts, urls=urls, translator=translator, fallback=fallback)
            print(f"  [{'OK' if ok else 'FAIL'}] {name} ({len(raw_texts)}条)")
            any_ok = any_ok or ok
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
    return any_ok
