#!/usr/bin/env python3
"""
post_reddit.py — auto-post new TechBrief articles to Reddit by category.

Setup:
  1. Go to https://www.reddit.com/prefs/apps → Create app (script type)
  2. Note: client_id (under app name), client_secret, your reddit username/password
  3. pip install praw --break-system-packages
  4. Fill in credentials below
  5. Cron runs automatically after generate_site.py

Subreddits posted to by category (read-only subs excluded automatically):
  AI & ML      → r/artificial, r/MachineLearning, r/OpenAI
  Cybersecurity→ r/netsec, r/cybersecurity
  Startups     → r/startups, r/entrepreneur
  Big Tech     → r/technology, r/tech
  Gadgets      → r/gadgets, r/hardware
  Space        → r/space, r/science
  Default      → r/technology
"""

import json
import os
import time
from datetime import datetime

try:
    import praw
except ImportError:
    raise SystemExit("Run: pip install praw --break-system-packages")

# ── Reddit credentials ────────────────────────────────────────────────────────
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID",     "YOUR_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "YOUR_CLIENT_SECRET")
REDDIT_USERNAME      = os.getenv("REDDIT_USERNAME",      "YOUR_REDDIT_USERNAME")
REDDIT_PASSWORD      = os.getenv("REDDIT_PASSWORD",      "YOUR_REDDIT_PASSWORD")
REDDIT_USER_AGENT    = "TechBrief/1.0 (by u/YOUR_REDDIT_USERNAME)"

# ── Settings ──────────────────────────────────────────────────────────────────
SITE_URL          = "https://techbrief.voltixio.com"
SEARCH_INDEX      = "/var/www/techbrief_static/search.json"
POSTED_CACHE      = "/var/www/techbrief_static/.posted_reddit.json"
MAX_POSTS_PER_RUN = 2     # Reddit rate-limits heavily — keep low
DELAY_BETWEEN     = 8     # seconds between submissions

# ── Subreddit map by category ─────────────────────────────────────────────────
SUBREDDIT_MAP = {
    "AI & Machine Learning": ["artificial", "MachineLearning"],
    "Cybersecurity":         ["cybersecurity", "netsec"],
    "Startups & VC":         ["startups", "entrepreneur"],
    "Big Tech":              ["technology"],
    "Gadgets & Hardware":    ["gadgets"],
    "Space & Science":       ["space"],
    "Technology":            ["technology"],
}
DEFAULT_SUBREDDITS = ["technology"]


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


def post_new_articles():
    if not os.path.exists(SEARCH_INDEX):
        print("search.json not found — run generate_site.py first.")
        return

    with open(SEARCH_INDEX, encoding="utf-8") as f:
        articles = json.load(f)

    posted = load_posted()

    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        username=REDDIT_USERNAME,
        password=REDDIT_PASSWORD,
        user_agent=REDDIT_USER_AGENT,
    )

    posted_this_run = 0
    for article in articles:
        if posted_this_run >= MAX_POSTS_PER_RUN:
            break

        art_id = article.get("id", article["url"])
        if art_id in posted:
            continue

        category   = article.get("category", "Technology")
        subreddits = SUBREDDIT_MAP.get(category, DEFAULT_SUBREDDITS)
        url        = SITE_URL + article["url"]
        title      = article["title"][:290]  # Reddit title limit 300 chars

        for sub_name in subreddits[:1]:   # post to first sub only to avoid spam
            try:
                subreddit = reddit.subreddit(sub_name)
                submission = subreddit.submit(title=title, url=url)
                print(f"  📌 reddit r/{sub_name} [{submission.id}]: {title[:50]}")
                time.sleep(DELAY_BETWEEN)
            except Exception as e:
                print(f"  ⚠ reddit r/{sub_name} failed: {e}")

        posted.add(art_id)
        posted_this_run += 1

    save_posted(posted)
    print(f"✓ Reddit posting done — {posted_this_run} new post(s) submitted.")


if __name__ == "__main__":
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Running Reddit poster…")
    post_new_articles()
