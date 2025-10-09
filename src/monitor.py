#!/usr/bin/env python3

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

def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many

MESSAGES_MISSED = [
    "Bro. {d} {_dunit} vanished? You think consistency takes breaks? 😤",
    "You disappeared for {d} {_dunit}? Even your shadow lost faith. 💀",
    "That’s {d} {_dunit} of pure sloth. Legendary downfall, bro. 😮‍💨",
    "MIA for {d} {_dunit}? I’d clap but you’d probably ghost that too. 👻",
    "You went full hibernation for {d} {_dunit}? Wake up, lazy legend. 🐻",
    "{d} {_dunit} of silence? Damn, monk mode without results. 🧘‍♂️",
    "Bro skipped {d} {_dunit} and thought I wouldn’t notice? Bold. 😏",
    "You fell off harder than my Wi-Fi after {d} {_dunit}. 📉",
    "That’s {d} {_dunit} of pure villain arc energy—except no payoff. 😈",
    "{d} {_dunit} gone? Your motivation packed its bags too. 🧳",
    "Bro blinked for {d} {_dunit} and the grind evaporated. 😩",
    "{d} {_dunit}? You allergic to progress or what? 🤧",
    "Even your coffee’s disappointed after {d} {_dunit}. ☕💀",
    "Bro, {d} {_dunit} away and your discipline filed for divorce. 💔",
    "{d} {_dunit} gone—your reputation’s sending condolences. 🪦",
    "You ghosted longer than my ex for {d} {_dunit}. Brutal. 💔",
    "Bro skipped {d} {_dunit}, and his goals started seeing other people. 😬",
    "That’s {d} {_dunit} of pure procrastination artistry. 🎨",
    "You dipped for {d} {_dunit}? Motivation’s pressing charges. 🚓",
    "Bro took {d} {_dunit} off and entered the witness protection program. 🕵️‍♂️",
    "You disappeared for {d} {_dunit}? Hope the couch is comfy. 🛋️",
    "{d} {_dunit} gap? You speedran mediocrity, my guy. 🏁",
    "Your momentum left a note: ‘Gone forever.’ {d} {_dunit} strong. 💀",
    "Bro took {d} {_dunit} off like it’s a lifestyle. 😤",
    "{d} {_dunit} blackout? Your productivity’s missing in action. 🕳️",
    "Even your alarm clock gave up after {d} {_dunit}. ⏰💤",
    "{d} {_dunit} of slacking detected. Deploy shame protocol. 🤖",
    "Bro vanished for {d} {_dunit}. Tragic, cinematic, unnecessary. 🎬",
    "You fell off harder than stock crypto after {d} {_dunit}. 📉",
    "Bro, {d} {_dunit} silent—are you alive or just lazy? 💀",
]

MESSAGES_ACTIVE = [
    "Still feral. Still flawless. Don’t lose that chaos, bro. 😈🔥",
    "You move like main-character energy every damn day. 💅",
    "The grind fears you. Keep that intimidation streak. 👀",
    "Bro’s been unstoppable for {streak}d straight. Wild. 🦾",
    "Your streak’s so cocky it needs its own sunglasses. 😎",
    "Still dangerous, still consistent after {streak} days. Keep menacing reality. 😏",
    "You wake up and excellence just happens. Rude. 😤",
    "Bro’s confidence got a six-pack. {streak}d strong. 💪",
    "Even your reflection’s like ‘Damn, he’s still at it after {streak} days.’ 🪞🔥",
    "The streak’s acting like a celebrity now. {streak} days of fame. 📸",
    "That’s {streak} days of pure menace. Keep terrorizing mediocrity. 😈",
    "You’re so consistent, calendars ask you for advice. {streak}d certified. 📅",
    "Bro wakes up and fate just adjusts itself. {streak}d legend. 😏",
    "Still running laps around laziness. {streak}d marathon. 🏁",
    "Your streak has its own aura. People can feel it. ⚡",
    "{streak} days deep and still looking smug. Keep it toxic. 😎",
    "Bro’s in a committed relationship with momentum. {streak}d romance. 💘",
    "Keep strutting like you invented productivity. {streak}d flex. 💅",
    "That’s {streak} days of pure disrespect to excuses. 🖕",
    "The world isn’t ready for your next move, bro. {streak} days in and still rising. 🫡",
    "Still untouchable, still thriving. Don’t ruin the {streak}d vibe. 😤",
    "Bro’s discipline got drip. {streak}d no-cap. 🧢🔥",
    "You’re the villain arc success story everyone’s jealous of. {streak}d menace. 😈",
    "That streak’s so clean it could pass for luxury skincare. {streak}d glow. 💎",
    "Keep existing like effort owes you rent. {streak} days strong. 🏠🔥",
    "Still dominating like it’s personal. Spoiler: it is. {streak}d domination. 💥",
    "Bro’s streak is legally classified as a weapon. {streak}d damage. ⚔️",
    "You’re what consistency looks like if it had an attitude. {streak}d monster. 😤",
    "That’s {streak} days of showing off and it’s still not enough. 😏",
    "The energy? Unholy. The streak? {streak} days of untouchable. 👹",
]



def pick_meme(days_missed: int, streak_length_days: int) -> str:
    if days_missed > 0:
        dunit = _plural(days_missed, "day", "days")
        msg = random.choice(MESSAGES_MISSED)
        return msg.format(d=days_missed, _dunit=dunit)
    else:
        msg = random.choice(MESSAGES_ACTIVE)
        return msg.format(streak=streak_length_days)

def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    print(f"[{ts}] {msg}", flush=True)

def env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v is not None and v != "" else default

def iso_to_date(d: str) -> date:
    return date.fromisoformat(d)

def today_utc() -> date:
    return datetime.now(timezone.utc).date()

def get_http_timeout() -> int:
    try:
        return int(env("HTTP_TIMEOUT_SECONDS", "15"))
    except Exception:
        return 15

def fetch_with_retry(url: str, timeout: int) -> Any:
    attempts = 0
    last_exc = None
    while attempts < 2:
        attempts += 1
        try:
            log(f"Fetching streak stats (attempt {attempts}) …")
            r = requests.get(url, timeout=timeout)
            ok = 200 <= r.status_code < 300
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
    attempts = 0
    last_exc = None
    while attempts < 2:
        attempts += 1
        try:
            sample = {
                "purpose": "streak_break_warning",
                "inputs": {
                    "lastActive": payload.get("content", "")[:200],
                }
            }
            log(f"Preparing Discord notification: {json.dumps(sample)[:240]}")

            r = requests.post(webhook_url, json=payload, timeout=timeout)
            ok = 200 <= r.status_code < 300
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

def normalize_stats(raw: Any) -> Dict[str, Any]:
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

    cs = obj["currentStreak"]
    ls = obj["longestStreak"]
    for streak_key, thing in [("currentStreak", cs), ("longestStreak", ls)]:
        if not isinstance(thing, dict):
            raise ValueError(f"{streak_key} must be an object")
        for sub in ["start", "end", "days"]:
            if sub not in thing:
                raise ValueError(f"Missing key: {streak_key}.{sub}")

    log(f"Validation: parsed fields: total={obj['totalContributions']}, currentStreak.days={obj['currentStreak']['days']}")
    return obj

def compute_days_missed(last_active_str: str) -> Tuple[int, date]:
    last_active_dt = iso_to_date(last_active_str)
    today = today_utc()
    delta_days = (today - last_active_dt).days
    return (max(0, delta_days), last_active_dt)

def notify_secondary(message: str, timeout: int) -> None:
    hook = env("SECONDARY_ERROR_WEBHOOK")
    if not hook:
        return
    try:
        requests.post(hook, json={"content": message}, timeout=timeout)
    except Exception as e:
        log(f"Secondary notification failed: {e}")

def build_discord_message(last_active: date, streak_length_days: int, days_missed: int, is_warning: bool) -> str:
    line1 = pick_meme(days_missed, streak_length_days)
    return f"{line1}\n"

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

        last_active_str = stats["currentStreak"]["end"]
        streak_len_days = int(stats["currentStreak"]["days"])
        days_missed, last_active = compute_days_missed(last_active_str)

        log(f"Computed daysMissed={days_missed} from today={today_utc().isoformat()} and lastActive={last_active.isoformat()}.")

        if days_missed > 0:
            content = build_discord_message(last_active, streak_len_days, days_missed, is_warning=True)
            payload = {"content": content}
            post_discord_with_retry(webhook, payload, timeout)
        else:
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
