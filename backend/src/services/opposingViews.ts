import { prisma } from '../lib/prisma';

export interface OpposingViewsResult {
  article: { id: string; title: string };
  supporting: { id: string; title: string; source: string }[];
  opposing: { id: string; title: string; source: string }[];
  neutral: { id: string; title: string; source: string }[];
}

/**
 * Finds competing analytical/technical takes on the same topic.
 * TechBrief uses stance framing (supporting/opposing/neutral), NOT political
 * left/right — see REBUILD_SPEC.md decision #4. NewsFeed's political framing
 * is a separate, unrelated classification problem.
 */
export async function findOpposingViews(articleId: string): Promise<OpposingViewsResult | null> {
  const article = await prisma.article.findUnique({ where: { id: articleId } });
  if (!article || article.aiLabel.length === 0) return null;

  // aiLabel is String[] — use hasSome, not `contains` (fixes bug #15).
  const related = await prisma.article.findMany({
    where: {
      id: { not: articleId },
      aiLabel: { hasSome: article.aiLabel },
      aiSentiment: { not: null },
    },
    take: 20,
    orderBy: { publishedAt: 'desc' },
  });

  const bucket = { supporting: [], opposing: [], neutral: [] } as Record<
    'supporting' | 'opposing' | 'neutral',
    { id: string; title: string; source: string }[]
  >;

  for (const r of related) {
    const stance = (r.aiSentiment as 'supporting' | 'opposing' | 'neutral' | null) ?? 'neutral';
    bucket[stance].push({ id: r.id, title: r.title, source: r.source });
  }

  return {
    article: { id: article.id, title: article.title },
    ...bucket,
  };
}
