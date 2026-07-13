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
RSS_URL           = "/root/uglyfeed/output/uglyfeed.xml"
OUTPUT_DIR        = "/var/www/techbrief_static"
ARTICLES_PER_PAGE = 20
SITE_URL          = "https://techbrief.voltixio.com"
SITE_TITLE        = "AI Tech Brief"
SITE_DESCRIPTION  = "Breaking tech news and insights, updated hourly."
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
OLLAMA_MODEL      = "llama3.2"                 # lighter model, stable across all articles
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


# ── Branded image generation (Pillow) ────────────────────────────────────────

# Category gradient palettes  [top-left, bottom-right, accent]
CAT_PALETTES = {
    "AI & Machine Learning": [(5, 15, 40),   (15, 5, 50),   (0, 198, 255)],
    "Cybersecurity":         [(30, 5, 5),    (10, 0, 20),   (255, 60, 60)],
    "Startups & VC":         [(5, 25, 15),   (5, 10, 35),   (0, 230, 130)],
    "Big Tech":              [(5, 10, 35),   (15, 5, 45),   (10, 132, 255)],
    "Gadgets & Hardware":    [(20, 10, 5),   (5, 15, 30),   (255, 170, 0)],
    "Space & Science":       [(5, 5, 30),    (20, 5, 40),   (180, 100, 255)],
    "Technology":            [(5, 12, 30),   (10, 8, 40),   (0, 198, 255)],
}

def _wrap_text(text: str, max_chars: int) -> list[str]:
    """Wrap text into lines of at most max_chars characters."""
    words  = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:4]   # max 4 lines on card


def _image_valid(path: str) -> bool:
    """Return True only if path exists and is a real image (>5 KB)."""
    return os.path.exists(path) and os.path.getsize(path) > 5120


def _load_font(size: int):
    """Load best available bold font at given size."""
    from PIL import ImageFont
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _overlay_text_on_image(img, title: str, category: str, accent: tuple):
    """Draw category badge + title + branding onto a PIL Image in-place."""
    from PIL import ImageDraw, ImageFont
    W, H = img.size
    draw = ImageDraw.Draw(img)

    font_title = _load_font(50)
    font_cat   = _load_font(20)
    font_brand = _load_font(22)
    font_small = _load_font(15)

    # Dark gradient scrim over bottom 55% so text pops on any background
    try:
        from PIL import Image as _Img
        scrim = _Img.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(scrim)
        scrim_top = int(H * 0.35)
        for sy in range(scrim_top, H):
            t = (sy - scrim_top) / (H - scrim_top)
            a = int(t ** 0.7 * 215)
            sd.line([(0, sy), (W, sy)], fill=(4, 10, 24, a))
        img.paste(_Img.fromarray(
            __import__("numpy", fromlist=["array"]).array(scrim)
        ), mask=scrim.split()[3])
    except Exception:
        # Fallback: simple dark rectangle on lower half
        draw.rectangle([(0, H//2), (W, H)], fill=(4, 10, 24))

    # Category badge
    cat_label = category.upper()
    badge_x, badge_y = 40, 36
    badge_w = len(cat_label) * 12 + 28
    draw.rounded_rectangle(
        [(badge_x, badge_y), (badge_x + badge_w, badge_y + 32)],
        radius=5, fill=(accent[0], accent[1], accent[2])
    )
    draw.text((badge_x + 14, badge_y + 6), cat_label, font=font_cat, fill=(255, 255, 255))

    # Title
    lines  = _wrap_text(title, 38)[:3]
    line_h = 60
    total  = len(lines) * line_h
    text_y = H - total - 72
    for i, line in enumerate(lines):
        y = text_y + i * line_h
        draw.text((42 + 2, y + 2), line, font=font_title, fill=(0, 0, 0))
        draw.text((42,     y),     line, font=font_title, fill=(255, 255, 255))

    # Accent bar + branding
    draw.rectangle([(0, H - 4), (W, H)], fill=(accent[0], accent[1], accent[2]))
    draw.text((42, H - 36), "techbrief.voltixio.com", font=font_small, fill=(160, 200, 235))
    brand = "TechBrief"
    draw.text((W - 150, H - 40), brand, font=font_brand, fill=(accent[0], accent[1], accent[2]))


def fetch_og_image_url(article_url: str) -> str:
    """Scrape og:image meta tag from the original article URL (3-second timeout)."""
    if not article_url or article_url == "#":
        return ""
    try:
        import urllib.request, re as _re
        req = urllib.request.Request(
            article_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TechBriefBot/1.0; +https://techbrief.voltixio.com)"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            chunk = resp.read(40000).decode("utf-8", errors="ignore")
        m = (_re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https?://[^"\'>\s]+)', chunk) or
             _re.search(r'<meta[^>]+content=["\'](https?://[^"\'>\s]+)[^>]+property=["\']og:image["\']', chunk))
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def build_article_image(article_url: str, rss_img_url: str, title: str, category: str, slug: str) -> str:
    """
    Best-effort article card image (1200×630 JPEG).
    Priority: og:image from article → RSS enclosure/media → branded Pillow fallback.
    Returns web-relative path /images/<slug>.jpg.
    """
    fname = f"{slug}.jpg"
    path  = os.path.join(OUTPUT_DIR, "images", fname)

    # Cache hit — only re-use if file is a real image (>5 KB)
    if _image_valid(path):
        return f"/images/{fname}"

    # ── Try to get a real photo from the source article ───────────────────────
    source_url = rss_img_url or fetch_og_image_url(article_url)

    if source_url:
        try:
            import urllib.request, io
            from PIL import Image
            req = urllib.request.Request(
                source_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; TechBriefBot/1.0)"}
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                raw = resp.read()

            src = Image.open(io.BytesIO(raw)).convert("RGB")
            W, H = 1200, 630
            # Centre-crop to 1200×630
            sr = src.width / src.height
            tr = W / H
            if sr > tr:
                nh = H; nw = int(H * sr)
            else:
                nw = W; nh = int(W / sr)
            src = src.resize((nw, nh), Image.LANCZOS)
            src = src.crop(((nw - W) // 2, (nh - H) // 2,
                             (nw - W) // 2 + W, (nh - H) // 2 + H))

            palette = CAT_PALETTES.get(category, CAT_PALETTES["Technology"])
            _, _, accent = palette
            src = src.convert("RGBA")
            _overlay_text_on_image(src, title, category, accent)
            src = src.convert("RGB")
            src.save(path, "JPEG", quality=88, optimize=True)
            print(f"  🖼  real photo [{category[:18]}] {title[:45]}")
            return f"/images/{fname}"
        except Exception as e:
            print(f"  ⚠ photo fetch failed ({e}) — using designed fallback")

    # ── Branded Pillow fallback (no external photo needed) ────────────────────
    try:
        from PIL import Image, ImageDraw
        import math, random as _rand

        W, H = 1200, 630
        palette = CAT_PALETTES.get(category, CAT_PALETTES["Technology"])
        c1, c2, accent = palette

        img  = Image.new("RGB", (W, H), c1)
        draw = ImageDraw.Draw(img)

        # Diagonal gradient
        for y in range(H):
            t = y / H
            r = int(c1[0] * (1 - t) + c2[0] * t)
            g = int(c1[1] * (1 - t) + c2[1] * t)
            b = int(c1[2] * (1 - t) + c2[2] * t)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # Large glowing circle (top-right)
        cx, cy = W - 160, -60
        for radius in range(320, 40, -8):
            fade = max(0, int(50 * (1 - radius / 320)))
            col  = (
                min(255, c1[0] + accent[0] // 3 + fade // 2),
                min(255, c1[1] + accent[1] // 3 + fade // 2),
                min(255, c1[2] + accent[2] // 3 + fade // 2),
            )
            draw.ellipse([(cx - radius, cy - radius), (cx + radius, cy + radius)], outline=col)

        # Horizontal scan lines (tech feel)
        for y in range(0, H, 18):
            alpha = 12
            draw.line([(0, y), (W, y)],
                      fill=(min(255, c1[0] + alpha), min(255, c1[1] + alpha), min(255, c1[2] + alpha)))

        # Category-specific large icon in the centre-right
        CAT_ICONS = {
            "AI & Machine Learning": "🤖",
            "Cybersecurity": "🔐",
            "Big Tech": "🏢",
            "Startups & VC": "🚀",
            "Technology": "📱",
            "Space & Science": "🛸",
        }
        icon = CAT_ICONS.get(category, "⚡")

        # Draw a large faint circle behind icon area
        draw.ellipse([(W - 380, H // 2 - 200), (W - 20, H // 2 + 200)],
                     fill=(min(255, c1[0] + 15), min(255, c1[1] + 15), min(255, c1[2] + 15)))

        img = img.convert("RGBA")
        _overlay_text_on_image(img, title, category, accent)
        img = img.convert("RGB")
        img.save(path, "JPEG", quality=90, optimize=True)
        print(f"  🖼  designed [{category[:18]}] {title[:45]}")

    except Exception as e:
        print(f"  ⚠ image error '{title[:35]}': {e}")
        # Last resort: solid colour block
        try:
            from PIL import Image as _I
            palette = CAT_PALETTES.get(category, CAT_PALETTES["Technology"])
            c1, _, _ = palette
            _I.new("RGB", (1200, 630), c1).save(path, "JPEG", quality=60)
        except Exception:
            pass

    return f"/images/{fname}"


def generate_branded_image(title: str, category: str, slug: str) -> str:
    """Legacy wrapper — calls build_article_image with no source URL."""
    return build_article_image("", "", title, category, slug)


def _create_fallback_image(path: str, title: str, category: str, accent: tuple):
    """Unused legacy stub — kept to avoid NameError in old call sites."""
    try:
        data = bytes([
            0xff,0xd8,0xff,0xe0,0x00,0x10,0x4a,0x46,0x49,0x46,0x00,0x01,
            0x01,0x00,0x00,0x01,0x00,0x01,0x00,0x00,0xff,0xdb,0x00,0x43,
            0x00,0x08,0x06,0x06,0x07,0x06,0x05,0x08,0x07,0x07,0x07,0x09,
            0x09,0x08,0x0a,0x0c,0x14,0x0d,0x0c,0x0b,0x0b,0x0c,0x19,0x12,
            0x13,0x0f,0x14,0x1d,0x1a,0x1f,0x1e,0x1d,0x1a,0x1c,0x1c,0x20,
            0x24,0x2e,0x27,0x20,0x22,0x2c,0x23,0x1c,0x1c,0x28,0x37,0x29,
            0x2c,0x30,0x31,0x34,0x34,0x34,0x1f,0x27,0x39,0x3d,0x38,0x32,
            0x3c,0x2e,0x33,0x34,0x32,0xff,0xc0,0x00,0x0b,0x08,0x00,0x01,
            0x00,0x01,0x01,0x01,0x11,0x00,0xff,0xc4,0x00,0x1f,0x00,0x00,
            0x01,0x05,0x01,0x01,0x01,0x01,0x01,0x01,0x00,0x00,0x00,0x00,
            0x00,0x00,0x00,0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,
            0x09,0x0a,0x0b,0xff,0xc4,0x00,0xb5,0x10,0x00,0x02,0x01,0x03,
            0x03,0x02,0x04,0x03,0x05,0x05,0x04,0x04,0x00,0x00,0x01,0x7d,
            0x01,0x02,0x03,0x00,0x04,0x11,0x05,0x12,0x21,0x31,0x41,0x06,
            0x13,0x51,0x61,0x07,0x22,0x71,0x14,0x32,0x81,0x91,0xa1,0x08,
            0x23,0x42,0xb1,0xc1,0x15,0x52,0xd1,0xf0,0x24,0x33,0x62,0x72,
            0x82,0x09,0x0a,0x16,0x17,0x18,0x19,0x1a,0x25,0x26,0x27,0x28,
            0x29,0x2a,0x34,0x35,0x36,0x37,0x38,0x39,0x3a,0x43,0x44,0x45,
            0x46,0x47,0x48,0x49,0x4a,0x53,0x54,0x55,0x56,0x57,0x58,0x59,
            0x5a,0x63,0x64,0x65,0x66,0x67,0x68,0x69,0x6a,0x73,0x74,0x75,
            0x76,0x77,0x78,0x79,0x7a,0x83,0x84,0x85,0x86,0x87,0x88,0x89,
            0x8a,0x93,0x94,0x95,0x96,0x97,0x98,0x99,0x9a,0xa2,0xa3,0xa4,
            0xa5,0xa6,0xa7,0xa8,0xa9,0xaa,0xb2,0xb3,0xb4,0xb5,0xb6,0xb7,
            0xb8,0xb9,0xba,0xc2,0xc3,0xc4,0xc5,0xc6,0xc7,0xc8,0xc9,0xca,
            0xd2,0xd3,0xd4,0xd5,0xd6,0xd7,0xd8,0xd9,0xda,0xe1,0xe2,0xe3,
            0xe4,0xe5,0xe6,0xe7,0xe8,0xe9,0xea,0xf1,0xf2,0xf3,0xf4,0xf5,
            0xf6,0xf7,0xf8,0xf9,0xfa,0xff,0xda,0x00,0x08,0x01,0x01,0x00,
            0x00,0x3f,0x00,0xfb,0xd3,0xff,0xd9
        ])
        with open(path, "wb") as f:
            f.write(data)
    except Exception:
        pass


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


# ── RSS image extraction ──────────────────────────────────────────────────────

def get_rss_image_url(entry) -> str:
    """Extract the best image URL from an RSS/feedparser entry."""
    # media:content
    mc = getattr(entry, "media_content", None) or entry.get("media_content", [])
    for m in mc:
        url = m.get("url", "")
        if url and any(url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
            return url
    # media:thumbnail
    mt = getattr(entry, "media_thumbnail", None) or entry.get("media_thumbnail", [])
    if mt:
        return mt[0].get("url", "")
    # enclosures
    for enc in entry.get("enclosures", []):
        t = enc.get("type", "")
        if t.startswith("image/"):
            return enc.get("href", enc.get("url", ""))
    # links
    for link in entry.get("links", []):
        if link.get("type", "").startswith("image/"):
            return link.get("href", "")
    return ""


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
        category  = detect_category(title, source_text)
        rss_img   = get_rss_image_url(entry)
        art_link  = entry.get("link", "")
        img_path  = build_article_image(art_link, rss_img, title, category, slug)

        articles.append({
            "title":        title,
            "link":         entry.get("link", "#"),
            "pubDate":      entry.get("published",
                                datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")),
            "summary":      summary,
            "full_content": rewritten,
            "excerpt":      excerpt,
            "slug":         slug,
            "image":        img_path,
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
  width:100%; background:#060c1a;
  display:flex; justify-content:center; align-items:center;
  padding:18px 0 0; line-height:0;
}
.hero-banner-inner {
  width:75%; max-width:1080px; position:relative;
  border-radius:12px; overflow:hidden;
  box-shadow:0 0 40px rgba(0,198,255,.12),0 0 80px rgba(10,132,255,.08);
}
.hero-banner img {
  width:100%; height:auto; display:block;
}
.hero-banner-gradient { display:none; }
.hero-banner-bottom   { display:none; }

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

/* ── Redirect / countdown box ── */
.redirect-box{background:var(--navy2);border:1px solid rgba(0,198,255,.2);border-radius:14px;padding:36px 28px;text-align:center;margin:36px 0;}
.redirect-icon{font-size:2.4rem;margin-bottom:14px;}
.redirect-box p{color:var(--silver);font-size:.95rem;margin-bottom:20px;line-height:1.7;}
.redirect-box p strong{color:var(--white);}
.btn-skip{display:inline-block;background:linear-gradient(135deg,var(--blue),var(--blue2));color:#fff;font-size:.92rem;font-weight:700;padding:13px 30px;border-radius:10px;text-decoration:none;letter-spacing:.02em;margin-bottom:20px;transition:opacity .2s;}
.btn-skip:hover{opacity:.85;}
.redirect-progress{background:rgba(255,255,255,.07);border-radius:4px;height:5px;margin-top:16px;overflow:hidden;}
.redirect-progress-bar{height:100%;background:linear-gradient(90deg,var(--blue),var(--blue2));width:0%;transition:width 1s linear;border-radius:4px;}
.article-clock{text-align:right;padding:10px 0 6px;font-size:.8rem;color:var(--silver);letter-spacing:.04em;}

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
    return f"""<!-- Favicon -->
<link rel="icon" type="image/png" href="/images/favicon.png">
<link rel="apple-touch-icon" href="/images/favicon.png">
<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_ID}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA4_ID}');</script>
<!-- Google Subscribe with Google (SwG) -->
<script async type="application/javascript" src="https://news.google.com/swg/js/v1/swg-basic.js"></script>
<script>(self.SWG_BASIC=self.SWG_BASIC||[]).push(b=>{{b.init({{type:"NewsArticle",isPartOfType:["Product"],isPartOfProductId:"CAowmtTgCw:openaccess",clientOptions:{{theme:"light",lang:"en"}}}});}});</script>"""


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
        {% for cat in categories %}<a href="/category/{{ cat|lower|replace(' & ','-')|replace(' ','-') }}.html">{{ cat.split(' &')[0] }}</a>{% endfor %}
        <a href="/about.html">About</a>
        <a href="/contact.html">Contact</a>
      </nav>
      <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
        <span class="live-dot">Live</span>
        <form class="search-bar" onsubmit="var q=this.querySelector('input').value.trim();if(q)window.location.href='/?q='+encodeURIComponent(q);return false;">
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
        <p>Original tech news updated every hour. Full-length articles powered by a local LLM — unique insights on the stories that matter.</p>
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
        <a href="/category/technology.html">Gadgets</a>
      </div>
      <div class="footer-col">
        <h4>Company</h4>
        <a href="/about.html">About TechBrief</a>
        <a href="/contact.html">Contact Us</a>
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
      <span>&copy; {{ year }} {{ site_title }} · A Voltixio Publication · Original coverage. Sources linked.</span>
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
  <meta property="og:image"       content="{{ site_url }}/images/hero-banner.png">
  <meta name="twitter:card"       content="summary_large_image">
  <meta name="twitter:image"      content="{{ site_url }}/images/hero-banner.png">
  <link rel="canonical"           href="{{ site_url }}">
  <link rel="alternate" type="application/rss+xml" title="{{ site_title }}" href="{{ site_url }}/feed.xml">
  """ + head_extras + "\n  " + jsonld + """
  <style>""" + SHARED_CSS + """</style>
</head>
<body>
""" + HEADER_TMPL + """

<!-- ── Hero Banner ───────────────────────────────── -->
<div class="hero-banner">
  <div class="hero-banner-inner">
    <img src="/images/hero-banner.png"
         alt="Trending Technology News – Real Time, Real News"
         onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">
    <div style="display:none;width:100%;height:120px;background:linear-gradient(135deg,#0a1a3a,#060c1a);align-items:center;justify-content:center;">
      <span style="color:rgba(0,198,255,.4);font-size:.75rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;">⚡ TechBrief — Real Time. Real News.</span>
    </div>
  </div>
</div>

<!-- ── Live Clock Bar ─────────────────────────────── -->
<div style="background:var(--navy2);border-bottom:1px solid rgba(0,198,255,.1);padding:8px 0;">
  <div class="container" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
    <div style="display:flex;align-items:center;gap:8px;">
      <span style="color:rgba(255,68,68,.9);font-size:.65rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;background:rgba(255,68,68,.12);border:1px solid rgba(255,68,68,.3);padding:3px 10px;border-radius:20px;">⚡ LIVE</span>
      <span style="color:var(--silver);font-size:.78rem;">Breaking tech news · Updated every hour</span>
    </div>
    <div style="display:flex;align-items:center;gap:5px;font-family:'Courier New',monospace;background:rgba(0,198,255,.06);border:1px solid rgba(0,198,255,.2);padding:5px 14px;border-radius:8px;">
      <span style="font-size:1.55rem;font-weight:900;color:var(--blue2);text-shadow:0 0 16px rgba(0,198,255,.8),0 0 4px rgba(0,198,255,.5);letter-spacing:.04em;" id="clock-h">--</span>
      <span style="font-size:1.55rem;font-weight:900;color:rgba(0,198,255,.6);animation:colonBlink .9s step-end infinite;line-height:1;">:</span>
      <span style="font-size:1.55rem;font-weight:900;color:var(--blue2);text-shadow:0 0 16px rgba(0,198,255,.8),0 0 4px rgba(0,198,255,.5);letter-spacing:.04em;" id="clock-m">--</span>
      <span style="font-size:1.55rem;font-weight:900;color:rgba(0,198,255,.6);animation:colonBlink .9s step-end infinite;line-height:1;">:</span>
      <span style="font-size:1rem;font-weight:800;color:rgba(0,198,255,.7);align-self:flex-end;padding-bottom:2px;" id="clock-s">--</span>
      <span style="font-size:.85rem;font-weight:800;color:var(--blue2);margin-left:2px;align-self:flex-end;padding-bottom:3px;" id="clock-ampm"></span>
      <span style="font-size:.75rem;color:var(--silver);margin-left:10px;align-self:center;" id="clock-date"></span>
    </div>
  </div>
</div>
<style>@keyframes colonBlink{0%,100%{opacity:1;}50%{opacity:.15;}}</style>

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
      <a href="/category/technology.html" class="cat-icon-item" style="text-decoration:none;">
        <div class="icon-circle">📱</div><span>Gadgets &amp; Reviews</span>
      </a>
      <a href="/category/big-tech.html" class="cat-icon-item" style="text-decoration:none;">
        <div class="icon-circle">🏢</div><span>Big Tech</span>
      </a>
      <a href="/category/startups-vc.html" class="cat-icon-item" style="text-decoration:none;">
        <div class="icon-circle">🚀</div><span>Startups &amp; VC</span>
      </a>
      <a href="/category/technology.html" class="cat-icon-item" style="text-decoration:none;">
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
      <p>Get the latest tech news delivered to your inbox — the stories that matter, in your language.</p>
    </div>
    <a href="/contact.html" class="cta-btn">Subscribe Now →</a>
  </div>

</div>
""" + FOOTER_TMPL + """
<script>
(function tick(){
  var n=new Date(),h=n.getHours(),m=n.getMinutes(),s=n.getSeconds();
  var ap=h>=12?'PM':'AM';h=h%12||12;
  var p=function(x){return String(x).padStart(2,'0');};
  var el=function(id){return document.getElementById(id);};
  if(el('clock-h'))el('clock-h').textContent=p(h);
  if(el('clock-m'))el('clock-m').textContent=p(m);
  if(el('clock-s'))el('clock-s').textContent=p(s);
  if(el('clock-ampm'))el('clock-ampm').textContent=ap;
  var D=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],M=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  if(el('clock-date'))el('clock-date').textContent=D[n.getDay()]+' '+M[n.getMonth()]+' '+n.getDate()+', '+n.getFullYear();
  setTimeout(tick,1000);
})();
</script>
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
<div class="container" style="max-width:820px;padding-top:36px;padding-bottom:80px;">

  <a href="/" class="back-btn">← Back to home</a>

  <!-- Hero image with title + category overlaid -->
  <div class="article-hero">
    <img src="{{ a.image }}" alt="{{ a.title }}"
         onerror="this.style.display='none'">
    <div class="article-hero-overlay">
      <span class="article-hero-cat">{{ a.category }}</span>
      <h1 class="article-hero-title">{{ a.title }}</h1>
      <div class="article-hero-meta">{{ a.pubDate }}</div>
    </div>
  </div>

  <!-- Live clock -->
  <div class="article-clock">
    <span id="clock-h">--</span>:<span id="clock-m">--</span>:<span id="clock-s">--</span>&nbsp;<span id="clock-ampm"></span>&ensp;·&ensp;<span id="clock-date"></span>
  </div>

  <!-- AI Brief (first 3 paragraphs) -->
  <div class="article-body">
    {% for para in paragraphs[:3] %}
    <p>{{ para }}</p>
    {% endfor %}
  </div>

  <!-- Countdown redirect box -->
  <div class="redirect-box">
    <div class="redirect-icon">📰</div>
    <p>You're being redirected to the full original story in <strong><span id="countdown">10</span> seconds</strong>.</p>
    <a href="{{ a.link }}" id="skip-btn" class="btn-skip" target="_blank" rel="noopener noreferrer">
      Skip — Read Original Now →
    </a>
    <div class="redirect-progress">
      <div class="redirect-progress-bar" id="progress-bar"></div>
    </div>
  </div>

</div>
""" + FOOTER_TMPL + """
<script>
// Live clock
(function tick(){
  var n=new Date(),h=n.getHours(),m=n.getMinutes(),s=n.getSeconds();
  var ap=h>=12?'PM':'AM';h=h%12||12;
  var p=function(x){return String(x).padStart(2,'0');};
  document.getElementById('clock-h').textContent=p(h);
  document.getElementById('clock-m').textContent=p(m);
  document.getElementById('clock-s').textContent=p(s);
  document.getElementById('clock-ampm').textContent=ap;
  var D=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'],M=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  document.getElementById('clock-date').textContent=D[n.getDay()]+' '+M[n.getMonth()]+' '+n.getDate()+', '+n.getFullYear();
  setTimeout(tick,1000);
})();
// Countdown redirect
(function(){
  var left=10, target={{ a.link | tojson }};
  var bar=document.getElementById('progress-bar');
  var num=document.getElementById('countdown');
  var iv=setInterval(function(){
    left--;
    num.textContent=left;
    bar.style.width=((10-left)/10*100)+'%';
    if(left<=0){clearInterval(iv);window.location.href=target;}
  },1000);
  document.getElementById('skip-btn').addEventListener('click',function(){clearInterval(iv);});
})();
</script>
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
                        articles=articles, year=datetime.now().year)
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
  <meta name="description" content="{{ cat }} tech news, updated hourly.">
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
      <a href="/">Home</a>
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
    <p>Original {{ cat }} news — updated every hour</p>
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
    <p>Search across all tech articles — updated every hour</p>
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
             f'  <url><loc>{SITE_URL}/about.html</loc><changefreq>monthly</changefreq><priority>0.6</priority></url>']
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
  <title>About – {SITE_TITLE} | AI-Powered Tech News</title>
  <meta name="description" content="Tech Brief is an AI-powered technology news platform built by Voltixio. Original, plagiarism-free tech journalism updated every hour.">
  <link rel="canonical" href="{SITE_URL}/about.html">
  {ga4_snippet()}
  <style>{SHARED_CSS}
.about-hero{{background:var(--navy2);border-bottom:1px solid rgba(0,198,255,.15);padding:64px 0 52px;position:relative;overflow:hidden;text-align:center;}}
.about-hero::before{{content:'';position:absolute;top:-80px;left:50%;transform:translateX(-50%);width:700px;height:400px;background:radial-gradient(ellipse,rgba(10,132,255,.1) 0%,transparent 65%);pointer-events:none;}}
.about-hero-grid{{position:absolute;inset:0;background:linear-gradient(rgba(10,132,255,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(10,132,255,.03) 1px,transparent 1px);background-size:40px 40px;}}
.about-badge{{display:inline-block;background:rgba(10,132,255,.15);border:1px solid rgba(0,198,255,.25);color:var(--blue2);font-size:.7rem;font-weight:800;text-transform:uppercase;letter-spacing:.12em;padding:5px 18px;border-radius:20px;margin-bottom:20px;}}
.about-hero h1{{font-size:2.6rem;font-weight:800;color:var(--white);line-height:1.15;margin-bottom:14px;}}
.about-hero h1 span{{color:var(--blue2);}}
.about-hero p{{color:var(--silver);font-size:1rem;max-width:580px;margin:0 auto;}}
.stats-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin:40px 0;}}
.stat-box{{background:var(--navy2);border:1px solid rgba(0,198,255,.12);border-radius:12px;padding:24px;text-align:center;}}
.stat-box .num{{font-size:2rem;font-weight:800;color:var(--blue2);display:block;}}
.stat-box .lbl{{font-size:.72rem;color:var(--silver);text-transform:uppercase;letter-spacing:.08em;margin-top:6px;display:block;}}
.about-grid{{display:grid;grid-template-columns:1fr 1fr;gap:40px;align-items:start;margin:40px 0;}}
.pipeline-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin:32px 0;}}
.pipe-step{{background:var(--navy2);border:1px solid rgba(0,198,255,.12);border-radius:12px;padding:22px 18px;text-align:center;position:relative;}}
.pipe-step .icon{{font-size:1.8rem;margin-bottom:10px;display:block;}}
.pipe-step h3{{font-size:.9rem;font-weight:700;color:var(--white);margin-bottom:6px;}}
.pipe-step p{{font-size:.8rem;color:var(--silver);line-height:1.55;}}
.pipe-num{{position:absolute;top:-10px;left:50%;transform:translateX(-50%);background:var(--blue);color:#fff;width:22px;height:22px;border-radius:50%;font-size:.65rem;font-weight:800;display:flex;align-items:center;justify-content:center;}}
.values-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:32px 0;}}
.val-card{{background:var(--navy2);border:1px solid rgba(0,198,255,.1);border-radius:12px;padding:24px 20px;}}
.val-card .icon{{font-size:1.4rem;margin-bottom:10px;}}
.val-card h3{{font-size:.9rem;font-weight:700;color:var(--white);margin-bottom:7px;}}
.val-card p{{font-size:.82rem;color:var(--silver);line-height:1.7;}}
.built-by-box{{background:var(--navy2);border:1px solid rgba(0,198,255,.15);border-radius:14px;padding:36px;display:flex;align-items:center;gap:32px;margin:32px 0;}}
.v-logo{{width:72px;height:72px;background:linear-gradient(135deg,#0a2045,#0d1a35);border:1.5px solid rgba(0,198,255,.25);border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:1.6rem;font-weight:900;color:var(--blue2);}}
.built-by-box h2{{font-size:1.3rem;font-weight:800;color:var(--white);margin-bottom:8px;}}
.built-by-box h2 span{{color:var(--blue2);}}
.built-by-box p{{color:var(--silver);font-size:.88rem;line-height:1.75;margin-bottom:14px;}}
.link-pills{{display:flex;gap:10px;flex-wrap:wrap;}}
.link-pill{{display:inline-flex;align-items:center;gap:5px;background:rgba(10,132,255,.12);border:1px solid rgba(0,198,255,.22);color:var(--blue2);font-size:.78rem;font-weight:700;padding:6px 14px;border-radius:8px;text-decoration:none;transition:background .2s;}}
.link-pill:hover{{background:rgba(10,132,255,.22);}}
.about-cta{{background:linear-gradient(135deg,var(--navy2),var(--navy3));border:1px solid rgba(0,198,255,.15);border-radius:14px;padding:44px;text-align:center;margin:32px 0;position:relative;overflow:hidden;}}
.about-cta::before{{content:'';position:absolute;top:-60px;left:50%;transform:translateX(-50%);width:400px;height:280px;background:radial-gradient(ellipse,rgba(10,132,255,.09) 0%,transparent 70%);pointer-events:none;}}
.about-cta h2{{font-size:1.7rem;font-weight:800;color:var(--white);margin-bottom:10px;}}
.about-cta p{{color:var(--silver);font-size:.92rem;margin-bottom:24px;max-width:460px;margin-left:auto;margin-right:auto;}}
.cta-row{{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;}}
.btn-p{{background:linear-gradient(135deg,var(--blue),var(--blue2));color:#fff;font-size:.88rem;font-weight:700;padding:12px 26px;border-radius:9px;border:none;cursor:pointer;text-decoration:none;display:inline-block;}}
.btn-g{{background:transparent;color:var(--blue2);font-size:.88rem;font-weight:700;padding:12px 26px;border-radius:9px;border:1px solid rgba(0,198,255,.3);text-decoration:none;display:inline-block;}}
@media(max-width:900px){{.stats-row{{grid-template-columns:1fr 1fr;}}.about-grid{{grid-template-columns:1fr;}}.pipeline-row{{grid-template-columns:1fr 1fr;}}.values-grid{{grid-template-columns:1fr 1fr;}}.built-by-box{{flex-direction:column;text-align:center;}}}}
@media(max-width:600px){{.pipeline-row{{grid-template-columns:1fr;}}.values-grid{{grid-template-columns:1fr;}}.stats-row{{grid-template-columns:1fr 1fr;}}}}
  </style>
</head>
<body>
{nav_mini}

<div class="about-hero">
  <div class="about-hero-grid"></div>
  <div class="container" style="position:relative;">
    <div class="about-badge">About Tech Brief</div>
    <h1>AI-Powered News,<br><span>Built for the Future</span></h1>
    <p>Every hour, our pipeline rewrites the tech world's most important stories — original, fast, and free from plagiarism.</p>
  </div>
</div>

<div class="container" style="max-width:1100px;padding-top:48px;padding-bottom:80px;">

  <div class="stats-row">
    <div class="stat-box"><span class="num">40+</span><span class="lbl">Source feeds</span></div>
    <div class="stat-box"><span class="num">24/7</span><span class="lbl">Live updates</span></div>
    <div class="stat-box"><span class="num">100%</span><span class="lbl">Original</span></div>
    <div class="stat-box"><span class="num">0</span><span class="lbl">Plagiarism</span></div>
  </div>

  <div class="section-header"><h2>Our Mission</h2></div>
  <div class="about-grid">
    <div class="content-box" style="margin:0;">
      <p style="margin-bottom:14px;">Tech Brief was built on a simple belief: technology news should be fast, original, and accessible to everyone. We pull from 40+ premium RSS sources, rewrite every article using a locally-hosted large language model, and publish the result — every single hour, around the clock.</p>
      <p style="margin-bottom:14px;">No paywalls. No copy-paste journalism. No tracking pixels selling your data. Just clean, original coverage of the stories shaping the world of technology.</p>
      <p>We cover the six verticals that matter most: <strong style="color:var(--blue2);">AI &amp; Machine Learning, Cybersecurity, Startups &amp; VC, Big Tech, Gadgets &amp; Hardware,</strong> and <strong style="color:var(--blue2);">Space &amp; Science.</strong></p>
    </div>
    <div class="content-box" style="margin:0;">
      <h3 style="margin-top:0;color:var(--blue2);">Our Technology Stack</h3>
      <p style="margin-bottom:12px;"><strong style="color:var(--white);">RSS Aggregation</strong> — UglyFeed pipeline pulls from 40+ curated tech sources every hour.</p>
      <p style="margin-bottom:12px;"><strong style="color:var(--white);">AI Rewriting</strong> — Ollama running Gemma2 9B locally rewrites every article into ~500 original words.</p>
      <p style="margin-bottom:12px;"><strong style="color:var(--white);">Image Generation</strong> — Pillow creates branded article card images per story, styled by category.</p>
      <p><strong style="color:var(--white);">Static Deploy</strong> — Python/Jinja2 builds the full site and nginx serves it via SSL on Certbot.</p>
    </div>
  </div>

  <div class="section-header"><h2>How It Works</h2></div>
  <div class="pipeline-row">
    <div class="pipe-step"><div class="pipe-num">1</div><span class="icon">📡</span><h3>Aggregate</h3><p>RSS feeds from 40+ trusted tech publications pulled every hour.</p></div>
    <div class="pipe-step"><div class="pipe-num">2</div><span class="icon">🤖</span><h3>Rewrite</h3><p>Local Ollama LLM (Gemma 9B) produces a fully original 500-word piece.</p></div>
    <div class="pipe-step"><div class="pipe-num">3</div><span class="icon">🎨</span><h3>Generate</h3><p>Branded article images created per story via Pillow — no external APIs.</p></div>
    <div class="pipe-step"><div class="pipe-num">4</div><span class="icon">🚀</span><h3>Publish</h3><p>Site rebuilds automatically. Articles syndicated to social channels.</p></div>
  </div>

  <div class="section-header"><h2>What We Stand For</h2></div>
  <div class="values-grid">
    <div class="val-card"><div class="icon">⚡</div><h3>Speed Without Compromise</h3><p>Our pipeline rebuilds every hour so you're never reading yesterday's news.</p></div>
    <div class="val-card"><div class="icon">🔒</div><h3>Privacy First</h3><p>No third-party ad networks, no data brokers, no cookies beyond essential analytics.</p></div>
    <div class="val-card"><div class="icon">✍️</div><h3>Original Content</h3><p>Every article rewritten from scratch. We don't republish — we create.</p></div>
    <div class="val-card"><div class="icon">🌐</div><h3>Free &amp; Open</h3><p>No paywalls, no subscriptions. Quality tech journalism free for everyone.</p></div>
    <div class="val-card"><div class="icon">🎯</div><h3>Focused Coverage</h3><p>Six verticals only — AI, Cyber, Startups, Big Tech, Gadgets, Space. Depth over breadth.</p></div>
    <div class="val-card"><div class="icon">📊</div><h3>Transparent Sources</h3><p>Every article links back to the original publication. Always.</p></div>
  </div>

  <div class="built-by-box">
    <div class="v-logo">V</div>
    <div>
      <h2>Built by <span>Voltixio</span></h2>
      <p>Tech Brief is a product of Voltixio — a Baltimore-based technology company building AI-powered tools and platforms. Voltixio develops automation pipelines, intelligent agents, and consumer products at the intersection of artificial intelligence and real-world utility.</p>
      <div class="link-pills">
        <a href="https://voltixio.com" target="_blank" class="link-pill">↗ voltixio.com</a>
        <a href="mailto:techbrief@voltixio.com" class="link-pill">✉ techbrief@voltixio.com</a>
        <a href="/feed.xml" class="link-pill">⛁ RSS Feed</a>
        <a href="/contact.html" class="link-pill">✦ Contact</a>
      </div>
    </div>
  </div>

  <div class="about-cta">
    <h2>Stay Ahead of the Curve</h2>
    <p>Get the top 5 tech stories delivered to your inbox every morning. Free, forever.</p>
    <div class="cta-row">
      <a href="/contact.html" class="btn-p">Subscribe Free →</a>
      <a href="/" class="btn-g">Read Latest News</a>
    </div>
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
        # Only regenerate if image not already set by parse_rss or file missing
        existing = a.get("image", "")
        existing_path = os.path.join(OUTPUT_DIR, existing.lstrip("/")) if existing else ""
        if existing and os.path.exists(existing_path):
            continue  # already generated with RSS source image
        a["image"] = generate_branded_image(a["title"], a.get("category", "tech"), a["uid"] + "-" + a["slug"][:20])

    categories = sorted(set(a["category"] for a in articles))
    print(f"\nBuilding {len(articles)} pages across {len(categories)} categories…")

    render_homepage(articles, categories)
    render_article_pages(articles, categories)
    render_category_pages(articles, categories)
    # search page removed — search is inline on homepage
    render_search_index(articles)  # keep search.json for future use
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
