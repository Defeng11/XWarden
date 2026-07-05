"""X profile fetcher via bb-browser: use 'following' API (home timeline), filter by user.

Why 'following' adapter (not 'tweets' or DOM)?
- @aleaboreddit is hidden from X search (user confirmed)
- Profile page fails to load in bb-browser Chrome  
- 'tweets' adapter returns "User not found" (stale GraphQL query IDs)
- BUT 'following' adapter works - it queries the home timeline
- Filter by author handle to get only @aleaboreddit's tweets
- Full text returned (no "show more" truncation)

Daemon + Chrome stay running (~30MB RAM). Each fetch = 1 API call, ~5 seconds.
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


def fetch_profile(user: str, limit: int = 15) -> list[dict]:
    """Fetch latest tweets for @user via the 'following' (home timeline) API."""
    ensure_daemon()

    r = _run("site", "twitter/following", "--count", "100", "--json", timeout=30)
    if r.returncode != 0:
        print(f"[!] bb-browser: rc={r.returncode}")
        return []

    try:
        data = json.loads(r.stdout.strip())
    except json.JSONDecodeError as e:
        print(f"[!] JSON: {e}")
        return []

    all_tweets = (data or {}).get("result", {}).get("tweets") or []

    # Filter: only original tweets (not replies/retweets) from @user
    out = []
    handle_lower = user.lower()
    for t in all_tweets:
        author = (t.get("author") or "").lower()
        ttype = t.get("type", "")
        if author != handle_lower:
            continue
        if ttype not in ("tweet",):
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
    print(f"[i] {len(out)} tweets from @{user} (of {len(all_tweets)} total)")
    return out
