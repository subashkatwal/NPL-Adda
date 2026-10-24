# Free deployment

| Piece | Service | URL |
|---|---|---|
| Frontend (Vite) | Render free static site | `https://npl-adda.onrender.com` |
| API (Django, Docker) | Render free web service | `https://npl-adda-api.onrender.com` |
| PostgreSQL | Neon free | connection details |
| Redis | Upstash free (or `REDIS_URL=none`) | `rediss://...` |
| Images | Cloudinary free | API keys |

The static site proxies `/api` and `/media` to the API (routes in `render.yaml`), so the browser sees one
origin and the session/CSRF cookies keep working. If Render assigns different URLs, update the hosts in
`render.yaml`.

## 1. Database: Neon
Create a project at neon.tech and note the host, database, user and password.

## 2. Redis: Upstash (optional)
Create a Redis database at upstash.com and copy the `rediss://` URL. Or skip it and set `REDIS_URL=none`.

## 3. Images: Cloudinary
Sign up at cloudinary.com and copy the cloud name, API key and API secret from Dashboard → API Keys.

## 4. Render (both services)
New → Blueprint → pick this repo. Render reads `render.yaml` and creates `npl-adda-api` and `npl-adda`.
Fill in the prompted values:
- API: `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `REDIS_URL`, `GOOGLE_CLIENT_ID`,
  `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, optionally `GOOGLE_GEMINI_API_KEY`
- Frontend: `VITE_GOOGLE_CLIENT_ID`

Migrations run on every API start. Render's free plan has no shell, so run one-off commands (admin user, seed
data) from your machine against Neon, from `backend/`:

```sh
docker compose run --rm --no-deps -e POSTGRES_HOST=<neon-host> -e POSTGRES_DB=neondb -e POSTGRES_USER=neondb_owner \
  -e POSTGRES_PASSWORD=<password> -e POSTGRES_SSLMODE=require web python manage.py createsuperuser
```

Replace `createsuperuser` with `seed_npl_teams` or `seed_npl_2026_fixtures` to load teams and fixtures.

## 5. Google sign-in
In Google Cloud Console add `https://npl-adda.onrender.com` as an authorized JavaScript origin.

## Free-tier caveats
- The API sleeps after ~15 minutes idle; the first request then takes 30–60 s. A free uptime pinger
  (UptimeRobot, cron-job.org) hitting `https://npl-adda-api.onrender.com/admin/login/` every 10 minutes keeps
  it awake. The static site never sleeps.
- Render's disk is ephemeral: without the Cloudinary variables, uploaded memes and avatars are lost on
  redeploy/restart.
