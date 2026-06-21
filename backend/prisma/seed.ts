import { prisma } from '../src/lib/prisma';

const articles = [
  {
    title: 'OpenAI rival Anthropic ships new agentic coding tools',
    description: 'A look at the latest wave of AI coding assistants and what it means for developer workflows.',
    url: 'https://example.com/seed/ai-coding-tools',
    source: 'seed',
    aiLabel: ['AI/ML', 'Developer Tools/Programming'],
    aiSummary: 'Anthropic and competitors are racing to ship agentic coding assistants that can plan and execute multi-step engineering tasks autonomously.',
    aiSimplified: 'Companies are making AI helpers that can write and fix code on their own, not just suggest snippets.',
    aiProcessed: true,
    aiSentiment: 'neutral',
  },
  {
    title: 'Critical vulnerability found in widely used SSH library',
    description: 'Security researchers disclose a remote code execution flaw affecting millions of servers.',
    url: 'https://example.com/seed/ssh-vuln',
    source: 'seed',
    aiLabel: ['Cybersecurity/Privacy'],
    aiSummary: 'A newly disclosed RCE vulnerability in a popular SSH library puts millions of internet-facing servers at risk; patches are available.',
    aiSimplified: 'A bug was found that could let hackers break into computers remotely. Update your software now to stay safe.',
    aiProcessed: true,
    aiSentiment: 'neutral',
  },
  {
    title: 'Cloud providers slash GPU prices amid AI compute glut',
    description: 'Falling demand and new capacity have pushed GPU rental prices down sharply this quarter.',
    url: 'https://example.com/seed/gpu-prices',
    source: 'seed',
    aiLabel: ['Cloud Computing/Infrastructure', 'AI/ML'],
    aiSummary: 'Major cloud providers have cut GPU instance pricing as new capacity comes online faster than demand for AI training workloads.',
    aiSimplified: 'Renting powerful computer chips for AI is getting cheaper because there are more of them available now.',
    aiProcessed: true,
    aiSentiment: 'supporting',
  },
  {
    title: 'Startup raises $50M to build next-gen battery recycling plants',
    description: 'The funding will go toward scaling lithium-ion battery recycling facilities across North America.',
    url: 'https://example.com/seed/battery-recycling',
    source: 'seed',
    aiLabel: ['Clean Energy/Climate Tech', 'Startups/Venture Capital'],
    aiSummary: 'A clean-tech startup secured $50M in Series B funding to expand battery recycling capacity as EV adoption accelerates.',
    aiSimplified: 'A company got a lot of money to build factories that turn old batteries into new ones.',
    aiProcessed: true,
    aiSentiment: 'supporting',
  },
  {
    title: 'Regulators scrutinize app store fees in new antitrust probe',
    description: 'Lawmakers are examining whether app store commission structures stifle competition.',
    url: 'https://example.com/seed/appstore-antitrust',
    source: 'seed',
    aiLabel: ['Regulation/Policy', 'Social Media/Platforms'],
    aiSummary: 'A new antitrust investigation is examining whether dominant app store fee structures unfairly limit competition among developers.',
    aiSimplified: 'The government is checking if app stores charge unfair fees that hurt smaller companies.',
    aiProcessed: true,
    aiSentiment: 'opposing',
  },
  {
    title: 'Welcome to TechBrief',
    description: 'Seed article for local development.',
    url: 'https://example.com/seed-article',
    source: 'seed',
  },
];

async function main() {
  for (const article of articles) {
    await prisma.article.upsert({
      where: { url: article.url },
      update: {},
      create: { ...article, publishedAt: new Date() },
    });
  }
}

main()
  .catch((err) => {
    console.error(err);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
