import { Router } from 'express';
import { trackPageview, getRetentionSummary } from '../services/analytics';

export const analyticsRouter = Router();

analyticsRouter.post('/track', async (req, res) => {
  try {
    const { visitorId, path, referrer } = req.body as {
      visitorId?: string;
      path?: string;
      referrer?: string;
    };
    if (!visitorId || typeof visitorId !== 'string' || !path || typeof path !== 'string') {
      return res.status(400).json({ error: 'visitorId and path are required' });
    }
    await trackPageview(visitorId, path, referrer);
    res.status(204).end();
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to record pageview' });
  }
});

analyticsRouter.get('/summary', async (req, res) => {
  try {
    const key = req.header('x-admin-key');
    if (!process.env.ADMIN_API_KEY || key !== process.env.ADMIN_API_KEY) {
      return res.status(401).json({ error: 'Unauthorized' });
    }
    const summary = await getRetentionSummary();
    res.json(summary);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to load analytics summary' });
  }
});
