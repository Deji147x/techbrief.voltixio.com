#!/usr/bin/env python3
"""
post_social.py — auto-post new articles to X (Twitter) after each site build.

Setup:
  1. Create a developer app at https://developer.x.com
  2. Generate OAuth 1.0a keys (need Read+Write permissions)
  3. pip install tweepy
  4. Fill in the four API keys below
  5. Add to cron AFTER generate_site.py:
       0 * * * * python3 /root/uglyfeed/generate_site.py && python3 /root/uglyfeed/post_social.py

How it works:
  - Reads search.json (the article index built by generate_site.py)
  - Maintains a posted.json cache so the same article is never tweeted twice
  - Posts up to MAX_POSTS_PER_RUN new articles per hour (default 3)
  - Tweet format: headline + excerpt snippet + URL + hashtags
"""

import json
import os
import hashlib
from datetime import datetime

try:
    import tweepy
except ImportError:
    raise SystemExit("Run: pip install tweepy")

# ── X / Twitter credentials ───────────────────────────────────────────────────
# Get these from https://developer.x.com → your app → Keys and Tokens
API_KEY             = "YOUR_API_KEY"
API_KEY_SECRET      = "YOUR_API_KEY_SECRET"
ACCESS_TOKEN        = "YOUR_ACCESS_TOKEN"
ACCESS_TOKEN_SECRET = "YOUR_ACCESS_TOKEN_SECRET"

# ── Settings ──────────────────────────────────────────────────────────────────
SITE_URL         = "https://techbrief.voltixio.com"
SEARCH_INDEX     = "/var/www/techbrief_static/search.json"
POSTED_CACHE     = "/var/www/techbrief_static/.posted_social.json"
MAX_POSTS_PER_RUN = 3    # max tweets per hourly run (avoid rate limits)
HASHTAGS_BY_CAT  = {
    "AI & Machine Learning": "#AI #MachineLearning #LLM",
    "Cybersecurity":         "#Cybersecurity #InfoSec #Hacking",
    "Startups & VC":         "#Startups #VentureCapital #Tech",
    "Big Tech":              "#BigTech #Technology",
    "Gadgets & Hardware":    "#Gadgets #Hardware #Tech",
    "Space & Science":       "#Space #Science #Technology",
    "Technology":            "#Tech #TechNews",
}
DEFAULT_HASHTAGS = "#TechNews #AI #Tech"


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


def build_tweet(article: dict) -> str:
    """Build tweet text ≤ 280 chars: title + snippet + URL + hashtags."""
    tags    = HASHTAGS_BY_CAT.get(article.get("category", ""), DEFAULT_HASHTAGS)
    url     = SITE_URL + article["url"]
    # Reserve space: URL (23 chars per Twitter's t.co) + space + hashtags + newlines
    reserved = 23 + 1 + len(tags) + 2
    max_title = 280 - reserved - 3   # -3 for " | "
    title     = article["title"]
    if len(title) > max_title:
        title = title[:max_title - 1] + "…"
    return f"{title}\n{url}\n{tags}"


def post_new_articles():
    if not os.path.exists(SEARCH_INDEX):
        print("search.json not found — run generate_site.py first.")
        return

    with open(SEARCH_INDEX, encoding="utf-8") as f:
        articles = json.load(f)

    posted = load_posted()

    # Authenticate
    client = tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_KEY_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_TOKEN_SECRET,
    )

    posted_this_run = 0
    for article in articles:
        if posted_this_run >= MAX_POSTS_PER_RUN:
            break
        art_id = article["id"]
        if art_id in posted:
            continue

        tweet_text = build_tweet(article)
        try:
            resp = client.create_tweet(text=tweet_text)
            print(f"  🐦 tweeted [{resp.data['id']}]: {article['title'][:50]}")
            posted.add(art_id)
            posted_this_run += 1
        except tweepy.TweepyException as e:
            print(f"  ⚠ tweet failed for '{article['title'][:40]}': {e}")

    save_posted(posted)
    print(f"✓ Social posting done — {posted_this_run} new tweet(s) sent.")


if __name__ == "__main__":
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Running social poster…")
    post_new_articles()
