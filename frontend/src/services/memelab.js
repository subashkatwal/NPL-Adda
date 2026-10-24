/** Meme Zone API (/api/v1/memelab). Caption suggestions say whether an AI model or the offline templates made them. */
import { api } from "../lib/api.js";

/** @typedef {import("./types.js").GenerationResult} GenerationResult */
/** @typedef {import("./types.js").MemeDraft} MemeDraft */

const newKey = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
const qs = (params = {}) => {
  const p = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""));
  return p.toString() ? `?${p}` : "";
};

export const memeService = {
  templates: () => api("/memelab/templates"),
  captionStatus: () => api("/memelab/caption-status"),
  /**
   * @param {{topic: string, language: string, style: string, team?: string|null, match?: string|null}} input
   * @returns {Promise<GenerationResult>}
   */
  generate: (input) => api("/memelab/generations", { method: "POST", body: { ...input, idempotency_key: newKey() } }),
  drafts: (params) => api(`/memelab/drafts${qs(params)}`),
  createDraft: (body) => api("/memelab/drafts", { method: "POST", body }),
  /** @returns {Promise<MemeDraft>} */
  saveDraft: (id, changes) => api(`/memelab/drafts/${id}`, { method: "PATCH", body: changes }),
  deleteDraft: (id) => api(`/memelab/drafts/${id}`, { method: "DELETE" }),
  submitDraft: (id) => api(`/memelab/drafts/${id}/submit`, { method: "POST" }),
  draftImage: (id) => api(`/memelab/drafts/${id}/image`, { blob: true }),
  upload: (file) => {
    const form = new FormData();
    form.append("image", file);
    return api("/memelab/uploads", { method: "POST", body: form });
  },
  /** Server-rendered (Pillow) JPEG preview. */
  render: (body, signal) => api("/memelab/render", { method: "POST", body, blob: true, signal }),

  memes: (params) => api(`/memelab/memes${qs(params)}`),
  meme: (id) => api(`/memelab/memes/${id}`),
  react: (id, kind) => api(`/memelab/memes/${id}/react`, { method: "POST", body: { kind } }),
  vote: (id, voteType) => api(`/content/${id}/vote`, { method: "POST", body: { vote_type: voteType } }),
  unvote: (id) => api(`/content/${id}/vote`, { method: "DELETE" }),
  report: (id, reason) => api("/moderation/reports", { method: "POST", body: { post: id, reason } }),
  comments: (id, page) => api(`/memelab/memes/${id}/comments${qs({ page })}`),
  comment: (id, body, parent) => api(`/memelab/memes/${id}/comments`, { method: "POST", body: { body, parent } }),
  deleteComment: (id) => api(`/memelab/comments/${id}`, { method: "DELETE" }),
  reportComment: (id, reason) => api(`/memelab/comments/${id}/report`, { method: "POST", body: { reason } }),

  contests: (phase) => api(`/memelab/contests${qs({ phase })}`),
  contest: (id) => api(`/memelab/contests/${id}`),
  enter: (id, post) => api(`/memelab/contests/${id}/enter`, { method: "POST", body: { post } }),
  contestVote: (id, entry) => api(`/memelab/contests/${id}/vote`, { method: "POST", body: { entry } }),
  hallOfFame: (period) => api(`/memelab/hall-of-fame${qs({ period })}`),
  teamWars: (period) => api(`/memelab/team-wars${qs({ period })}`),
};

export const REACTIONS = [
  { kind: "fire", emoji: "🔥", label: "Fire" },
  { kind: "laugh", emoji: "😂", label: "Laugh" },
  { kind: "clap", emoji: "👏", label: "Clap" },
  { kind: "heartbreak", emoji: "💔", label: "Heartbreak" },
];
