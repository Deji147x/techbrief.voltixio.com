#!/usr/bin/env python3
"""
test_pipeline.py — confirms Ollama rewriting + image fetching work before running the full build.
Run this on the server: python3 /root/uglyfeed/test_pipeline.py
"""

import requests
import feedparser
import hashlib
import os
import json
import sys
import time

OLLAMA_URL   = "http://localhost:11434"
OLLAMA_MODEL = "gemma2:9b"
RSS_URL      = "http://localhost:8001/uglyfeed.xml"
IMG_TEST_DIR = "/tmp/tb_img_test"
os.makedirs(IMG_TEST_DIR, exist_ok=True)

PASS = "  ✅"
FAIL = "  ❌"
WARN = "  ⚠️ "

results = {}

def section(title):
    print(f"\n{'─'*52}")
    print(f"  {title}")
    print('─'*52)

# ── 1. Ollama reachability ────────────────────────────────────────────────────
section("1 · Ollama connection")
try:
    r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=8)
    models = [m["name"] for m in r.json().get("models", [])]
    print(f"{PASS} Ollama is running at {OLLAMA_URL}")
    print(f"     Installed models: {', '.join(models) if models else 'none found'}")
    if any(OLLAMA_MODEL in m for m in models):
        print(f"{PASS} Model '{OLLAMA_MODEL}' is available")
        results["ollama_model"] = True
    else:
        print(f"{FAIL} Model '{OLLAMA_MODEL}' NOT found — run: ollama pull {OLLAMA_MODEL}")
        results["ollama_model"] = False
    results["ollama_up"] = True
except Exception as e:
    print(f"{FAIL} Cannot reach Ollama: {e}")
    print(f"     Is Ollama running? Try: ollama serve &")
    results["ollama_up"] = False
    results["ollama_model"] = False

# ── 2. Ollama rewrite test ────────────────────────────────────────────────────
section("2 · Ollama article rewrite (live test)")
if results.get("ollama_up") and results.get("ollama_model"):
    PROMPT = """You are a sharp tech journalist. Rewrite this in 3 engaging paragraphs, no headers or bullets.
Title: OpenAI releases GPT-5 with real-time reasoning
Summary: OpenAI has launched GPT-5, a model that can reason step by step in real time.
Write the article:"""
    try:
        t0 = time.time()
        r = requests.post(f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": PROMPT, "stream": False,
                  "options": {"temperature": 0.7, "num_predict": 300}},
            timeout=120)
        elapsed = time.time() - t0
        text = r.json().get("response","").strip()
        if len(text) > 80:
            print(f"{PASS} Rewrite successful in {elapsed:.1f}s  ({len(text)} chars)")
            print(f"\n     Preview:\n     {text[:220].replace(chr(10),' ')}…\n")
            results["ollama_rewrite"] = True
        else:
            print(f"{FAIL} Response too short ({len(text)} chars): {text}")
            results["ollama_rewrite"] = False
    except Exception as e:
        print(f"{FAIL} Rewrite failed: {e}")
        results["ollama_rewrite"] = False
else:
    print(f"{WARN} Skipped — Ollama not available")
    results["ollama_rewrite"] = False

# ── 3. Image fetching ─────────────────────────────────────────────────────────
section("3 · Image auto-generation (Picsum)")
test_cases = [
    ("openai",    int(hashlib.md5(b"openai").hexdigest()[:8], 16) % 1000),
    ("security",  int(hashlib.md5(b"security").hexdigest()[:8], 16) % 1000),
    ("startup",   int(hashlib.md5(b"startup").hexdigest()[:8], 16) % 1000),
]
img_ok = 0
for keyword, img_id in test_cases:
    url  = f"https://picsum.photos/id/{img_id}/800/400"
    path = os.path.join(IMG_TEST_DIR, f"{keyword}.jpg")
    try:
        r = requests.get(url, timeout=12)
        if r.status_code == 200 and len(r.content) > 5000:
            with open(path, "wb") as f: f.write(r.content)
            print(f"{PASS} [{keyword}] → image ID {img_id} ({len(r.content)//1024}KB saved to {path})")
            img_ok += 1
        else:
            # Picsum ID may not exist, try fallback
            r2 = requests.get("https://picsum.photos/800/400", timeout=12)
            if r2.status_code == 200:
                with open(path, "wb") as f: f.write(r2.content)
                print(f"{WARN} [{keyword}] ID {img_id} missing, used random fallback ({len(r2.content)//1024}KB)")
                img_ok += 1
            else:
                print(f"{FAIL} [{keyword}] Both ID and fallback failed (status {r.status_code})")
    except Exception as e:
        print(f"{FAIL} [{keyword}] Network error: {e}")

results["images"] = img_ok == len(test_cases)
if img_ok > 0:
    print(f"\n{PASS} {img_ok}/{len(test_cases)} images downloaded successfully")
    print(f"     Images saved to {IMG_TEST_DIR}/ — verify they look correct")

# ── 4. RSS / uglyfeed feed ────────────────────────────────────────────────────
section("4 · Uglyfeed RSS feed")
try:
    feed = feedparser.parse(RSS_URL)
    count = len(feed.entries)
    if count > 0:
        print(f"{PASS} Feed is live — {count} article(s) found")
        for i, e in enumerate(feed.entries[:3]):
            title   = e.get("title","?")
            summary = e.get("description", e.get("summary",""))[:80]
            print(f"     [{i+1}] {title[:60]}")
            print(f"          {summary.strip()[:70]}…")
        results["rss"] = True
    else:
        print(f"{FAIL} Feed is empty — add RSS sources via Streamlit at http://31.97.132.83:8501")
        results["rss"] = False
except Exception as e:
    print(f"{FAIL} Cannot parse RSS feed: {e}")
    results["rss"] = False

# ── 5. Full mini-build test (1 article end-to-end) ────────────────────────────
section("5 · End-to-end mini-build (1 article)")
if results.get("rss") and results.get("ollama_up"):
    try:
        feed  = feedparser.parse(RSS_URL)
        entry = feed.entries[0]
        title = entry.get("title","Test Article")
        import re
        raw   = re.sub(r"<[^>]+>","",entry.get("description",entry.get("summary","No content.")))

        print(f"     Article: {title[:60]}")
        print(f"     Source text ({len(raw)} chars): {raw[:80]}…")

        # Rewrite
        PROMPT2 = f"""You are a sharp tech journalist. Rewrite in 2 engaging paragraphs, no headers or bullets.
Title: {title}
Summary: {raw[:600]}
Write:"""
        t0 = time.time()
        r  = requests.post(f"{OLLAMA_URL}/api/generate",
            json={"model":OLLAMA_MODEL,"prompt":PROMPT2,"stream":False,
                  "options":{"temperature":0.75,"num_predict":300}},
            timeout=120)
        rewrite = r.json().get("response","").strip()
        elapsed = time.time()-t0

        print(f"{PASS} Rewrite done in {elapsed:.1f}s ({len(rewrite)} chars)")
        print(f"\n     {rewrite[:300].replace(chr(10),' ')}…\n")

        # Image
        words = title.split()
        stop  = {"a","an","the","and","of","to","for","in","on","with"}
        kw    = next((w.lower() for w in words if w.lower() not in stop and len(w)>3),"tech")
        img_id = int(hashlib.md5(kw.encode()).hexdigest()[:8],16) % 1000
        img_r  = requests.get(f"https://picsum.photos/id/{img_id}/800/400",timeout=12)
        img_path = os.path.join(IMG_TEST_DIR,"e2e_article.jpg")
        with open(img_path,"wb") as f: f.write(img_r.content)
        print(f"{PASS} Article image saved → {img_path} (keyword: {kw}, ID: {img_id})")
        results["e2e"] = True
    except Exception as e:
        print(f"{FAIL} End-to-end test failed: {e}")
        results["e2e"] = False
else:
    print(f"{WARN} Skipped — requires RSS feed + Ollama")
    results["e2e"] = False

# ── SUMMARY ───────────────────────────────────────────────────────────────────
section("SUMMARY")
checks = [
    ("Ollama running",          results.get("ollama_up")),
    (f"Model {OLLAMA_MODEL}",   results.get("ollama_model")),
    ("Article rewrite",         results.get("ollama_rewrite")),
    ("Image auto-generation",   results.get("images")),
    ("Uglyfeed RSS feed",       results.get("rss")),
    ("End-to-end build test",   results.get("e2e")),
]
passed = sum(1 for _,v in checks if v)
for label,ok in checks:
    icon = "✅" if ok else "❌"
    print(f"  {icon}  {label}")

print(f"\n  {passed}/{len(checks)} checks passed")
if passed == len(checks):
    print("\n  🚀 All systems go — run python3 generate_site.py to build the full site!\n")
else:
    print("\n  ⚠️  Fix the failing checks above, then re-run this test.\n")
    sys.exit(1)
