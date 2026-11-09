import { request, withQuery } from "./http";
import type { OffsetPage, PageQuery } from "./pagination";
import type { ArtifactDependency } from "./contracts/artifacts";
import type { BusinessCase, BusinessCaseDataAttachment } from "./contracts/businessCases";
import type { BusinessCaseCatalogEntry } from "./contracts/businessCaseAccess";

export const businessCasesApi = {
  listBusinessCases: () => request<BusinessCase[]>("/business-cases"),
  pageBusinessCases: (query: PageQuery & { manageable_only?: boolean } = {}) =>
    request<OffsetPage<BusinessCase>>(withQuery("/business-cases/page", query)),
  pageBusinessCaseCatalog: (query: PageQuery = {}) =>
    request<OffsetPage<BusinessCaseCatalogEntry>>(
      withQuery("/business-cases/catalog/page", query)
    ),
  createBusinessCase: (payload: Record<string, unknown>) =>
    request<BusinessCase>("/business-cases", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateBusinessCase: (businessCaseId: string, payload: Record<string, unknown>) =>
    request<BusinessCase>(`/business-cases/${businessCaseId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  transferBusinessCaseOwnership: (businessCaseId: string, payload: { new_owner_id: string; reason?: string }) =>
    request<BusinessCase>(`/business-cases/${businessCaseId}/transfer-ownership`, {
      method: "POST", body: JSON.stringify(payload)
    }),
  attachBusinessCaseData: (businessCaseId: string, payload: Record<string, unknown>) =>
    request<BusinessCaseDataAttachment>(`/business-cases/${businessCaseId}/data-attachments`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listBusinessCaseDataAttachments: (businessCaseId: string) =>
    request<BusinessCaseDataAttachment[]>(`/business-cases/${businessCaseId}/data-attachments`),
  pageBusinessCaseDataAttachments: (
    businessCaseId: string,
    query: PageQuery & {
      role?: string;
      pipeline_id?: string;
      pipeline_type?: string;
      uploaded_only?: boolean;
      deleted_only?: boolean;
    } = {}
  ) => request<OffsetPage<BusinessCaseDataAttachment>>(
    withQuery(`/business-cases/${encodeURIComponent(businessCaseId)}/data-attachments/page`, query)
  ),
  updateBusinessCaseDataAttachment: (businessCaseId: string, attachmentId: string, payload: Record<string, unknown>) =>
    request<BusinessCaseDataAttachment>(`/business-cases/${businessCaseId}/data-attachments/${attachmentId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  deleteBusinessCaseDataAttachment: (businessCaseId: string, attachmentId: string) =>
    request<{ deleted: boolean }>(`/business-cases/${businessCaseId}/data-attachments/${attachmentId}`, {
      method: "DELETE"
    }),
  getArtifactDependencies: (referenceId: string, artifactType: string) =>
    request<ArtifactDependency[]>(
      `/business-cases/dependencies/${encodeURIComponent(referenceId)}?artifact_type=${encodeURIComponent(artifactType)}`
    )
};
