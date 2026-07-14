import 'dotenv/config';
import cron from 'node-cron';
import { pollFeeds } from '../services/rssAggregator';

async function run() {
  const result = await pollFeeds();
  console.log(`[rss] fetched ${result.fetched}, stored ${result.stored} new articles`);
}

// Every 30 min — not the excessive 5-min cadence flagged in bug #19.
cron.schedule('*/30 * * * *', run);
run();
