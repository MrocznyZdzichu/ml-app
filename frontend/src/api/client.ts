const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const API_ROOT_URL = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
const TOKEN_STORAGE_KEY = "ml_app_access_token";

let accessToken = localStorage.getItem(TOKEN_STORAGE_KEY) ?? "";

export function setAccessToken(token: string | null) {
  accessToken = token ?? "";
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

export function getAccessToken() {
  return accessToken;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(readErrorMessage(body) || response.statusText);
  }

  return response.json() as Promise<T>;
}

function readErrorMessage(body: string) {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
  } catch {
    return body;
  }
  return body;
}

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
};

export type UserProfile = {
  user_id: string;
  email: string;
  display_name: string;
  roles: string[];
};

export type DataAsset = {
  id: string;
  owner_id: string;
  name: string;
  source_type: string;
  format: string;
  description: string;
  original_filename: string | null;
  location_uri: string | null;
  file_size_bytes: number | null;
  row_count: number | null;
  has_header: boolean | null;
  uploaded_by: string | null;
  uploaded_at: string | null;
  deleted_by: string | null;
  deleted_at: string | null;
  status: string;
  tags: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type DatasetColumn = {
  name: string;
  type: "text" | "number" | "date" | "boolean" | "empty" | "mixed" | "unsupported";
};

export type DatasetPreview = {
  dataset_id: string;
  columns: DatasetColumn[];
  records: Array<Record<string, string | number | boolean | null>>;
  row_count: number;
  returned_count: number;
  limit: number;
};

export type VisualizationKind = "line" | "bar" | "scatter" | "histogram" | "boxplot" | "kpi" | "projection" | "time_series" | "autocorrelation" | "lag_relationship";
export type VisualizationAggregation = "average" | "median" | "std" | "sum" | "count" | "min" | "max";
export type VisualizationTrend = "none" | "linear" | "spline" | "polynomial" | "exponential";

export type DatasetVisualizationRequest = {
  kind: VisualizationKind;
  x: string;
  y: string;
  group: string;
  aggregations: VisualizationAggregation[];
  selected_groups: string[] | null;
  x_epsilon: number;
  y_epsilon: number;
  trend: VisualizationTrend;
  polynomial_degree: number;
  max_points: number;
  bins: number;
  feature_columns: string[];
  target_column: string;
  reduction_method: "pca";
  max_lag: number;
  rolling_window: number;
  driver_column: string;
};

export type VisualizationPoint = {
  x: number;
  y: number;
  xLabel: string;
  series: string;
  group?: string;
  aggregation?: VisualizationAggregation;
  count?: number;
  xRange?: [number, number];
  yRange?: [number, number];
  xRangeInclusive?: boolean;
  yRangeInclusive?: boolean;
  minimum?: number;
  q1?: number;
  median?: number;
  q3?: number;
  maximum?: number;
  lowerWhisker?: number;
  upperWhisker?: number;
  outlierCount?: number;
  targetValue?: number | null;
};

export type VisualizationTrendCurve = {
  series: string;
  kind: Exclude<VisualizationTrend, "none">;
  valid_count: number;
  approximate?: boolean;
  parameters: Record<string, number | number[]>;
  r_squared?: number | null;
  fit_space: "y" | "log_y" | "binned_y";
  points: Array<{ x: number; y: number }>;
};

export type DatasetDrillOperator = "contains" | "equals" | "not_equals" | "in" | "regex" | "starts_with" | "ends_with" | "gt" | "gte" | "lt" | "lte" | "between" | "empty" | "not_empty";

export type DatasetDrillFilter = {
  operator: DatasetDrillOperator;
  value?: string;
  values?: string[];
  upper_inclusive?: boolean;
};

export type DatasetDrillRequest = {
  filters: Record<string, DatasetDrillFilter>;
  limit?: number;
};

export type DatasetVisualization = {
  dataset_id: string;
  row_count: number;
  scanned_row_count: number;
  points: VisualizationPoint[];
  trends: VisualizationTrendCurve[];
  series: string[];
  kpi: number | null;
  valid_count: number;
  execution_mode: "full_dataset";
  truncated: boolean;
  approximate: boolean;
  approximation_method?: "binned_gaussian_kde";
  reduction_metadata?: {
    method: "pca";
    feature_columns: string[];
    feature_count?: number;
    target_column?: string | null;
    target_type: "continuous" | "categorical" | "none";
    explained_variance_ratio?: number[];
    complete_case_rows: number;
    fit_scope: "full_dataset_complete_cases";
  } | null;
};

export type DatasetVisualizationGroups = {
  dataset_id: string;
  values: string[];
  truncated: boolean;
};

export type TimeSeriesAnalysis = {
  dataset_id: string;
  time_column: string;
  value_column: string;
  row_count: number;
  scanned_row_count: number;
  valid_count: number;
  execution_mode: "full_dataset";
  summary: {
    start: string;
    end: string;
    span_seconds: number;
    missing_time_count: number;
    invalid_value_count: number;
    duplicate_timestamp_count: number;
    median_interval_seconds: number | null;
    mean_interval_seconds: number | null;
    interval_std_seconds: number | null;
    minimum_interval_seconds: number | null;
    maximum_interval_seconds: number | null;
    regular_interval_ratio: number | null;
    gap_count: number;
    mean: number | null;
    std_dev: number | null;
    minimum: number | null;
    maximum: number | null;
    trend_per_day: number | null;
    trend_r_squared: number | null;
    difference_mean: number | null;
    difference_std_dev: number | null;
    lag1_autocorrelation: number | null;
    suggested_seasonal_period: number | null;
    seasonal_period: number | null;
    interval_count: number;
    driver_column?: string | null;
    strongest_driver_column?: string | null;
    strongest_driver_lag?: number | null;
    strongest_driver_correlation?: number | null;
  };
  series: Array<{ timestamp: string; value: number; minimum: number; maximum: number; count: number; rolling_mean: number | null; rolling_std_dev: number | null }>;
  autocorrelation: Array<{ lag: number; correlation: number | null; pair_count: number }>;
  cross_correlation: Array<{ lag: number; correlation: number | null; pair_count: number }>;
  driver_relationships: Array<{
    driver_column: string;
    strongest_lag: number | null;
    strongest_correlation: number | null;
    pair_count: number;
    direction: "positive" | "negative" | "flat" | "none";
    strength: string;
    correlations: Array<{ lag: number; correlation: number | null; pair_count: number }>;
  }>;
  seasonal_profile: Array<{ phase: number; mean: number; std_dev: number | null; count: number }>;
  decomposition: Array<{ timestamp: string; observed: number | null; trend: number | null; seasonal: number | null; residual: number | null; count: number }>;
  difference_series: Array<{ timestamp: string; difference: number | null; std_dev: number | null; rolling_abs_difference: number | null; count: number }>;
  feature_preview: Array<{ timestamp: string; value: number; lag_1: number | null; seasonal_lag: number | null; difference: number | null; rolling_mean: number | null; rolling_std_dev: number | null; position: number }>;
  quality_notes: string[];
};

type TimeSeriesAnalysisJob = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  result: TimeSeriesAnalysis | null;
  error: string | null;
};

async function analyzeTimeSeries(datasetId: string, payload: { time_column: string; value_column: string; max_lag: number; seasonal_period: number; rolling_window: number; max_points: number; driver_column: string; driver_columns: string[] }) {
  let job = await request<TimeSeriesAnalysisJob>(`/datasets/${datasetId}/time-series-analysis`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
  while (job.status === "queued" || job.status === "running") {
    await abortableDelay(750);
    job = await request<TimeSeriesAnalysisJob>(`/datasets/${datasetId}/time-series-analysis/${job.job_id}`);
  }
  if (job.status === "failed" || !job.result) throw new Error(job.error || "Time-series analysis failed");
  return job.result;
}

export type FullDescriptiveProfileResponse = {
  dataset_id: string;
  columns: DatasetColumn[];
  row_count: number;
  profile: Record<string, unknown>;
};

type FullDescriptiveProfileJob = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  result: FullDescriptiveProfileResponse | null;
  error: string | null;
};

async function profileDataset(datasetId: string, payload: Record<string, unknown>, signal?: AbortSignal) {
  let job = await request<FullDescriptiveProfileJob>(`/datasets/${datasetId}/descriptive-profile`, {
    method: "POST",
    body: JSON.stringify(payload),
    signal
  });
  while (job.status === "queued" || job.status === "running") {
    await abortableDelay(750, signal);
    job = await request<FullDescriptiveProfileJob>(`/datasets/${datasetId}/descriptive-profile/${job.job_id}`, { signal });
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

export type DataViewCreatePayload = {
  name: string;
  source_dataset_id: string;
  definition: Record<string, unknown>;
  description?: string;
  tags?: string[];
};

export type AnalysisJob = {
  id: string;
  title: string;
  kind: string;
  dataset_id: string;
  status: string;
};

export type ModelArtifact = {
  id: string;
  name: string;
  version: string;
  algorithm: string;
  stage: string;
  artifact_uri: string;
};

export type Deployment = {
  id: string;
  name: string;
  model_id: string;
  status: string;
  endpoint_url: string | null;
};

export type ScoreResponse = {
  deployment_id: string;
  predictions: Array<Record<string, unknown>>;
};

export const api = {
  health: () => fetch(`${API_ROOT_URL}/health`).then((response) => response.json()),
  register: (payload: { email: string; password: string; display_name?: string }) =>
    request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  login: (payload: { email: string; password: string }) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  me: () => request<UserProfile>("/auth/me"),
  listDatasets: () => request<DataAsset[]>("/datasets"),
  createDataset: (payload: Record<string, unknown>) =>
    request<DataAsset>("/datasets", { method: "POST", body: JSON.stringify(payload) }),
  uploadDataset: (payload: FormData) =>
    request<DataAsset>("/datasets/upload", { method: "POST", body: payload }),
  deleteDataset: (datasetId: string) =>
    request<DataAsset>(`/datasets/${datasetId}`, { method: "DELETE" }),
  updateDatasetMetadata: (datasetId: string, metadata: Record<string, unknown>) =>
    request<DataAsset>(`/datasets/${datasetId}/metadata`, {
      method: "PATCH",
      body: JSON.stringify({ metadata })
    }),
  previewDataset: (datasetId: string, limit = 5000) =>
    request<DatasetPreview>(`/datasets/${datasetId}/preview?limit=${limit}`),
  profileDataset,
  queryDataset: (datasetId: string, sql: string, limit = 50000) =>
    request<DatasetPreview>(`/datasets/${datasetId}/query`, {
      method: "POST",
      body: JSON.stringify({ sql, limit })
    }),
  visualizeDataset: (datasetId: string, payload: DatasetVisualizationRequest, signal?: AbortSignal) =>
    request<DatasetVisualization>(`/datasets/${datasetId}/visualization`, {
      method: "POST",
      body: JSON.stringify(payload),
      signal
    }),
  drillDataset: (datasetId: string, payload: DatasetDrillRequest) =>
    request<DatasetPreview>(`/datasets/${datasetId}/drill`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  visualizationGroups: (datasetId: string, column: string, limit = 100) =>
    request<DatasetVisualizationGroups>(`/datasets/${datasetId}/visualization/groups`, {
      method: "POST",
      body: JSON.stringify({ column, limit })
    }),
  analyzeTimeSeries,
  createDataView: (payload: DataViewCreatePayload) =>
    request<DataAsset>("/datasets/views", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  createAnalysis: (payload: Record<string, unknown>) =>
    request<AnalysisJob>("/analysis", { method: "POST", body: JSON.stringify(payload) }),
  describeRecords: (records: Array<Record<string, unknown>>) =>
    request<Record<string, unknown>>("/analysis/descriptive-stats", {
      method: "POST",
      body: JSON.stringify({ records })
    }),
  trainModel: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/models/training-jobs", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listModels: () => request<ModelArtifact[]>("/models"),
  createDeployment: (payload: Record<string, unknown>) =>
    request<Deployment>("/serving/deployments", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listDeployments: () => request<Deployment[]>("/serving/deployments"),
  score: (deploymentId: string, records: Array<Record<string, unknown>>) =>
    request<ScoreResponse>(`/serving/deployments/${deploymentId}/score`, {
      method: "POST",
      body: JSON.stringify({ records })
    }),
  share: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/sharing/grants", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  exportResource: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/exports", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
