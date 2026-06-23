import React from 'react';
import Link from 'next/link';
import { Layout } from '../components/Layout';

export default function About() {
  return (
    <Layout
      title="About"
      description="Tech Brief is an AI-powered technology news platform built by Voltixio. Original, plagiarism-free tech journalism updated every hour."
      canonicalPath="/about"
    >
      <div className="about-hero">
        <div className="container">
          <div className="about-badge">About Tech Brief</div>
          <h1>
            AI-Powered News,
            <br />
            <span>Built for the Future</span>
          </h1>
          <p>
            Every hour, our pipeline fetches and summarizes the tech world&apos;s most important stories — fast,
            clean, and ad-free.
          </p>
        </div>
      </div>

      <div className="container" style={{ maxWidth: 1100, paddingTop: 48, paddingBottom: 80 }}>
        <div className="stats-row">
          <div className="stat-box">
            <span className="num">40+</span>
            <span className="lbl">Source feeds</span>
          </div>
          <div className="stat-box">
            <span className="num">24/7</span>
            <span className="lbl">Live updates</span>
          </div>
          <div className="stat-box">
            <span className="num">100%</span>
            <span className="lbl">Original</span>
          </div>
          <div className="stat-box">
            <span className="num">0</span>
            <span className="lbl">Plagiarism</span>
          </div>
        </div>

        <div className="section-header">
          <h2>Our Mission</h2>
        </div>
        <div className="about-grid">
          <div className="content-box" style={{ margin: 0 }}>
            <p style={{ marginBottom: 14 }}>
              Tech Brief was built on a simple belief: technology news should be fast, original, and accessible to
              everyone. We pull from 40+ premium RSS sources, summarize and contextualize every article using a
              locally-hosted language model, and publish the result — every single hour, around the clock.
            </p>
            <p style={{ marginBottom: 14 }}>
              No paywalls. No copy-paste journalism. No tracking pixels selling your data. Just clean, original
              coverage of the stories shaping the world of technology.
            </p>
            <p>
              We cover the six verticals that matter most:{' '}
              <strong style={{ color: 'var(--blue2)' }}>
                AI &amp; Machine Learning, Cybersecurity, Startups &amp; VC, Big Tech, Gadgets &amp; Hardware,
              </strong>{' '}
              and <strong style={{ color: 'var(--blue2)' }}>Space &amp; Science.</strong>
            </p>
          </div>
          <div className="content-box" style={{ margin: 0 }}>
            <h3 style={{ marginTop: 0, color: 'var(--blue2)' }}>Our Technology Stack</h3>
            <p style={{ marginBottom: 12 }}>
              <strong style={{ color: 'var(--white)' }}>RSS Aggregation</strong> — Our pipeline pulls from 40+
              curated tech sources every hour.
            </p>
            <p style={{ marginBottom: 12 }}>
              <strong style={{ color: 'var(--white)' }}>Smart Summarization</strong> — Every article is summarized
              and contextualized using AI.
            </p>
            <p style={{ marginBottom: 12 }}>
              <strong style={{ color: 'var(--white)' }}>Real-Time Pipeline</strong> — Articles are processed and
              published continuously, around the clock.
            </p>
            <p>
              <strong style={{ color: 'var(--white)' }}>Modern Web Stack</strong> — Built on Next.js and a Postgres
              database for speed and reliability.
            </p>
          </div>
        </div>

        <div className="section-header">
          <h2>How It Works</h2>
        </div>
        <div className="pipeline-row">
          <div className="pipe-step">
            <div className="pipe-num">1</div>
            <span className="icon">📡</span>
            <h3>Aggregate</h3>
            <p>RSS feeds from 40+ trusted tech publications pulled every hour.</p>
          </div>
          <div className="pipe-step">
            <div className="pipe-num">2</div>
            <span className="icon">🤖</span>
            <h3>Rewrite</h3>
            <p>AI produces a clean, readable summary of every story.</p>
          </div>
          <div className="pipe-step">
            <div className="pipe-num">3</div>
            <span className="icon">🏷️</span>
            <h3>Categorize</h3>
            <p>Stories are sorted into focused verticals automatically.</p>
          </div>
          <div className="pipe-step">
            <div className="pipe-num">4</div>
            <span className="icon">🚀</span>
            <h3>Publish</h3>
            <p>The site updates continuously — always current, never stale.</p>
          </div>
        </div>

        <div className="section-header">
          <h2>What We Stand For</h2>
        </div>
        <div className="values-grid">
          <div className="val-card">
            <div className="icon">⚡</div>
            <h3>Speed Without Compromise</h3>
            <p>Our pipeline updates continuously so you&apos;re never reading yesterday&apos;s news.</p>
          </div>
          <div className="val-card">
            <div className="icon">🔒</div>
            <h3>Privacy First</h3>
            <p>No third-party ad networks, no data brokers, no cookies beyond essential analytics.</p>
          </div>
          <div className="val-card">
            <div className="icon">✍️</div>
            <h3>Original Content</h3>
            <p>Every article rewritten from scratch. We don&apos;t republish — we create.</p>
          </div>
          <div className="val-card">
            <div className="icon">🌐</div>
            <h3>Free &amp; Open</h3>
            <p>No paywalls, no subscriptions. Quality tech journalism free for everyone.</p>
          </div>
          <div className="val-card">
            <div className="icon">🎯</div>
            <h3>Focused Coverage</h3>
            <p>Six verticals only — AI, Cyber, Startups, Big Tech, Gadgets, Space. Depth over breadth.</p>
          </div>
          <div className="val-card">
            <div className="icon">📊</div>
            <h3>Transparent Sources</h3>
            <p>Every article links back to the original publication. Always.</p>
          </div>
        </div>

        <div className="built-by-box">
          <div className="v-logo">V</div>
          <div>
            <h2>
              Built by <span>Voltixio</span>
            </h2>
            <p>
              Tech Brief is a product of Voltixio — a technology company building AI-powered tools and platforms.
              Voltixio develops automation pipelines, intelligent agents, and consumer products at the intersection
              of artificial intelligence and real-world utility.
            </p>
            <div className="link-pills">
              <a href="https://voltixio.com" target="_blank" rel="noopener noreferrer" className="link-pill">
                ↗ voltixio.com
              </a>
              <a href="mailto:voltixio_editor@voltixio.com" className="link-pill">
                ✉ voltixio_editor@voltixio.com
              </a>
              <Link href="/contact" className="link-pill">
                ✦ Contact
              </Link>
            </div>
          </div>
        </div>

        <div className="about-cta">
          <h2>Stay Ahead of the Curve</h2>
          <p>Get the top tech stories delivered to your inbox every morning. Free, forever.</p>
          <div className="cta-row">
            <Link href="/contact" className="btn-p">
              Subscribe Free →
            </Link>
            <Link href="/" className="btn-g">
              Read Latest News
            </Link>
          </div>
        </div>
      </div>
    </Layout>
  );
}
