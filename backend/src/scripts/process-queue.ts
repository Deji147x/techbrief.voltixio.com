import 'dotenv/config';
import { prisma } from '../lib/prisma';
import { processArticle } from '../services/aiProcessor';

async function run() {
  const unprocessed = await prisma.article.findMany({
    where: { aiProcessed: false },
    take: 10,
  });

  for (const article of unprocessed) {
    try {
      await processArticle(article.id);
      console.log(`[ai] processed ${article.id}`);
    } catch (err) {
      console.error(`[ai] failed to process ${article.id}:`, (err as Error).message);
    }
  }
}

run();
