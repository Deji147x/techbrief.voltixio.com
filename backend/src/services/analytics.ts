import { prisma } from '../lib/prisma';

const DAY_MS = 24 * 60 * 60 * 1000;

export async function trackPageview(visitorId: string, path: string, referrer?: string): Promise<void> {
  const existing = await prisma.visitor.findUnique({ where: { id: visitorId } });
  const now = new Date();

  if (!existing) {
    await prisma.visitor.create({ data: { id: visitorId, firstSeenAt: now, lastSeenAt: now } });
  } else {
    const isNewDay = now.getTime() - existing.lastSeenAt.getTime() > DAY_MS / 2;
    await prisma.visitor.update({
      where: { id: visitorId },
      data: { lastSeenAt: now, visitCount: isNewDay ? { increment: 1 } : undefined },
    });
  }

  await prisma.pageView.create({ data: { visitorId, path, referrer } });
}

function startOfDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

export async function getActiveVisitors(sinceMs: number): Promise<number> {
  const since = new Date(Date.now() - sinceMs);
  return prisma.visitor.count({ where: { lastSeenAt: { gte: since } } });
}

export async function getRetentionSummary() {
  const now = new Date();
  const [dau, wau, mau, totalVisitors, returningVisitors, topPages] = await Promise.all([
    getActiveVisitors(DAY_MS),
    getActiveVisitors(7 * DAY_MS),
    getActiveVisitors(30 * DAY_MS),
    prisma.visitor.count(),
    prisma.visitor.count({ where: { visitCount: { gt: 1 } } }),
    prisma.pageView.groupBy({
      by: ['path'],
      _count: { path: true },
      orderBy: { _count: { path: 'desc' } },
      take: 10,
    }),
  ]);

  // Day-1 / Day-7 retention: of visitors first seen N+ days ago, what fraction
  // came back at least once on/after day N from their first visit.
  const cohortRetention = async (dayOffset: number) => {
    const cohortStart = new Date(now.getTime() - (dayOffset + 14) * DAY_MS);
    const cohortEnd = new Date(now.getTime() - dayOffset * DAY_MS);
    const cohort = await prisma.visitor.findMany({
      where: { firstSeenAt: { gte: cohortStart, lt: cohortEnd } },
      select: { id: true, firstSeenAt: true, lastSeenAt: true },
    });
    if (cohort.length === 0) return null;
    const returned = cohort.filter(
      (v) => v.lastSeenAt.getTime() - v.firstSeenAt.getTime() >= dayOffset * DAY_MS
    ).length;
    return { cohortSize: cohort.length, returned, rate: returned / cohort.length };
  };

  const [day1Retention, day7Retention] = await Promise.all([cohortRetention(1), cohortRetention(7)]);

  return {
    dau,
    wau,
    mau,
    totalVisitors,
    returningVisitors,
    returningVisitorRate: totalVisitors > 0 ? returningVisitors / totalVisitors : 0,
    day1Retention,
    day7Retention,
    topPages: topPages.map((p) => ({ path: p.path, views: p._count.path })),
    generatedAt: startOfDay(now).toISOString(),
  };
}
