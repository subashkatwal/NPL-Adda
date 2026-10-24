/** Staff admin console API (/api/v1/admin). Every call needs a staff session. */
import { api } from "../lib/api.js";

const query = (params = {}) => {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, v);
  });
  const s = p.toString();
  return s ? `?${s}` : "";
};

const metaCache = new Map();

export const adminService = {
  /** @returns {Promise<{me: object, resources: object[]}>} */
  index: () => api("/admin/resources"),
  dashboard: () => api("/admin/dashboard"),
  /** OPTIONS: resource description, field definitions and custom action inputs (cached per resource). */
  meta: (key) => {
    if (!metaCache.has(key)) {
      metaCache.set(key, api(`/admin/${key}`, { method: "OPTIONS" }).catch((err) => {
        metaCache.delete(key);
        throw err;
      }));
    }
    return metaCache.get(key);
  },
  list: (key, params) => api(`/admin/${key}${query(params)}`),
  get: (key, id) => api(`/admin/${key}/${id}`),
  create: (key, body) => api(`/admin/${key}`, { method: "POST", body }),
  update: (key, id, body) => api(`/admin/${key}/${id}`, { method: "PATCH", body }),
  remove: (key, id) => api(`/admin/${key}/${id}`, { method: "DELETE" }),
  restore: (key, id) => api(`/admin/${key}/${id}/restore`, { method: "POST", body: {} }),
  /** Bulk soft delete/restore: `{ids}` or `{all: true}` for every row matching `params` (the list's filters). */
  bulk: (key, params, body) => api(`/admin/${key}/bulk${query(params)}`, { method: "POST", body }),
  run: (key, id, action, body = {}) => api(`/admin/${key}/${id}/run/${action}`, { method: "POST", body }),
  /** Run a quick action (e.g. verify) on many rows at once. */
  bulkRun: (key, action, body) => api(`/admin/${key}/bulk-run/${action}`, { method: "POST", body }),
  /** Nav badge counts per resource: {pending?, new?}. */
  attention: () => api("/admin/attention"),
  markSeen: (key) => api("/admin/attention", { method: "POST", body: { resource: key } }),
};
