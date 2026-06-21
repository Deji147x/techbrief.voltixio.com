# Deploying TechBrief

Two independent pieces: the Next.js frontend on Vercel, and the backend
(API + Postgres + Redis + Ollama) on a VPS via Docker Compose.

## Frontend (Vercel)

1. Import this repo into Vercel, set the project root to `apps/techbrief`.
2. In the Vercel project's environment variables, set whatever `NEXT_PUBLIC_*`
   values `apps/techbrief/.env.local` currently defines (check that file —
   nothing else should be needed; the backend owns all secrets).
3. Set `NEXT_PUBLIC_API_URL` (or whatever var points at the backend) to your
   VPS's public backend URL, e.g. `https://api.yourdomain.com`.
4. Push to `main` — Vercel auto-deploys from there once connected.

## Backend (VPS + Docker Compose)

Requires a VPS with at least 4 vCPU / 8GB RAM (gemma2:9b needs ~6GB resident;
give the host headroom for Postgres/Redis/Node alongside it).

1. SSH in, install Docker + Docker Compose plugin.
2. `git clone` this repo, `cd` into it.
3. Copy and fill in the two production env files (do NOT commit the filled versions):
   ```
   cp .env.production.example .env.production
   cp backend/.env.production.example backend/.env.production
   ```
   Use the same Postgres user/password/db in both files.
4. Set `CORS_ORIGIN` in `backend/.env.production` to your Vercel frontend's URL.
5. Bring up the stack:
   ```
   docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
   ```
6. Pull the Ollama model once the `ollama` container is up:
   ```
   docker compose -f docker-compose.prod.yml exec ollama ollama pull gemma2:9b
   ```
7. Run migrations against the running Postgres:
   ```
   docker compose -f docker-compose.prod.yml exec backend npx prisma migrate deploy
   ```
8. Put a reverse proxy (Caddy or nginx) in front of port 4000 for TLS on your
   API domain — this repo doesn't include one, so set it up directly on the VPS.

## Updating

Each new deploy: `git pull`, then
`docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build`.
Vercel redeploys the frontend automatically on push to `main`.
