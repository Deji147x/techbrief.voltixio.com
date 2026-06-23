import React, { useEffect, useRef, useState } from 'react';

const COUNTDOWN_SECONDS = 10;

interface RedirectBoxProps {
  url: string;
  source: string;
}

export function RedirectBox({ url, source }: RedirectBoxProps) {
  const [secondsLeft, setSecondsLeft] = useState(COUNTDOWN_SECONDS);
  const skippedRef = useRef(false);

  useEffect(() => {
    const id = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          clearInterval(id);
          if (!skippedRef.current) window.location.href = url;
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [url]);

  const progressPct = ((COUNTDOWN_SECONDS - secondsLeft) / COUNTDOWN_SECONDS) * 100;

  return (
    <div className="redirect-box">
      <div className="redirect-icon">🔗</div>
      <p>
        Redirecting you to <strong>{source}</strong> to read the full original article in {secondsLeft}s…
      </p>
      <a
        href={url}
        className="btn-skip"
        onClick={() => {
          skippedRef.current = true;
        }}
      >
        Skip — Read Original Now
      </a>
      <div className="redirect-progress">
        <div className="redirect-progress-bar" style={{ width: `${progressPct}%` }} />
      </div>
    </div>
  );
}
