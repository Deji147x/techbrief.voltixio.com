const API_URL = process.env.NEXT_PUBLIC_API_URL;

export interface Article {
  id: string;
  title: string;
  description: string | null;
  url: string;
  source: string;
  imageUrl: string | null;
  publishedAt: string;
  aiLabel: string[];
  aiSummary: string | null;
}

export async function getArticles(search?: string): Promise<Article[]> {
  const url = new URL(`${API_URL}/articles`);
  if (search) url.searchParams.set('q', search);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error('Failed to load articles');
  const data = await res.json();
  return data.articles;
}

export async function getAIContent(articleId: string) {
  const res = await fetch(`${API_URL}/articles/${articleId}/ai`);
  if (!res.ok) throw new Error('Failed to load AI content');
  return res.json();
}

export async function getOpposingViews(articleId: string) {
  const res = await fetch(`${API_URL}/articles/${articleId}/opposing-views`);
  if (!res.ok) throw new Error('Failed to load opposing views');
  return res.json();
}

export async function recordEngagement(articleId: string, type: 'view' | 'read' | 'share') {
  const { getVisitorId } = await import('./analytics');
  await fetch(`${API_URL}/articles/${articleId}/engagement`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, visitorId: getVisitorId() }),
  }).catch((err) => console.error('Failed to record engagement:', err));
}
