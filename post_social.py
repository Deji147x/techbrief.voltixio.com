#!/usr/bin/env python3
"""
post_social.py — Master social dispatcher for TechBrief.

Runs all social posters in sequence after each site build:
  1. X (Twitter)
  2. Facebook Page
  3. Reddit
  4. Telegram

Cron line (add AFTER generate_site.py):
  0 * * * * cd /root/uglyfeed && python3 generate_site.py && python3 post_social.py >> /var/log/techbrief.log 2>&1

Individual posters can still be run standalone:
  python3 post_facebook.py
  python3 post_reddit.py
  python3 post_telegram.py
"""

import subprocess
import sys
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

POSTERS = [
    ("X / Twitter",  os.path.join(SCRIPT_DIR, "post_twitter.py")),
    ("Facebook",     os.path.join(SCRIPT_DIR, "post_facebook.py")),
    ("Reddit",       os.path.join(SCRIPT_DIR, "post_reddit.py")),
    ("Telegram",     os.path.join(SCRIPT_DIR, "post_telegram.py")),
]

def run_poster(name: str, script_path: str):
    if not os.path.exists(script_path):
        print(f"  ⏭  {name}: script not found, skipping.")
        return
    print(f"\n── {name} ──────────────────────────────")
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=False,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"  ⚠  {name} exited with code {result.returncode}")
        else:
            print(f"  ✅ {name} done")
    except subprocess.TimeoutExpired:
        print(f"  ⚠  {name} timed out after 120s")
    except Exception as e:
        print(f"  ⚠  {name} error: {e}")


def main():
    print(f"\n{'='*50}")
    print(f"  TechBrief Social Dispatcher")
    print(f"  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"{'='*50}")

    for name, path in POSTERS:
        run_poster(name, path)

    print(f"\n{'='*50}")
    print(f"  All social posts dispatched.")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
