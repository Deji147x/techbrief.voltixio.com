import React, { useEffect, useMemo, useState } from 'react';
import { Layout } from '../components/Layout';
import { ArticleCard } from '../components/ArticleCard';
import { LiveClock } from '../components/LiveClock';
import { Article, getArticles } from '../lib/api';

const CATEGORY_ICONS: Record<string, string> = {
  'AI & Machine Learning': '🤖',
  Cybersecurity: '🛡️',
  'Startups & VC': '🚀',
  'Big Tech': '🏢',
  'Gadgets & Hardware': '📱',
  'Space & Science': '🛰️',
  Technology: '💻',
};

export default function Home() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState<string>('All');

  useEffect(() => {
    getArticles()
      .then(setArticles)
      .finally(() => setIsLoading(false));
  }, []);

  const categories = useMemo(() => {
    const set = new Set<string>();
    articles.forEach((a) => set.add(a.aiLabel[0] || 'Technology'));
    return Array.from(set);
  }, [articles]);

  const filtered = useMemo(() => {
    if (activeCategory === 'All') return articles;
    return articles.filter((a) => (a.aiLabel[0] || 'Technology') === activeCategory);
  }, [articles, activeCategory]);

  const heroArticle = articles[0];
  const gridArticles = activeCategory === 'All' ? filtered.slice(1) : filtered;

  const itemListJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    itemListElement: articles.slice(0, 20).map((a, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      url: `https://techbrief.voltixio.com/article/${a.id}`,
      name: a.title,
    })),
  };

  return (
    <Layout tickerArticles={articles.slice(0, 8)} canonicalPath="/" ogImage={heroArticle?.imageUrl || undefined}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(itemListJsonLd) }}
      />

      {heroArticle?.imageUrl && (
        <div className="hero-banner">
          <div className="hero-banner-inner">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={heroArticle.imageUrl} alt={heroArticle.title} />
          </div>
        </div>
      )}

      <div className="clock-bar">
        <div className="container inner">
          <span className="live-badge">Updated Hourly</span>
          <LiveClock />
        </div>
      </div>

      {categories.length > 0 && (
        <div className="cat-icons-row">
          <div className="container cat-icons-inner">
            {categories.map((cat) => (
              <div key={cat} className="cat-icon-item" onClick={() => setActiveCategory(cat)}>
                <span className="icon-circle">{CATEGORY_ICONS[cat] || '💻'}</span>
                {cat}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="container">
        <div className="section-header">
          <h2>Latest Stories</h2>
          <a href="/rss.xml">RSS Feed →</a>
        </div>

        <div className="cats-nav">
          <a
            className={activeCategory === 'All' ? 'active' : ''}
            onClick={() => setActiveCategory('All')}
            href="#"
          >
            All
          </a>
          {categories.map((cat) => (
            <a
              key={cat}
              className={activeCategory === cat ? 'active' : ''}
              onClick={(e) => {
                e.preventDefault();
                setActiveCategory(cat);
              }}
              href="#"
            >
              {cat}
            </a>
          ))}
        </div>

        {isLoading ? (
          <p style={{ color: 'var(--silver)' }}>Loading articles...</p>
        ) : (
          <div className="grid">
            {gridArticles.map((article) => (
              <ArticleCard key={article.id} article={article} />
            ))}
          </div>
        )}

        <div className="subscribe-cta">
          <div className="subscribe-cta-text">
            <h3>Never miss a breaking story</h3>
            <p>AI-curated tech news, rewritten and delivered hourly — straight to the point.</p>
          </div>
          <a href="mailto:hello@voltixio.com?subject=Subscribe" className="cta-btn">
            Subscribe Free
          </a>
        </div>
      </div>
    </Layout>
  );
}
