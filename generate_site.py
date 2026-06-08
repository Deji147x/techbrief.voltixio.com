#!/usr/bin/env python3
"""
Static site generator for techbrief.voltixio.com
Fetches uglyfeed RSS → rewrites each article with Ollama → builds full static site.

Features:
  - Ollama LLM rewrites each article into a full engaging ~500-word piece
  - Rewrite cache (avoids re-calling Ollama on articles already processed)
  - Hero image with title/category text overlay on article pages
  - Card images with gradient + title text overlay on homepage
  - Stable slug-based article URLs (won't renumber between runs)
  - Auto-detected categories
  - Client-side search (lunr.js + search.json)
  - Sitemap.xml, feed.xml, robots.txt
  - Full About + Contact pages
"""

import feedparser
import requests
import hashlib
import os
import re
import json
import time
from datetime import datetime, timezone
from email.utils import formatdate
from jinja2 import Template

# ── Configuration ─────────────────────────────────────────────────────────────
RSS_URL           = "http://localhost:8001/uglyfeed.xml"
OUTPUT_DIR        = "/var/www/techbrief_static"
ARTICLES_PER_PAGE = 20
SITE_URL          = "https://techbrief.voltixio.com"
SITE_TITLE        = "AI Tech Brief"
SITE_DESCRIPTION  = "AI‑rewritten tech news and insights, updated hourly."
SITE_AUTHOR       = "AI Tech Brief"
CONTACT_EMAIL     = "editor@techbrief.voltixio.com"

# ── Analytics & Ads ───────────────────────────────────────────────────────────
GA4_ID            = "G-DHCN454V9J"
ADSENSE_PUB_ID    = "ca-pub-XXXXXXXXXXXXXXXX" # replace with your AdSense publisher ID
ADSENSE_SLOT_BANNER   = "1234567890"          # horizontal banner slot (homepage)
ADSENSE_SLOT_ARTICLE  = "0987654321"          # in-article slot (article pages)
ENABLE_ADS        = False                     # set True once AdSense account is approved

# ── Ollama settings ───────────────────────────────────────────────────────────
OLLAMA_URL        = "http://localhost:11434"   # change if Ollama runs elsewhere
OLLAMA_MODEL      = "gemma2:9b"                # excellent at following tone instructions
OLLAMA_TIMEOUT    = 180                        # seconds per article — increase if GPU is slow
REWRITE_CACHE     = os.path.join(OUTPUT_DIR, ".rewrite_cache.json")

# ── Category keyword map ──────────────────────────────────────────────────────
CATEGORY_KEYWORDS = {
    "AI & Machine Learning": ["ai", "machine learning", "llm", "gpt", "neural", "openai",
                               "anthropic", "gemini", "deepmind", "chatgpt", "model", "generative"],
    "Cybersecurity":         ["hack", "security", "breach", "malware", "ransomware",
                               "vulnerability", "exploit", "phishing", "cyber"],
    "Startups & VC":         ["startup", "funding", "series a", "series b", "vc",
                               "venture", "valuation", "unicorn", "ipo"],
    "Big Tech":              ["google", "apple", "microsoft", "amazon", "meta",
                               "tesla", "nvidia", "samsung", "intel"],
    "Gadgets & Hardware":    ["phone", "chip", "processor", "device", "hardware",
                               "laptop", "tablet", "wearable", "headset"],
    "Space & Science":       ["nasa", "spacex", "space", "rocket", "satellite",
                               "quantum", "physics", "climate"],
}

# ── Directory setup ───────────────────────────────────────────────────────────
for d in [OUTPUT_DIR,
          os.path.join(OUTPUT_DIR, "article"),
          os.path.join(OUTPUT_DIR, "images"),
          os.path.join(OUTPUT_DIR, "category")]:
    os.makedirs(d, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80]


def stable_id(title: str) -> str:
    return hashlib.md5(title.encode()).hexdigest()[:8]


def detect_category(title: str, summary: str) -> str:
    combined = (title + " " + summary).lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return category
    return "Technology"


def image_id_for_keyword(keyword: str) -> int:
    hex8 = hashlib.md5(keyword.encode()).hexdigest()[:8]
    return int(hex8, 16) % 1000


def fetch_or_create_image(title: str, slug: str) -> str:
    words   = title.split()
    stop    = {"a", "an", "the", "and", "of", "to", "for", "in", "on", "with"}
    keyword = next((w.lower() for w in words if w.lower() not in stop and len(w) > 3), "technology")
    img_id  = image_id_for_keyword(keyword)
    fname   = f"{slug}.jpg"
    path    = os.path.join(OUTPUT_DIR, "images", fname)
    if not os.path.exists(path):
        for url in [f"https://picsum.photos/id/{img_id}/1200/630",
                    "https://picsum.photos/id/0/1200/630"]:
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    with open(path, "wb") as f:
                        f.write(r.content)
                    print(f"  ↓ image [{keyword}]")
                    break
            except Exception as e:
                print(f"  ⚠ image error: {e}")
    return f"/images/{fname}"


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


# ── Rewrite cache ─────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if os.path.exists(REWRITE_CACHE):
        try:
            with open(REWRITE_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache: dict):
    with open(REWRITE_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── Ollama rewriting ──────────────────────────────────────────────────────────

REWRITE_PROMPT = """\
You are a sharp, engaging tech journalist writing for a digital magazine.

Rewrite the article below into a compelling, original piece of approximately 450–550 words.
Requirements:
- Start with a punchy opening sentence that hooks the reader immediately.
- Develop 4 natural flowing paragraphs — no headers, no bullet points, no lists.
- Weave in wider context: why this matters, who is affected, what comes next.
- Keep the tone confident and conversational — like a smart friend explaining the news.
- Vary sentence length. Use vivid, specific language. Avoid clichés.
- End with a forward-looking sentence about implications.
- Output ONLY the article text. No intro like "Here is the article:" or meta-commentary.

Title: {title}
Original content: {summary}
"""


def rewrite_with_ollama(title: str, summary: str, cache: dict) -> str:
    """
    Call local Ollama to rewrite an article.
    Returns the rewritten text. Falls back to original summary on any error.
    Uses a stable cache keyed on (title + summary) hash to avoid re-calling Ollama
    for articles that haven't changed between hourly runs.
    """
    cache_key = hashlib.md5((title + summary).encode()).hexdigest()
    if cache_key in cache:
        return cache[cache_key]

    prompt = REWRITE_PROMPT.format(title=title, summary=summary[:2000])

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model":  OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.75,
                    "top_p": 0.9,
                    "num_predict": 700,   # ~550 words with a little headroom
                }
            },
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        data    = resp.json()
        rewrite = data.get("response", "").strip()

        if len(rewrite) < 100:
            print(f"  ⚠ Ollama returned too-short response for '{title[:40]}', using original")
            return summary

        cache[cache_key] = rewrite
        save_cache(cache)
        print(f"  ✍ rewritten: {title[:55]}…")
        return rewrite

    except requests.exceptions.ConnectionError:
        print(f"  ⚠ Ollama not reachable at {OLLAMA_URL}. Using original summary.")
        return summary
    except Exception as e:
        print(f"  ⚠ Ollama error for '{title[:40]}': {e}. Using original summary.")
        return summary


# ── RSS parsing ───────────────────────────────────────────────────────────────

def parse_rss(cache: dict) -> list[dict]:
    print(f"\nFetching RSS from {RSS_URL} …")
    feed     = feedparser.parse(RSS_URL)
    articles = []

    total = min(len(feed.entries), ARTICLES_PER_PAGE)
    for i, entry in enumerate(feed.entries[:total]):
        title   = entry.get("title", "Untitled")
        summary = strip_html(entry.get("description", entry.get("summary", "")))

        # Use content:encoded if available (fuller body from uglyfeed)
        if hasattr(entry, "content") and entry.content:
            source_text = strip_html(entry.content[0].get("value", summary))
        else:
            source_text = summary

        print(f"  [{i+1}/{total}] {title[:60]}")

        # ── Ollama rewrite ────────────────────────────────────────────────
        rewritten = rewrite_with_ollama(title, source_text, cache)

        excerpt  = rewritten[:240] + "…" if len(rewritten) > 240 else rewritten
        slug     = slugify(title)
        uid      = stable_id(title)
        category = detect_category(title, source_text)

        articles.append({
            "title":        title,
            "link":         entry.get("link", "#"),
            "pubDate":      entry.get("published",
                                datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")),
            "summary":      summary,
            "full_content": rewritten,
            "excerpt":      excerpt,
            "slug":         slug,
            "uid":          uid,
            "detail_url":   f"/article/{uid}-{slug}.html",
            "category":     category,
        })

    return articles


# ── Shared CSS ────────────────────────────────────────────────────────────────
SHARED_CSS = """
:root {
  --navy:   #060c1a;
  --navy2:  #0d1526;
  --navy3:  #111d33;
  --navy4:  #162040;
  --blue:   #0a84ff;
  --blue2:  #00c6ff;
  --cyan:   #00e5ff;
  --glow:   rgba(0,198,255,.18);
  --red:    #ff3b3b;
  --silver: #a8bcd4;
  --silver2:#cdd9e8;
  --white:  #ffffff;
}
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:var(--navy); color:var(--silver2); line-height:1.6;
}
a { text-decoration:none; }
.container { max-width:1240px; margin:0 auto; padding:0 24px; }

/* ── Breaking News Ticker ── */
.ticker-wrap {
  background:linear-gradient(90deg,var(--red) 0%,#c0392b 100%);
  padding:8px 0; overflow:hidden; position:relative; z-index:10;
}
.ticker-inner { display:flex; align-items:center; gap:0; }
.ticker-label {
  background:var(--white); color:var(--red); font-size:.72rem; font-weight:800;
  text-transform:uppercase; letter-spacing:.1em; padding:3px 12px; white-space:nowrap;
  margin-right:20px; flex-shrink:0; border-radius:2px;
}
.ticker-track {
  overflow:hidden; flex:1;
}
.ticker-items {
  display:inline-flex; gap:60px; white-space:nowrap;
  animation:ticker 40s linear infinite;
}
.ticker-items span { color:var(--white); font-size:.82rem; font-weight:500; }
.ticker-items span::before { content:"⚡ "; }
@keyframes ticker { 0%{transform:translateX(0)} 100%{transform:translateX(-50%)} }

/* ── Header ── */
header {
  background:rgba(6,12,26,.96);
  backdrop-filter:blur(12px);
  border-bottom:1px solid rgba(0,198,255,.15);
  padding:14px 0;
  position:sticky; top:0; z-index:100;
}
header .inner { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; }
.logo-wrap { display:flex; align-items:center; gap:10px; }
.logo-wrap img { height:40px; width:40px; object-fit:contain; border-radius:8px; }
.logo-text { font-size:1.3rem; font-weight:800; color:var(--white); letter-spacing:-.02em; }
.logo-text span { color:var(--blue2); }
nav a {
  color:var(--silver); margin-right:20px; font-size:.85rem; font-weight:500;
  transition:color .2s; letter-spacing:.02em;
}
nav a:hover { color:var(--blue2); }
.live-dot {
  display:inline-flex; align-items:center; gap:6px;
  background:rgba(255,59,59,.15); border:1px solid rgba(255,59,59,.4);
  color:var(--red); font-size:.72rem; font-weight:700; letter-spacing:.08em;
  padding:4px 10px; border-radius:20px; text-transform:uppercase;
}
.live-dot::before {
  content:""; width:7px; height:7px; background:var(--red); border-radius:50%;
  animation:pulse-red 1.2s ease-in-out infinite;
}
@keyframes pulse-red {
  0%,100%{box-shadow:0 0 0 0 rgba(255,59,59,.6)}
  50%{box-shadow:0 0 0 5px rgba(255,59,59,0)}
}
.search-bar { display:flex; gap:8px; }
.search-bar input {
  padding:7px 14px; border-radius:8px; font-size:.85rem; width:200px;
  background:var(--navy3); border:1px solid rgba(0,198,255,.25); color:var(--silver2);
  outline:none; transition:border .2s;
}
.search-bar input:focus { border-color:var(--blue2); }
.search-bar button {
  padding:7px 16px; background:linear-gradient(135deg,var(--blue),var(--blue2));
  color:white; border:none; border-radius:8px; cursor:pointer; font-size:.85rem; font-weight:600;
  transition:opacity .2s;
}
.search-bar button:hover { opacity:.85; }

/* ── Hero Banner ── */
.hero-banner {
  position:relative; width:100%; overflow:hidden;
  max-height:380px; display:block;
}
.hero-banner img {
  width:100%; height:380px; object-fit:cover; object-position:center;
  display:block;
}
.hero-banner-gradient {
  position:absolute; inset:0;
  background:linear-gradient(
    to right,
    rgba(6,12,26,.45) 0%,
    transparent 40%,
    transparent 60%,
    rgba(6,12,26,.45) 100%
  );
  pointer-events:none;
}
.hero-banner-bottom {
  position:absolute; bottom:0; left:0; right:0; height:60px;
  background:linear-gradient(to top,var(--navy) 0%,transparent 100%);
}

/* ── Category Icons Row ── */
.cat-icons-row {
  background:var(--navy2);
  border-top:1px solid rgba(0,198,255,.12);
  border-bottom:1px solid rgba(0,198,255,.12);
  padding:16px 0;
}
.cat-icons-inner {
  display:flex; align-items:center; justify-content:center;
  flex-wrap:wrap; gap:8px 24px;
}
.cat-icon-item {
  display:flex; align-items:center; gap:8px; color:var(--silver);
  font-size:.8rem; font-weight:600; letter-spacing:.04em;
  text-transform:uppercase; transition:color .2s; cursor:pointer;
}
.cat-icon-item:hover { color:var(--blue2); }
.cat-icon-item .icon-circle {
  width:34px; height:34px; border-radius:50%;
  background:var(--navy3); border:1px solid rgba(0,198,255,.2);
  display:flex; align-items:center; justify-content:center; font-size:1rem;
  transition:border-color .2s, background .2s;
}
.cat-icon-item:hover .icon-circle { border-color:var(--blue2); background:rgba(0,198,255,.08); }

/* ── Section header ── */
.section-header {
  display:flex; align-items:center; justify-content:space-between;
  margin:32px 0 20px; padding-bottom:12px;
  border-bottom:1px solid rgba(0,198,255,.12);
}
.section-header h2 {
  font-size:1.2rem; font-weight:700; color:var(--white);
  text-transform:uppercase; letter-spacing:.08em;
}
.section-header h2::before { content:""; display:inline-block; width:4px; height:18px; background:var(--blue2); border-radius:2px; margin-right:10px; vertical-align:middle; }
.section-header a { color:var(--blue2); font-size:.82rem; font-weight:600; }

/* ── Grid ── */
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(350px,1fr)); gap:24px; margin-bottom:50px; }

/* ── Cards ── */
.card {
  background:var(--navy2); border-radius:14px; overflow:hidden;
  border:1px solid rgba(0,198,255,.1);
  transition:transform .22s, border-color .22s, box-shadow .22s;
}
.card:hover {
  transform:translateY(-5px);
  border-color:rgba(0,198,255,.35);
  box-shadow:0 8px 32px rgba(0,198,255,.1);
}
.card-img-wrap { position:relative; height:210px; overflow:hidden; }
.card-img-wrap img { width:100%; height:100%; object-fit:cover; transition:transform .4s; }
.card:hover .card-img-wrap img { transform:scale(1.05); }
.card-img-overlay {
  position:absolute; bottom:0; left:0; right:0;
  background:linear-gradient(to top, rgba(6,12,26,.92) 0%, rgba(6,12,26,.4) 60%, transparent 100%);
  padding:36px 16px 14px;
  color:var(--white); font-size:.92rem; font-weight:600; line-height:1.35;
}
.card-img-cat {
  display:inline-block; font-size:.62rem; font-weight:700; text-transform:uppercase; letter-spacing:.08em;
  padding:3px 10px; border-radius:20px; margin-bottom:6px;
  background:linear-gradient(135deg,var(--blue),var(--blue2)); color:white;
}
.card-content { padding:16px 20px 20px; }
.card-excerpt { color:var(--silver); font-size:.9rem; margin-bottom:12px; line-height:1.6; }
.card-meta    { font-size:.75rem; color:rgba(168,188,212,.6); margin-bottom:14px; }
.read-more {
  display:inline-block; background:transparent;
  border:1px solid rgba(0,198,255,.4); color:var(--blue2);
  padding:7px 16px; border-radius:8px; font-size:.82rem; font-weight:600;
  transition:background .2s, border-color .2s;
}
.read-more:hover { background:rgba(0,198,255,.1); border-color:var(--blue2); }

/* ── Category nav pills ── */
.cats-nav { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:28px; }
.cats-nav a {
  background:var(--navy2); border:1px solid rgba(0,198,255,.15);
  color:var(--silver); padding:6px 18px; border-radius:20px; font-size:.82rem; font-weight:500;
  transition:all .2s;
}
.cats-nav a:hover, .cats-nav a.active {
  background:linear-gradient(135deg,var(--blue),var(--blue2));
  color:white; border-color:transparent;
}

/* ── Subscribe CTA banner ── */
.subscribe-cta {
  background:linear-gradient(135deg,var(--navy3) 0%,var(--navy4) 100%);
  border:1px solid rgba(0,198,255,.2);
  border-radius:16px; padding:36px 40px;
  display:flex; align-items:center; justify-content:space-between; gap:24px;
  margin:40px 0; flex-wrap:wrap;
  box-shadow:0 0 40px rgba(0,198,255,.06);
}
.subscribe-cta-text h3 { font-size:1.4rem; font-weight:800; color:var(--white); margin-bottom:6px; }
.subscribe-cta-text p  { color:var(--silver); font-size:.92rem; }
.cta-btn {
  background:linear-gradient(135deg,var(--blue) 0%,var(--blue2) 100%);
  color:white; font-weight:700; font-size:.95rem; padding:13px 28px;
  border-radius:10px; white-space:nowrap; letter-spacing:.02em;
  box-shadow:0 4px 20px rgba(0,198,255,.3);
  transition:box-shadow .2s, transform .2s;
}
.cta-btn:hover { box-shadow:0 6px 28px rgba(0,198,255,.5); transform:translateY(-1px); }

/* ── Article page ── */
.article-page .container { max-width:860px; }
.article-hero {
  position:relative; width:100%; border-radius:16px; overflow:hidden;
  margin:28px 0 32px; height:430px;
}
.article-hero img { width:100%; height:100%; object-fit:cover; display:block; }
.article-hero-overlay {
  position:absolute; inset:0;
  background:linear-gradient(to top, rgba(6,12,26,.92) 0%, rgba(6,12,26,.45) 50%, rgba(6,12,26,.1) 100%);
  display:flex; flex-direction:column; justify-content:flex-end; padding:36px 36px;
  color:var(--white);
}
.article-hero-cat {
  display:inline-block;
  background:linear-gradient(135deg,var(--blue),var(--blue2)); color:white;
  font-size:.7rem; font-weight:700; text-transform:uppercase; letter-spacing:.1em;
  padding:4px 14px; border-radius:20px; margin-bottom:14px; width:fit-content;
}
.article-hero-title { font-size:2.1rem; font-weight:800; line-height:1.22; text-shadow:0 2px 10px rgba(0,0,0,.5); }
.article-hero-meta  { margin-top:12px; font-size:.83rem; color:var(--silver); }
.article-body {
  background:var(--navy2); padding:40px; border-radius:16px;
  border:1px solid rgba(0,198,255,.1);
  font-size:1.08rem; line-height:1.85; margin-bottom:30px; color:var(--silver2);
}
.article-body p { margin-bottom:1.5em; }
.article-body p:last-child { margin-bottom:0; }
.source-link { text-align:center; margin-top:28px; padding-top:22px; border-top:1px solid rgba(0,198,255,.12); }
.source-link a { color:var(--blue2); font-size:.9rem; }
.back-btn {
  display:inline-flex; align-items:center; gap:6px;
  background:var(--navy2); border:1px solid rgba(0,198,255,.2);
  color:var(--blue2); padding:9px 20px; border-radius:8px; margin:24px 0 0;
  font-size:.88rem; font-weight:600; transition:all .2s;
}
.back-btn:hover { background:rgba(0,198,255,.08); border-color:var(--blue2); }

/* ── Search page ── */
#search-input {
  width:100%; padding:15px 20px; font-size:1rem;
  background:var(--navy2); border:1px solid rgba(0,198,255,.25);
  color:var(--silver2); border-radius:12px; margin:24px 0 20px; outline:none;
  transition:border .2s;
}
#search-input:focus { border-color:var(--blue2); box-shadow:0 0 0 3px rgba(0,198,255,.1); }
.search-result-item {
  background:var(--navy2); padding:22px; border-radius:12px; margin-bottom:16px;
  border:1px solid rgba(0,198,255,.1); transition:border-color .2s;
}
.search-result-item:hover { border-color:rgba(0,198,255,.3); }
.search-result-item h3 a { color:var(--white); font-size:1.02rem; font-weight:600; }
.search-result-item h3 a:hover { color:var(--blue2); }
.search-result-item p { color:var(--silver); font-size:.88rem; margin-top:6px; }
.no-results { text-align:center; color:var(--silver); padding:60px; }

/* ── Footer ── */
footer {
  background:var(--navy2);
  border-top:1px solid rgba(0,198,255,.12);
  color:var(--silver); padding:50px 0 28px; margin-top:60px;
}
.footer-grid {
  display:grid; grid-template-columns:2fr 1fr 1fr 1.2fr; gap:40px;
  padding-bottom:36px; border-bottom:1px solid rgba(0,198,255,.1);
  margin-bottom:24px;
}
.footer-brand .logo-text { font-size:1.3rem; font-weight:800; color:var(--white); }
.footer-brand .logo-text span { color:var(--blue2); }
.footer-brand p { color:var(--silver); font-size:.85rem; line-height:1.7; margin-top:12px; max-width:280px; }
.footer-col h4 { color:var(--white); font-size:.82rem; font-weight:700; text-transform:uppercase; letter-spacing:.1em; margin-bottom:16px; }
.footer-col a { display:block; color:var(--silver); font-size:.85rem; margin-bottom:8px; transition:color .2s; }
.footer-col a:hover { color:var(--blue2); }
.footer-col .contact-item { display:flex; align-items:flex-start; gap:8px; font-size:.84rem; color:var(--silver); margin-bottom:10px; }
.footer-col .contact-item a { color:var(--blue2); }
.footer-bottom { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; font-size:.78rem; color:rgba(168,188,212,.5); }
.footer-bottom a { color:rgba(168,188,212,.7); margin:0 8px; }
.footer-bottom a:hover { color:var(--blue2); }

/* ── Page hero (category/static) ── */
.page-hero {
  background:linear-gradient(135deg,var(--navy3),var(--navy4));
  border-bottom:1px solid rgba(0,198,255,.12);
  padding:40px 0 36px;
}
.page-hero h1 { font-size:2rem; font-weight:800; color:var(--white); }
.page-hero p  { color:var(--silver); font-size:.95rem; margin-top:8px; }

/* ── Static page content box ── */
.content-box {
  background:var(--navy2); padding:36px; border-radius:16px;
  border:1px solid rgba(0,198,255,.1); font-size:1.03rem;
  line-height:1.8; color:var(--silver2); margin:30px 0;
}
.content-box a { color:var(--blue2); }
.content-box h3 { color:var(--white); font-size:1.1rem; margin:24px 0 10px; }

@media(max-width:900px) {
  .footer-grid { grid-template-columns:1fr 1fr; }
}
@media(max-width:768px) {
  .grid { grid-template-columns:1fr; }
  .hero-banner img { height:220px; }
  .hero-banner { max-height:220px; }
  .article-hero { height:260px; }
  .article-hero-title { font-size:1.4rem; }
  .article-hero-overlay { padding:20px; }
  header .inner { flex-direction:column; align-items:flex-start; }
  .subscribe-cta { flex-direction:column; }
  .footer-grid { grid-template-columns:1fr; gap:24px; }
  .footer-bottom { flex-direction:column; text-align:center; }
}
"""

def ga4_snippet() -> str:
    return f"""<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_ID}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA4_ID}');</script>"""


def adsense_banner() -> str:
    if not ENABLE_ADS:
        return ""
    return f"""<div style="text-align:center;margin:20px 0;">
<ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_PUB_ID}"
     data-ad-slot="{ADSENSE_SLOT_BANNER}" data-ad-format="auto" data-full-width-responsive="true"></ins>
<script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script>
</div>"""


def adsense_article() -> str:
    if not ENABLE_ADS:
        return ""
    return f"""<div style="text-align:center;margin:28px 0;">
<ins class="adsbygoogle" style="display:block;text-align:center" data-ad-client="{ADSENSE_PUB_ID}"
     data-ad-slot="{ADSENSE_SLOT_ARTICLE}" data-ad-layout="in-article" data-ad-format="fluid"></ins>
<script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script>
</div>"""


def adsense_head() -> str:
    if not ENABLE_ADS:
        return ""
    return f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_PUB_ID}" crossorigin="anonymous"></script>'


HEADER_TMPL = """
<!-- Breaking News Ticker -->
<div class="ticker-wrap">
  <div class="container">
    <div class="ticker-inner">
      <span class="ticker-label">Breaking</span>
      <div class="ticker-track">
        <div class="ticker-items">
          {% for a in articles[:8] %}<span>{{ a.title }}</span>{% endfor %}
          {% for a in articles[:8] %}<span>{{ a.title }}</span>{% endfor %}
        </div>
      </div>
    </div>
  </div>
</div>
<header>
  <div class="container">
    <div class="inner">
      <a href="/" class="logo-wrap" style="text-decoration:none;">
        <img src="/images/logo.png" alt="Tech Brief"
             onerror="this.style.display='none'">
        <span class="logo-text">Tech<span>Brief</span></span>
      </a>
      <nav>
        <a href="/">Home</a>
        <a href="/search.html">Search</a>
        {% for cat in categories %}<a href="/category/{{ cat|lower|replace(' & ','-')|replace(' ','-') }}.html">{{ cat.split(' &')[0] }}</a>{% endfor %}
        <a href="/about.html">About</a>
        <a href="/contact.html">Contact</a>
      </nav>
      <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
        <span class="live-dot">Live</span>
        <form class="search-bar" action="/search.html" method="get">
          <input type="text" name="q" placeholder="Search news…">
          <button type="submit">Search</button>
        </form>
      </div>
    </div>
  </div>
</header>
"""

FOOTER_TMPL = """
<footer>
  <div class="container">
    <div class="footer-grid">
      <div class="footer-brand">
        <div class="logo-text">Tech<span>Brief</span></div>
        <p>AI-rewritten tech news updated every hour. Unique full-length articles powered by a local LLM — original insights on the stories that matter.</p>
        <div style="display:flex;gap:14px;margin-top:18px;">
          <a href="/feed.xml" style="color:var(--blue2);font-size:.82rem;font-weight:600;border:1px solid rgba(0,198,255,.3);padding:6px 14px;border-radius:8px;">RSS Feed</a>
          <a href="/contact.html" style="color:var(--blue2);font-size:.82rem;font-weight:600;border:1px solid rgba(0,198,255,.3);padding:6px 14px;border-radius:8px;">Subscribe</a>
        </div>
      </div>
      <div class="footer-col">
        <h4>Sections</h4>
        <a href="/">All News</a>
        <a href="/category/ai-machine-learning.html">AI &amp; ML</a>
        <a href="/category/cybersecurity.html">Cybersecurity</a>
        <a href="/category/startups-vc.html">Startups &amp; VC</a>
        <a href="/category/big-tech.html">Big Tech</a>
        <a href="/category/gadgets-hardware.html">Gadgets</a>
      </div>
      <div class="footer-col">
        <h4>Company</h4>
        <a href="/about.html">About TechBrief</a>
        <a href="/contact.html">Contact Us</a>
        <a href="/search.html">Search</a>
        <a href="/feed.xml">RSS Feed</a>
        <a href="https://learnai.voltixio.com/privacy" target="_blank">Privacy Policy</a>
        <a href="https://learnai.voltixio.com/tos" target="_blank">Terms of Service</a>
      </div>
      <div class="footer-col">
        <h4>Contact</h4>
        <div class="contact-item">📧 <a href="mailto:voltixio_editor@voltixio.com">voltixio_editor@voltixio.com</a></div>
        <div class="contact-item">📞 <span>(443) 853-1405</span></div>
        <div class="contact-item">📍 <span>Windsor Ave, Baltimore MD 21216</span></div>
        <div class="contact-item" style="margin-top:8px;">
          <a href="https://voltixio.com" target="_blank" style="color:var(--blue2);font-size:.82rem;">voltixio.com ↗</a>
        </div>
      </div>
    </div>
    <div class="footer-bottom">
      <span>&copy; {{ year }} {{ site_title }} · A Voltixio Publication · AI-rewritten summaries. Sources linked.</span>
      <div>
        <a href="https://learnai.voltixio.com/privacy" target="_blank">Privacy</a>
        <a href="https://learnai.voltixio.com/tos" target="_blank">Terms</a>
        <a href="/sitemap.xml">Sitemap</a>
      </div>
    </div>
  </div>
</footer>
"""


# ── Page renderers ────────────────────────────────────────────────────────────

def render_homepage(articles: list[dict], categories: list[str]):
    head_extras = ga4_snippet() + "\n  " + adsense_head()
    banner      = adsense_banner()
    # Schema.org JSON-LD for the news site
    jsonld = f"""<script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"NewsMediaOrganization",
    "name":"{SITE_TITLE}","url":"{SITE_URL}","logo":"{SITE_URL}/images/logo.png",
    "contactPoint":{{"@type":"ContactPoint","telephone":"+14438531405","contactType":"editorial"}},
    "address":{{"@type":"PostalAddress","streetAddress":"Windsor Ave","addressLocality":"Baltimore",
      "addressRegion":"MD","postalCode":"21216","addressCountry":"US"}}
  }}
  </script>"""
    tmpl_str = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ site_title }} – Trending Tech News, Updated Hourly</title>
  <meta name="description" content="{{ site_description }}">
  <meta property="og:title"       content="{{ site_title }}">
  <meta property="og:description" content="{{ site_description }}">
  <meta property="og:type"        content="website">
  <meta property="og:url"         content="{{ site_url }}">
  <meta property="og:image"       content="{{ site_url }}/images/hero-banner.jpg">
  <meta name="twitter:card"       content="summary_large_image">
  <meta name="twitter:image"      content="{{ site_url }}/images/hero-banner.jpg">
  <link rel="canonical"           href="{{ site_url }}">
  <link rel="alternate" type="application/rss+xml" title="{{ site_title }}" href="{{ site_url }}/feed.xml">
  """ + head_extras + "\n  " + jsonld + """
  <style>""" + SHARED_CSS + """</style>
</head>
<body>
""" + HEADER_TMPL + """

<!-- ── Hero Banner ───────────────────────────────── -->
<div class="hero-banner">
  <img src="/images/hero-banner.jpg"
       alt="Trending Technology News – Real Time, Real News"
       onerror="this.style.display='none'">
  <div class="hero-banner-gradient"></div>
  <div class="hero-banner-bottom"></div>
</div>

<!-- ── Category Icons Row ─────────────────────────── -->
<div class="cat-icons-row">
  <div class="container">
    <div class="cat-icons-inner">
      <a href="/category/ai-machine-learning.html" class="cat-icon-item" style="text-decoration:none;">
        <div class="icon-circle">🤖</div><span>AI &amp; Innovation</span>
      </a>
      <a href="/category/cybersecurity.html" class="cat-icon-item" style="text-decoration:none;">
        <div class="icon-circle">🔐</div><span>Cybersecurity</span>
      </a>
      <a href="/category/gadgets-hardware.html" class="cat-icon-item" style="text-decoration:none;">
        <div class="icon-circle">📱</div><span>Gadgets &amp; Reviews</span>
      </a>
      <a href="/category/big-tech.html" class="cat-icon-item" style="text-decoration:none;">
        <div class="icon-circle">🏢</div><span>Big Tech</span>
      </a>
      <a href="/category/startups-vc.html" class="cat-icon-item" style="text-decoration:none;">
        <div class="icon-circle">🚀</div><span>Startups &amp; VC</span>
      </a>
      <a href="/category/space-science.html" class="cat-icon-item" style="text-decoration:none;">
        <div class="icon-circle">☁️</div><span>Cloud &amp; Future Tech</span>
      </a>
    </div>
  </div>
</div>

<div class="container">
  """ + banner + """

  <!-- Category filter pills -->
  <div class="section-header" style="margin-top:36px;">
    <h2>Latest Stories</h2>
    <a href="/feed.xml">RSS Feed →</a>
  </div>
  <div class="cats-nav">
    <a href="/" class="active">All</a>
    {% for cat in categories %}
    <a href="/category/{{ cat|lower|replace(' & ','-')|replace(' ','-') }}.html">{{ cat }}</a>
    {% endfor %}
  </div>

  <!-- Article grid -->
  <div class="grid">
    {% for a in articles %}
    <div class="card">
      <a href="{{ a.detail_url }}">
        <div class="card-img-wrap">
          <img src="{{ a.image }}" alt="{{ a.title }}" loading="lazy">
          <div class="card-img-overlay">
            <span class="card-img-cat">{{ a.category }}</span>
            <div>{{ a.title }}</div>
          </div>
        </div>
      </a>
      <div class="card-content">
        <div class="card-excerpt">{{ a.excerpt }}</div>
        <div class="card-meta">🕐 {{ a.pubDate }}</div>
        <a href="{{ a.detail_url }}" class="read-more">Read full story →</a>
      </div>
    </div>
    {% endfor %}
  </div>

  <!-- Subscribe CTA -->
  <div class="subscribe-cta">
    <div class="subscribe-cta-text">
      <h3>🔔 Subscribe &amp; Stay Ahead of the Future</h3>
      <p>Get AI-rewritten tech news delivered to your inbox — the stories that matter, in your language.</p>
    </div>
    <a href="/contact.html" class="cta-btn">Subscribe Now →</a>
  </div>

</div>
""" + FOOTER_TMPL + """
</body>
</html>"""
    t    = Template(tmpl_str)
    html = t.render(site_title=SITE_TITLE, site_description=SITE_DESCRIPTION,
                    site_url=SITE_URL, articles=articles, categories=categories,
                    year=datetime.now().year)
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("✓ index.html")


def render_article_pages(articles: list[dict], categories: list[str]):
    head_extras  = ga4_snippet() + "\n  " + adsense_head()
    ad_in_article = adsense_article()
    tmpl_str = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ a.title }} – {{ site_title }}</title>
  <meta name="description"        content="{{ a.excerpt }}">
  <meta property="og:title"       content="{{ a.title }}">
  <meta property="og:description" content="{{ a.excerpt }}">
  <meta property="og:image"       content="{{ site_url }}{{ a.image }}">
  <meta property="og:url"         content="{{ site_url }}{{ a.detail_url }}">
  <meta name="twitter:card"       content="summary_large_image">
  <link rel="canonical"           href="{{ site_url }}{{ a.detail_url }}">
  <link rel="alternate" type="application/rss+xml" title="{{ site_title }}" href="{{ site_url }}/feed.xml">
  """ + head_extras + """
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    "headline": {{ a.title | tojson }},
    "description": {{ a.excerpt | tojson }},
    "image": "{{ site_url }}{{ a.image }}",
    "datePublished": "{{ a.pubDate }}",
    "url": "{{ site_url }}{{ a.detail_url }}",
    "author": {"@type":"Organization","name":"{{ site_title }}"},
    "publisher": {"@type":"Organization","name":"{{ site_title }}"}
  }
  </script>
  <style>""" + SHARED_CSS + """</style>
</head>
<body class="article-page">
""" + HEADER_TMPL + """
<div class="container">

  <a href="/" class="back-btn">← Back to home</a>

  <!-- Hero image with title + category overlaid -->
  <div class="article-hero">
    <img src="{{ a.image }}" alt="{{ a.title }}">
    <div class="article-hero-overlay">
      <span class="article-hero-cat">{{ a.category }}</span>
      <h1 class="article-hero-title">{{ a.title }}</h1>
      <div class="article-hero-meta">{{ a.pubDate }}</div>
    </div>
  </div>

  <!-- Full rewritten article body -->
  <div class="article-body">
    {% for para in paragraphs %}
    <p>{{ para }}</p>
    {% if loop.index == 2 %}""" + ad_in_article + """{% endif %}
    {% endfor %}
    <div class="source-link">
      <a href="{{ a.link }}" target="_blank" rel="noopener noreferrer">
        Read original source →
      </a>
    </div>
  </div>

</div>
""" + FOOTER_TMPL + """
</body>
</html>"""
    t = Template(tmpl_str)
    for a in articles:
        # Split rewritten content into paragraphs at blank lines or double-newlines
        raw_paras = re.split(r"\n{2,}", a["full_content"])
        paragraphs = [p.replace("\n", " ").strip() for p in raw_paras if p.strip()]
        if not paragraphs:
            paragraphs = [a["full_content"]]

        html = t.render(site_title=SITE_TITLE, site_url=SITE_URL,
                        a=a, paragraphs=paragraphs, categories=categories,
                        year=datetime.now().year)
        fname = os.path.join(OUTPUT_DIR, "article", f"{a['uid']}-{a['slug']}.html")
        with open(fname, "w", encoding="utf-8") as f:
            f.write(html)
    print(f"✓ {len(articles)} article pages")


def render_category_pages(articles: list[dict], categories: list[str]):
    tmpl_str = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ cat }} – {{ site_title }}</title>
  <meta name="description" content="{{ cat }} tech news, AI-rewritten hourly.">
  <link rel="canonical" href="{{ site_url }}/category/{{ cat_slug }}.html">
  <style>""" + SHARED_CSS + """</style>
</head>
<body>
<header>
  <div class="container"><div class="inner">
    <a href="/" class="logo-wrap" style="text-decoration:none;">
      <img src="/images/logo.png" alt="Tech Brief" style="height:40px;" onerror="this.style.display='none'">
      <span class="logo-text">Tech<span style="color:var(--blue2);">Brief</span></span>
    </a>
    <nav>
      <a href="/">Home</a><a href="/search.html">Search</a>
      {% for c in categories %}<a href="/category/{{ c|lower|replace(' & ','-')|replace(' ','-') }}.html"
        {% if c == cat %}style="color:var(--blue2);"{% endif %}>{{ c.split(' &')[0] }}</a>{% endfor %}
      <a href="/about.html">About</a>
    </nav>
    <span class="live-dot">Live</span>
  </div></div>
</header>
<div class="page-hero">
  <div class="container">
    <h1>{{ cat }}</h1>
    <p>AI-rewritten {{ cat }} news — updated every hour</p>
  </div>
</div>
<div class="container">
  <div class="section-header">
    <h2>{{ cat_articles|length }} Stories</h2>
    <a href="/">← All news</a>
  </div>
  <div class="grid">
    {% for a in cat_articles %}
    <div class="card">
      <a href="{{ a.detail_url }}">
        <div class="card-img-wrap">
          <img src="{{ a.image }}" alt="{{ a.title }}" loading="lazy">
          <div class="card-img-overlay">
            <span class="card-img-cat">{{ a.category }}</span>
            <div>{{ a.title }}</div>
          </div>
        </div>
      </a>
      <div class="card-content">
        <div class="card-excerpt">{{ a.excerpt }}</div>
        <div class="card-meta">🕐 {{ a.pubDate }}</div>
        <a href="{{ a.detail_url }}" class="read-more">Read full story →</a>
      </div>
    </div>
    {% endfor %}
    {% if not cat_articles %}
    <p style="color:var(--silver);padding:40px 0;">No articles in this category yet. Check back soon.</p>
    {% endif %}
  </div>
</div>
""" + FOOTER_TMPL + """
</body>
</html>"""
    t = Template(tmpl_str)
    for cat in categories:
        cat_slug     = cat.lower().replace(" & ", "-").replace(" ", "-")
        cat_articles = [a for a in articles if a["category"] == cat]
        html = t.render(site_title=SITE_TITLE, site_url=SITE_URL, cat=cat,
                        cat_slug=cat_slug, cat_articles=cat_articles,
                        categories=categories, year=datetime.now().year)
        with open(os.path.join(OUTPUT_DIR, "category", f"{cat_slug}.html"), "w", encoding="utf-8") as f:
            f.write(html)
    print(f"✓ {len(categories)} category pages")


def render_search_page(categories: list[str]):
    year = datetime.now().year
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Search – {SITE_TITLE}</title>
  {ga4_snippet()}
  <style>{SHARED_CSS}</style>
</head>
<body>
<div class="ticker-wrap" style="background:linear-gradient(90deg,#0a84ff,#00c6ff);">
  <div class="container"><div class="ticker-inner">
    <span class="ticker-label" style="color:#0a84ff;">Search</span>
    <div style="color:white;font-size:.82rem;padding:0 20px;">Find any article across all tech categories</div>
  </div></div>
</div>
<header>
  <div class="container"><div class="inner">
    <a href="/" class="logo-wrap" style="text-decoration:none;">
      <img src="/images/logo.png" alt="Tech Brief" style="height:40px;" onerror="this.style.display='none'">
      <span class="logo-text">Tech<span>Brief</span></span>
    </a>
    <nav>
      <a href="/">Home</a><a href="/search.html" style="color:var(--blue2);">Search</a>
      <a href="/about.html">About</a><a href="/contact.html">Contact</a>
    </nav>
    <span class="live-dot">Live</span>
  </div></div>
</header>
<div class="page-hero">
  <div class="container">
    <h1>Search Articles</h1>
    <p>Search across all AI-rewritten tech articles — updated every hour</p>
  </div>
</div>
<div class="container" style="max-width:860px;padding-top:0;">
  <input type="text" id="search-input" placeholder="Search AI, cybersecurity, startups, gadgets…" autofocus>
  <div id="search-results"></div>
</div>
<footer>
  <div class="container">
    <div class="footer-bottom">
      <span>&copy; {year} {SITE_TITLE} · A Voltixio Publication</span>
      <div><a href="/">Home</a><a href="/about.html">About</a><a href="/feed.xml">RSS</a>
        <a href="https://learnai.voltixio.com/privacy" target="_blank">Privacy</a>
        <a href="https://learnai.voltixio.com/tos" target="_blank">Terms</a>
      </div>
    </div>
  </div>
</footer>
<script src="https://cdnjs.cloudflare.com/ajax/libs/lunr.js/2.3.9/lunr.min.js"></script>
<script>
(async () => {{
  const data = await (await fetch('/search.json')).json();
  const idx  = lunr(function() {{
    this.ref('id');
    this.field('title', {{ boost: 10 }});
    this.field('excerpt');
    this.field('category', {{ boost: 3 }});
    data.forEach(d => this.add(d));
  }});
  const resultsEl = document.getElementById('search-results');
  const inputEl   = document.getElementById('search-input');
  const q0 = new URLSearchParams(window.location.search).get('q') || '';
  if (q0) {{ inputEl.value = q0; doSearch(q0); }}
  inputEl.addEventListener('input', () => doSearch(inputEl.value));
  function doSearch(query) {{
    query = query.trim();
    if (!query) {{ resultsEl.innerHTML = ''; return; }}
    let results;
    try {{ results = idx.search(query + '~1'); }} catch(e) {{ results = []; }}
    if (!results.length) {{
      resultsEl.innerHTML = '<div class="no-results">No articles found for <strong style="color:var(--blue2);">' + query + '</strong>.</div>';
      return;
    }}
    resultsEl.innerHTML = results.map(r => {{
      const a = data.find(d => d.id === r.ref);
      return `<div class="search-result-item">
        <h3><a href="${{a.url}}">${{a.title}}</a></h3>
        <p>${{a.excerpt}}</p>
        <span style="font-size:.75rem;color:var(--silver);margin-top:8px;display:block;">
          <span style="color:var(--blue2);">${{a.category}}</span> · ${{a.pubDate}}
        </span>
      </div>`;
    }}).join('');
  }}
}})();
</script>
</body>
</html>"""
    with open(os.path.join(OUTPUT_DIR, "search.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("✓ search.html")


def render_search_index(articles: list[dict]):
    idx = [{"id": a["uid"], "title": a["title"], "excerpt": a["excerpt"],
             "category": a["category"], "url": a["detail_url"], "pubDate": a["pubDate"]}
           for a in articles]
    with open(os.path.join(OUTPUT_DIR, "search.json"), "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False)
    print("✓ search.json")


def render_sitemap(articles: list[dict]):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
             f'  <url><loc>{SITE_URL}/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>',
             f'  <url><loc>{SITE_URL}/search.html</loc><changefreq>hourly</changefreq><priority>0.8</priority></url>']
    for a in articles:
        lines.append(f'  <url><loc>{SITE_URL}{a["detail_url"]}</loc><lastmod>{today}</lastmod>'
                     f'<changefreq>monthly</changefreq><priority>0.7</priority></url>')
    lines.append("</urlset>")
    with open(os.path.join(OUTPUT_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("✓ sitemap.xml")


def render_rss_feed(articles: list[dict]):
    now_rfc = formatdate(usegmt=True)
    items   = "\n".join(f"""  <item>
    <title><![CDATA[{a['title']}]]></title>
    <link>{SITE_URL}{a['detail_url']}</link>
    <guid isPermaLink="true">{SITE_URL}{a['detail_url']}</guid>
    <pubDate>{a['pubDate']}</pubDate>
    <category>{a['category']}</category>
    <description><![CDATA[{a['excerpt']}]]></description>
  </item>""" for a in articles)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{SITE_TITLE}</title>
  <link>{SITE_URL}</link>
  <description>{SITE_DESCRIPTION}</description>
  <language>en-us</language>
  <lastBuildDate>{now_rfc}</lastBuildDate>
  <atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
{items}
</channel>
</rss>"""
    with open(os.path.join(OUTPUT_DIR, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(xml)
    print("✓ feed.xml")


def render_robots_txt():
    with open(os.path.join(OUTPUT_DIR, "robots.txt"), "w") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    print("✓ robots.txt")


def render_static_pages():
    year = datetime.now().year
    nav_mini = f"""
<header>
  <div class="container"><div class="inner">
    <a href="/" class="logo-wrap" style="text-decoration:none;">
      <img src="/images/logo.png" alt="Tech Brief" style="height:40px;" onerror="this.style.display='none'">
      <span class="logo-text">Tech<span>Brief</span></span>
    </a>
    <nav>
      <a href="/">Home</a><a href="/search.html">Search</a>
      <a href="/about.html">About</a><a href="/contact.html">Contact</a>
    </nav>
    <span class="live-dot">Live</span>
  </div></div>
</header>"""
    footer_mini = f"""
<footer>
  <div class="container">
    <div class="footer-bottom">
      <span>&copy; {year} {SITE_TITLE} · A Voltixio Publication</span>
      <div>
        <a href="/">Home</a><a href="/about.html">About</a><a href="/feed.xml">RSS</a>
        <a href="https://learnai.voltixio.com/privacy" target="_blank">Privacy</a>
        <a href="https://learnai.voltixio.com/tos" target="_blank">Terms</a>
      </div>
    </div>
  </div>
</footer>"""

    about = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>About – {SITE_TITLE}</title>
  {ga4_snippet()}
  <style>{SHARED_CSS}</style>
</head>
<body>
{nav_mini}
<div class="page-hero">
  <div class="container">
    <h1>About {SITE_TITLE}</h1>
    <p>AI-rewritten tech news from Baltimore, MD · A Voltixio Publication</p>
  </div>
</div>
<div class="container" style="max-width:860px;">
  <div class="content-box">
    <p><strong style="color:var(--white);">{SITE_TITLE}</strong> automatically aggregates the latest technology
      news from leading sources around the web — including TechCrunch, Ars Technica, VentureBeat, The Hacker News,
      OpenAI, Anthropic, and more — then uses a local large language model (Ollama with gemma2:9b) to rewrite each
      article into a unique, engaging, full-length ~500-word piece. Updated every hour. Plagiarism-free.</p>
    <h3>What We Cover</h3>
    <p>AI &amp; Machine Learning · Cybersecurity · Startups &amp; VC · Big Tech · Gadgets &amp; Hardware · Space &amp; Science</p>
    <h3>Our Technology</h3>
    <p>Every article is re-crafted by a locally-hosted LLM — no data leaves our server, no third-party AI APIs.
      Original sources are always linked at the bottom of each article. Unique stock photography is auto-generated
      per article using a deterministic image pipeline.</p>
    <h3>Part of Voltixio</h3>
    <p>TechBrief is a publication by <a href="https://voltixio.com" target="_blank">Voltixio</a>, a digital
      media &amp; AI company based in Baltimore, MD. We build automated content platforms that deliver real value
      to real readers.</p>
    <p style="margin-top:20px;">
      <a href="/feed.xml" style="margin-right:16px;">📡 Subscribe via RSS →</a>
      <a href="/contact.html">✉️ Contact us →</a>
    </p>
  </div>
</div>
{footer_mini}
</body></html>"""

    contact = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Contact – {SITE_TITLE}</title>
  {ga4_snippet()}
  <style>{SHARED_CSS}
  .contact-form input, .contact-form textarea {{
    width:100%; padding:13px 16px; border-radius:10px; font-size:.95rem;
    background:var(--navy3); border:1px solid rgba(0,198,255,.2); color:var(--silver2);
    outline:none; transition:border .2s; margin-bottom:16px; font-family:inherit;
  }}
  .contact-form input:focus, .contact-form textarea:focus {{ border-color:var(--blue2); }}
  .contact-form textarea {{ height:130px; resize:vertical; }}
  .contact-form button {{
    background:linear-gradient(135deg,var(--blue),var(--blue2));
    color:white; font-weight:700; font-size:.95rem; padding:13px 32px;
    border:none; border-radius:10px; cursor:pointer; width:100%;
    transition:opacity .2s;
  }}
  .contact-form button:hover {{ opacity:.88; }}
  </style>
</head>
<body>
{nav_mini}
<div class="page-hero">
  <div class="container">
    <h1>Contact TechBrief</h1>
    <p>Questions, tips, partnerships, corrections — we read every message</p>
  </div>
</div>
<div class="container" style="max-width:900px;">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:0;">
    <div class="content-box" style="margin:30px 0;">
      <h3 style="margin-top:0;">Get in Touch</h3>
      <p style="margin-bottom:20px;">For editorial questions, corrections, story tips, advertising enquiries,
        or partnership opportunities, reach out via any of the channels below.</p>
      <div class="contact-item" style="margin-bottom:14px;">
        📧 &nbsp;<a href="mailto:voltixio_editor@voltixio.com">voltixio_editor@voltixio.com</a>
      </div>
      <div class="contact-item" style="margin-bottom:14px;">
        📞 &nbsp;<a href="tel:+14438531405">(443) 853-1405</a>
      </div>
      <div class="contact-item" style="margin-bottom:14px;">
        📍 &nbsp;Windsor Ave, Baltimore MD 21216
      </div>
      <div class="contact-item" style="margin-bottom:14px;">
        🌐 &nbsp;<a href="https://voltixio.com" target="_blank">voltixio.com</a>
      </div>
      <p style="margin-top:20px;font-size:.85rem;color:var(--silver);">
        We typically respond within 48 hours.
      </p>
    </div>
    <div class="content-box" style="margin:30px 0;">
      <h3 style="margin-top:0;">Send a Message</h3>
      <form class="contact-form" action="mailto:voltixio_editor@voltixio.com" method="post" enctype="text/plain">
        <input type="text" name="name" placeholder="Your name" required>
        <input type="email" name="email" placeholder="Your email" required>
        <input type="text" name="subject" placeholder="Subject">
        <textarea name="message" placeholder="Your message…" required></textarea>
        <button type="submit">Send Message →</button>
      </form>
    </div>
  </div>
</div>
{footer_mini}
</body></html>"""

    with open(os.path.join(OUTPUT_DIR, "about.html"), "w", encoding="utf-8") as f:
        f.write(about)
    with open(os.path.join(OUTPUT_DIR, "contact.html"), "w", encoding="utf-8") as f:
        f.write(contact)
    print("✓ about.html + contact.html")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print("=" * 56)
    print(f"  {SITE_TITLE} – build  {datetime.now():%Y-%m-%d %H:%M}")
    print(f"  Ollama model: {OLLAMA_MODEL}  @ {OLLAMA_URL}")
    print("=" * 56)

    cache    = load_cache()
    articles = parse_rss(cache)

    if not articles:
        print("❌  No articles found. Check RSS_URL / uglyfeed container.")
        return

    print(f"\nAttaching images…")
    for a in articles:
        a["image"] = fetch_or_create_image(a["title"], a["uid"] + "-" + a["slug"][:20])

    categories = sorted(set(a["category"] for a in articles))
    print(f"\nBuilding {len(articles)} pages across {len(categories)} categories…")

    render_homepage(articles, categories)
    render_article_pages(articles, categories)
    render_category_pages(articles, categories)
    render_search_page(categories)
    render_search_index(articles)
    render_sitemap(articles)
    render_rss_feed(articles)
    render_robots_txt()
    render_static_pages()

    elapsed = time.time() - t0
    print("=" * 56)
    print(f"  ✅  Build complete in {elapsed:.1f}s → {OUTPUT_DIR}")
    print("=" * 56)


if __name__ == "__main__":
    main()
