import 'dotenv/config';
import { prisma } from '../lib/prisma';

/**
 * Counts label frequency across recently processed articles to surface
 * trending topics. Simple frequency count — no ML, matches what's actually
 * needed at current traffic levels.
 */
async function run() {
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000);
  const recent = await prisma.article.findMany({
    where: { aiProcessed: true, publishedAt: { gte: since } },
    select: { aiLabel: true },
  });

  const counts = new Map<string, number>();
  for (const { aiLabel } of recent) {
    for (const label of aiLabel) {
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
  }

  const trending = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  console.log('[trends] top labels in last 24h:', trending);
}

run();
