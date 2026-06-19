import Parser from 'rss-parser';
import { prisma } from '../lib/prisma';
import { TECHBRIEF_FEEDS } from '../config/feeds';

const parser = new Parser();

export async function pollFeeds(): Promise<{ fetched: number; stored: number }> {
  let fetched = 0;
  let stored = 0;

  for (const feedUrl of TECHBRIEF_FEEDS) {
    let feed;
    try {
      feed = await parser.parseURL(feedUrl);
    } catch (err) {
      console.error(`[rss] failed to fetch ${feedUrl}:`, (err as Error).message);
      continue;
    }

    for (const item of feed.items) {
      if (!item.link || !item.title) continue;
      fetched += 1;

      // Dedup on URL uniqueness constraint — no separate similarity engine needed.
      const existing = await prisma.article.findUnique({ where: { url: item.link } });
      if (existing) continue;

      await prisma.article.create({
        data: {
          title: item.title,
          description: item.contentSnippet ?? null,
          url: item.link,
          source: feed.title ?? new URL(feedUrl).hostname,
          rawContent: item.content ?? null,
          imageUrl: (item as any).enclosure?.url ?? null,
          publishedAt: item.pubDate ? new Date(item.pubDate) : new Date(),
        },
      });
      stored += 1;
    }
  }

  return { fetched, stored };
}
