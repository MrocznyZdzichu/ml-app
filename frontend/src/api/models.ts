import { request, withQuery } from "./http";
import type { OffsetPage, PageQuery } from "./pagination";
import type { DatasetLineageReference } from "./contracts/artifacts";
import type { ModelArtifact } from "./contracts/models";
import type { ModelServingUsage } from "./contracts/serving";

export const modelsApi = {
  listModels: () => request<ModelArtifact[]>("/models"),
  listModelSummaries: () => request<ModelArtifact[]>("/models?summary=true"),
  pageModels: (
    query: PageQuery & {
      business_case_id?: string;
      stage?: string;
      pipeline_id?: string;
      pipeline_type?: string;
    } = {}
  ) => request<OffsetPage<{ latest: ModelArtifact; version_count: number }>>(
    withQuery("/models/page", query)
  ),
  promoteModel: (modelId: string, stage: "developed" | "staging" | "production" | "archived") =>
    request<ModelArtifact>(`/models/${encodeURIComponent(modelId)}/stage`, {
      method: "PATCH",
      body: JSON.stringify({ stage })
    }),
  listModelVersions: (logicalId: string) =>
    request<ModelArtifact[]>(`/models/${encodeURIComponent(logicalId)}/versions`),
  pageModelVersions: (logicalId: string, query: PageQuery = {}) =>
    request<OffsetPage<ModelArtifact>>(
      withQuery(`/models/${encodeURIComponent(logicalId)}/versions/page`, query)
    ),
  listModelServingUsage: (logicalId: string) =>
    request<ModelServingUsage[]>(`/serving/model-families/${encodeURIComponent(logicalId)}/usage`),
  pageModelServingUsage: (modelId: string, query: PageQuery = {}) =>
    request<OffsetPage<ModelServingUsage>>(
      withQuery(`/serving/models/${encodeURIComponent(modelId)}/usage/page`, query)
    ),
  getModel: (modelId: string) =>
    request<ModelArtifact>(`/models/${encodeURIComponent(modelId)}`),
  getModelDataLineage: (modelId: string) =>
    request<DatasetLineageReference[]>(`/models/${encodeURIComponent(modelId)}/data-lineage`)
};
