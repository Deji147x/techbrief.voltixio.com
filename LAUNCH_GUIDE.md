# TechBrief — Full Launch Guide
**Site:** https://techbrief.voltixio.com  
**Server:** root@31.97.132.83

---

## PHASE 1 — Deploy Files to Server

### Step 1 — Upload all files (run in PowerShell)
```powershell
$s = "root@31.97.132.83"
$l = "C:\Users\Parlevu_Global\OneDrive\Documents\Claude\Projects\Techbrief"

scp "$l\index_template.html"  "$s:/var/www/techbrief_static/index.html"
scp "$l\generate_site.py"     "$s:/root/uglyfeed/generate_site.py"
scp "$l\post_social.py"       "$s:/root/uglyfeed/post_social.py"
scp "$l\post_facebook.py"     "$s:/root/uglyfeed/post_facebook.py"
scp "$l\post_reddit.py"       "$s:/root/uglyfeed/post_reddit.py"
scp "$l\post_telegram.py"     "$s:/root/uglyfeed/post_telegram.py"
scp "$l\update_server.sh"     "$s:/root/uglyfeed/update_server.sh"
```

### Step 2 — Upload hero banner image
```powershell
# Your file has a double extension — upload as hero-banner.png on the server
scp "C:\Users\Parlevu_Global\Downloads\hero-banner.jpg.png" "root@31.97.132.83:/var/www/techbrief_static/images/hero-banner.png"
```
> **Note:** `about.html` and `contact.html` are now generated automatically by `generate_site.py` on every run — do **not** manually SCP them; they will be overwritten.

### Step 3 — SSH into server and run update script
```bash
ssh root@31.97.132.83
bash /root/uglyfeed/update_server.sh
```
This installs Pillow, praw, upgrades all packages, and does a full test build.

---

## PHASE 2 — Configure Social Credentials

### Step 4 — Set environment variables on server
```bash
# Facebook (already have token — rotate if exposed)
echo 'export FB_PAGE_TOKEN="your_token_here"' >> /root/.bashrc
echo 'export FB_PAGE_ID="61585689098382"' >> /root/.bashrc

# Reddit — get from https://www.reddit.com/prefs/apps
echo 'export REDDIT_CLIENT_ID="your_id"' >> /root/.bashrc
echo 'export REDDIT_CLIENT_SECRET="your_secret"' >> /root/.bashrc
echo 'export REDDIT_USERNAME="your_username"' >> /root/.bashrc
echo 'export REDDIT_PASSWORD="your_password"' >> /root/.bashrc

# Telegram — get from @BotFather on Telegram
echo 'export TELEGRAM_BOT_TOKEN="your_bot_token"' >> /root/.bashrc
echo 'export TELEGRAM_CHANNEL="@TechBriefNews"' >> /root/.bashrc

source /root/.bashrc
```

### Step 5 — Create Reddit App
1. Go to https://www.reddit.com/prefs/apps
2. Click **Create another app** → choose **script**
3. Name: `TechBrief Poster`
4. Redirect URI: `http://localhost:8080`
5. Copy **client id** (under app name) and **secret**
6. Add to server env vars above

### Step 6 — Create Telegram Bot & Channel
1. Open Telegram → message **@BotFather** → `/newbot`
2. Name: `TechBrief News Bot` → Username: `TechBriefBot`
3. Copy the bot token
4. Create a public channel: **@TechBriefNews**
5. Add bot as admin to the channel
6. Add token + channel to server env vars above

---

## PHASE 3 — Google Indexing (Most Important for Traffic)

### Step 7 — Google Search Console
1. Go to https://search.google.com/search-console
2. Click **Add property** → enter `https://techbrief.voltixio.com`
3. Choose **HTML tag** verification method
4. Copy the meta tag (looks like `<meta name="google-site-verification" content="xxxxx">`)
5. Add it to `index_template.html` inside `<head>` and re-upload
6. Click **Verify**
7. Go to **Sitemaps** → submit `https://techbrief.voltixio.com/sitemap.xml`

### Step 8 — Apply for Google News
1. Go to https://publishercenter.google.com
2. Sign in → **Add publication**
3. Publication name: `TechBrief`
4. URL: `https://techbrief.voltixio.com`
5. Submit news sitemap: `https://techbrief.voltixio.com/sitemap.xml`
6. Complete the publisher information form
7. Wait 2–4 weeks for approval (massive traffic when approved)

---

## PHASE 4 — Social Channel Setup

### Step 9 — Create social accounts (if not done)
| Platform | Action |
|----------|--------|
| X/Twitter | Create @TechBriefNews account |
| Reddit | Create u/TechBrief account |
| Telegram | Create @TechBriefNews channel |
| Facebook | Already exists: facebook.com/profile.php?id=61585689098382 |
| LinkedIn | Already exists: linkedin.com/company/111946667 |
| Instagram | Already exists: @voltixioai |

### Step 10 — Submit to RSS Aggregators (free backlinks)
Submit your RSS feed at each:
- https://feedly.com/i/discover (search your site, subscribe)
- https://flipboard.com (create magazine, add RSS)
- https://www.inoreader.com
- https://news.ycombinator.com/submitlink (Hacker News — manual, one story at a time)
- https://www.reddit.com/r/technology (submit manually first to build karma)

### Step 11 — Manual launch posts (Day 1)
Post these on launch day manually:

**Facebook:**
```
🚀 TechBrief just launched!

AI-rewritten tech news updated every hour — no fluff, no recycled headlines.
Full original articles covering AI, Cybersecurity, Startups, Big Tech, Gadgets & Space.

Read free: https://techbrief.voltixio.com

Real Time. Real News. 24/7. 🌐
```

**LinkedIn:**
```
We built something different.

TechBrief is an AI-powered technology news channel that rewrites every story
using a local LLM — producing original full-length coverage updated hourly.

No paywalls. No plagiarism. Just fast, original tech journalism at machine speed.

🔗 https://techbrief.voltixio.com

#TechNews #AI #MachineLearning #Startups #Cybersecurity #Innovation
```

**Instagram:**
```
⚡ Real Time. Real News.
TechBrief just launched — AI-rewritten tech news updated every hour 🌐
Breaking stories in AI, Cyber, Startups & more 👇
🔗 techbrief.voltixio.com

#TechNews #AI #ArtificialIntelligence #MachineLearning #Cybersecurity
#Startups #BigTech #TechBrief #Voltixio #FutureTech #Breaking #NewsUpdate
```

---

## PHASE 5 — Activate Auto-Posting Cron

### Step 12 — Set up cron (after all credentials confirmed working)
```bash
crontab -e
```
Replace any existing line with:
```
0 * * * * cd /root/uglyfeed && git pull origin main && python3 generate_site.py && python3 post_social.py >> /var/log/techbrief.log 2>&1
```
Verify:
```bash
crontab -l
tail -f /var/log/techbrief.log
```

---

## PHASE 6 — Security & Performance

### Step 13 — Lock Streamlit to your IP
Find your IP at https://whatismyip.com, then:
```bash
ufw allow from YOUR.IP.HERE to any port 8501
ufw deny 8501
ufw allow 8001
ufw reload
```

### Step 14 — Push everything to GitHub
```bash
cd /root/uglyfeed
git add -A
git commit -m "Launch: all social posters + branded images + launch guide"
git push origin main
```

---

## PHASE 7 — Traffic Growth Checklist (Week 1+)

| Action | Frequency | Impact |
|--------|-----------|--------|
| Google Search Console — monitor | Daily | High |
| Reddit — submit top articles manually | Daily | High |
| Hacker News — submit best story | Daily | Very High |
| LinkedIn — engage on comments | Daily | Medium |
| Product Hunt launch | One-time | Very High |
| Feedly/Flipboard submission | One-time | Medium |
| Google News approval follow-up | Weekly | Very High |
| Add more RSS feeds via Streamlit | Weekly | High |

---

## Quick Reference — All URLs

| Resource | URL |
|----------|-----|
| Live site | https://techbrief.voltixio.com |
| Sitemap | https://techbrief.voltixio.com/sitemap.xml |
| RSS Feed | https://techbrief.voltixio.com/feed.xml |
| Streamlit (feeds UI) | http://31.97.132.83:8501 |
| Build log | ssh → `tail -f /var/log/techbrief.log` |
| Facebook page | https://www.facebook.com/profile.php?id=61585689098382 |
| LinkedIn | https://www.linkedin.com/company/111946667 |
| Instagram | https://www.instagram.com/voltixioai |
| Google Search Console | https://search.google.com/search-console |
| Google Publisher Center | https://publishercenter.google.com |
| Reddit App Setup | https://www.reddit.com/prefs/apps |
| Telegram BotFather | https://t.me/BotFather |
| GitHub repo | https://github.com/Deji147x/techbrief.voltixio.com |
