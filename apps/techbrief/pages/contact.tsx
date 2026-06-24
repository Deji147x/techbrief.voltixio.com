import React from 'react';
import { Layout } from '../components/Layout';

export default function Contact() {
  return (
    <Layout
      title="Contact"
      description="Questions, tips, partnerships, corrections — Tech Brief reads every message."
      canonicalPath="/contact"
    >
      <div className="page-hero">
        <div className="container">
          <h1>Contact TechBrief</h1>
          <p>Questions, tips, partnerships, corrections — we read every message</p>
        </div>
      </div>

      <div className="container" style={{ maxWidth: 900 }}>
        <div className="contact-grid" style={{ marginTop: 0 }}>
          <div className="content-box" style={{ margin: '30px 0' }}>
            <h3 style={{ marginTop: 0 }}>Get in Touch</h3>
            <p style={{ marginBottom: 20 }}>
              For editorial questions, corrections, story tips, advertising enquiries, or partnership
              opportunities, reach out via any of the channels below.
            </p>
            <div className="contact-item" style={{ marginBottom: 14 }}>
              📧 &nbsp;<a href="mailto:voltixio_editor@voltixio.com">voltixio_editor@voltixio.com</a>
            </div>
            <div className="contact-item" style={{ marginBottom: 14 }}>
              🌐 &nbsp;
              <a href="https://voltixio.com" target="_blank" rel="noopener noreferrer">
                voltixio.com
              </a>
            </div>
            <p style={{ marginTop: 20, fontSize: '0.85rem', color: 'var(--silver)' }}>
              We typically respond within 48 hours.
            </p>
          </div>
          <div className="content-box" style={{ margin: '30px 0' }}>
            <h3 style={{ marginTop: 0 }}>Send a Message</h3>
            <form className="contact-form" action="mailto:voltixio_editor@voltixio.com" method="post" encType="text/plain">
              <input type="text" name="name" placeholder="Your name" required />
              <input type="email" name="email" placeholder="Your email" required />
              <input type="text" name="subject" placeholder="Subject" />
              <textarea name="message" placeholder="Your message…" required />
              <button type="submit">Send Message →</button>
            </form>
          </div>
        </div>
      </div>
    </Layout>
  );
}
