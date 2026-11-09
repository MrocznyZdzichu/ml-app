import { request, withQuery } from "./http";
import type { OffsetPage, PageQuery } from "./pagination";
import type { DirectoryUser } from "./contracts/sharing";

export const usersApi = {
  listAdminUsers: () => request<DirectoryUser[]>("/users"),
  pageAdminUsers: (
    query: PageQuery & { is_active?: boolean; is_technical?: boolean } = {}
  ) => request<OffsetPage<DirectoryUser>>(withQuery("/users/page", query)),
  updateAdminUser: (userId: string, payload: { roles: string[]; is_active: boolean }) =>
    request<DirectoryUser>(`/users/${encodeURIComponent(userId)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  resetUserPassword: (userId: string, newPassword: string) =>
    request<void>(`/users/${encodeURIComponent(userId)}/reset-password`, { method: "POST", body: JSON.stringify({ new_password: newPassword }) })
};
