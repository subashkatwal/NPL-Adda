# NPL Adda — Backend

An independent digital fan community for Nepali cricket supporters. The stack is Django 5.2, Django REST Framework, PostgreSQL 17 and Redis 7, all running in Docker. AI generation is handled by a separate service and is not part of this backend.

## Quick start

```bash
cp .env.example .env   # first time only; then set secrets
docker compose -f compose.yml -f docker-compose.override.yml up --build
```

The API runs on `http://localhost:${WEB_PORT}` (default `9009`). Docs are at `/api/docs` (Swagger), `/api/redoc` and `/api/schema`. The admin is at `/admin/`.

| File | Role |
| --- | --- |
| `Dockerfile` | Builds the application image. |
| `compose.yml` | Runs Django, PostgreSQL and Redis (Postgres data in the `npl_adda_postgres_data` volume). |
| `docker-compose.override.yml` | Local development: code mount, auto-migrate, dev server. |
| `.env` / `.env.example` | Local configuration / documented variables. |

```bash
DC="docker compose -f compose.yml -f docker-compose.override.yml"
$DC run --rm web pytest
$DC run --rm web python manage.py createsuperuser
$DC run --rm web python manage.py seed_npl_teams          # the eight franchises
$DC run --rm web python manage.py seed_npl_2026_fixtures  # published NPL 2026 schedule (idempotent)
```

## Authentication

**Anyone can browse** teams, fixtures, results, published posts, polls and leaderboards without logging in. **Taking part needs an account.** That covers joining a team, creating or editing a fan profile, voting, predicting, posting, reporting and MEME Zone. Anonymous callers get `401`; logged-in users without a fan profile get `403`.

| Client | How it authenticates |
| --- | --- |
| Web app (browser) | Django **session cookie** (HttpOnly, SameSite=Lax, Secure in production) plus the **CSRF** token (`csrftoken` cookie sent back as `X-CSRFToken`). `GET /accounts/session` sets the CSRF cookie. Tokens are never stored in JavaScript. Logout deletes the session on the server. |
| API clients | JWT: `POST /accounts/token`, `/accounts/token/refresh`, and `/accounts/token/blacklist` to invalidate a refresh token on logout. Access tokens last 15 minutes. |

- **Email/password:** `POST /accounts/register` and `POST /accounts/login` both start a session. Passwords go through Django's validators. Login returns the same error for an unknown email and a wrong password.
- **Google:** the frontend's Google button returns a signed ID token. `POST /accounts/google` verifies it with the official `google-auth` library (signature, audience = `GOOGLE_CLIENT_ID`, issuer, expiry and verified email). No client secret is used anywhere.
- **Account linking:**
  - Google identities are matched by Google's stable `sub` id, never by email alone.
  - A new Google login attaches to an existing account with the same email only if that account's email is verified or it has no password. Otherwise it gets a `409 account_exists_unverified`, which blocks takeover through an account someone else pre-registered with your email.
  - The owner can link Google from Settings while logged in (`POST /accounts/google/link`).
  - Unlinking (`DELETE`) requires a password, so nobody locks themselves out.
- **Rate limits:** login, Google and link calls are limited by `AUTH_RATE` (10/min per IP); registration by `AUTH_REGISTER_RATE` (10/hour).
- **CSRF:** enforced on login, register, Google and logout, even for anonymous callers, which prevents login CSRF.
- **Moderators:** users with the `moderation.moderate_content` permission. Grant it in the admin.
- **Legacy guest sessions:** `/accounts/guest-sessions*` are kept so guest data created before accounts were required can be claimed (`POST /accounts/guest-sessions/claim`). A guest token can no longer act as a fan.

The API never trusts IDs sent by the client for identity. The owner always comes from the session or JWT.

### Google sign-in setup (Google Cloud)

1. In [Google Cloud Console](https://console.cloud.google.com/), create or select a project, then go to **APIs & Services → OAuth consent screen**.
   - Choose **External**.
   - Fill in the app name, support email and developer contact.
   - Scopes: `openid`, `email`, `profile`.
   - Add yourself as a test user while the app is in testing.
2. Go to **APIs & Services → Credentials → Create credentials → OAuth client ID → Web application**.
   - **Authorised JavaScript origins:** `http://localhost:5173`, plus your production origin, e.g. `https://npladda.example`.
   - **Redirect URIs:** none are needed; the Google button uses popup mode.
3. Copy the **Client ID**, which looks like `1234-abc.apps.googleusercontent.com`. It is public, and you do **not** need the client secret.
   - Backend `.env`: `GOOGLE_CLIENT_ID=<client id>`. Then restart the stack.
   - Frontend `frontend/.env.local`: `VITE_GOOGLE_CLIENT_ID=<same client id>`. Then restart `npm run dev`.
4. Open http://localhost:5173, click **Log in**, then **Continue with Google**.

Until both values are set, `POST /accounts/google` returns `503 google_not_configured` and the UI shows "Google sign-in isn't configured".

**Production checklist:**
- `DJANGO_DEBUG=False` turns on Secure cookies and HTTPS redirects.
- Serve the frontend and API from the same site, or list the frontend origin in both `CORS_ALLOWED_ORIGINS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Publish the OAuth consent screen.

## Scaling

These are already in place:

| Concern | What's in place |
| --- | --- |
| Connections | psycopg **connection pool** (`DB_POOL_MAX_SIZE` per worker, Django 5.2 built-in). Keep `WEB_CONCURRENCY × DB_POOL_MAX_SIZE` below Postgres `max_connections`, and add PgBouncer when running many app instances. |
| Runaway queries | `statement_timeout` (`DB_STATEMENT_TIMEOUT_MS`, default 15 s). |
| Hot queries | Indexes on team leaderboard sums (`activity(team, occurred_at)`), badge progress (`activity(profile, type)`), poll counts, prediction splits, team schedules (home/away), the moderation queue, and **partial indexes** for public and team feeds (published, non-deleted only) and active memberships. |
| N+1 queries | Poll lists load vote counts and the caller's vote with the page; profile lists prefetch the current team; feeds prefetch authors and memes. `tests/test_scaling.py` asserts that query counts don't grow with row counts. |
| Expensive public reads | Fan and team leaderboards are cached in Redis for `LEADERBOARD_CACHE_SECONDS` (60). The data is identical for every caller, and staleness is bounded by the TTL. |
| App servers | Stateless gunicorn (`WEB_CONCURRENCY` workers, recycled every ~1000 requests). Sessions live in Postgres and caches in Redis, so you can run more containers behind a load balancer. |

Next steps when traffic needs them, none required yet:
- read replicas through a database router
- cursor pagination for very deep feeds
- moving prediction scoring to a background job
- a materialised points total per profile if the ledger grows to tens of millions of rows

## Endpoints (`/api/v1`, no trailing slashes)

| Area | Routes |
| --- | --- |
| health | `GET /health` |
| accounts | `GET /accounts/session`, `POST /accounts/register`, `POST /accounts/login`, `POST /accounts/logout`, `POST /accounts/google`, `POST\|DELETE /accounts/google/link`, `GET\|PATCH /accounts/me`; JWT: `POST /accounts/token`, `/accounts/token/refresh`, `/accounts/token/blacklist`; legacy: `/accounts/guest-sessions`, `/current`, `/revoke`, `/claim` |
| teams | `/teams`, `/teams/<uuid>`, `GET /teams/<uuid>/roster?season_year=`, `/teams/players[/<uuid>]`, `/teams/rosters[/<uuid>]`. Read is public; writes are staff only. |
| matches | `/matches[/<uuid>]` (filters: `season`, `status`, `team`, `starts_after`, `starts_before`), `GET /matches/<uuid>/performances`, `/matches/seasons`, `/matches/innings`, `/matches/performances`. Read is public; writes are staff only. |
| fanpage | `/fanpage[/<uuid>]` (profiles), `GET /fanpage/me`, `GET\|POST /fanpage/me/membership` (join or switch team), `GET /fanpage/me/memberships`, `/me/activities`, `/me/badges`, `/me/challenges`, `/me/season-summary?season=`, `/fanpage/badges`, `/fanpage/leaderboard?team=&season=` (dense rank), `/fanpage/leaderboard/teams?season=`, `/fanpage/polls[/<uuid>]` (includes `my_vote` and `results` when visible), `POST /polls/<uuid>/vote`, `GET /polls/<uuid>/results`, `/fanpage/predictions[/<uuid>]`, `GET /fanpage/matches/<uuid>/prediction-summary` (after the deadline), `POST /fanpage/matches/<uuid>/score-predictions` (staff) |
| content | `/content[/<uuid>]` (only published posts are public; authors see their own), `GET /content/mine`, `POST\|DELETE /content/<uuid>/vote` |
| memelab | `/memelab/templates[/<uuid>]` (5 original templates are seeded), `POST /memelab/generations` (needs an `Idempotency-Key`; rate limited by `MEME_GENERATION_RATE`, default 20/hour per fan; returns `is_mock`; errors are `{code, detail}` with 409/429/503), `GET /memelab/generations[/<uuid>]`, `/memelab/drafts[/<uuid>]`, `POST /memelab/drafts/<uuid>/submit` (409 on duplicate content) |
| moderation | `/moderation/reports[/<uuid>]` (any fan can file; moderators list and resolve), `GET\|POST /moderation/actions` |
| ai-agents | `GET /ai-agents/runs[/<uuid>]`, `GET /ai-agents/runs/<uuid>/tool-calls`. Staff-only audit of runs recorded by the external AI service. |
| admin | Staff only. `GET /admin/resources` (index), `GET /admin/dashboard`, and per resource `GET\|POST /admin/<key>`, `GET\|PATCH\|DELETE /admin/<key>/<uuid>`, `POST /admin/<key>/<uuid>/restore`, `POST /admin/<key>/<uuid>/run/<action>`. `OPTIONS /admin/<key>` describes fields and actions. Lists take `search`, `ordering`, `page_size`, field filters and `deleted=exclude\|only\|include`. |

### Admin console

The web app's admin console is at **`/staff`** (Admin in the user menu, for staff accounts). It is built entirely from `apps/backoffice`: each resource registered in `apps/backoffice/v1/views.py` gets a table, filters, a create/edit form, soft delete and restore, and its custom actions (change a fan's team, adjust points, award a badge, moderate a post, score predictions, revoke a guest session). Rules:
- Only superusers can grant staff, superuser or moderator access, or edit a superuser. Nobody can deactivate, demote or delete their own account.
- Every section can be edited and soft-deleted (then restored). Rows the app writes itself (memberships, points ledger, votes, predictions, earned badges, moderation actions, AI runs) can't be created by hand; prefer **Adjust points** over editing ledger rows so corrections stay traceable.
- Post status changes only through **Moderate**, which writes the moderation audit log (moderator permission required).

Constraint violations return `409`; validation errors return `400`.

**MEME Zone captions.** `MEME_CAPTION_PROVIDER=mock` (the default) uses a deterministic offline generator in `apps/memelab/captioning.py`. It fills fixed English, Nepali and mixed templates with stored team and match facts. Responses mark it `provider: "mock"` and `is_mock: true`, and posts made from it are not flagged as AI-generated. The external AI service (Prompt 4) plugs in by implementing `generate()` there.

## Data model rules

- **Base model:** every model inherits `BaseModel` (UUID `id`, `created_at`, `updated_at`, `deleted_at`). `objects` hides soft-deleted rows and `all_objects` includes them. Every field has a `help_text`, and a test enforces it.
- **Uniqueness:** unique rules that should allow re-creation after soft deletion are conditional constraints (`WHERE deleted_at IS NULL`).
- **Cricket statistics:** overs are derived from integer `legal_balls`; rates use `Decimal` (`apps/common/cricket.py`).
- **Points:** points exist only in the `FanActivity` ledger, written by backend services with idempotency keys. Rankings are sums of that ledger.
- **Database checks:**
  - match teams differ;
  - the toss winner and the winner must be one of the two teams;
  - a winner can only be set on a completed match;
  - innings and player statistics are non-negative and consistent;
  - a fan profile has exactly one owner (user or guest);
  - a profile has at most one open team membership;
  - one vote per poll, one prediction per match, and one badge of each kind per profile.

### Deletion policy

| Behaviour | Models |
| --- | --- |
| `DELETE` via the API soft-deletes | Team, Player, TeamRoster, Season, Match, MatchInnings, PlayerMatchPerformance, FanProfile, Poll, CommunityPost (author), ContentVote (withdraw), MemeTemplate, MemeDraft |
| Never deleted via the API (history and audit) | TeamMembership (closed with `left_at`), FanActivity, FanBadge, Vote, Prediction, ModerationAction, ModerationReport, AgentRun, AgentToolCall, GuestSession (revoked instead) |
| Protected from physical deletion (`PROTECT`) | Teams and players referenced by matches, rosters or history; matches referenced by predictions or polls; posts referenced by moderation actions |
| Physical deletion | Only explicit superuser operations in the admin, which apply the database `on_delete` rules |

Moderator removal soft-deletes a post and sets its status to `hidden`; the `restored` action reverses it. Meme drafts follow the moderation outcome of the post created from them.
