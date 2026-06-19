import React, { useState, useEffect } from 'react';
import { getOpposingViews } from '../lib/api';

interface OpposingViewsProps {
  articleId: string | null;
}

export function OpposingViews({ articleId }: OpposingViewsProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    if (!articleId) {
      setData(null);
      return;
    }
    setIsLoading(true);
    setError(null);
    getOpposingViews(articleId)
      .then(setData)
      .catch(() => setError('No opposing views available for this article.'))
      .finally(() => setIsLoading(false));
  }, [articleId]);

  if (!articleId) {
    return <p className="text-slate-500 text-center py-12">Select an article to see competing takes.</p>;
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" />
      </div>
    );
  }

  if (error || !data) {
    return <p className="text-slate-500 text-center py-12">{error}</p>;
  }

  const sections: { key: 'supporting' | 'opposing' | 'neutral'; label: string; color: string }[] = [
    { key: 'supporting', label: 'Supporting take', color: 'bg-green-50 border-green-200' },
    { key: 'opposing', label: 'Opposing take', color: 'bg-red-50 border-red-200' },
    { key: 'neutral', label: 'Neutral take', color: 'bg-slate-50 border-slate-200' },
  ];

  return (
    <div className="space-y-4">
      {sections.map(({ key, label, color }) => (
        <div key={key} className={`rounded-xl p-4 border ${color}`}>
          <h4 className="font-semibold text-slate-800 mb-2">{label}</h4>
          {data[key].length === 0 ? (
            <p className="text-sm text-slate-500">No articles found.</p>
          ) : (
            <ul className="space-y-1">
              {data[key].map((a: { id: string; title: string; source: string }) => (
                <li key={a.id} className="text-sm text-slate-700">
                  {a.title} <span className="text-slate-400">— {a.source}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
