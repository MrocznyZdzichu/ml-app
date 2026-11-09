import { request, withQuery } from "./http";
import type { OffsetPage, PageQuery } from "./pagination";
import type { BusinessCaseAccessRequest, BusinessCaseAccessRole } from "./contracts/businessCaseAccess";
import type { AccessGroup, BusinessCaseGrant, DirectoryUser, GroupMembership, ResourceGrant } from "./contracts/sharing";

export const sharingApi = {
  listDirectoryUsers: () => request<DirectoryUser[]>("/sharing/directory/users"),
  pageDirectoryUsers: (query: PageQuery = {}) =>
    request<OffsetPage<DirectoryUser>>(withQuery("/sharing/directory/users/page", query)),
  listGroups: () => request<AccessGroup[]>("/sharing/groups"),
  pageGroups: (query: PageQuery & { is_active?: boolean } = {}) =>
    request<OffsetPage<AccessGroup>>(withQuery("/sharing/groups/page", query)),
  createGroup: (payload: { name: string; description: string }) =>
    request<AccessGroup>("/sharing/groups", { method: "POST", body: JSON.stringify(payload) }),
  updateGroup: (groupId: string, payload: { name: string; description: string; is_active: boolean }) =>
    request<AccessGroup>(`/sharing/groups/${encodeURIComponent(groupId)}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteGroup: (groupId: string) =>
    request<void>(`/sharing/groups/${encodeURIComponent(groupId)}`, { method: "DELETE" }),
  listGroupMembers: (groupId: string) =>
    request<GroupMembership[]>(`/sharing/groups/${encodeURIComponent(groupId)}/members`),
  pageGroupMembers: (groupId: string, query: PageQuery = {}) =>
    request<OffsetPage<GroupMembership>>(
      withQuery(`/sharing/groups/${encodeURIComponent(groupId)}/members/page`, query)
    ),
  upsertGroupMember: (groupId: string, payload: { user_id: string; membership_role: "member" | "manager" }) =>
    request<GroupMembership>(`/sharing/groups/${encodeURIComponent(groupId)}/members`, { method: "PUT", body: JSON.stringify(payload) }),
  removeGroupMember: (groupId: string, userId: string) =>
    request<void>(`/sharing/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(userId)}`, { method: "DELETE" }),
  listBusinessCaseGrants: (businessCaseId: string) =>
    request<BusinessCaseGrant[]>(`/sharing/business-cases/${encodeURIComponent(businessCaseId)}/grants`),
  pageBusinessCaseGrants: (businessCaseId: string, query: PageQuery = {}) =>
    request<OffsetPage<BusinessCaseGrant>>(
      withQuery(`/sharing/business-cases/${encodeURIComponent(businessCaseId)}/grants/page`, query)
    ),
  grantBusinessCase: (businessCaseId: string, payload: Record<string, unknown>) =>
    request<BusinessCaseGrant>(`/sharing/business-cases/${encodeURIComponent(businessCaseId)}/grants`, { method: "PUT", body: JSON.stringify(payload) }),
  revokeBusinessCaseGrant: (businessCaseId: string, grantId: string) =>
    request<void>(`/sharing/business-cases/${encodeURIComponent(businessCaseId)}/grants/${encodeURIComponent(grantId)}`, { method: "DELETE" }),
  requestBusinessCaseAccess: (
    businessCaseId: string,
    payload: { requested_role: Exclude<BusinessCaseAccessRole, "owner">; justification: string }
  ) => request<BusinessCaseAccessRequest>(
    `/sharing/business-cases/${encodeURIComponent(businessCaseId)}/access-requests`,
    { method: "POST", body: JSON.stringify(payload) }
  ),
  pageBusinessCaseAccessRequests: (
    query: PageQuery & {
      box: "incoming" | "mine" | "submitted_history" | "handled";
      status?: "pending" | "approved" | "rejected";
    }
  ) => request<OffsetPage<BusinessCaseAccessRequest>>(
    withQuery("/sharing/access-requests/page", query)
  ),
  pageBusinessCaseAccessRequestsForBusinessCase: (
    businessCaseId: string,
    query: PageQuery & {
      history?: boolean;
      status?: "pending" | "approved" | "rejected";
    }
  ) => request<OffsetPage<BusinessCaseAccessRequest>>(
    withQuery(
      `/sharing/business-cases/${encodeURIComponent(businessCaseId)}/access-requests/page`,
      query
    )
  ),
  approveBusinessCaseAccessRequest: (
    requestId: string,
    payload: { access_role: Exclude<BusinessCaseAccessRole, "owner">; decision_note?: string }
  ) => request<BusinessCaseAccessRequest>(
    `/sharing/access-requests/${encodeURIComponent(requestId)}/approve`,
    { method: "POST", body: JSON.stringify(payload) }
  ),
  rejectBusinessCaseAccessRequest: (
    requestId: string,
    payload: { decision_note?: string }
  ) => request<BusinessCaseAccessRequest>(
    `/sharing/access-requests/${encodeURIComponent(requestId)}/reject`,
    { method: "POST", body: JSON.stringify(payload) }
  ),
  listResourceGrants: (kind: string, resourceId: string) =>
    request<ResourceGrant[]>(`/sharing/resources/${encodeURIComponent(kind)}/${encodeURIComponent(resourceId)}/grants`),
  pageResourceGrants: (kind: string, resourceId: string, query: PageQuery = {}) =>
    request<OffsetPage<ResourceGrant>>(
      withQuery(
        `/sharing/resources/${encodeURIComponent(kind)}/${encodeURIComponent(resourceId)}/grants/page`,
        query
      )
    ),
  grantResource: (payload: Record<string, unknown>) =>
    request<ResourceGrant>("/sharing/resources/grants", { method: "PUT", body: JSON.stringify(payload) }),
  revokeResourceGrant: (grantId: string) =>
    request<void>(`/sharing/resources/grants/${encodeURIComponent(grantId)}`, { method: "DELETE" })
};
