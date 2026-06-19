# Voltixio Rebuild — Spec & Punch List

Status: DRAFT — not yet frozen. Items marked `[DECIDE]` block the build and need an answer before scaffolding starts. Items marked `[BUG]` are confirmed defects in reviewed code. Items marked `[GAP]` are missing pieces with no design yet.

## 0. Starting point (reality check)

- Today: one Python script (`generate_site.py`) generates a static site from RSS via a local `uglyfeed` instance + local Ollama rewrite, plus two standalone social-posting scripts. No DB, no accounts, no backend, no app.
- Target: two independent products — **TechBrief** (niche/tech, professional audience) and **NewsFeed** (general news, habit/engagement focus) — sharing one backend (RSS aggregation, AI processing, content storage), each with its own frontend, domain, accounts, and subscriptions.
- Current traffic: near zero / pre-launch.

## 1. Product/account model (decided)

- **Fully independent apps.** Separate user tables, separate auth/sessions, separate subscriptions/billing per app. No SSO, no cross-app entitlement. One person can have a TechBrief account and a NewsFeed account with no link between them.
- Shared backend serves both via an `app: 'techbrief' | 'newsfeed'` discriminator on content.

## 2. Open decisions `[DECIDE]`

1. **LLM provider/cost model.** Today's rewrite uses local Ollama (free). Proposed AI processing service uses OpenAI `gpt-4-turbo-preview` (paid, 3 calls/article: summary, simplified, label). Decide: does OpenAI replace Ollama entirely, does Ollama keep doing the heavy rewrite while OpenAI only does summary/simplify/label, or does everything stay on a self-hosted model? This is a real recurring-cost decision, not a code detail — estimate $/month at expected article volume before committing.
2. **Category taxonomy.** Must become a fixed enum (e.g., `AI/ML, Cybersecurity, Startups/VC, Big Tech, Gadgets/Hardware, Space/Science, Other` for TechBrief; a separate list for NewsFeed), enforced via structured output/function calling at generation time — not free-text. Free-text labels are what's currently breaking personalization (interest scores fragment across near-duplicate strings).
3. **Per-app prompt differentiation.** TechBrief = technical/professional tone; NewsFeed = general-audience tone. No prompts branch by `app` yet anywhere reviewed. Needs explicit prompt sets per app, not one prompt reused for both.
4. **"Opposing Views" feature design — RESOLVED DIRECTION, needs build-out.** Reviewed UI (`OpposingViews.tsx`) renders a left/right political-spectrum badge design copied from general-news competitive research (AllSides/SmartNews-style). That framing doesn't fit TechBrief's audience or content — most tech/AI/security/startup stories have no coherent left/right axis, so the feature would render empty or look forced on most articles. Recommendation: reframe TechBrief's version as **competing analytical/technical stances** (e.g., "vendor's claim vs. security researcher's rebuttal," "bullish vs. skeptical take on a launch") instead of political lean. Keep the left/right political framing for NewsFeed, where it actually matches the general-news audience and competitive pattern. Still needs: cross-source topic clustering to find a counter-take, and a tagging scheme for "stance" (TechBrief) vs. "lean" (NewsFeed) — these are two different classification problems, not one shared feature.
5. **Engagement event wiring.** `updateEngagementScore` (view/read/share weights) exists but nothing calls it. Need: where do view/read/share events actually fire from the frontend (article open, scroll/dwell timer for "read" ≥30s per your engaged-clicks goal, share button), and what API endpoint receives them.
6. **Infra sizing.** Kubernetes was proposed for a pre-launch, zero-traffic product. Recommend: start with a single Docker Compose host (Postgres + Redis + backend + both frontends), revisit orchestration only once there's real load. Confirm before any `/infrastructure/k8s` work happens.
7. **RSS source list.** Several proposed URLs are dead (see bugs below). Confirm final source list per app — reuse the existing curated `feeds.txt` for TechBrief; NewsFeed's general-news list needs a working equivalent (BBC, Guardian, NPR, AP — verify each URL resolves before adding).
8. **Category taxonomy keeps drifting — pick ONE list and stop.** Four different category sets have appeared across files reviewed so far: (a) original `feeds.txt` groupings, (b) the enum proposed in this spec (#2 above), (c) `techbrief-sources.ts`'s per-feed `category` field (`Startups & VC, Consumer Tech, Science & Tech...`), (d) `techbrief-processor.ts`'s `categorizeTechContent` prompt (14 categories: `AI/ML, Cybersecurity/Privacy, Cloud Computing/Infrastructure...`). Every new file invents its own list. Before more code is written: pick (d) as the working draft (it's the most thorough), finalize it as the canonical TechBrief enum, delete the other three, and use it everywhere — feed source config, AI categorization prompt, and personalization matching all need to reference the same fixed list.
9. **`aiLabel` type is inconsistent across files — string or array?** `AIProcessingService.generateLabel` (earlier file) returns a single string. `TechBriefProcessor.categorizeTechContent` (this file) returns `string[]` (multiple categories via comma-split). `detectTechTrends` defensively handles both (`Array.isArray(article.aiLabel) ? ... : [article.aiLabel]`) — meaning even the code itself isn't sure which type `aiLabel` is. This needs to be settled in the Prisma schema as one type (recommend `aiLabel: String[]` if multi-category is the real intent) and every service updated to match — not defensive `Array.isArray` checks scattered through the codebase.

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
