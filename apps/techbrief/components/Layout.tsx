import React from 'react';
import Head from 'next/head';
import Link from 'next/link';
import { Article } from '../lib/api';

interface LayoutProps {
  children: React.ReactNode;
  tickerArticles?: Article[];
  title?: string;
  description?: string;
  canonicalPath?: string;
  ogImage?: string;
}

const SITE_NAME = 'TechBrief';
const SITE_URL = 'https://techbrief.voltixio.com';
const DEFAULT_DESCRIPTION =
  'AI-rewritten tech news, updated hourly. Breaking coverage of AI, cybersecurity, startups, big tech, gadgets, and space — summarized fast.';

export function Layout({
  children,
  tickerArticles = [],
  title,
  description = DEFAULT_DESCRIPTION,
  canonicalPath = '/',
  ogImage,
}: LayoutProps) {
  const pageTitle = title ? `${title} | ${SITE_NAME}` : `${SITE_NAME} — AI-Rewritten Tech News, Updated Hourly`;
  const canonicalUrl = `${SITE_URL}${canonicalPath}`;

  return (
    <>
      <Head>
        <title>{pageTitle}</title>
        <meta name="description" content={description} />
        <link rel="canonical" href={canonicalUrl} />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="robots" content="index, follow" />
        <meta property="og:type" content="website" />
        <meta property="og:site_name" content={SITE_NAME} />
        <meta property="og:title" content={pageTitle} />
        <meta property="og:description" content={description} />
        <meta property="og:url" content={canonicalUrl} />
        {ogImage && <meta property="og:image" content={ogImage} />}
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={pageTitle} />
        <meta name="twitter:description" content={description} />
        {ogImage && <meta name="twitter:image" content={ogImage} />}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              '@context': 'https://schema.org',
              '@type': 'NewsMediaOrganization',
              name: SITE_NAME,
              url: SITE_URL,
              description: DEFAULT_DESCRIPTION,
            }),
          }}
        />
      </Head>

      {tickerArticles.length > 0 && (
        <div className="ticker-wrap">
          <div className="container ticker-inner">
            <span className="ticker-label">Breaking</span>
            <div className="ticker-track">
              <div className="ticker-items">
                {tickerArticles.map((a) => (
                  <span key={a.id}>{a.title}</span>
                ))}
                {tickerArticles.map((a) => (
                  <span key={`${a.id}-dup`}>{a.title}</span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <header>
        <div className="container inner">
          <div className="logo-wrap">
            <Link href="/" className="logo-text">
              Tech<span>Brief</span>
            </Link>
          </div>
          <nav>
            <Link href="/">Home</Link>
            <Link href="/about">About</Link>
            <Link href="/contact">Contact</Link>
          </nav>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <span className="live-dot">Live</span>
            <form action="/" method="get" className="search-bar">
              <input type="text" name="q" placeholder="Search news..." aria-label="Search news" />
              <button type="submit">Go</button>
            </form>
          </div>
        </div>
      </header>

      <main>{children}</main>

      <footer>
        <div className="container">
          <div className="footer-grid">
            <div className="footer-brand">
              <div className="logo-text">
                Tech<span>Brief</span>
              </div>
              <p>{DEFAULT_DESCRIPTION}</p>
            </div>
            <div className="footer-col">
              <h4>Sections</h4>
              <Link href="/">Latest</Link>
              <Link href="/">AI &amp; Machine Learning</Link>
              <Link href="/">Cybersecurity</Link>
              <Link href="/">Big Tech</Link>
            </div>
            <div className="footer-col">
              <h4>Company</h4>
              <Link href="/about">About</Link>
              <Link href="/contact">Contact</Link>
            </div>
            <div className="footer-col">
              <h4>Contact</h4>
              <div className="contact-item">
                <a href="mailto:voltixio_editor@voltixio.com">voltixio_editor@voltixio.com</a>
              </div>
            </div>
          </div>
          <div className="footer-bottom">
            <span>&copy; {new Date().getFullYear()} TechBrief by Voltixio. AI-rewritten summaries, sources linked.</span>
          </div>
        </div>
      </footer>
    </>
  );
}
