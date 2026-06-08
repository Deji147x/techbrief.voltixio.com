# Tech Brief – One-Shot Deployment Guide
Server: root@31.97.132.83

---

## STEP 1 — Upload all files to server

Run from your Windows machine (PowerShell):

```powershell
$server = "root@31.97.132.83"
$local  = "C:\Users\Parlevu_Global\OneDrive\Documents\Claude\Projects\Techbrief"

scp "$local\generate_site.py"    "$server:/root/uglyfeed/"
scp "$local\post_facebook.py"    "$server:/root/uglyfeed/"
scp "$local\post_social.py"      "$server:/root/uglyfeed/"
```

## STEP 2 — Upload logo + hero banner

Save your TB logo as `logo.png` in the Techbrief folder.
Save the hero banner image as `hero-banner.jpg` in the Techbrief folder.

```powershell
scp "$local\logo.png"        "$server:/var/www/techbrief_static/images/logo.png"
scp "$local\hero-banner.jpg" "$server:/var/www/techbrief_static/images/hero-banner.jpg"
```

---

## STEP 3 — Install Python dependencies on server

SSH in, then:

```bash
pip install feedparser jinja2 requests tweepy --break-system-packages
```

---

## STEP 4 — Check uglyfeed sources via Streamlit

Open http://31.97.132.83:8501 in your browser.
Add these RSS feeds (copy from feeds.txt):
- https://venturebeat.com/category/ai/feed/
- https://feeds.arstechnica.com/arstechnica/index
- https://feeds.feedburner.com/TheHackersNews
- https://techcrunch.com/startups/feed/
- (full list in feeds.txt)

---

## STEP 5 — Set environment variables (Facebook poster)

```bash
echo 'export FB_PAGE_TOKEN="EAAUlDXS...ZDZD"' >> /root/.bashrc
echo 'export FB_PAGE_ID="YOUR_FACEBOOK_PAGE_ID"' >> /root/.bashrc
source /root/.bashrc
```

---

## STEP 6 — Test a manual build

```bash
cd /root/uglyfeed
python3 generate_site.py
```

Expected output:
```
==================================================
  AI Tech Brief – build  2026-06-08 12:00
  Ollama model: gemma2:9b  @ http://localhost:11434
==================================================
  20 articles parsed
  ✍ rewritten: OpenAI releases...
  ↓ image [openai]
  ✓ index.html
  ✓ 20 article pages
  ✓ 3 category pages
  ✓ search.html
  ✓ sitemap.xml
  ✓ feed.xml
  ✓ robots.txt
  ✅  Build complete in 142.3s → /var/www/techbrief_static
```

Check the live site: https://techbrief.voltixio.com

---

## STEP 7 — Set up cron (hourly auto-update)

```bash
crontab -e
```

Add this line:

```
0 * * * * cd /root/uglyfeed && git pull origin main && python3 generate_site.py && python3 post_facebook.py >> /var/log/techbrief.log 2>&1
```

Verify it's saved:
```bash
crontab -l
```

---

## STEP 8 — Lock Streamlit to your IP only

Find your home/office IP: https://whatismyip.com  
Then on the server:

```bash
# Allow your IP on port 8501
ufw allow from YOUR.HOME.IP.HERE to any port 8501
# Block everyone else from 8501
ufw deny 8501
ufw reload
```

Port 8001 (uglyfeed XML feed) should stay open for generate_site.py to read:
```bash
ufw allow 8001
```

---

## STEP 9 — Push everything to GitHub

```bash
cd /root/uglyfeed
git add -A
git commit -m "Deploy: futuristic redesign + Ollama rewriting + social posting"
git push origin main
```

---

## Traffic Pipeline Confirmed

```
RSS Sources (40+ feeds)
        ↓
  uglyfeed container (port 8001)
  - Aggregates feeds
  - Rewrites with AI
  - Outputs uglyfeed.xml
        ↓
  generate_site.py (runs every hour via cron)
  - Reads uglyfeed.xml
  - Rewrites again with Ollama gemma2:9b (500-word articles)
  - Generates HTML, sitemap, RSS feed, search index
  - Saves to /var/www/techbrief_static/
        ↓
  Nginx serves /var/www/techbrief_static/
        ↓
  https://techbrief.voltixio.com ✅
        ↓
  post_facebook.py (runs after build)
  - Posts new articles to Facebook Page
```

---

## Checklist

- [ ] Files uploaded to server
- [ ] logo.png uploaded to /var/www/techbrief_static/images/
- [ ] Dependencies installed
- [ ] uglyfeed sources added via Streamlit
- [ ] FB_PAGE_TOKEN + FB_PAGE_ID set
- [ ] Manual build tested and site loads
- [ ] Cron job set
- [ ] Streamlit locked to your IP
- [ ] Pushed to GitHub
