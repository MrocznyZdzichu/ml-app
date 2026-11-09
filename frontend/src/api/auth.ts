import { API_ROOT_URL, request } from "./http";
import type { AuthResponse, UserProfile } from "./contracts/auth";
import type { CreatedPersonalAccessToken, PersonalAccessToken } from "./contracts/personalAccessToken";

export const authApi = {
  health: () => fetch(`${API_ROOT_URL}/health`).then((response) => response.json()),
  register: (payload: { email: string; password: string; display_name?: string }) =>
    request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  login: (payload: { login?: string; email?: string; password: string }) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ login: payload.login ?? payload.email, password: payload.password })
    }),
  me: () => request<UserProfile>("/auth/me"),
  changePassword: (payload: { current_password: string; new_password: string }) =>
    request<void>("/auth/change-password", { method: "POST", body: JSON.stringify(payload) }),
  createPersonalAccessToken: (name: string, expiresAt: string | null) =>
    request<CreatedPersonalAccessToken>("/auth/api-credentials", {
      method: "POST",
      body: JSON.stringify({ name, expires_at: expiresAt })
    }),
  listPersonalAccessTokens: () => request<PersonalAccessToken[]>("/auth/api-credentials"),
  revokePersonalAccessToken: (tokenId: string) =>
    request<void>(`/auth/api-credentials/${encodeURIComponent(tokenId)}`, { method: "DELETE" })
};
