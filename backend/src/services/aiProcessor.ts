import OpenAI from 'openai';
import { prisma } from '../lib/prisma';
import { TECHBRIEF_CATEGORIES } from '../lib/categories';

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
const MODEL = process.env.OPENAI_MODEL || 'gpt-4-turbo-preview';

async function generateSummary(content: string): Promise<string> {
  const res = await openai.chat.completions.create({
    model: MODEL,
    messages: [
      { role: 'system', content: 'Summarize this tech news article in 2-3 sentences for a technical/professional audience.' },
      { role: 'user', content },
    ],
  });
  return res.choices[0]?.message?.content ?? '';
}

async function generateSimplified(content: string): Promise<string> {
  const res = await openai.chat.completions.create({
    model: MODEL,
    messages: [
      { role: 'system', content: "Explain this tech news article like I'm 5 years old, in 2-3 simple sentences." },
      { role: 'user', content },
    ],
  });
  return res.choices[0]?.message?.content ?? '';
}

async function generateLabels(content: string): Promise<string[]> {
  const res = await openai.chat.completions.create({
    model: MODEL,
    response_format: { type: 'json_object' },
    messages: [
      {
        role: 'system',
        content: `Categorize this article. Return JSON: {"labels": string[]}. Each label MUST be exactly one of: ${TECHBRIEF_CATEGORIES.join(', ')}. Use multiple labels if the article spans categories.`,
      },
      { role: 'user', content },
    ],
  });
  const parsed = JSON.parse(res.choices[0]?.message?.content ?? '{"labels":[]}');
  const labels: string[] = Array.isArray(parsed.labels) ? parsed.labels : [];
  // Enforce the canonical enum — drop anything the model hallucinates outside it.
  return labels.filter((l) => (TECHBRIEF_CATEGORIES as readonly string[]).includes(l));
}

/**
 * Process a single article. Each AI call is independent and retried on its own —
 * a failure in one (e.g. labels) doesn't re-run the others (fixes bug #3).
 */
export async function processArticle(articleId: string): Promise<void> {
  const article = await prisma.article.findUnique({ where: { id: articleId } });
  if (!article) return;

  const content = article.rawContent || article.description || article.title;

  const [summary, simplified, labels] = await Promise.all([
    retry(() => generateSummary(content)),
    retry(() => generateSimplified(content)),
    retry(() => generateLabels(content)),
  ]);

  await prisma.article.update({
    where: { id: articleId },
    data: {
      aiSummary: summary,
      aiSimplified: simplified,
      aiLabel: labels,
      aiProcessed: true,
      processedAt: new Date(),
    },
  });
}

async function retry<T>(fn: () => Promise<T>, attempts = 3): Promise<T> {
  let lastErr: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      await new Promise((r) => setTimeout(r, 500 * 2 ** i));
    }
  }
  throw lastErr;
}
