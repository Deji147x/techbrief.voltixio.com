import React from 'react';
import type { GetServerSideProps } from 'next';
import Link from 'next/link';
import { Layout } from '../../components/Layout';
import { ArticleCard } from '../../components/ArticleCard';
import { Article } from '../../lib/api';
import { categorySlug, categoryFromSlug } from '../../lib/categories';

const API_URL = process.env.NEXT_PUBLIC_API_URL;

interface CategoryPageProps {
  category: string;
  articles: Article[];
}

export default function CategoryPage({ category, articles }: CategoryPageProps) {
  return (
    <Layout title={category} canonicalPath={`/category/${categorySlug(category)}`}>
      <div className="page-hero">
        <div className="container">
          <h1>{category}</h1>
          <p>Original {category} news — updated every hour</p>
        </div>
      </div>
      <div className="container">
        <div className="section-header">
          <h2>{articles.length} Stories</h2>
          <Link href="/">← All news</Link>
        </div>
        <div className="grid">
          {articles.map((article) => (
            <ArticleCard key={article.id} article={article} />
          ))}
          {articles.length === 0 && (
            <p style={{ color: 'var(--silver)', padding: '40px 0' }}>
              No articles in this category yet. Check back soon.
            </p>
          )}
        </div>
      </div>
    </Layout>
  );
}

export const getServerSideProps: GetServerSideProps<CategoryPageProps> = async ({ params }) => {
  const slug = params?.slug as string;
  const res = await fetch(`${API_URL}/articles?pageSize=50`);
  if (!res.ok) throw new Error('Failed to load articles');
  const data = await res.json();
  const all: Article[] = data.articles;

  const categories = Array.from(new Set(all.map((a) => a.aiLabel[0] || 'Technology')));
  const category = categoryFromSlug(slug, categories);
  if (!category) return { notFound: true };

  const articles = all.filter((a) => (a.aiLabel[0] || 'Technology') === category);
  return { props: { category, articles } };
};
