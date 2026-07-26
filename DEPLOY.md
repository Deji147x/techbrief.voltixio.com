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
