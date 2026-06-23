# Deployment Runbook — TechBrief Next.js Migration

Replaces the legacy UglyFeed Python static-site pipeline (`generate_site.py` → `/var/www/techbrief_static`) with the Next.js app (`apps/techbrief`) + Express/Prisma backend (`backend`), using the existing `docker-compose.yml`.

## 0. Prerequisites on the VPS

- Docker + Docker Compose installed.
- DNS for `techbrief.voltixio.com` already pointed at the VPS (unchanged).
- Existing nginx/reverse proxy config that currently serves `/var/www/techbrief_static`.

## 1. Get the code onto the VPS

Until the sandbox's git push unblocks, ship the branch manually:

```bash
# on the VPS
git clone git@github.com:Deji147x/techbrief.voltixio.com.git techbrief-next
cd techbrief-next
git fetch origin claude/happy-hopper-4elj90
git checkout claude/happy-hopper-4elj90
```

(Once push access is restored, this becomes a normal `git merge`/`git pull` of the PR into `main`.)

## 2. Configure environment files

`backend/.env` (used by `backend`, `rss-poller`, `ai-processor` services):

```
DATABASE_URL=postgresql://user:password@postgres:5432/techbrief
REDIS_URL=redis://redis:6379
OPENAI_API_KEY=...
SENDGRID_API_KEY=...
ADMIN_API_KEY=<generate a long random secret>   # new — gates GET /analytics/summary
PORT=4000
```

`apps/techbrief/.env.local` (used by `techbrief` service):

```
NEXT_PUBLIC_API_URL=https://api.techbrief.voltixio.com   # or http://backend:4000 if proxied internally
NEXT_PUBLIC_APP_URL=https://techbrief.voltixio.com
```

Note: `NEXT_PUBLIC_*` vars are baked in at build time, so the production API URL must be correct *before* `docker compose build`.

## 3. Build and start the stack

```bash
docker compose build backend techbrief
docker compose up -d postgres redis
docker compose up -d backend techbrief rss-poller ai-processor
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
curl -sf http://localhost:4000/articles?pageSize=1
curl -sf http://localhost:3000/
curl -sf -X POST http://localhost:4000/analytics/track \
  -H 'Content-Type: application/json' \
  -d '{"visitorId":"smoke-test","path":"/"}'
curl -sf -H "x-admin-key: $ADMIN_API_KEY" http://localhost:4000/analytics/summary
```

All four should return 2xx JSON.

## 6. Cut the reverse proxy over

Update nginx (or equivalent) to proxy `techbrief.voltixio.com` → `127.0.0.1:3000` (Next.js) instead of serving the static directory, and add/keep `api.techbrief.voltixio.com` (or `/api/` path) → `127.0.0.1:4000` for the backend.

Example nginx server block change:

```nginx
server {
    server_name techbrief.voltixio.com;
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Reload: `sudo nginx -t && sudo systemctl reload nginx`.

## 7. Retire the old pipeline

- Disable the UglyFeed cron job(s) that ran `generate_site.py`.
- Leave `/var/www/techbrief_static` in place untouched for a few days as a rollback fallback, then remove once confident.

## 8. Rollback plan

If the new stack misbehaves:

```bash
docker compose stop techbrief backend rss-poller ai-processor
```

Point nginx back at `/var/www/techbrief_static`, reload nginx, re-enable the old cron job. No data is lost since Postgres keeps running independently.

## Open items

- Confirm whether Vercel (`npm run deploy:production` in `apps/techbrief/package.json`) is meant to replace self-hosting the Next.js app instead of the `techbrief` Docker service above — the two are alternatives, not both. This runbook assumes self-hosted via Docker Compose to match the existing VPS setup; switch only if you intend to move off the VPS for the frontend.
- `ADMIN_API_KEY` must be set before first deploy or `/analytics/summary` stays permanently locked out (401).
