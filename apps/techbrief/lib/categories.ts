export function categorySlug(category: string): string {
  return category.toLowerCase().replace(/ & /g, '-').replace(/\s+/g, '-');
}

export function categoryFromSlug(slug: string, categories: string[]): string | undefined {
  return categories.find((c) => categorySlug(c) === slug);
}
