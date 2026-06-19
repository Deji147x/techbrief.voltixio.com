import React from 'react';
import { Article, recordEngagement } from '../lib/api';

interface ArticleCardProps {
  article: Article;
  onSelect: (id: string) => void;
}

export function ArticleCard({ article, onSelect }: ArticleCardProps) {
  const handleClick = () => {
    recordEngagement(article.id, 'view');
    onSelect(article.id);
  };

  return (
    <div
      onClick={handleClick}
      className="bg-white rounded-xl shadow-sm hover:shadow-md transition cursor-pointer p-4"
    >
      {article.imageUrl && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={article.imageUrl} alt="" className="w-full h-32 object-cover rounded-lg mb-3" />
      )}
      <h3 className="font-semibold text-slate-800 line-clamp-2">{article.title}</h3>
      <p className="text-sm text-slate-500 mt-1">{article.source}</p>
      {article.aiLabel.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {article.aiLabel.map((label) => (
            <span key={label} className="px-2 py-0.5 bg-slate-100 rounded-full text-xs text-slate-600">
              {label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
