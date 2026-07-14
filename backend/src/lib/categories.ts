// Canonical TechBrief category enum — see REBUILD_SPEC.md section 1b.
// This is the single source of truth; nothing else should redefine this list.
export const TECHBRIEF_CATEGORIES = [
  'AI/ML',
  'Cybersecurity/Privacy',
  'Cloud Computing/Infrastructure',
  'Developer Tools/Programming',
  'Consumer Tech/Gadgets',
  'Startups/Venture Capital',
  'Blockchain/Web3',
  'Biotech/Health Tech',
  'Clean Energy/Climate Tech',
  'Space/Aerospace',
  'Semiconductors/Hardware',
  'Social Media/Platforms',
  'Regulation/Policy',
  'Tech Culture/Workplace',
  'Other',
] as const;

export type TechBriefCategory = (typeof TECHBRIEF_CATEGORIES)[number];
