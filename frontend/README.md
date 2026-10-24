# NPL Adda — Frontend

React 19 + Vite. Talks to the Django API in `../backend`.

```bash
npm install
npm run dev      # http://localhost:5173, proxies /api to http://localhost:9009
npm run lint
npm test
npm run build
```

Set `VITE_PROXY_TARGET` if the API is on another host or port, or set `VITE_API_BASE_URL` to call the API directly. CORS already allows `localhost:5173`.

## Routes

| Path | Page |
| --- | --- |
| `/` | Landing page. Next fixture, team strip and upcoming matches come from the API. Featured posts are real when published; otherwise they are labelled demo items. |
| `/choose-team` | "Aaja, afno team choose gara!" Starts a guest session, creates the fan profile or switches team, and shows a confirmation only after the API confirms the membership. |
| `/card` | Fan card with edit, PNG download and native share (with a copy-link and download fallback). |
| `/home` | Team home built from the backend membership. Tabs: team feed (composer, votes, reports, meme posts), Fan Wars for this team (polls, predictions), and My season (points, rank, history, challenges). Also shows the schedule and squad, with a team switch. |
| `/fan-wars` | Poll cards, winner predictions, the prediction split after the deadline, team and fan rankings, and challenges. |
| `/meme-lab` | Theme, language, caption ideas (mock output is labelled), edit, original template preview, then download, share or submit. |
| `/profile` | Membership history, fan card link, season stats, badges, participation history, your posts and saved drafts. |
| `/teams/:teamId/community` | Published posts for a team. |
| `/matches`, `/matches/:matchId` | Fixtures and results, innings, player statistics, source and freshness. Development samples are labelled. |

## Structure

- **API services:** `src/services/*.js`, typed with JSDoc in `services/types.js`. On failure they surface the error and never fall back to fake data.
- **Language and theme:** the English/Nepali switch and light/dark theme live in `src/lib/PrefsProvider.jsx`. Strings are in `src/i18n/strings.js` (Nepali falls back to English), and the theme uses `data-theme` on `<html>`.
- **Meme rendering:** meme images are drawn on a canvas in `src/lib/memeRender.js` with original procedural backgrounds, so no image service is needed.

## Image credits

`public/hero/tu-ground-night.jpg`: "Tribhuvan University International Cricket Stadium" by Janak Bhatta, [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Tribhuvan_University_International_Cricket_Stadium.jpg), [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), resized to 1920px. The credit is also shown in the site footer, as the licence requires. `public/hero/stadium-night.svg` is an original fallback illustration.

## Auth

- **Session:** the app uses Django's HttpOnly session cookie. `src/lib/api.js` sends `credentials: "include"` and the `X-CSRFToken` header on writes. No tokens are kept in JavaScript, and the client never sends a user ID.
- **Browsing vs taking part:** guests can browse everything public. Protected actions (join, vote, predict, post, memes) open the login dialog, and so does any `401` from the API.
- **Header:** shows **Log in** when logged out, or the avatar menu (Profile, My Team, Settings, Logout) when logged in. `/settings` edits your name and username, links or unlinks Google, and sets language and theme.
- **Google:** set `VITE_GOOGLE_CLIENT_ID` in `.env.local`; see `.env.example` and the backend README. Without it, the Google button is shown disabled with a note.
