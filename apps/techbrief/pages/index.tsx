import React, { useState, useEffect } from 'react';
import { Layout } from '../components/Layout';
import { ArticleCard } from '../components/ArticleCard';
import { AIAssistant } from '../components/AIAssistant';
import { OpposingViews } from '../components/OpposingViews';
import { Article, getArticles } from '../lib/api';

type Tab = 'feed' | 'ai-assistant' | 'opposing-views';

export default function Home() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedArticle, setSelectedArticle] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('feed');

  useEffect(() => {
    getArticles()
      .then(setArticles)
      .finally(() => setIsLoading(false));
  }, []);

  const handleSelect = (id: string) => {
    setSelectedArticle(id);
    setTab('ai-assistant');
  };

  return (
    <Layout>
      <div className="flex gap-2 mb-6">
        {(['feed', 'ai-assistant', 'opposing-views'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              tab === t ? 'bg-blue-600 text-white' : 'bg-white text-slate-600'
            }`}
          >
            {t.replace('-', ' ')}
          </button>
        ))}
      </div>

      {tab === 'feed' && (
        isLoading ? (
          <p className="text-slate-500">Loading articles...</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {articles.map((article) => (
              <ArticleCard key={article.id} article={article} onSelect={handleSelect} />
            ))}
          </div>
        )
      )}

      {tab === 'ai-assistant' && <AIAssistant articleId={selectedArticle} />}
      {tab === 'opposing-views' && <OpposingViews articleId={selectedArticle} />}
    </Layout>
  );
}
