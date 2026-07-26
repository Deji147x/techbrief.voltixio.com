#!/bin/bash
# ── TechBrief Server Update Script ────────────────────────────────────────────
# Run on server: bash /root/uglyfeed/update_server.sh
# Does: package upgrades → git pull → test build → verify site

set -e
echo ""
echo "════════════════════════════════════════"
echo "  TechBrief Server Update"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════"

# ── 1. Upgrade pip packages ────────────────────────────────────────────────────
echo ""
echo "[ 1/5 ] Upgrading pip packages..."
pip install --break-system-packages --upgrade \
  feedparser \
  requests \
  jinja2 \
  Pillow \
  tweepy \
  flask \
  gunicorn

echo "  ✓ Packages upgraded"

# ── 2. Pull latest code from GitHub ───────────────────────────────────────────
echo ""
echo "[ 2/5 ] Pulling latest code from GitHub..."
cd /root/uglyfeed
git pull origin main
echo "  ✓ Code up to date"

# ── 3. Ensure output directories exist ────────────────────────────────────────
echo ""
echo "[ 3/5 ] Ensuring output directories..."
mkdir -p /var/www/techbrief_static/images
mkdir -p /var/www/techbrief_static/article
mkdir -p /var/www/techbrief_static/category
echo "  ✓ Directories OK"

# ── 4. Verify Ollama is running ────────────────────────────────────────────────
echo ""
echo "[ 4/5 ] Checking Ollama..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
  echo "  ✓ Ollama is running"
  # Check if gemma2:9b model is available
  MODELS=$(curl -s http://localhost:11434/api/tags | python3 -c "import sys,json; d=json.load(sys.stdin); print([m['name'] for m in d.get('models',[])])" 2>/dev/null || echo "unknown")
  echo "  Models: $MODELS"
else
  echo "  ⚠ Ollama not responding — articles will use original summaries"
  echo "    Start with: ollama serve &"
fi

# ── 5. Test site build ─────────────────────────────────────────────────────────
echo ""
echo "[ 5/5 ] Running site build test..."
cd /root/uglyfeed
python3 generate_site.py && echo "  ✅ Build succeeded → https://techbrief.voltixio.com" \
                         || echo "  ❌ Build failed — check output above"

echo ""
echo "════════════════════════════════════════"
echo "  Update complete!"
echo "  Site: https://techbrief.voltixio.com"
echo "════════════════════════════════════════"
echo ""

# ── Cron reminder ─────────────────────────────────────────────────────────────
echo "Active cron jobs:"
crontab -l 2>/dev/null || echo "  (none)"
