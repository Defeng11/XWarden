"""X profile fetcher via bb-browser: fetch user's tweets directly.

Uses bb-browser's twitter/tweets adapter, which returns the user's own
timeline filtering from the home feed. No filtering needed.
"""

from __future__ import annotations
import json, subprocess, time

BB = r"D:\npm\bb-browser.cmd"
DAEMON_TIMEOUT = 20


def _run(*a, timeout=30):
    return subprocess.run([BB, *a], capture_output=True, text=True, errors="replace", timeout=timeout)


def ensure_daemon():
    """Start daemon if not running; block until CDP connected."""
    r = _run("daemon", "status", timeout=5)
    if "CDP connected" in r.stdout and "yes" in r.stdout:
        return
    _run("daemon", "start", timeout=10)
    deadline = time.time() + DAEMON_TIMEOUT
    while time.time() < deadline:
        r = _run("daemon", "status", timeout=5)
        if "CDP connected" in r.stdout and "yes" in r.stdout:
            return
        time.sleep(1)


def fetch_profile(user: str, limit: int = 5) -> list[dict]:
    """Fetch latest original tweets for @user via bb-browser's tweets API."""
    ensure_daemon()

    r = _run("site", "twitter/tweets", "--username", user, "--count", str(max(limit * 2, 20)), "--json", timeout=30)
    if r.returncode != 0:
        print(f"[!] bb-browser: rc={r.returncode}")
        return []

    try:
        data = json.loads(r.stdout.strip())
    except json.JSONDecodeError as e:
        print(f"[!] JSON: {e}")
        return []

    all_tweets = (data or {}).get("result", {}).get("tweets") or []
    count = data.get("result", {}).get("count", 0)
    print(f"[i] {count} tweets from @{user} total")

    out = []
    for t in all_tweets:
        # Only original tweets
        if t.get("type", "") not in ("tweet",):
            continue

        text = (t.get("text") or "").strip()
        if not text:
            continue

        out.append({
            "text": text,
            "url": t.get("url", ""),
            "time": t.get("created_at", ""),
        })

    out = out[:limit]
    print(f"[i] {len(out)} original tweets from @{user}")
    return out
