/** Fan engagement API (/api/v1/fanpage). Every value shown to fans comes from these calls. */
import { api } from "../lib/api.js";

/** @typedef {import("./types.js").Poll} Poll */
/** @typedef {import("./types.js").PollResults} PollResults */
/** @typedef {import("./types.js").Prediction} Prediction */
/** @typedef {import("./types.js").TeamRank} TeamRank */
/** @typedef {import("./types.js").Challenge} Challenge */
/** @typedef {import("./types.js").SeasonSummary} SeasonSummary */

const qs = (params) => {
  const search = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== ""));
  return search.toString() ? `?${search}` : "";
};

export const fanService = {
  /** @returns {Promise<import("./types.js").Page>} */
  polls: (params = {}) => api(`/fanpage/polls${qs(params)}`),
  /** @returns {Promise<PollResults>} */
  vote: (pollId, optionId) => api(`/fanpage/polls/${pollId}/vote`, { method: "POST", body: { option: optionId } }),
  /** @returns {Promise<Poll>} */
  poll: (pollId) => api(`/fanpage/polls/${pollId}`),

  /** @returns {Promise<import("./types.js").Page>} */
  myPredictions: () => api("/fanpage/predictions"),
  /** @returns {Promise<Prediction>} */
  predict: (matchId, teamId) =>
    api("/fanpage/predictions", { method: "POST", body: { match: matchId, predicted_winner: teamId } }),
  predictionSplit: (matchId) => api(`/fanpage/matches/${matchId}/prediction-summary`),

  /** @returns {Promise<TeamRank[]>} */
  teamRanks: (season) => api(`/fanpage/leaderboard/teams${qs({ season })}`),
  /** @returns {Promise<import("./types.js").Page>} */
  fanRanks: (params = {}) => api(`/fanpage/leaderboard${qs(params)}`),

  /** @returns {Promise<Challenge[]>} */
  challenges: () => api("/fanpage/me/challenges"),
  /** @returns {Promise<SeasonSummary>} */
  seasonSummary: (season) => api(`/fanpage/me/season-summary${qs({ season })}`),
  activities: () => api("/fanpage/me/activities"),
  memberships: () => api("/fanpage/me/memberships"),
  badges: () => api("/fanpage/me/badges"),
  allBadges: () => api("/fanpage/badges"),

  /** Fan card: everything the server verified (level, stats, badges) plus the owner's privacy switches. */
  myCard: () => api("/fanpage/me/card"),
  /** Another fan's card, limited to what they chose to show. 404 when private. */
  publicCard: (profileId) => api(`/fanpage/${profileId}/card`),
  updateProfile: (profileId, body) => api(`/fanpage/${profileId}`, { method: "PATCH", body }),
  switchTeam: (teamId) => api("/fanpage/me/membership", { method: "POST", body: { team: teamId } }),
  uploadAvatar: (file) => {
    const form = new FormData();
    form.append("image", file);
    return api("/fanpage/me/avatar", { method: "POST", body: form });
  },
  removeAvatar: () => api("/fanpage/me/avatar", { method: "DELETE" }),
};
