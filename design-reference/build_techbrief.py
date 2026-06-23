import feedparser, os, re, hashlib, requests
from datetime import datetime
from jinja2 import Template

RSS_URL = "http://localhost:8001/uglyfeed.xml"
OUTPUT_DIR = "/var/www/techbrief_static"
ARTICLES_PER_PAGE = 20
SITE_URL = "https://techbrief.voltixio.com"
SITE_TITLE = "AI Tech Brief"
SITE_DESCRIPTION = "AI‑rewritten tech news, updated hourly."

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "article"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "images"), exist_ok=True)

def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def fetch_image(title, idx):
    keyword = re.sub(r'[^a-zA-Z]', '', title.split()[0] if title.split() else 'tech')
    img_id = int(hashlib.md5(keyword.encode()).hexdigest()[:8], 16) % 1000
    url = f"https://picsum.photos/id/{img_id}/800/400"
    local = f"/images/img_{idx}.jpg"
    path = OUTPUT_DIR + local
    if not os.path.exists(path):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(path, 'wb') as f:
                    f.write(r.content)
        except: pass
    return local

feed = feedparser.parse(RSS_URL)
articles = []
for i, entry in enumerate(feed.entries[:ARTICLES_PER_PAGE]):
    desc = re.sub('<.*?>', '', entry.get('description', ''))
    articles.append({
        'title': entry.get('title', ''),
        'link': entry.get('link', ''),
        'pubDate': entry.get('published', ''),
        'summary': desc,
        'excerpt': desc[:200] + '...' if len(desc) > 200 else desc,
        'image': fetch_image(entry.get('title', ''), i),
        'detail_url': f"/article/{i+1}.html"
    })

# Render homepage
home_tpl = Template(open('/root/uglyfeed/home_template.html').read() if False else """
<!DOCTYPE html><html><head><title>{{ site_title }}</title><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{{ site_description }}"><style>
body{font-family:system-ui;background:#f5f7fa;margin:0;padding:0}header{background:#1a202c;color:#fff;padding:20px}.container{max-width:1200px;margin:0 auto;padding:20px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:30px}.card{background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 4px rgba(0,0,0,0.1)}.card img{width:100%;height:200px;object-fit:cover}.card-content{padding:20px}.card-title{font-size:1.2rem;font-weight:600;margin:0 0 10px}.card-title a{color:#1a202c;text-decoration:none}.card-excerpt{color:#4a5568;margin-bottom:15px}.read-more{display:inline-block;background:#667eea;color:#fff;padding:8px 16px;border-radius:6px;text-decoration:none}footer{background:#1a202c;color:#cbd5e0;text-align:center;padding:20px;margin-top:40px}</style></head><body><header><div class="container"><h1>{{ site_title }}</h1></div></header><div class="container"><div class="grid">{% for a in articles %}<div class="card"><img src="{{ a.image }}"><div class="card-content"><div class="card-title"><a href="{{ a.detail_url }}">{{ a.title }}</a></div><div class="card-excerpt">{{ a.excerpt }}</div><div class="card-meta">{{ a.pubDate }}</div><a href="{{ a.detail_url }}" class="read-more">Read full story →</a></div></div>{% endfor %}</div></div><footer><div class="container">&copy; 2026 {{ site_title }}. AI‑rewritten summaries, sources linked.</div></footer></body></html>
""")
with open(os.path.join(OUTPUT_DIR, 'index.html'), 'w') as f:
    f.write(home_tpl.render(site_title=SITE_TITLE, site_description=SITE_DESCRIPTION, articles=articles))

# Render individual article pages
article_tpl = Template("""<!DOCTYPE html><html><head><title>{{ a.title }} – {{ site_title }}</title><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{{ a.excerpt }}"><meta property="og:image" content="{{ a.image }}"><style>body{font-family:system-ui;background:#f5f7fa;margin:0;padding:0}header{background:#1a202c;color:#fff;padding:20px}.container{max-width:800px;margin:0 auto;padding:20px}article{background:#fff;border-radius:12px;padding:30px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}h1{margin-top:0}.featured-image{width:100%;border-radius:8px;margin:20px 0}.source-link{margin-top:30px;font-size:0.9rem}.back-home{display:inline-block;margin-top:20px;background:#667eea;color:#fff;padding:8px 16px;border-radius:6px;text-decoration:none}footer{background:#1a202c;color:#cbd5e0;text-align:center;padding:20px;margin-top:40px}</style></head><body><header><div class="container"><h1>{{ site_title }}</h1></div></header><div class="container"><article><h1>{{ a.title }}</h1><div class="meta">{{ a.pubDate }}</div><img src="{{ a.image }}" class="featured-image"><p>{{ a.summary }}</p><div class="source-link"><a href="{{ a.link }}" target="_blank" rel="noopener">Read original source →</a></div><a href="/" class="back-home">← Back to homepage</a></article></div><footer><div class="container">&copy; 2026 {{ site_title }}</div></footer></body></html>""")
for i, a in enumerate(articles):
    with open(os.path.join(OUTPUT_DIR, 'article', f'{i+1}.html'), 'w') as f:
        f.write(article_tpl.render(site_title=SITE_TITLE, a=a))

print(f"Site built in {OUTPUT_DIR}")
