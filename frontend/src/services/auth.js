/** Account/auth API (/api/v1/accounts). Session-cookie based; no tokens are stored in the browser. */
import { api } from "../lib/api.js";

/** @typedef {{ id: string, email: string, username: string | null, display_name: string, avatar_url: string,
 *   has_password: boolean, providers: string[], is_staff: boolean }} User */

export const authService = {
  /** @returns {Promise<{authenticated: boolean, user: User | null}>} */
  session: () => api("/accounts/session", { silent401: true }),
  /** @returns {Promise<User>} */
  login: (email, password) => api("/accounts/login", { method: "POST", body: { email, password }, silent401: true }),
  /** @returns {Promise<User>} */
  register: (data) => api("/accounts/register", { method: "POST", body: data }),
  /** @returns {Promise<User & {created: boolean}>} */
  google: (credential) => api("/accounts/google", { method: "POST", body: { credential }, silent401: true }),
  linkGoogle: (credential) => api("/accounts/google/link", { method: "POST", body: { credential } }),
  unlinkGoogle: () => api("/accounts/google/link", { method: "DELETE" }),
  logout: () => api("/accounts/logout", { method: "POST", silent401: true }),
  /** @returns {Promise<User>} */
  updateMe: (changes) => api("/accounts/me", { method: "PATCH", body: changes }),
};
