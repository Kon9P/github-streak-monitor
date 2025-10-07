#!/usr/bin/env python3
"""
Kong's GitHub streak monitor → Discord notifier

- Fetches streak stats
- Computes days missed (UTC)
- Generates a spicy meme-style message with DeepSeek
- Posts to Discord via webhook
- Logs & retries with exponential backoff
"""
from __future__ import annotations

import os
import sys
import json
import time
import logging
from typing import Any, Dict, Optional, Tuple
from datetime import datetime, timezone, date

import requests
from dotenv import load_dotenv

# ----------------------------
# Config & Logging
# ----------------------------

def _setup_logging() -> None:
    # Structured, concise logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(asctime)sZ %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _today_str_utc() -> str:
    return _now_utc().date().isoformat()

# ----------------------------
# HTTP with retries
# ----------------------------

def _request_with_retries(method: str, url: str, *,
                          headers: Optional[Dict[str, str]] = None,
                          json_body: Optional[Dict[str, Any]] = None,
                          timeout: int = 15,
                          max_retries: int = 3,
                          backoff_base: float = 1.0) -> Tuple[Optional[requests.Response], Optional[Exception]]:
    """
    HTTP request with up to max_retries attempts and exponential backoff.
    Logs warnings and returns (response, error). One of them will be None.
    """
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            if method.upper() == "GET":
                resp = requests.get(url, headers=headers, timeout=timeout)
            else:
                resp = requests.post(url, headers=headers, json=json_body, timeout=timeout)

            if 200 <= resp.status_code < 300:
                logging.info("[INFO] [%s] HTTP %s OK (%s)", _now_utc().isoformat(), method.upper(), str(resp.status_code))
                return resp, None

            # Non-2xx → retry
            logging.warning("[WARN] [%s] %s %s failed: HTTP %s, Retrying (%s/%s)",
                            _now_utc().isoformat(), method.upper(), url, str(resp.status_code), attempt, max_retries)
        except Exception as e:  # network error, etc.
            last_err = e
            logging.warning("[WARN] [%s] %s %s exception: %s, Retrying (%s/%s)",
                            _now_utc().isoformat(), method.upper(), url, str(e), attempt, max_retries)
        time.sleep(backoff_base * (2 ** (attempt - 1)))

    # Final failure
    payload_str = json.dumps(json_body) if json_body is not None else ""
    logging.error("[ERROR] [%s] Persistent %s failure for %s after %s retries. Payload=%s",
                  _now_utc().isoformat(), method.upper(), url, max_retries, payload_str)
    return None, last_err

# ----------------------------
# Core steps
# ----------------------------

def fetch_streak_stats(streak_api_url: str) -> Dict[str, Any]:
    # Purpose (log): Fetch GitHub streak stats; Inputs: url only
    logging.info("Purpose: Fetch GitHub streak stats. Inputs: url=%s", streak_api_url)
    resp, err = _request_with_retries("GET", streak_api_url)
    if err or resp is None:
        raise RuntimeError(f"Failed to fetch stats from {streak_api_url}: {str(err)}")
    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Stats response is not valid JSON: {str(e)}")
    # Validate minimal structure
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"Stats JSON shape unexpected: {str(data)}")
    logging.info("Validation: fetched stats JSON list with length=%s", str(len(data)))
    return data[0]

def compute_days_missed(last_active_str: str, today_str: Optional[str] = None) -> int:
    # Purpose (log): Compute days missed using UTC; Inputs: lastActive string, today string (UTC)
    if today_str is None:
        today_str = _today_str_utc()
    logging.info("Purpose: Compute days missed. Inputs: lastActive=%s, todayUTC=%s", str(last_active_str), str(today_str))
    try:
        last_active = date.fromisoformat(last_active_str)
        today = date.fromisoformat(today_str)
    except Exception as e:
        raise ValueError(f"Invalid date strings. lastActive={last_active_str}, today={today_str}. Error={e}")
    delta_days = (today - last_active).days
    missed = max(0, int(delta_days))
    logging.info("Validation: computed daysMissed=%s", str(missed))
    return missed

def deepseek_generate_message(api_key: str, *, today: str, last_active: str, current_streak_days: int, days_missed: int,
                              base_url: str = "https://api.deepseek.com",
                              model: str = "deepseek-chat",
                              temperature: float = 0.9,
                              max_tokens: int = 120) -> str:
    # Purpose (log): Generate motivational message via DeepSeek; Inputs: model name, prompt variables (dates, ints)
    logging.info("Purpose: Generate message via DeepSeek. Inputs: model=%s, today=%s, lastActive=%s, streakDays=%s, daysMissed=%s",
                 model, str(today), str(last_active), str(current_streak_days), str(days_missed))
    if not api_key:
        logging.warning("Validation: DEEPSEEK_API_KEY missing; falling back to local message template.")
        return _fallback_message(today, last_active, current_streak_days, days_missed)

    url = f"{base_url.rstrip('/')}/chat/completions"
    prompt = f"""
Generate a short, naughty meme-style message for **Kong** that sounds spicy, a bit angry, and slightly guilt-inducing if they missed their streak. Use light curse words (like *damn*, *hell*, or *shit*)—nothing too harsh.

Use these variables:
- **Today's Date**: {today}
- **Last Activity Date**: {last_active}
- **Current Streak**: {current_streak_days}
- **Days Missed**: {days_missed}

Rules:
- If Kong missed 1 or more days, make it sound angry/teasing and guilt-tripping about breaking the streak.
- If Kong didn't miss any days, make it cocky, flirty, or teasing to keep motivation high.
- The message must be short (under 2 lines) and funny, including light profanity naturally.
"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt.strip()}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    resp, err = _request_with_retries("POST", url, headers=headers, json_body=body)
    if err or resp is None:
        logging.error("Validation: DeepSeek call failed; using fallback message.")
        return _fallback_message(today, last_active, current_streak_days, days_missed)

    try:
        data = resp.json()
        msg = data["choices"][0]["message"]["content"].strip()
        logging.info("Validation: received DeepSeek message (len=%s)", str(len(msg)))
        return str(msg)
    except Exception as e:
        logging.error("Validation failed: DeepSeek JSON parse error=%s; using fallback.", str(e))
        return _fallback_message(today, last_active, current_streak_days, days_missed)

def _fallback_message(today: str, last_active: str, current_streak_days: int, days_missed: int) -> str:
    if days_missed > 0:
        return f"KONG. You ghosted for {days_missed} day(s) since {last_active}. Get back in before the streak flatlines, damn it 🔥😤"
    else:
        return f"Still cooking on {current_streak_days} days as of {today}. Don’t you dare slack now, badass 😎🔥"

def discord_post_message(webhook_url: str, content: str) -> None:
    # Purpose (log): Post message to Discord via webhook; Inputs: webhook URL present, JSON payload with 'content'
    logging.info("Purpose: Post message to Discord. Inputs: webhook_url_present=%s, payload_keys=%s",
                 str(bool(webhook_url)), str(["content"]))
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL is missing.")
    payload = {"content": str(content)}
    headers = {"Content-Type": "application/json"}
    resp, err = _request_with_retries("POST", webhook_url, headers=headers, json_body=payload)
    if err or resp is None:
        raise RuntimeError(f"Failed to post to Discord: {str(err)}")
    logging.info("Validation: Discord POST HTTP=%s", str(resp.status_code))

# ----------------------------
# Main orchestration
# ----------------------------

def run() -> int:
    _setup_logging()
    load_dotenv()

    # Read config/secrets
    STREAK_API_URL = os.getenv("STREAK_API_URL", "https://api.franznkemaka.com/github-streak/stats/kongesque")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

    # Step 1: Fetch stats
    try:
        stats = fetch_streak_stats(STREAK_API_URL)
    except Exception as e:
        logging.error("Fatal: could not fetch streak stats. %s", str(e))
        return 1

    # Extract pieces
    try:
        current = stats.get("currentStreak", {}) or {}
        last_active = str(current.get("end"))
        current_streak_days = int(current.get("days"))
        today_str = _today_str_utc()
        logging.info("Extracted values: today=%s, lastActive=%s, currentStreakDays=%s",
                     str(today_str), str(last_active), str(current_streak_days))
    except Exception as e:
        logging.error("Fatal: invalid stats structure: %s", str(e))
        return 1

    # Step 2: Compute days missed
    try:
        days_missed = compute_days_missed(last_active, today_str)
    except Exception as e:
        logging.error("Fatal: can't compute daysMissed: %s", str(e))
        return 1

    # Step 3: Generate message with DeepSeek (or fallback)
    message = deepseek_generate_message(
        DEEPSEEK_API_KEY,
        today=today_str,
        last_active=last_active,
        current_streak_days=current_streak_days,
        days_missed=days_missed
    )

    logging.info("Generated message: %s", str(message))

    # Step 4: Post to Discord
    try:
        discord_post_message(DISCORD_WEBHOOK_URL, message)
    except Exception as e:
        logging.error("Fatal: Discord post failed: %s", str(e))
        return 1

    # Final: Also echo a compact summary (stringified)
    summary = {
        "todayUTC": str(today_str),
        "lastActive": str(last_active),
        "currentStreakDays": str(current_streak_days),
        "daysMissed": str(days_missed),
        "message": str(message),
    }
    logging.info("Done. Summary=%s", json.dumps(summary))
    return 0

if __name__ == "__main__":
    sys.exit(run())
