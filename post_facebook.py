#!/usr/bin/env python3
"""
post_facebook.py — auto-post new articles to a Facebook Page after each site build.

Setup:
  1. Set env vars on server:
       export FB_PAGE_TOKEN="your_page_access_token"
       export FB_PAGE_ID="your_facebook_page_id"
  2. pip install requests
  3. Add to cron AFTER generate_site.py:
       0 * * * * python3 /root/uglyfeed/generate_site.py && python3 /root/uglyfeed/post_facebook.py >> /var/log/techbrief.log 2>&1

How it works:
  - Reads search.json built by generate_site.py
  - Posts up to MAX_POSTS_PER_RUN new articles per hour
  - Caches posted article IDs in .posted_facebook.json to avoid duplicates
  - Post format: engaging intro + article URL (Facebook scrapes OG tags for preview card)

Token notes:
  - Use a Page Access Token (not a User token) for posting to a Page
  - Page tokens don't expire if your app is in Live mode
  - Generate at: https://developers.facebook.com → your app → Graph API Explorer
  - Required permissions: pages_manage_posts, pages_read_engagement
"""

import json
import os
import requests
from datetime import datetime

# ── Config (read from environment — never hardcode tokens) ───────────────────
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "")
FB_PAGE_ID    = os.environ.get("FB_PAGE_ID", "")

SITE_URL         = "https://techbrief.voltixio.com"
SEARCH_INDEX     = "/var/www/techbrief_static/search.json"
POSTED_CACHE     = "/var/www/techbrief_static/.posted_facebook.json"
MAX_POSTS_PER_RUN = 2    # keep it low — FB penalises page spam
GRAPH_API        = "https://graph.facebook.com/v19.0"

INTROS_BY_CAT = {
    "AI & Machine Learning": "🤖 AI update worth reading:",
    "Cybersecurity":         "🔐 Security alert:",
    "Startups & VC":         "🚀 Startup news:",
    "Big Tech":              "💻 Big Tech:",
    "Gadgets & Hardware":    "📱 Gadget news:",
    "Space & Science":       "🛸 Space & Science:",
    "Technology":            "⚡ Tech news:",
}
DEFAULT_INTRO = "⚡ Latest from AI Tech Brief:"


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


def build_post(article: dict) -> str:
    """
    Build Facebook post message.
    Facebook auto-generates a rich link preview from OG tags — so the message
    just needs a hook line + URL. Keep it short and punchy.
    """
    intro   = INTROS_BY_CAT.get(article.get("category", ""), DEFAULT_INTRO)
    url     = SITE_URL + article["url"]
    title   = article["title"]
    excerpt = article["excerpt"][:180] + "…" if len(article["excerpt"]) > 180 else article["excerpt"]
    return f"{intro}\n\n{title}\n\n{excerpt}\n\n{url}"


def post_to_facebook(message: str, url: str) -> dict | None:
    endpoint = f"{GRAPH_API}/{FB_PAGE_ID}/feed"
    resp = requests.post(endpoint, data={
        "message":      message,
        "link":         url,
        "access_token": FB_PAGE_TOKEN,
    }, timeout=30)
    data = resp.json()
    if "error" in data:
        print(f"  ⚠ Facebook API error: {data['error'].get('message', data['error'])}")
        return None
    return data


def post_new_articles():
    if not FB_PAGE_TOKEN or not FB_PAGE_ID:
        print("  ⚠ FB_PAGE_TOKEN or FB_PAGE_ID not set. Skipping Facebook posting.")
        print("    Run: export FB_PAGE_TOKEN='...' && export FB_PAGE_ID='...'")
        return

    if not os.path.exists(SEARCH_INDEX):
        print("  search.json not found — run generate_site.py first.")
        return

    with open(SEARCH_INDEX, encoding="utf-8") as f:
        articles = json.load(f)

    posted           = load_posted()
    posted_this_run  = 0

    for article in articles:
        if posted_this_run >= MAX_POSTS_PER_RUN:
            break
        art_id = article["id"]
        if art_id in posted:
            continue

        message  = build_post(article)
        art_url  = SITE_URL + article["url"]
        result   = post_to_facebook(message, art_url)

        if result and "id" in result:
            print(f"  📘 posted [{result['id']}]: {article['title'][:55]}")
            posted.add(art_id)
            posted_this_run += 1
        else:
            print(f"  ✗ failed to post: {article['title'][:55]}")

    save_posted(posted)
    print(f"✓ Facebook posting done — {posted_this_run} new post(s) sent.")


if __name__ == "__main__":
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Running Facebook poster…")
    post_new_articles()
