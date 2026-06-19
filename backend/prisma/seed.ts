import { prisma } from '../src/lib/prisma';

async function main() {
  await prisma.article.upsert({
    where: { url: 'https://example.com/seed-article' },
    update: {},
    create: {
      title: 'Welcome to TechBrief',
      description: 'Seed article for local development.',
      url: 'https://example.com/seed-article',
      source: 'seed',
      publishedAt: new Date(),
    },
  });
}

main()
  .catch((err) => {
    console.error(err);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
