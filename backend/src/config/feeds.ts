import fs from 'fs';
import path from 'path';

// Resolves decision #7: reuse the existing curated feeds.txt at repo root
// instead of the separate, partially-dead RSS_SOURCES list reviewed earlier.
function loadFeeds(): string[] {
  const feedsPath = path.resolve(__dirname, '../../../feeds.txt');
  const raw = fs.readFileSync(feedsPath, 'utf-8');
  return raw
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith('#'));
}

export const TECHBRIEF_FEEDS = loadFeeds();
