/** Community content and moderation-report API (/api/v1/content, /api/v1/moderation). */
import { api } from "../lib/api.js";

/** @typedef {import("./types.js").Post} Post */

export const contentService = {
  /** Published posts only (the API never returns unapproved content here). */
  feed: ({ team, contentType, page } = {}) => {
    const p = new URLSearchParams();
    if (team) p.set("team", team);
    if (contentType) p.set("content_type", contentType);
    if (page) p.set("page", page);
    return api(`/content${p.toString() ? `?${p}` : ""}`);
  },
  /** @returns {Promise<Post>} */
  get: (id) => api(`/content/${id}`),
  mine: () => api("/content/mine"),
  /** @returns {Promise<Post>} */
  create: (body) => api("/content", { method: "POST", body: { ...body, submit_for_review: true } }),
  update: (id, body) => api(`/content/${id}`, { method: "PATCH", body }),
  remove: (id) => api(`/content/${id}`, { method: "DELETE" }),
  vote: (id, voteType) => api(`/content/${id}/vote`, { method: "POST", body: { vote_type: voteType } }),
  report: (postId, reason, description = "") =>
    api("/moderation/reports", { method: "POST", body: { post: postId, reason, description } }),
};
