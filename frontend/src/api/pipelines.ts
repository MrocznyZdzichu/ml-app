import { request, withQuery } from "./http";
import type { OffsetPage, PageQuery } from "./pagination";
import type {
  Pipeline,
  PipelineRun,
  PipelineRunDetails,
  PipelineRunOutputPreview,
  PipelineRunOutputProfile,
  PipelineRunStatus,
  PipelineStepRun,
  PipelineVersion
} from "./contracts/pipelines";

export const pipelinesApi = {
  listPipelines: (businessCaseId?: string) =>
    request<Pipeline[]>(businessCaseId ? `/pipelines?business_case_id=${encodeURIComponent(businessCaseId)}` : "/pipelines"),
  pagePipelines: (
    query: PageQuery & {
      business_case_id?: string;
      pipeline_type?: string;
      pipeline_template?: string;
      status?: string;
      include_deprecated?: boolean;
    } = {}
  ) => request<OffsetPage<Pipeline>>(withQuery("/pipelines/page", query)),
  getPipeline: (pipelineId: string) =>
    request<Pipeline>(`/pipelines/${encodeURIComponent(pipelineId)}`),
  getModelTrainingCatalog: <T = unknown>() =>
    request<T>("/pipelines/model-training/catalog"),
  createPipeline: (payload: Record<string, unknown>) =>
    request<Pipeline>("/pipelines", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updatePipeline: (pipelineId: string, payload: { name: string; description: string; type: string }) =>
    request<Pipeline>(`/pipelines/${pipelineId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  copyPipeline: (pipelineId: string, payload: { name: string }) =>
    request<Pipeline>(`/pipelines/${pipelineId}/copy`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  deletePipeline: (pipelineId: string) =>
    request<{ action: "deleted" | "deprecated" }>(`/pipelines/${pipelineId}`, {
      method: "DELETE"
    }),
  listPipelineVersions: (pipelineId: string) =>
    request<PipelineVersion[]>(`/pipelines/${pipelineId}/versions`),
  pagePipelineVersions: (
    pipelineId: string,
    query: PageQuery & { status?: "draft" | "published" | "" } = {}
  ) => request<OffsetPage<PipelineVersion>>(
    withQuery(`/pipelines/${encodeURIComponent(pipelineId)}/versions/page`, query)
  ),
  updateDraftPipelineVersion: (pipelineId: string, definition: Record<string, unknown>) =>
    request<PipelineVersion>(`/pipelines/${pipelineId}/versions/draft`, {
      method: "PATCH",
      body: JSON.stringify({ definition })
    }),
  publishDraftPipelineVersion: (pipelineId: string) =>
    request<PipelineVersion>(`/pipelines/${pipelineId}/versions/draft/publish`, {
      method: "POST"
    }),
  createNextDraftPipelineVersion: (pipelineId: string) =>
    request<PipelineVersion>(`/pipelines/${pipelineId}/versions/draft`, {
      method: "POST"
    }),
  runPipeline: (pipelineId: string, payload: Record<string, unknown>) =>
    request<PipelineRun>(`/pipelines/${pipelineId}/runs`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listPipelineRuns: (pipelineId: string, limit = 200, offset = 0) =>
    request<PipelineRun[]>(
      `/pipelines/${encodeURIComponent(pipelineId)}/runs?limit=${limit}&offset=${offset}`
    ),
  listPipelineRunHistory: (limit = 200) =>
    request<PipelineRun[]>(`/pipelines/runs/history?limit=${limit}`),
  pagePipelineRunHistory: (
    query: PageQuery & {
      status?: string;
      pipeline_id?: string;
      pipeline_version_id?: string;
      business_case_id?: string;
      trigger_type?: string;
      dry_run?: boolean;
    } = {}
  ) => request<OffsetPage<PipelineRun>>(withQuery("/pipelines/runs/history/page", query)),
  getPipelineRun: (pipelineId: string, runId: string) =>
    request<PipelineRun>(`/pipelines/${pipelineId}/runs/${runId}`),
  getPipelineRunStatus: (pipelineId: string, runId: string) =>
    request<PipelineRunStatus>(`/pipelines/${pipelineId}/runs/${runId}/status`),
  getPipelineRunDetails: (pipelineId: string, runId: string) =>
    request<PipelineRunDetails>(`/pipelines/${pipelineId}/runs/${runId}/details`),
  cancelPipelineRun: (pipelineId: string, runId: string) =>
    request<PipelineRun>(`/pipelines/${pipelineId}/runs/${runId}/cancel`, { method: "POST" }),
  retryPipelineRun: (pipelineId: string, runId: string) =>
    request<PipelineRun>(`/pipelines/${pipelineId}/runs/${runId}/retry`, { method: "POST" }),
  listPipelineStepRuns: (pipelineId: string, runId: string) =>
    request<PipelineStepRun[]>(`/pipelines/${pipelineId}/runs/${runId}/steps`),
  previewPipelineRunOutput: (
    pipelineId: string,
    runId: string,
    outputId: string,
    pipelineStepId: string,
    limit: number,
    offset: number
  ) =>
    request<PipelineRunOutputPreview>(
      `/pipelines/${pipelineId}/runs/${runId}/preview?output_id=${encodeURIComponent(outputId)}&pipeline_step_id=${encodeURIComponent(pipelineStepId)}&limit=${limit}&offset=${offset}`
    ),
  profilePipelineRunOutput: (pipelineId: string, runId: string, outputId: string, pipelineStepId: string) =>
    request<PipelineRunOutputProfile>(
      `/pipelines/${pipelineId}/runs/${runId}/profile?output_id=${encodeURIComponent(outputId)}&pipeline_step_id=${encodeURIComponent(pipelineStepId)}`
    )
};
