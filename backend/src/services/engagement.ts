import { prisma } from '../lib/prisma';

const WEIGHTS: Record<string, number> = { view: 1, read: 3, share: 5 };

export async function recordEngagement(articleId: string, type: 'view' | 'read' | 'share', userId?: string): Promise<void> {
  await prisma.$transaction([
    prisma.engagementEvent.create({ data: { articleId, type, userId } }),
    prisma.article.update({
      where: { id: articleId },
      data: { engagementScore: { increment: WEIGHTS[type] ?? 0 } },
    }),
  ]);
}
