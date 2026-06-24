# Deployment Runbook — TechBrief Next.js Migration

Replaces the legacy UglyFeed Python static-site pipeline (`generate_site.py` → `/var/www/techbrief_static`) with:
- **Frontend** (`apps/techbrief`): deployed on **Vercel**.
- **Backend** (`backend`, Express/Prisma) + **Postgres**/**Redis**: stay self-hosted on the VPS via `docker-compose.yml`.

## 0. Prerequisites

- Vercel project created and linked to this GitHub repo (already configured), with **Root Directory** set to `apps/techbrief`.
- VPS has Docker + Docker Compose installed.
- DNS: `techbrief.voltixio.com` → Vercel (per Vercel's domain setup), `api.techbrief.voltixio.com` → VPS, for the backend.
- Existing nginx/reverse proxy config on the VPS that currently serves `/var/www/techbrief_static` — this will be replaced by a reverse proxy to the backend container only (no more static site or Next.js container on the VPS).

## 1. Get the code merged

Until the sandbox's git push unblocks (currently 403 — see below), ship the branch manually:

```bash
# on the VPS, or wherever you merge from
git clone git@github.com:Deji147x/techbrief.voltixio.com.git techbrief-next
cd techbrief-next
git fetch origin claude/happy-hopper-4elj90
git checkout claude/happy-hopper-4elj90
```

Merge `claude/happy-hopper-4elj90` into `main` once reviewed — Vercel should auto-deploy `main` (confirm in Vercel project settings under Git → Production Branch).

## 2. Configure Vercel environment variables (frontend)

In the Vercel project dashboard → Settings → Environment Variables, set for **Production**:

```
NEXT_PUBLIC_API_URL=https://api.techbrief.voltixio.com
NEXT_PUBLIC_APP_URL=https://techbrief.voltixio.com
```

`NEXT_PUBLIC_*` vars are baked in at build time — Vercel rebuilds on every push to `main`, so these just need to be correct in the dashboard before the first production deploy.

The `deploy:staging` / `deploy:production` scripts in `apps/techbrief/package.json` (`vercel --env staging`, `vercel --prod`) are for manual CLI deploys if you ever need to push outside the Git integration; the Git integration deploying on push to `main` is the primary path and needs no manual action.

## 3. Configure and start the backend stack on the VPS

`backend/.env` (used by `backend`, `rss-poller`, `ai-processor` services):

```
DATABASE_URL=postgresql://user:password@postgres:5432/techbrief
REDIS_URL=redis://redis:6379
OPENAI_API_KEY=...
SENDGRID_API_KEY=...
ADMIN_API_KEY=<generate a long random secret>   # new — gates GET /analytics/summary
PORT=4000
CORS_ORIGIN=https://techbrief.voltixio.com
```

Confirm `backend/src/index.ts` actually reads `CORS_ORIGIN` (or wherever CORS is configured) and restricts it to the Vercel-served domain — since the frontend now calls the API cross-origin (Vercel → VPS) instead of same-host, CORS must explicitly allow `https://techbrief.voltixio.com`.

Remove the `techbrief` service from `docker-compose.yml` (no longer needed — Vercel hosts the frontend):

```bash
docker compose build backend
docker compose up -d postgres redis
docker compose up -d backend rss-poller ai-processor
```

## 4. Run the database migration

This adds `Visitor`, `PageView`, and `EngagementEvent.visitorId` for the new analytics feature:

```bash
docker compose exec backend npx prisma migrate deploy
```

Verify:

```bash
docker compose exec postgres psql -U user -d techbrief -c '\dt'
```

Confirm `Visitor` and `PageView` tables exist.

## 5. Smoke test before cutover

```bash
# backend, on the VPS
curl -sf http://localhost:4000/articles?pageSize=1
curl -sf -X POST http://localhost:4000/analytics/track \
  -H 'Content-Type: application/json' \
  -d '{"visitorId":"smoke-test","path":"/"}'
curl -sf -H "x-admin-key: $ADMIN_API_KEY" http://localhost:4000/analytics/summary

# frontend, from anywhere, once Vercel deploy completes
curl -sf https://techbrief.voltixio.com/
```

All should return 2xx.

## 6. Point nginx at the backend only

`techbrief.voltixio.com` itself no longer needs an nginx vhost on the VPS — DNS points it straight at Vercel. Keep/add a vhost only for `api.techbrief.voltixio.com`:

```nginx
server {
    server_name api.techbrief.voltixio.com;
    location / {
        proxy_pass http://127.0.0.1:4000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Reload: `sudo nginx -t && sudo systemctl reload nginx`.

Remove the old vhost/static-file block that served `/var/www/techbrief_static` for `techbrief.voltixio.com`, since that hostname is moving to Vercel's DNS targets.

## 7. Retire the old pipeline

- Disable the UglyFeed cron job(s) that ran `generate_site.py`.
- Leave `/var/www/techbrief_static` in place untouched for a few days as a rollback fallback, then remove once confident.

## 8. Rollback plan

If the new stack misbehaves:

- **Frontend**: revert to the previous Vercel deployment via the Vercel dashboard (Deployments → ⋯ → Promote to Production on an earlier build) — instant, no DNS change needed.
- **Backend**: `docker compose stop backend rss-poller ai-processor`, point nginx back at the old static-file setup if needed, re-enable the old cron job.

No data is lost in either case since Postgres keeps running independently.

## Open items

- `ADMIN_API_KEY` must be set before first deploy or `/analytics/summary` stays permanently locked out (401).
- Confirm CORS on the backend explicitly allows `https://techbrief.voltixio.com` now that frontend and backend are on different hosts (this was implicitly same-origin under the old static-site setup).
- Once git push access is restored from this session (currently blocked — see PR/branch status), the merge in Step 1 happens automatically via the PR instead of a manual clone/checkout.
