#!/usr/bin/env python3
"""
post_telegram.py — broadcast new TechBrief articles to a Telegram channel.

Setup:
  1. Message @BotFather on Telegram → /newbot → copy the token
  2. Create a public channel e.g. @TechBriefNews
  3. Add your bot as admin to the channel
  4. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL below (or as env vars)
  5. pip install requests --break-system-packages (already installed)

Each article posts as a formatted Telegram message with title, excerpt, and link.
"""

import json
import os
import time
import requests
from datetime import datetime

# ── Telegram credentials ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHANNEL   = os.getenv("TELEGRAM_CHANNEL",   "@TechBriefNews")  # or "-100xxxxxxxxxx"

# ── Settings ──────────────────────────────────────────────────────────────────
SITE_URL          = "https://techbrief.voltixio.com"
SEARCH_INDEX      = "/var/www/techbrief_static/search.json"
POSTED_CACHE      = "/var/www/techbrief_static/.posted_telegram.json"
MAX_POSTS_PER_RUN = 5
DELAY_BETWEEN     = 3    # seconds between messages (Telegram limit: 30/sec)

# ── Category emoji map ────────────────────────────────────────────────────────
CAT_EMOJI = {
    "AI & Machine Learning": "🤖",
    "Cybersecurity":         "🔐",
    "Startups & VC":         "🚀",
    "Big Tech":              "🏢",
    "Gadgets & Hardware":    "📱",
    "Space & Science":       "🌌",
    "Technology":            "⚡",
}


def load_posted() -> set:
    if os.path.exists(POSTED_CACHE):
        try:
            with open(POSTED_CACHE) as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_posted(posted: set):
    with open(POSTED_CACHE, "w") as f:
        json.dump(list(posted), f)


def send_message(text: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHANNEL,
        "text":       text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"  ⚠ Telegram error: {e}")
        return False


def build_message(article: dict) -> str:
    cat    = article.get("category", "Technology")
    emoji  = CAT_EMOJI.get(cat, "⚡")
    title  = article["title"]
    url    = SITE_URL + article["url"]
    excerpt = article.get("excerpt", "")[:200]

    return (
        f"{emoji} <b>{title}</b>\n\n"
        f"{excerpt}…\n\n"
        f"<a href='{url}'>Read full story →</a>\n\n"
        f"<i>#{cat.replace(' & ','').replace(' ','').replace('/','')}</i> "
        f"| <a href='https://techbrief.voltixio.com'>TechBrief</a>"
    )


def post_new_articles():
    if not os.path.exists(SEARCH_INDEX):
        print("search.json not found — run generate_site.py first.")
        return

    with open(SEARCH_INDEX, encoding="utf-8") as f:
        articles = json.load(f)

    posted = load_posted()
    posted_this_run = 0

    for article in articles:
        if posted_this_run >= MAX_POSTS_PER_RUN:
            break

        art_id = article.get("id", article["url"])
        if art_id in posted:
            continue

        msg = build_message(article)
        if send_message(msg):
            print(f"  ✈ telegram: {article['title'][:55]}")
            posted.add(art_id)
            posted_this_run += 1
            time.sleep(DELAY_BETWEEN)
        else:
            print(f"  ⚠ telegram failed: {article['title'][:40]}")

    save_posted(posted)
    print(f"✓ Telegram posting done — {posted_this_run} new message(s) sent.")


if __name__ == "__main__":
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Running Telegram poster…")
    post_new_articles()
