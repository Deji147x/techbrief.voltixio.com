import React, { useState, useEffect, useRef } from 'react';
import { getAIContent } from '../lib/api';

interface AIAssistantProps {
  articleId: string | null;
}

type Mode = 'summary' | 'simplified' | 'keywords';

export function AIAssistant({ articleId }: AIAssistantProps) {
  const [mode, setMode] = useState<Mode>('summary');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [content, setContent] = useState<any>(null);
  const requestId = useRef(0);

  useEffect(() => {
    if (!articleId) {
      setContent(null);
      return;
    }
    const thisRequest = ++requestId.current;
    setIsLoading(true);
    setError(null);

    getAIContent(articleId)
      .then((data) => {
        if (requestId.current === thisRequest) setContent(data);
      })
      .catch(() => {
        if (requestId.current === thisRequest) setError('Failed to load AI analysis. Try again.');
      })
      .finally(() => {
        if (requestId.current === thisRequest) setIsLoading(false);
      });
  }, [articleId]);

  if (!articleId) {
    return (
      <div className="text-center py-12 text-slate-500">
        <div className="text-6xl mb-4">🤖</div>
        <p className="text-lg font-medium">No AI analysis available</p>
        <p className="text-sm">Select an article to get AI-powered insights</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-lg overflow-hidden">
      <div className="border-b border-slate-200 p-4 bg-slate-50/50 flex gap-2">
        {(['summary', 'simplified', 'keywords'] as Mode[]).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              mode === m ? 'bg-blue-600 text-white shadow-md' : 'bg-white text-slate-600 hover:bg-slate-200'
            }`}
          >
            {m}
          </button>
        ))}
      </div>

      <div className="p-6 min-h-[200px]">
        {isLoading && (
          <div className="flex justify-center items-center h-32">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" />
          </div>
        )}
        {error && <p className="text-red-600 text-sm">{error}</p>}
        {!isLoading && !error && content && (
          <>
            {mode === 'summary' && <p className="text-slate-700 leading-relaxed">{content.summary}</p>}
            {mode === 'simplified' && <p className="text-slate-700 leading-relaxed text-lg">{content.simplified}</p>}
            {mode === 'keywords' && (
              <div className="flex flex-wrap gap-2">
                {(content.keywords ?? []).map((k: string) => (
                  <span key={k} className="px-4 py-2 bg-slate-100 rounded-lg text-purple-700 font-medium">
                    {k}
                  </span>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
