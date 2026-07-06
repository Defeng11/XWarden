"""X profile fetcher via bb-browser: fetch user's tweets directly.

Uses bb-browser's twitter/tweets adapter, which returns the user's own
timeline filtering from the home feed. No filtering needed.
"""

from __future__ import annotations
import json, os, re, shutil, subprocess, sys, time

BB = os.getenv("BB_BROWSER_BIN") or shutil.which("bb-browser") or r"D:\npm\bb-browser.cmd"
DAEMON_TIMEOUT = 20
BB_HOME = os.path.expanduser(os.getenv("BB_BROWSER_HOME", "~/.bb-browser"))
MANAGED_USER_DATA_DIR = os.path.join(BB_HOME, "browser", "user-data")
DAEMON_JSON = os.path.join(BB_HOME, "daemon.json")
DAEMON_PORT = int(os.getenv("BB_BROWSER_DAEMON_PORT", "19824"))
TWEET_ID_RE = re.compile(r"/status/(\d+)")
_TCO_URL_RE = re.compile(r"\s*https?://t\.co/\w+\s*")
_TRUNCATION_HINTS = (
    "显示更多", "显示这条帖子", "Show this thread", "Show more",
    "Read more", "Continue reading",
)


def _run(*a, timeout=30):
    return subprocess.run(
        [BB, *a],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _console_safe(text: str) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _powershell(script: str, timeout=10):
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )


def _start_daemon() -> subprocess.CompletedProcess:
    r = _run("daemon", "start", timeout=15)
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip()
        if detail:
            print(_console_safe(f"[!] bb-browser daemon start failed: {detail}"))
    return r


def _daemon_json_exists() -> bool:
    return os.path.exists(DAEMON_JSON)


def _daemon_port_is_listening() -> bool:
    r = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=10,
    )
    return any(f":{DAEMON_PORT}" in line and "LISTENING" in line for line in r.stdout.splitlines())


def _kill_stale_daemon_port_owner():
    """Kill a stale bb-browser daemon process that still owns the daemon port."""
    r = subprocess.run(
        ["netstat", "-ano"],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=10,
    )
    pids: set[str] = set()
    for line in r.stdout.splitlines():
        if f":{DAEMON_PORT}" not in line or "LISTENING" not in line:
            continue
        parts = re.split(r"\s+", line.strip())
        if parts:
            pids.add(parts[-1])

    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", pid, "/F"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
        )


def _kill_project_chrome():
    """Kill only Chrome instances launched with bb-browser's managed profile."""
    profile = MANAGED_USER_DATA_DIR.replace("'", "''")
    script = f"""
$profile = '{profile}'
Get-CimInstance Win32_Process -Filter "name = 'chrome.exe'" |
    Where-Object {{ $_.CommandLine -and $_.CommandLine.Contains($profile) }} |
    ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}
"""
    _powershell(script, timeout=10)


def _wait_daemon_ready(timeout: int) -> bool:
    """轮询 daemon status 直到 CDP connected=yes 或超时. 返回 True 表示 ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = _run("daemon", "status", timeout=5)
        if "CDP connected" in r.stdout and "yes" in r.stdout:
            return True
        time.sleep(1)
    return False


def ensure_daemon():
    """Start daemon if not running; block until CDP connected.

    Auto-recovers from zombie state: 如果 daemon start 卡死, 清理残留的
    daemon 端口占用和 bb-browser 专用 Chrome profile, 再 retry 一次.
    """
    r = _run("daemon", "status", timeout=5)
    if "CDP connected" in r.stdout and "yes" in r.stdout and _daemon_json_exists():
        return

    if not _daemon_json_exists() and _daemon_port_is_listening():
        print("[!] Stale bb-browser daemon port without daemon.json, cleaning up...")
        _kill_stale_daemon_port_owner()
        _kill_project_chrome()
        time.sleep(3)

    # 第一次尝试
    _start_daemon()
    if _wait_daemon_ready(DAEMON_TIMEOUT):
        return

    # 卡住了 → 清掉残留 daemon 端口和项目拉的 Chrome → 重试
    print("[!] Daemon stuck, cleaning up stale bb-browser daemon and Chrome...")
    _kill_stale_daemon_port_owner()
    _kill_project_chrome()
    time.sleep(3)
    _start_daemon()
    if _wait_daemon_ready(DAEMON_TIMEOUT):
        return

    raise RuntimeError("bb-browser daemon failed to start after cleanup retry")


def _tweet_id(url: str) -> str | None:
    match = TWEET_ID_RE.search(url or "")
    return match.group(1) if match else None


def _looks_truncated(tweet: dict) -> bool:
    """判断 timeline 文本是否可能被截. 只对疑似被截的才调 thread API 补全,
    避免 X 限流 (HTTP 429).

    判断原则: 普通推文 (< 270 字) timeline 已给完整, 不调 detail.
    只有疑似折叠/截断的特征才调.
    """
    text = (tweet.get("text") or "").strip()
    if not text:
        return False
    # 折叠提示语 (X 多语言) — 任何长度都算折叠
    for hint in _TRUNCATION_HINTS:
        if hint in text:
            return True
    # 截断省略号: 只在末尾 (中点或三点), 普通英文 `...` 不会出现在末尾
    if text.endswith("…") or text.endswith("..."):
        return True
    # 典型折叠模式: "... https://t.co/xxx" + 长度 >= 200 (折叠推文总长接近 280)
    # 普通 95 字推文带 video 也匹配 "..." + t.co, 但字数短, 排除
    if len(text) >= 200 and (re.search(r"\.\.\.\s+https?://t\.co/", text) or re.search(r"…\s+https?://t\.co/", text)):
        return True
    # 长度 >= 270 才怀疑折叠 (普通推文 < 280, 折叠推文 = 280)
    # 270+ 字 + 末尾 t.co = 疑似 note_tweet 折叠 + media 截断
    if len(text) >= 270 and _TCO_URL_RE.search(text[-40:]):
        return True
    return False


def _strip_tco_links(text: str) -> str:
    """去掉推文中的 t.co 短链 (手机上点不开, 是噪音). 保留推文主 URL (在 url 字段)."""
    cleaned = _TCO_URL_RE.sub(" ", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" \t\n,;:.")
    return cleaned


def _detail_text(tweet: dict) -> str:
    """Fetch full tweet text from TweetDetail when timeline text is truncated."""
    tweet_id = _tweet_id(tweet.get("url", ""))
    if not tweet_id:
        return tweet.get("text", "")

    r = _run("site", "twitter/thread", tweet_id, "--json", timeout=30)
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip()
        if detail:
            print(_console_safe(f"[!] bb-browser detail fetch failed for {tweet_id}: {detail}"))
        return tweet.get("text", "")

    try:
        data = json.loads(r.stdout.strip())
    except json.JSONDecodeError as e:
        print(f"[!] TweetDetail JSON: {e}")
        return tweet.get("text", "")

    tweets = (data or {}).get("result", {}).get("tweets") or []
    for item in tweets:
        if str(item.get("id")) == tweet_id:
            text = (item.get("text") or "").strip()
            if len(text) > len(tweet.get("text", "")):
                return text
            return tweet.get("text", "")

    return tweet.get("text", "")


def _hydrate_full_text(tweet: dict) -> dict:
    # 智能判断: timeline 已给完整文本 (note_tweet) 时不调 detail, 避免 429
    if not _looks_truncated(tweet):
        return tweet
    text = _detail_text(tweet)
    if text and text != tweet.get("text"):
        print(f"[i] Hydrated full text for {tweet.get('url', '')} ({len(tweet.get('text', ''))} -> {len(text)} chars)")
        return {**tweet, "text": text}
    return tweet


def fetch_profile(user: str, limit: int = 5) -> list[dict]:
    """Fetch latest original tweets for @user via bb-browser's tweets API."""
    ensure_daemon()

    r = _run("site", "twitter/tweets", "--username", user, "--count", str(max(limit * 2, 20)), "--json", timeout=30)
    if r.returncode != 0:
        print(f"[!] bb-browser: rc={r.returncode}")
        detail = (r.stderr or r.stdout or "").strip()
        if detail:
            print(_console_safe(f"[!] bb-browser detail: {detail}"))
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
    out = [_hydrate_full_text(t) for t in out]
    # 去掉 t.co 短链 (手机端噪音)
    for t in out:
        if t.get("text"):
            t["text"] = _strip_tco_links(t["text"])
    print(f"[i] {len(out)} original tweets from @{user}")
    return out
