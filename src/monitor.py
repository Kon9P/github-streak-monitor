import os
import sys
import json
import time
import traceback
from datetime import datetime, timezone, date
from typing import Any, Dict, Optional, Tuple, List

import requests
from dotenv import load_dotenv

import random

# ---------- Meme message lists (short; under 2 lines) ----------

def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many

# For when Kong MISSES 1+ days (angry, spicy, slightly guilty-inducing)
MESSAGES_MISSED = [
    "KONG. {d} {_dunit} off? Hell no—get back in the repo. 😤🔥",
    "You ghosted your streak for {d} {_dunit}? Damn. Commit now. 💀",
    "{d} {_dunit} gone and you’re acting chill? Get your ass back in. 😡",
    "Bruh. {d} {_dunit} MIA? Push or I’ll lose my shit. 🫠",
    "Your streak called. It’s crying after {d} {_dunit}. Fix it. 😭",
    "Damn. {d} {_dunit} vanished like your resolve. Open the editor. 🧯",
    "{d} {_dunit} off? The repo’s not a museum, chief. Move. 🏃‍♂️",
    "Congrats, you speedran disappointment in {d} {_dunit}. Commit. 🫵",
    "Shit, {d} {_dunit} already? Don’t make me ping you again. 🔔",
    "You let the flame die for {d} {_dunit}. Relight it, pyromaniac. 🔥",
    "KONG, quit ghosting. {d} {_dunit} break is not ‘balance’. 😤",
    "Damn it. {d} {_dunit} gap. Push code, sinner. ⛓️",
    "You skipped {d} {_dunit}. Even your README is judging you. 👀",
    "Hell no. {d} {_dunit} blackout? Git back in there. 🪓",
]

# For when Kong MISSES 0 days (cocky, flirty, teasing motivation)
MESSAGES_ACTIVE = [
    "Still hot, still shipping. Don’t you dare cool off. 😎🔥",
    "Commit king behavior. Keep flexing or else. 💅",
    "You’re on fire—don’t let it be a campfire, keep it a blaze. 🔥",
    "Look at you, shipping like a menace. Don’t stop. 😼",
    "Cocky and consistent—just how I like it. Keep pushing. 😉",
    "Streak alive and smug. Stay dangerous. 😏⚡",
    "Badass mode: ON. Keep the PRs coming. 🚀",
    "No misses. No mercy. Keep bullying those bugs. 🥊",
    "Chef’s kiss commits—serve another course. 👨‍🍳",
    "Top tier menace. Keep the streak arrogant. 🏆",
]

def pick_meme(days_missed: int) -> str:
    if days_missed > 0:
        dunit = _plural(days_missed, "day", "days")
        msg = random.choice(MESSAGES_MISSED)
        return msg.format(d=days_missed, _dunit=dunit)
    else:
        return random.choice(MESSAGES_ACTIVE)


# ---- Utilities ----

def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    print(f"[{ts}] {msg}", flush=True)

def env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v is not None and v != "" else default

def iso_to_date(d: str) -> date:
    # Accept YYYY-MM-DD exactly.
    return date.fromisoformat(d)

def today_utc() -> date:
    return datetime.now(timezone.utc).date()

def get_http_timeout() -> int:
    try:
        return int(env("HTTP_TIMEOUT_SECONDS", "15"))
    except Exception:
        return 15

# ---- Core fetching & posting with retry ----

def fetch_with_retry(url: str, timeout: int) -> Any:
    """
    Fetch JSON from the streak API with 1 retry after 5 minutes on failure.
    Returns parsed JSON or raises after final attempt.
    """
    attempts = 0
    last_exc = None
    while attempts < 2:
        attempts += 1
        try:
            log(f"Fetching streak stats (attempt {attempts}) …")
            r = requests.get(url, timeout=timeout)
            ok = 200 <= r.status_code < 300
            # Validation line (1–2 lines)
            log(f"Validation: streak API HTTP {r.status_code}; {'OK' if ok else 'NOT OK'}")
            if not ok:
                raise RuntimeError(f"Streak API returned HTTP {r.status_code}: {r.text[:300]}")
            try:
                return r.json()
            except Exception as e:
                raise RuntimeError(f"Invalid JSON from streak API: {e}") from e
        except Exception as e:
            last_exc = e
            log(f"Error on fetch: {e.__class__.__name__}: {e}")
            if attempts < 2:
                log("Retrying in 5 minutes …")
                time.sleep(300)
    assert last_exc is not None
    raise last_exc

def post_discord_with_retry(webhook_url: str, payload: Dict[str, Any], timeout: int) -> None:
    """
    Post to Discord with 1 retry after 5 minutes on failure.
    """
    attempts = 0
    last_exc = None
    while attempts < 2:
        attempts += 1
        try:
            # State purpose & minimal inputs BEFORE sending
            sample = {
                "purpose": "streak_break_warning",
                "inputs": {
                    "lastActive": payload.get("content", "")[:200],  # logged within content lines
                }
            }
            log(f"Preparing Discord notification: {json.dumps(sample)[:240]}")

            r = requests.post(webhook_url, json=payload, timeout=timeout)
            ok = 200 <= r.status_code < 300
            # Validation line (1–2 lines)
            log(f"Validation: Discord HTTP {r.status_code}; {'delivered' if ok else 'failed'}")
            if not ok:
                raise RuntimeError(f"Discord returned HTTP {r.status_code}: {r.text[:300]}")
            return
        except Exception as e:
            last_exc = e
            log(f"Error on Discord post: {e.__class__.__name__}: {e}")
            if attempts < 2:
                log("Retrying Discord in 5 minutes …")
                time.sleep(300)
    assert last_exc is not None
    raise last_exc

# ---- Domain logic ----

def normalize_stats(raw: Any) -> Dict[str, Any]:
    """
    Accepts:
      - A list with one object
      - Or a single object
    Ensures required fields exist. Returns normalized dict.
    """
    obj = None
    if isinstance(raw, list) and raw:
        obj = raw[0]
    elif isinstance(raw, dict):
        obj = raw
    else:
        raise ValueError("Unexpected API response shape; expected list with one object or a single object.")

    required_top = ["totalContributions", "firstContribution", "longestStreak", "currentStreak"]
    for k in required_top:
        if k not in obj:
            raise ValueError(f"Missing key: {k}")

    # Basic field checks
    cs = obj["currentStreak"]
    ls = obj["longestStreak"]
    for streak_key, thing in [("currentStreak", cs), ("longestStreak", ls)]:
        if not isinstance(thing, dict):
            raise ValueError(f"{streak_key} must be an object")
        for sub in ["start", "end", "days"]:
            if sub not in thing:
                raise ValueError(f"Missing key: {streak_key}.{sub}")

    # Validation line (1–2 lines)
    log(f"Validation: parsed fields: total={obj['totalContributions']}, currentStreak.days={obj['currentStreak']['days']}")
    return obj

def compute_days_missed(last_active_str: str) -> Tuple[int, date]:
    last_active_dt = iso_to_date(last_active_str)
    today = today_utc()
    delta_days = (today - last_active_dt).days
    return (max(0, delta_days), last_active_dt)

def build_warning_content(last_active: date, streak_length_days: int, days_missed: int) -> str:
    # Plain text payload
    lines = [
        "Warning: Your GitHub streak has ended!",
        f"- Last active (UTC): {last_active.isoformat()}",
        f"- Streak length: {streak_length_days} days",
        f"- Days missed: {days_missed}",
    ]
    return "\n".join(lines)

def notify_secondary(message: str, timeout: int) -> None:
    hook = env("SECONDARY_ERROR_WEBHOOK")
    if not hook:
        return
    try:
        requests.post(hook, json={"content": message}, timeout=timeout)
    except Exception as e:
        log(f"Secondary notification failed: {e}")

def build_discord_message(last_active: date, streak_length_days: int, days_missed: int, is_warning: bool) -> str:
    # line 1: spicy meme (depends on missed or not)
    line1 = pick_meme(days_missed)
    # line 2: compact details (kept under 2 lines total; includes the required fields when warning)
    if is_warning:
        # Explicitly say it's a warning and include last active, streak days, and days missed.
        line2 = f"⚠️ Warning — Last: {last_active.isoformat()} | Streak: {streak_length_days}d | Missed: {days_missed}d"
    else:
        # Optional hype line when not missed (only sent if ALWAYS_NOTIFY_ACTIVE=1)
        line2 = f"✅ Streak alive — Last: {last_active.isoformat()} | Streak: {streak_length_days}d | Missed: 0d"
    return f"{line1}\n{line2}"


def main() -> int:
    load_dotenv(override=False)

    endpoint = env("STREAK_API_ENDPOINT", "https://api.franznkemaka.com/github-streak/stats/kongesque")
    webhook = env("DISCORD_WEBHOOK_URL")
    timeout = get_http_timeout()

    if not webhook:
        log("FATAL: DISCORD_WEBHOOK_URL not set")
        notify_secondary("Streak monitor: DISCORD_WEBHOOK_URL missing.", timeout)
        return 2

    try:
        raw = fetch_with_retry(endpoint, timeout)
        stats = normalize_stats(raw)

        # Business rules
        last_active_str = stats["currentStreak"]["end"]
        streak_len_days = int(stats["currentStreak"]["days"])
        days_missed, last_active = compute_days_missed(last_active_str)

        log(f"Computed daysMissed={days_missed} from today={today_utc().isoformat()} and lastActive={last_active.isoformat()}.")

        if days_missed > 0:
            # Streak is broken → send spicy warning + required details
            content = build_discord_message(last_active, streak_len_days, days_missed, is_warning=True)
            payload = {"content": content}
            post_discord_with_retry(webhook, payload, timeout)
        else:
            # Optional: send hype/tease even when active (opt-in)
            always_notify = env("ALWAYS_NOTIFY_ACTIVE", "0") == "1"
            if always_notify:
                content = build_discord_message(last_active, streak_len_days, days_missed, is_warning=False)
                payload = {"content": content}
                post_discord_with_retry(webhook, payload, timeout)
            else:
                log("No action: streak is active (daysMissed=0). Set ALWAYS_NOTIFY_ACTIVE=1 to send hype messages daily.")



        return 0

    except Exception as e:
        log("FATAL: job failed after retry.")
        log("Traceback:\n" + "".join(traceback.format_exception(e)))
        notify_secondary(f"Streak monitor failed: {e}", timeout)
        return 1

if __name__ == "__main__":
    sys.exit(main())
