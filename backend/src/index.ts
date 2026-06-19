import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import rateLimit from 'express-rate-limit';
import { articlesRouter } from './routes/articles';

const app = express();

app.use(cors({ origin: process.env.CORS_ORIGIN }));
app.use(express.json());
app.use(rateLimit({ windowMs: 60_000, max: 120 }));

app.use('/articles', articlesRouter);

app.get('/health', (_req, res) => res.json({ ok: true }));

const port = Number(process.env.PORT) || 4000;
app.listen(port, () => console.log(`backend listening on :${port}`));
