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
4. **"Opposing Views" feature design.** Referenced in the TechBrief homepage UI but has zero backend design: no source political/editorial-lean tagging, no cross-source topic clustering to find a counter-article. This needs its own spec (how do we tag source lean? how do we cluster same-story-different-source? is this even in scope for TechBrief — a tech audience — or was this copied from the NewsFeed competitive research and misapplied?) before any UI references it.
5. **Engagement event wiring.** `updateEngagementScore` (view/read/share weights) exists but nothing calls it. Need: where do view/read/share events actually fire from the frontend (article open, scroll/dwell timer for "read" ≥30s per your engaged-clicks goal, share button), and what API endpoint receives them.
6. **Infra sizing.** Kubernetes was proposed for a pre-launch, zero-traffic product. Recommend: start with a single Docker Compose host (Postgres + Redis + backend + both frontends), revisit orchestration only once there's real load. Confirm before any `/infrastructure/k8s` work happens.
7. **RSS source list.** Several proposed URLs are dead (see bugs below). Confirm final source list per app — reuse the existing curated `feeds.txt` for TechBrief; NewsFeed's general-news list needs a working equivalent (BBC, Guardian, NPR, AP — verify each URL resolves before adding).

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
| 11 | `pages/index.tsx` | Switching to Assistant/Opposing-Views tabs with no article selected isn't guarded against (mitigated in `AIAssistant.tsx` itself, but `OpposingViews.tsx` hasn't been reviewed yet — confirm it has the same guard). |

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
