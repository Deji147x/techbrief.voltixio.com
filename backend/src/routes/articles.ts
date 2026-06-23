import { Router } from 'express';
import { prisma } from '../lib/prisma';
import { findOpposingViews } from '../services/opposingViews';
import { recordEngagement } from '../services/engagement';

export const articlesRouter = Router();

articlesRouter.get('/', async (req, res) => {
  try {
    const search = typeof req.query.q === 'string' ? req.query.q : undefined;
    const page = Math.max(1, parseInt(String(req.query.page ?? '1'), 10) || 1);
    const pageSize = Math.min(50, parseInt(String(req.query.pageSize ?? '20'), 10) || 20);

    const articles = await prisma.article.findMany({
      where: search
        ? { title: { contains: search, mode: 'insensitive' } }
        : undefined,
      orderBy: { publishedAt: 'desc' },
      skip: (page - 1) * pageSize,
      take: pageSize,
    });

    res.json({ articles, page, pageSize });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to load articles' });
  }
});

articlesRouter.get('/:id', async (req, res) => {
  try {
    const article = await prisma.article.findUnique({ where: { id: req.params.id } });
    if (!article) return res.status(404).json({ error: 'Article not found' });
    res.json({ article });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to load article' });
  }
});

articlesRouter.get('/:id/ai', async (req, res) => {
  try {
    const article = await prisma.article.findUnique({ where: { id: req.params.id } });
    if (!article) return res.status(404).json({ error: 'Article not found' });

    res.json({
      summary: article.aiSummary,
      simplified: article.aiSimplified,
      keywords: article.aiKeywords,
      sentiment: article.aiSentiment,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to load AI content' });
  }
});

articlesRouter.get('/:id/opposing-views', async (req, res) => {
  try {
    const result = await findOpposingViews(req.params.id);
    if (!result) return res.status(404).json({ error: 'No opposing views available' });
    res.json(result);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to load opposing views' });
  }
});

articlesRouter.post('/:id/engagement', async (req, res) => {
  try {
    const { type, userId, visitorId } = req.body as { type?: string; userId?: string; visitorId?: string };
    if (type !== 'view' && type !== 'read' && type !== 'share') {
      return res.status(400).json({ error: 'Invalid engagement type' });
    }
    await recordEngagement(req.params.id, type, userId, visitorId);
    res.status(204).end();
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to record engagement' });
  }
});
