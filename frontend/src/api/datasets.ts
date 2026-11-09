import { request, withQuery } from "./http";
import type { OffsetPage, PageQuery } from "./pagination";
import type {
  DataAsset,
  DatasetDrillRequest,
  DatasetPreview,
  DatasetVisualization,
  DatasetVisualizationGroups,
  DatasetVisualizationRequest,
  DataViewCreatePayload,
  FullDescriptiveProfileResponse,
  TimeSeriesAnalysis
} from "./contracts/datasets";

export function temporaryPipelineOutputId(runId: string, outputId: string, pipelineStepId = "") {
  const parts = [encodeURIComponent(runId)];
  if (pipelineStepId) parts.push(encodeURIComponent(pipelineStepId));
  parts.push(encodeURIComponent(outputId));
  return `dry-run-output:${parts.join(":")}`;
}

function datasetRouteId(datasetId: string) {
  return encodeURIComponent(datasetId);
}

type TimeSeriesAnalysisJob = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  result: TimeSeriesAnalysis | null;
  error: string | null;
};

async function analyzeTimeSeries(datasetId: string, payload: { time_column: string; value_column: string; max_lag: number; seasonal_period: number; rolling_window: number; max_points: number; driver_column: string; driver_columns: string[] }) {
  let job = await request<TimeSeriesAnalysisJob>(`/datasets/${datasetRouteId(datasetId)}/time-series-analysis`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
  while (job.status === "queued" || job.status === "running") {
    await abortableDelay(750);
    job = await request<TimeSeriesAnalysisJob>(`/datasets/${datasetRouteId(datasetId)}/time-series-analysis/${job.job_id}`);
  }
  if (job.status === "failed" || !job.result) throw new Error(job.error || "Time-series analysis failed");
  return job.result;
}

type FullDescriptiveProfileJob = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  result: FullDescriptiveProfileResponse | null;
  error: string | null;
};

async function profileDataset(datasetId: string, payload: Record<string, unknown>, signal?: AbortSignal) {
  let job = await request<FullDescriptiveProfileJob>(`/datasets/${datasetRouteId(datasetId)}/descriptive-profile`, {
    method: "POST",
    body: JSON.stringify(payload),
    signal
  });
  while (job.status === "queued" || job.status === "running") {
    await abortableDelay(750, signal);
    job = await request<FullDescriptiveProfileJob>(`/datasets/${datasetRouteId(datasetId)}/descriptive-profile/${job.job_id}`, { signal });
  }
  if (job.status === "failed" || !job.result) {
    throw new Error(job.error || "Dataset profiling failed");
  }
  return job.result;
}

function abortableDelay(milliseconds: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timeout);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timeout = window.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, milliseconds);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export const datasetsApi = {
  listDatasets: () => request<DataAsset[]>("/datasets"),
  listDatasetSummaries: () => request<DataAsset[]>("/datasets?summary=true"),
  getDataset: (datasetId: string) =>
    request<DataAsset>(`/datasets/${encodeURIComponent(datasetId)}`),
  pageDatasets: (query: PageQuery & {
    status?: string;
    source_type?: string;
    asset_kind?: "dataset" | "view";
    include_deleted?: boolean;
    families?: boolean;
    business_case_id?: string;
    pipeline_id?: string;
    pipeline_type?: string;
    uploaded_only?: boolean;
    owned_only?: boolean;
    summary?: boolean;
  } = {}, signal?: AbortSignal) =>
    request<OffsetPage<DataAsset>>(withQuery("/datasets/page", { summary: true, ...query }), signal ? { signal } : undefined),
  listDatasetVersions: (logicalId: string) =>
    request<DataAsset[]>(`/datasets/${datasetRouteId(logicalId)}/versions`),
  pageDatasetVersions: (logicalId: string, query: PageQuery = {}) =>
    request<OffsetPage<DataAsset>>(
      withQuery(`/datasets/${datasetRouteId(logicalId)}/versions/page`, query)
    ),
  createDataset: (payload: Record<string, unknown>) =>
    request<DataAsset>("/datasets", { method: "POST", body: JSON.stringify(payload) }),
  uploadDataset: (payload: FormData) =>
    request<DataAsset>("/datasets/upload", { method: "POST", body: payload }),
  deleteDataset: (datasetId: string) =>
    request<DataAsset>(`/datasets/${datasetRouteId(datasetId)}`, { method: "DELETE" }),
  updateDatasetMetadata: (datasetId: string, metadata: Record<string, unknown>) =>
    request<DataAsset>(`/datasets/${datasetRouteId(datasetId)}/metadata`, {
      method: "PATCH",
      body: JSON.stringify({ metadata })
    }),
  previewDataset: (datasetId: string, limit = 5000) =>
    request<DatasetPreview>(`/datasets/${datasetRouteId(datasetId)}/preview?limit=${limit}`),
  profileDataset,
  queryDataset: (datasetId: string, sql: string, limit = 50000) =>
    request<DatasetPreview>(`/datasets/${datasetRouteId(datasetId)}/query`, {
      method: "POST",
      body: JSON.stringify({ sql, limit })
    }),
  visualizeDataset: (datasetId: string, payload: DatasetVisualizationRequest, signal?: AbortSignal) =>
    request<DatasetVisualization>(`/datasets/${datasetRouteId(datasetId)}/visualization`, {
      method: "POST",
      body: JSON.stringify(payload),
      signal
    }),
  drillDataset: (datasetId: string, payload: DatasetDrillRequest) =>
    request<DatasetPreview>(`/datasets/${datasetRouteId(datasetId)}/drill`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  visualizationGroups: (datasetId: string, column: string, limit = 100) =>
    request<DatasetVisualizationGroups>(`/datasets/${datasetRouteId(datasetId)}/visualization/groups`, {
      method: "POST",
      body: JSON.stringify({ column, limit })
    }),
  analyzeTimeSeries,
  createDataView: (payload: DataViewCreatePayload) =>
    request<DataAsset>("/datasets/views", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
