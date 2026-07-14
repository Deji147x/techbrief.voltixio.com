const API_URL = process.env.NEXT_PUBLIC_API_URL;
const STORAGE_KEY = 'tb_visitor_id';

export function getVisitorId(): string {
  if (typeof window === 'undefined') return '';
  let id = window.localStorage.getItem(STORAGE_KEY);
  if (!id) {
    id = crypto.randomUUID();
    window.localStorage.setItem(STORAGE_KEY, id);
  }
  return id;
}

export function trackPageview(path: string): void {
  if (typeof window === 'undefined') return;
  const visitorId = getVisitorId();
  fetch(`${API_URL}/analytics/track`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ visitorId, path, referrer: document.referrer || undefined }),
    keepalive: true,
  }).catch(() => {});
}
