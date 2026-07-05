"""XWarden — watch an X/Twitter account, LLM translate, push to phone.

Architecture:
  bb-browser daemon → Twitter/following API → LLM translation → Bark/TG/Feishu

Translation backends (configurable in .env):
  - minimax (default) — MiniMax-M2.7-highspeed (Token Plan)
  - deepseek — deepseek-v4-flash (pay-as-you-go)
  Auto-fallback if primary provider is rate-limited / quota exhausted.
"""

__version__ = "0.2.0"
