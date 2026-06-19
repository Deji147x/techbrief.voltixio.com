# Voltixio Rebuild — Spec & Punch List

Status: DRAFT — not yet frozen. Items marked `[DECIDE]` block the build and need an answer before scaffolding starts. Items marked `[BUG]` are confirmed defects in reviewed code. Items marked `[GAP]` are missing pieces with no design yet.

## 0. Starting point (reality check)

- Today: one Python script (`generate_site.py`) generates a static site from RSS via a local `uglyfeed` instance + local Ollama rewrite, plus two standalone social-posting scripts. No DB, no accounts, no backend, no app.
- Target: two independent products — **TechBrief** (niche/tech, professional audience) and **NewsFeed** (general news, habit/engagement focus) — sharing one backend (RSS aggregation, AI processing, content storage), each with its own frontend, domain, accounts, and subscriptions.
- Current traffic: near zero / pre-launch.

## 1. Product/account model (decided)

- **Fully independent apps.** Separate user tables, separate auth/sessions, separate subscriptions/billing per app. No SSO, no cross-app entitlement. One person can have a TechBrief account and a NewsFeed account with no link between them.
- Shared backend serves both via an `app: 'techbrief' | 'newsfeed'` discriminator on content.

## 1b. Canonical TechBrief category enum (locked)

```
AI/ML
Cybersecurity/Privacy
Cloud Computing/Infrastructure
Developer Tools/Programming
Consumer Tech/Gadgets
Startups/Venture Capital
Blockchain/Web3
Biotech/Health Tech
Clean Energy/Climate Tech
Space/Aerospace
Semiconductors/Hardware
Social Media/Platforms
Regulation/Policy
Tech Culture/Workplace
Other
```

Source: adapted from `techbrief-processor.ts`'s `categorizeTechContent` prompt (most thorough of four competing lists found in review). Supersedes the original `feeds.txt` groupings, the earlier draft enum in this spec, and `techbrief-sources.ts`'s per-feed categories. `aiLabel` is `String[]` (multi-category per article), enforced via structured output/function calling — never free-text. NewsFeed needs its own separate category list, not yet drafted.

## 1c. Canonical Prisma schema (locked, consolidates all fields seen so far)

Same problem as the taxonomy: `aiKeywords`, `aiSentiment`, `engagementScore`, etc. have each been introduced ad hoc in different files with no single schema doc. This consolidates every field referenced across all reviewed code into one canonical model — this supersedes any field set implied elsewhere.

```prisma
enum AppName {
  techbrief
  newsfeed
}

model Article {
  id            String   @id @default(uuid())
  app           AppName
  title         String
  description   String?
  url           String   @unique
  source        String
  rawContent    String?
  imageUrl      String?
  publishedAt   DateTime

  // AI-generated fields
  aiProcessed     Boolean   @default(false)
  aiSummary       String?
  aiSimplified    String?
  aiLabel         String[]  // canonical category enum, see 1b — NOT a single string
  aiKeywords      String[]  @default([])
  aiSentiment     String?   // 'supporting' | 'opposing' | 'neutral' — TechBrief stance framing (see 2.4); NewsFeed uses a separate 'lean' field, not this one
  processedAt     DateTime?

  // Engagement
  engagementScore Int      @default(0)

  createdAt     DateTime @default(now())

  @@index([app, publishedAt])
  @@index([aiLabel])
}

// Fully independent per-app user models (per decision in section 1) — NOT a shared User table.
model TechBriefUser {
  id            String   @id @default(uuid())
  email         String   @unique
  createdAt     DateTime @default(now())
  // subscription/auth fields TBD when decision #1 (LLM cost) and premium-tier work (explicitly deferred, section 5) are revisited
}

model NewsFeedUser {
  id            String   @id @default(uuid())
  email         String   @unique
  createdAt     DateTime @default(now())
}
```

Note: `aiSentiment` is reused for TechBrief's "opposing views" stance (`supporting/opposing/neutral`, per the resolved direction in decision #4) — NewsFeed's political-lean version of the same UI pattern needs its own separate field (e.g. `politicalLean`), not this one, since they're different classification problems per decision #4.

## 2. Open decisions `[DECIDE]`

1. **LLM provider/cost model — PARTIALLY RESOLVED by `.env.local`.** `apps/techbrief/.env.local` sets `OPENAI_MODEL=gpt-4-turbo-preview`, confirming OpenAI is the intended provider (not Ollama, not self-hosted). Still open: no Ollama reference anywhere in the env config, so the question of whether Ollama is dropped entirely or kept for the heavy rewrite step is now answered by omission (dropped) — confirm that's intentional, and estimate $/month at expected article volume (3 OpenAI calls/article × volume) since this is now a real recurring cost, not a placeholder.
1b. **Auth provider — NEW, needs a decision.** `.env.local` introduces Auth0 (`AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`) — not mentioned anywhere else in reviewed code or this spec. No file reviewed so far actually implements Auth0 login/session handling. Decide: is Auth0 the real choice for both apps' independent auth (per section 1's "fully independent accounts" decision), or a placeholder copied from a template? If real, NewsFeed needs its own separate Auth0 tenant/app registration, not a shared one (per the "no SSO" decision).
2. **Category taxonomy — RESOLVED.** Canonical TechBrief category enum, locked (see section 1b for full rationale):
   ```
   AI/ML, Cybersecurity/Privacy, Cloud Computing/Infrastructure, Developer Tools/Programming,
   Consumer Tech/Gadgets, Startups/Venture Capital, Blockchain/Web3, Biotech/Health Tech,
   Clean Energy/Climate Tech, Space/Aerospace, Semiconductors/Hardware, Social Media/Platforms,
   Regulation/Policy, Tech Culture/Workplace, Other
   ```
   This replaces all four previously-conflicting lists (original `feeds.txt` groupings, the earlier draft enum, `techbrief-sources.ts`'s per-feed categories, and the ad-hoc list in `techbrief-processor.ts`'s prompt). Must be enforced via structured output/function calling at generation time, not free-text parsing. NewsFeed gets its own separate list (general-news categories) — not yet drafted, needs its own decision pass when NewsFeed's backend work starts.
3. **Per-app prompt differentiation.** TechBrief = technical/professional tone; NewsFeed = general-audience tone. No prompts branch by `app` yet anywhere reviewed. Needs explicit prompt sets per app, not one prompt reused for both.
4. **"Opposing Views" feature design — RESOLVED DIRECTION, needs build-out.** Reviewed UI (`OpposingViews.tsx`) renders a left/right political-spectrum badge design copied from general-news competitive research (AllSides/SmartNews-style). That framing doesn't fit TechBrief's audience or content — most tech/AI/security/startup stories have no coherent left/right axis, so the feature would render empty or look forced on most articles. Recommendation: reframe TechBrief's version as **competing analytical/technical stances** (e.g., "vendor's claim vs. security researcher's rebuttal," "bullish vs. skeptical take on a launch") instead of political lean. Keep the left/right political framing for NewsFeed, where it actually matches the general-news audience and competitive pattern. Still needs: cross-source topic clustering to find a counter-take, and a tagging scheme for "stance" (TechBrief) vs. "lean" (NewsFeed) — these are two different classification problems, not one shared feature.
5. **Engagement event wiring.** `updateEngagementScore` (view/read/share weights) exists but nothing calls it. Need: where do view/read/share events actually fire from the frontend (article open, scroll/dwell timer for "read" ≥30s per your engaged-clicks goal, share button), and what API endpoint receives them.
6. **Infra sizing.** Kubernetes was proposed for a pre-launch, zero-traffic product. Recommend: start with a single Docker Compose host (Postgres + Redis + backend + both frontends), revisit orchestration only once there's real load. Confirm before any `/infrastructure/k8s` work happens.
7. **RSS source list.** Several proposed URLs are dead (see bugs below). Confirm final source list per app — reuse the existing curated `feeds.txt` for TechBrief; NewsFeed's general-news list needs a working equivalent (BBC, Guardian, NPR, AP — verify each URL resolves before adding).
8. **Category taxonomy drift — RESOLVED.** See #2 above: the 14-category `techbrief-processor.ts` list (plus `Other`) is now canonical for TechBrief. The other three lists (`feeds.txt` groupings, the original draft enum, `techbrief-sources.ts`'s per-feed categories) are superseded — when the schema/config/prompts are actually built, they must all reference the single list in #2, not their own versions.
9. **`aiLabel` type — RESOLVED: `String[]`.** Multi-category is the real intent (per `categorizeTechContent`), so the Prisma schema field is `aiLabel: String[]`. `AIProcessingService.generateLabel` (single-string version) must be rewritten to return an array matching the canonical enum via structured output. Every consuming service (`detectTechTrends`, `findOpposingViews`, `PersonalizationEngine`) must assume array type directly — no defensive `Array.isArray` checks. `findOpposingViews`'s `aiLabel: { contains: topic }` Prisma filter must become `aiLabel: { hasSome: [topic] }` to match the array type correctly (this was bug #15 in section 3 — now has a concrete fix).

## 3. Confirmed bugs in reviewed code `[BUG]`

| # | Location | Issue |
|---|----------|-------|
| 1 | `aggregator.DeduplicationEngine.calculateSimilarity` | Hardcoded `return 0` — dedup never fires. Class is unused dead code; actual dedup check is a separate exact title/URL match in `fetchAndStore`. |
| 2 | `RSS_SOURCES` | Yahoo (`rss.news.yahoo.com`, `news.search.yahoo.com`) and Reuters (`microsite.reuters.co.uk`) RSS endpoints are defunct — will 404/redirect, not return feeds. |
| 3 | `AIProcessingService.retryProcessing` | On partial failure (e.g. summary succeeds, label throws), retry re-runs **all three** calls, not just the failed one — wastes cost and compounds API spend on retries. |
| 4 | `AIProcessingService.processQueue` | Serial loop, no concurrency, no backoff on OpenAI 429s — will choke under any real volume. |
| 5 | `AIProcessingService.generateLabel` | Category enum exists only in a code comment, never sent to the model or validated against the response — ties to taxonomy decision above. |
| 6 | `PersonalizationEngine` | Interest scores and read history live only in Redis with no stated persistence (AOF/RDB) — restart/flush silently wipes all personalization data. |
| 7 | `AIAssistant.tsx` | No request cancellation — rapid mode/article switches can let a stale response overwrite a fresh one. |
| 8 | `AIAssistant.tsx` | No error handling on fetch — failed request leaves `isLoading` stuck `true` forever (spinner never clears). |
| 9 | `AIAssistant.tsx` | "Refresh with new AI analysis" button calls `onSummarize(articleId)`, which in the parent is a `console.log` stub — button does nothing. |
| 10 | `pages/index.tsx` | `loading` from `usePersonalization` destructured but never rendered — no loading state shown for the main feed. |
| 11 | `pages/index.tsx` | Switching to Assistant/Opposing-Views tabs with no article selected isn't guarded against — **resolved**: `OpposingViews.tsx` reviewed, it does have the `!articleId` guard, matching `AIAssistant.tsx`. |
| 12 | `OpposingViews.tsx` / `AIAssistant.tsx` | No request cancellation or error handling on `getOpposingViewpoints`/`getAIContent` fetches — same stuck-spinner pattern as bug #7/#8, repeated in this component. |
| 13 | **Frontend/backend contract mismatch on Opposing Views.** | `OpposingViews.tsx` UI checks `view.side === 'left' \| 'right'` (political framing). `TechBriefProcessor.findOpposingViews`/`determinePerspective` (this file) actually produces `side: 'supporting' \| 'opposing' \| 'neutral'` (stance framing) — the UI will never match these values, so the political-color badges (`bg-blue-100`/`bg-red-100`) will never render correctly against this backend. Confirms the spec #4 reframing decision was right, but the UI component needs to be rewritten to match `supporting/opposing/neutral`, not patched. |
| 14 | `TechBriefProcessor.determinePerspective` | Parses model output via `result.split(',')` expecting an exact `"stance,confidence"` format with no structured output/JSON enforcement and `max_tokens: 30` — fragile; any extra text from the model breaks parsing silently (falls back to `'neutral', 0.5` via the `|| 0.5` only on the confidence half, not the stance half, which could end up as garbled text). |
| 15 | `TechBriefProcessor.findOpposingViews` | Matches candidate articles by `aiLabel: { contains: topic }` (broad category match) — not true same-story clustering across sources. This is the cheap version of the "needs cross-source topic clustering" gap noted in spec #4; it will surface same-*category* articles, not necessarily the same *story*. Also: if `aiLabel` becomes `String[]` (see #9), `contains` is the wrong Prisma filter — needs `hasSome`. |
| 16 | `techbrief-sources.ts` | Still includes the dead Yahoo endpoints (`yahoo_tech_top`, `yahoo_tech_search`) flagged in bug #2 — not yet removed despite being known-dead. |
| 17 | `techbrief-sources.ts` | `github_trending` (`github.com/trending.rss`) is likely not a real GitHub-owned endpoint — GitHub doesn't officially publish trending-page RSS; this pattern is used by third-party unofficial mirrors. Needs verification before use. |
| 18 | `techbrief-sources.ts` | `product_hunt` (`producthunt.com/feed`) — Product Hunt deprecated public RSS in favor of an OAuth-gated GraphQL API; this URL is likely dead or non-functional. Needs verification. |
| 19 | `techbrief-sources.ts` | Polling cadence (primary feeds every 5 min) is far more frequent than these sources actually publish (a few articles/hour) — wasteful request volume for no benefit at current or near-term scale. Hourly for primary, every few hours for lower-priority tiers is sufficient. |
| 20 | `techbrief-routes.ts` | `prisma` used in `ai-analysis` and `opposing-views` handlers but never imported anywhere in the file — won't compile/run as written. |
| 21 | `techbrief-routes.ts` | `/suggestions` calls `personalizationEngine.getSuggestedArticles(...)` — method doesn't exist on `PersonalizationEngine` (only has `trackRead`, `getRecommendations`, `getPopularArticles`, `updateEngagementScore`). Will throw at runtime. |
| 22 | `techbrief-routes.ts` | `/feed` calls `getRecommendations(userId, app, limit, page)` — service only accepts `(userId, app, limit)`, no pagination (skip/cursor) logic implemented anywhere. `page` param is currently decorative. |
| 23 | `techbrief-routes.ts` | `/opposing-views/:articleId` passes `article.aiLabel \|\| article.category` directly as the single-string `topic` arg to `findOpposingViews` — breaks under the now-locked `aiLabel: String[]` schema (section 1c); needs to pick one category from the array or `findOpposingViews` needs to accept an array. |
| 24 | `techbrief-routes.ts` | Every catch block returns raw `error.message` to the client (`res.status(500).json({ error: error.message })`) — leaks internal/DB error details externally. Should log server-side, return a generic message externally. |
| 25 | `techbrief-routes.ts` | No rate limiting on routes that indirectly trigger OpenAI calls (`opposing-views`, `trending`) — cost/abuse exposure. |
| 26 | `techbrief-routes.ts` | References `article.aiKeywords` and `article.aiSentiment` — fields never defined in any schema sketch before this file. Same ad hoc drift pattern as the category taxonomy, now resolved in section 1c (canonical schema) — this file predates that fix and needs to be reconciled against it. |
| 27 | `Layout.tsx` | Calls `<AIAssistant onSelectArticle={...} />` and `<OpposingViews onSelectArticle={...} />` — neither component has an `onSelectArticle` prop (actual interfaces are `{ articleId, onSummarize }` and `{ articleId, onSelectView }` respectively). Prop is silently dropped; the intended callback never reaches either component. |
| 28 | `Layout.tsx` vs `pages/index.tsx` | **Duplicate, conflicting state ownership.** Both files independently own `activeFeature`/`activeView` and `selectedArticle` state and both render the same Feed/Assistant/Opposing-Views tab switcher. If `Layout` wraps `pages/index.tsx`, there are two independent tab-switchers and two independent "selected article" states that can desync. Needs an explicit decision: tab/selection state belongs in the layout (shared) or the page (per-page) — not both. |
| 29 | `Layout.tsx` | "Upgrade" button has no `onClick` — dead control, same pattern as bug #12 ("Customize interests"). |
| 30 | `Layout.tsx` | Wires in `useSubscription`/`isPremium`/upgrade CTA despite section 5 explicitly deferring premium/paywall work until there's real traffic. Not a bug, but a direct conflict with an already-stated decision — needs your call: still deferred, or has that changed? |
| 31 | **`ArticleCard.tsx` × `pages/index.tsx` — HIGH PRIORITY, breaks a feature end-to-end.** | `ArticleCard` expects prop `onClick`. `pages/index.tsx` passes `onRead={() => setSelectedArticle(article.id)}` — wrong prop name, so `onClick` is always `undefined`. `ArticleCard.handleClick`'s fallback then fires (`router.push('/article/{id}')`), so clicking a homepage card navigates away instead of setting `selectedArticle`. Net effect: the AI Assistant / Opposing Views tabs can never have an article to work with when reached via the normal homepage click path — this isn't an incomplete stub like the other prop mismatches, it silently breaks the feature's actual data flow. Fix: rename `onRead` → `onClick` in `pages/index.tsx`, or vice versa, and verify which behavior (navigate vs. select-in-place) is actually intended. |
| 32 | `ArticleCard.tsx` | `aiLabel: string \| string[] \| null` type and `Array.isArray` branch in `getCategoryDisplay()` — same resolved-but-not-yet-applied drift as bug #9; should be simplified to `string[] \| null` only, per the locked canonical schema (section 1c). |
| 33 | `ArticleCard.tsx` | No engagement/view event fired on click — same gap as decision #5, now confirmed present in every reviewed component that handles article interaction. |
| 34 | **`AIAssistant.tsx` (expanded version, has its own article search/selector) × parent component — duplicate/diverging state ownership.** | This version takes an `articleId` prop but only seeds `selectedArticle` once via `useState(articleId)` — there's no `useEffect` syncing `selectedArticle` when `articleId` changes later. If the parent re-selects an article (e.g. via a fixed `ArticleCard.onClick`, bug #31), this component won't notice; it only updates when the user picks from its own internal search list, which then calls `onSelectArticle(id)` back up. Two independent paths can disagree about which article is "selected." Needs one owner — recommend parent-owned `articleId` with a `useEffect([articleId])` sync here, dropping the internal `selectedArticle` state entirely. |
| 35 | `AIAssistant.tsx` sentiment mode | Renders `content.positive/neutral/negative` percentages and `content.overall` ('positive'/'neutral'/'negative') with emoji — but the canonical schema's `aiSentiment` (section 1c) is `'supporting' \| 'opposing' \| 'neutral'` stance framing, not a positive/negative sentiment score. This UI's data contract doesn't match anything produced by `techbrief-processor.ts`. Needs a decision: is sentiment-as-mood a real planned feature requiring new AI output fields, or should this mode be dropped/replaced with the stance framing already used in Opposing Views? |
| 36 | `AIAssistant.tsx` `loadAIContent` | No request cancellation or race-condition guard. Rapidly switching `mode` or `selectedArticle` can let a stale response land after a newer one, showing wrong content for the current selection — same class of issue as bug #7. |
| 37 | `AIAssistant.tsx` `fetchArticles` | Fires on every keystroke via `useEffect([searchTerm])` with no debounce — hits the search/article-list endpoint on every character typed. |
| 38 | `AIAssistant.tsx` | No error handling on `getAIContent`/`getArticles` — a failed fetch leaves `isLoading` stuck `false` with stale/empty `content`, no retry or error message shown (same stuck-state family as bug #8, but here it fails silently-empty rather than silently-spinning). |
| 39 | **`apps/techbrief/.env.local` — SECURITY.** `STRIPE_SECRET_KEY=sk_live_...` is defined in the **frontend** Next.js app's env file, alongside `JWT_SECRET`, `OPENAI_API_KEY`, `DATABASE_URL`, and `SENDGRID_API_KEY`. Secret keys have no legitimate reason to exist in a frontend app's config at all — only `NEXT_PUBLIC_*` values (and the publishable Stripe key) belong here. If any of these get referenced in frontend code (not just present in the file), they ship to the browser bundle. Also: this is a `sk_live_` (production) key sitting in a `.env.local` for a pre-launch, zero-traffic product — directly conflicts with bug #30/section 5's premium deferral. Fix: secret keys (Stripe secret, JWT secret, DB URL, SendGrid, OpenAI) belong only in the **backend** service's env, never the frontend's, regardless of gitignore status. |

## 4. Build order (once section 2 is resolved)

1. Freeze this spec (resolve all `[DECIDE]` items).
2. Fix backend bugs in section 3 (#1–6) as part of writing the real backend, not after.
3. Schema (Postgres/Prisma): `Article`, per-app `User`/`Subscription` tables, category enum.
4. Aggregator service (working feed list only).
5. AI processing service (correct retry granularity, concurrency, enforced taxonomy).
6. Personalization service (persisted, not Redis-only-with-no-backup).
7. Engagement event endpoint + frontend wiring.
8. Frontend: TechBrief first, ship and validate content quality before NewsFeed.
9. NewsFeed second, once TechBrief's personalization/retention loop is proven.
10. Monetization (ads, premium, IAP) and infra scaling (k8s, multi-instance) — last, only once there's real traffic.

## 5. Explicitly deferred (do not build yet)

- Premium tier / paywall / IAP — no users to monetize yet.
- Programmatic ad integration — needs traffic history first.
- Native mobile apps / push notifications — web-first; revisit once web product validates.
- Kubernetes / multi-instance scaling — single-host deploy until load requires otherwise.
