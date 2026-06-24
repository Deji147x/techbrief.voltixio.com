import React, { useEffect } from 'react';
import type { GetServerSideProps } from 'next';
import Link from 'next/link';
import { Layout } from '../../components/Layout';
import { RedirectBox } from '../../components/RedirectBox';
import { Article, recordEngagement } from '../../lib/api';

const API_URL = process.env.NEXT_PUBLIC_API_URL;

interface ArticlePageProps {
  article: Article;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export default function ArticlePage({ article }: ArticlePageProps) {
  const category = article.aiLabel[0] || 'Technology';
  const body = (article.aiSummary || article.description || '')
    .split(/\n+/)
    .map((p) => p.trim())
    .filter(Boolean)
    .slice(0, 3);

  useEffect(() => {
    recordEngagement(article.id, 'read');
  }, [article.id]);

  return (
    <Layout
      title={article.title}
      description={(article.aiSummary || article.description || '').slice(0, 160)}
      canonicalPath={`/article/${article.id}`}
      ogImage={article.imageUrl || undefined}
    >
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'NewsArticle',
            headline: article.title,
            datePublished: article.publishedAt,
            image: article.imageUrl ? [article.imageUrl] : undefined,
            description: article.aiSummary || article.description || undefined,
            articleSection: category,
            isBasedOn: article.url,
          }),
        }}
      />

      <div className="article-page container">
        <Link href="/" className="back-btn">
          ← Back to homepage
        </Link>

        <div className="article-hero">
          {article.imageUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={article.imageUrl} alt={article.title} />
          )}
          <div className="article-hero-overlay">
            <span className="article-hero-cat">{category}</span>
            <h1 className="article-hero-title">{article.title}</h1>
            <div className="article-hero-meta">
              {article.source} &middot; {formatDate(article.publishedAt)}
            </div>
          </div>
        </div>

        <div className="article-body">
          {body.length > 0 ? (
            body.map((p, i) => <p key={i}>{p}</p>)
          ) : (
            <p>No summary available yet.</p>
          )}
        </div>

        <RedirectBox url={article.url} source={article.source} />
      </div>
    </Layout>
  );
}

export const getServerSideProps: GetServerSideProps<ArticlePageProps> = async ({ params }) => {
  const id = params?.id as string;
  const res = await fetch(`${API_URL}/articles/${id}`);
  if (res.status === 404) return { notFound: true };
  if (!res.ok) throw new Error('Failed to load article');
  const data = await res.json();
  return { props: { article: data.article } };
};
