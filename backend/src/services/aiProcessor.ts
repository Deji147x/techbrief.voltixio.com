import { prisma } from '../lib/prisma';
import { TECHBRIEF_CATEGORIES } from '../lib/categories';

const OLLAMA_URL = process.env.OLLAMA_URL || 'http://localhost:11434';
const MODEL = process.env.OLLAMA_MODEL || 'gemma2:9b';

async function ollamaChat(system: string, content: string, json = false): Promise<string> {
  const res = await fetch(`${OLLAMA_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: MODEL,
      stream: false,
      ...(json ? { format: 'json' } : {}),
      messages: [
        { role: 'system', content: system },
        { role: 'user', content },
      ],
    }),
  });
  if (!res.ok) throw new Error(`Ollama request failed: ${res.status} ${await res.text()}`);
  const data = (await res.json()) as { message?: { content?: string } };
  return data.message?.content ?? '';
}

async function generateSummary(content: string): Promise<string> {
  return ollamaChat('Summarize this tech news article in 2-3 sentences for a technical/professional audience.', content);
}

async function generateSimplified(content: string): Promise<string> {
  return ollamaChat("Explain this tech news article like I'm 5 years old, in 2-3 simple sentences.", content);
}

async function generateLabels(content: string): Promise<string[]> {
  const raw = await ollamaChat(
    `Categorize this article. Return JSON: {"labels": string[]}. Each label MUST be exactly one of: ${TECHBRIEF_CATEGORIES.join(', ')}. Use multiple labels if the article spans categories.`,
    content,
    true,
  );
  const parsed = JSON.parse(raw || '{"labels":[]}');
  const labels: string[] = Array.isArray(parsed.labels) ? parsed.labels : [];
  return labels.filter((l) => (TECHBRIEF_CATEGORIES as readonly string[]).includes(l));
}

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
