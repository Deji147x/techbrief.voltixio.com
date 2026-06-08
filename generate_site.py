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
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
       background:#f5f7fa; color:#1a202c; line-height:1.6; }
a { text-decoration:none; }
.container { max-width:1200px; margin:0 auto; padding:0 20px; }

/* ── Header ── */
header { background:#1a202c; color:white; padding:16px 0; }
header .inner { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px; }
header h1 { font-size:1.6rem; }
header h1 a { color:white; }
nav a { color:#a0aec0; margin-right:18px; font-size:.9rem; }
nav a:hover { color:white; }
.search-bar { display:flex; gap:8px; }
.search-bar input { padding:6px 12px; border-radius:6px; border:none; font-size:.9rem; width:200px; }
.search-bar button { padding:6px 14px; background:#667eea; color:white; border:none; border-radius:6px; cursor:pointer; }

/* ── Hero ── */
.hero { text-align:center; padding:50px 20px;
        background:linear-gradient(135deg,#667eea,#764ba2); color:white;
        border-radius:12px; margin:30px 0 40px; }
.hero h2 { font-size:2.4rem; margin-bottom:8px; }
.hero p  { font-size:1.1rem; opacity:.9; }

/* ── Grid ── */
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:28px; margin-bottom:50px; }

/* ── Cards with image text overlay ── */
.card { background:white; border-radius:12px; overflow:hidden;
        box-shadow:0 2px 8px rgba(0,0,0,.08); transition:transform .2s,box-shadow .2s; }
.card:hover { transform:translateY(-4px); box-shadow:0 8px 20px rgba(0,0,0,.14); }
.card-img-wrap { position:relative; height:210px; overflow:hidden; }
.card-img-wrap img { width:100%; height:100%; object-fit:cover; transition:transform .4s; }
.card:hover .card-img-wrap img { transform:scale(1.04); }
.card-img-overlay {
  position:absolute; bottom:0; left:0; right:0;
  background:linear-gradient(to top, rgba(0,0,0,.82) 0%, rgba(0,0,0,.35) 60%, transparent 100%);
  padding:36px 16px 14px;
  color:white; font-size:.95rem; font-weight:600; line-height:1.35;
}
.card-img-cat {
  display:inline-block; background:rgba(102,126,234,.9); color:white;
  font-size:.65rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em;
  padding:2px 9px; border-radius:20px; margin-bottom:6px;
}
.card-content { padding:16px 20px 20px; }
.card-excerpt { color:#4a5568; font-size:.92rem; margin-bottom:12px; }
.card-meta    { font-size:.78rem; color:#718096; margin-bottom:12px; }
.read-more { display:inline-block; background:#667eea; color:white; padding:7px 16px; border-radius:6px; font-size:.85rem; }
.read-more:hover { background:#5a67d8; }

/* ── Category nav ── */
.cats-nav { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:30px; }
.cats-nav a { background:white; border:1px solid #e2e8f0; color:#4a5568; padding:6px 16px; border-radius:20px; font-size:.85rem; }
.cats-nav a:hover, .cats-nav a.active { background:#667eea; color:white; border-color:#667eea; }

/* ── Article page ── */
.article-page .container { max-width:820px; }

/* Hero image with overlaid title */
.article-hero {
  position:relative; width:100%; border-radius:14px; overflow:hidden;
  margin:28px 0 32px; height:420px;
}
.article-hero img { width:100%; height:100%; object-fit:cover; display:block; }
.article-hero-overlay {
  position:absolute; inset:0;
  background:linear-gradient(to top, rgba(0,0,0,.85) 0%, rgba(0,0,0,.45) 45%, rgba(0,0,0,.1) 100%);
  display:flex; flex-direction:column; justify-content:flex-end; padding:36px 32px;
  color:white;
}
.article-hero-cat {
  display:inline-block; background:rgba(102,126,234,.95); color:white;
  font-size:.72rem; font-weight:700; text-transform:uppercase; letter-spacing:.08em;
  padding:4px 12px; border-radius:20px; margin-bottom:12px; width:fit-content;
}
.article-hero-title { font-size:2rem; font-weight:700; line-height:1.25; text-shadow:0 2px 6px rgba(0,0,0,.4); }
.article-hero-meta  { margin-top:10px; font-size:.85rem; opacity:.85; }

/* Article body */
.article-body {
  background:white; padding:36px; border-radius:14px;
  box-shadow:0 2px 10px rgba(0,0,0,.08); font-size:1.08rem;
  line-height:1.8; margin-bottom:28px;
}
.article-body p { margin-bottom:1.4em; }
.article-body p:last-child { margin-bottom:0; }
.source-link { text-align:center; margin-top:28px; padding-top:22px; border-top:1px solid #e2e8f0; }
.source-link a { color:#667eea; font-size:.9rem; }
.back-btn { display:inline-block; background:#667eea; color:white; padding:9px 20px; border-radius:8px; margin:24px 0 0; }
.back-btn:hover { background:#5a67d8; }

/* ── Search page ── */
#search-input { width:100%; padding:14px 18px; font-size:1.1rem;
                border:2px solid #e2e8f0; border-radius:10px; margin:24px 0 20px; outline:none; }
#search-input:focus { border-color:#667eea; }
.search-result-item { background:white; padding:20px; border-radius:10px; margin-bottom:16px; box-shadow:0 1px 5px rgba(0,0,0,.07); }
.search-result-item h3 a { color:#1a202c; font-size:1.05rem; }
.search-result-item h3 a:hover { color:#667eea; }
.search-result-item p { color:#4a5568; font-size:.9rem; margin-top:6px; }
.no-results { text-align:center; color:#718096; padding:50px; }

/* ── Footer ── */
footer { background:#1a202c; color:#718096; text-align:center; padding:30px; margin-top:40px; font-size:.85rem; }
footer a { color:#a0aec0; margin:0 8px; }
footer a:hover { color:white; }

@media(max-width:768px) {
  .grid { grid-template-columns:1fr; }
  .hero h2 { font-size:1.7rem; }
  .article-hero { height:280px; }
  .article-hero-title { font-size:1.4rem; }
  .article-hero-overlay { padding:20px; }
  header .inner { flex-direction:column; align-items:flex-start; }
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
<header>
  <div class="container">
    <div class="inner">
      <h1><a href="/">{{ site_title }}</a></h1>
      <nav>
        <a href="/">Home</a>
        <a href="/search.html">Search</a>
        {% for cat in categories %}<a href="/category/{{ cat|lower|replace(' & ','-')|replace(' ','-') }}.html">{{ cat }}</a>{% endfor %}
        <a href="/about.html">About</a>
      </nav>
      <form class="search-bar" action="/search.html" method="get">
        <input type="text" name="q" placeholder="Search articles…">
        <button type="submit">Go</button>
      </form>
    </div>
  </div>
</header>
"""

FOOTER_TMPL = """
<footer>
  <p>&copy; {{ year }} {{ site_title }}. AI‑rewritten summaries are unique. Sources linked.</p>
  <p style="margin-top:8px;">
    <a href="/">Home</a> | <a href="/search.html">Search</a> |
    <a href="/about.html">About</a> | <a href="/contact.html">Contact</a> |
    <a href="/feed.xml">RSS Feed</a>
  </p>
</footer>
"""


# ── Page renderers ────────────────────────────────────────────────────────────

def render_homepage(articles: list[dict], categories: list[str]):
    head_extras = ga4_snippet() + "\n  " + adsense_head()
    banner      = adsense_banner()
    tmpl_str = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ site_title }} – AI‑Rewritten Tech News</title>
  <meta name="description" content="{{ site_description }}">
  <meta property="og:title"       content="{{ site_title }}">
  <meta property="og:description" content="{{ site_description }}">
  <meta property="og:type"        content="website">
  <meta property="og:url"         content="{{ site_url }}">
  <meta name="twitter:card"       content="summary_large_image">
  <link rel="canonical"           href="{{ site_url }}">
  <link rel="alternate" type="application/rss+xml" title="{{ site_title }}" href="{{ site_url }}/feed.xml">
  """ + head_extras + """
  <style>""" + SHARED_CSS + """</style>
</head>
<body>
""" + HEADER_TMPL + """
<div class="container">
  <div class="hero">
    <h2>AI‑Rewritten Tech News, Updated Hourly</h2>
    <p>Unique full articles powered by a local LLM – no plagiarism, just original insights.</p>
  </div>
  """ + banner + """
  <div class="cats-nav">
    <a href="/" class="active">All</a>
    {% for cat in categories %}
    <a href="/category/{{ cat|lower|replace(' & ','-')|replace(' ','-') }}.html">{{ cat }}</a>
    {% endfor %}
  </div>
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
        <div class="card-meta">{{ a.pubDate }}</div>
        <a href="{{ a.detail_url }}" class="read-more">Read full story →</a>
      </div>
    </div>
    {% endfor %}
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
  <meta name="description" content="{{ cat }} news, AI-rewritten hourly.">
  <link rel="canonical" href="{{ site_url }}/category/{{ cat_slug }}.html">
  <style>""" + SHARED_CSS + """</style>
</head>
<body>
""" + HEADER_TMPL + """
<div class="container">
  <h2 style="margin:30px 0 24px;font-size:1.8rem;">{{ cat }}</h2>
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
        <div class="card-meta">{{ a.pubDate }}</div>
        <a href="{{ a.detail_url }}" class="read-more">Read full story →</a>
      </div>
    </div>
    {% endfor %}
    {% if not cat_articles %}
    <p style="color:#718096;padding:20px 0;">No articles in this category yet.</p>
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
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Search – {SITE_TITLE}</title>
  <style>{SHARED_CSS}</style>
</head>
<body>
<header>
  <div class="container"><div class="inner">
    <h1><a href="/">{SITE_TITLE}</a></h1>
    <nav><a href="/">Home</a> <a href="/search.html">Search</a> <a href="/about.html">About</a></nav>
  </div></div>
</header>
<div class="container">
  <h2 style="margin-top:30px;font-size:1.8rem;">Search Articles</h2>
  <input type="text" id="search-input" placeholder="Type to search…" autofocus>
  <div id="search-results"></div>
</div>
<footer>
  <p>&copy; {datetime.now().year} {SITE_TITLE}.
    <a href="/">Home</a> | <a href="/about.html">About</a> | <a href="/feed.xml">RSS</a>
  </p>
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
      resultsEl.innerHTML = '<div class="no-results">No articles found for <strong>' + query + '</strong>.</div>';
      return;
    }}
    resultsEl.innerHTML = results.map(r => {{
      const a = data.find(d => d.id === r.ref);
      return `<div class="search-result-item">
        <h3><a href="${{a.url}}">${{a.title}}</a></h3>
        <p>${{a.excerpt}}</p>
        <span style="font-size:.75rem;color:#a0aec0;">${{a.category}} · ${{a.pubDate}}</span>
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

    about = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>About – {SITE_TITLE}</title><style>{SHARED_CSS}</style></head>
<body>
<header><div class="container"><div class="inner">
  <h1><a href="/">{SITE_TITLE}</a></h1>
  <nav><a href="/">Home</a><a href="/search.html">Search</a><a href="/about.html">About</a><a href="/contact.html">Contact</a></nav>
</div></div></header>
<div class="container" style="max-width:760px;padding:40px 20px;">
  <h2 style="font-size:2rem;margin-bottom:20px;">About {SITE_TITLE}</h2>
  <div style="background:white;padding:32px;border-radius:14px;box-shadow:0 2px 8px rgba(0,0,0,.08);line-height:1.8;font-size:1.05rem;">
    <p style="margin-bottom:16px;"><strong>{SITE_TITLE}</strong> automatically aggregates the latest tech news
      from across the web and uses a local large language model (Ollama) to rewrite each article into a
      unique, engaging, full-length piece — plagiarism-free, updated every hour.</p>
    <p style="margin-bottom:16px;">We cover AI &amp; Machine Learning, Cybersecurity, Startups &amp; VC,
      Big Tech, Gadgets &amp; Hardware, and Space &amp; Science.</p>
    <p style="margin-bottom:16px;">All content is AI-generated from publicly available sources.
      Original sources are always linked. No tracking. No ads. No cookies.</p>
    <p><a href="/feed.xml" style="color:#667eea;">Subscribe via RSS →</a></p>
  </div>
</div>
<footer><p>&copy; {year} {SITE_TITLE}. <a href="/">Home</a> | <a href="/contact.html">Contact</a> | <a href="/feed.xml">RSS</a></p></footer>
</body></html>"""

    contact = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Contact – {SITE_TITLE}</title><style>{SHARED_CSS}</style></head>
<body>
<header><div class="container"><div class="inner">
  <h1><a href="/">{SITE_TITLE}</a></h1>
  <nav><a href="/">Home</a><a href="/search.html">Search</a><a href="/about.html">About</a><a href="/contact.html">Contact</a></nav>
</div></div></header>
<div class="container" style="max-width:760px;padding:40px 20px;">
  <h2 style="font-size:2rem;margin-bottom:20px;">Contact</h2>
  <div style="background:white;padding:32px;border-radius:14px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <p style="margin-bottom:16px;">For questions, corrections, or partnership enquiries:</p>
    <p style="margin-bottom:16px;"><strong>Email:</strong> <a href="mailto:{CONTACT_EMAIL}" style="color:#667eea;">{CONTACT_EMAIL}</a></p>
    <p style="color:#718096;font-size:.9rem;">We typically respond within 48 hours.</p>
  </div>
</div>
<footer><p>&copy; {year} {SITE_TITLE}. <a href="/">Home</a> | <a href="/about.html">About</a> | <a href="/feed.xml">RSS</a></p></footer>
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
