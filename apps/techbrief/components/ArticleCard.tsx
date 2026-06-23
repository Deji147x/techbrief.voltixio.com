import React from 'react';
import Link from 'next/link';
import { Article, recordEngagement } from '../lib/api';

interface ArticleCardProps {
  article: Article;
}

function timeAgo(dateStr: string): string {
  const diffMs = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function ArticleCard({ article }: ArticleCardProps) {
  const category = article.aiLabel[0] || 'Technology';
  const excerpt = article.aiSummary || article.description || '';

  return (
    <div className="card" onClick={() => recordEngagement(article.id, 'view')}>
      <Link href={`/article/${article.id}`}>
        <div className="card-img-wrap">
          {article.imageUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={article.imageUrl} alt={article.title} loading="lazy" />
          )}
          <div className="card-img-overlay">
            <span className="card-img-cat">{category}</span>
          </div>
        </div>
        <div className="card-content">
          <h3 style={{ color: 'var(--white)', fontSize: '1.05rem', fontWeight: 700, marginBottom: '8px', lineHeight: 1.35 }}>
            {article.title}
          </h3>
          {excerpt && <p className="card-excerpt">{excerpt.slice(0, 140)}{excerpt.length > 140 ? '...' : ''}</p>}
          <div className="card-meta">{article.source} &middot; {timeAgo(article.publishedAt)}</div>
          <span className="read-more">Read full story →</span>
        </div>
      </Link>
    </div>
  );
}
