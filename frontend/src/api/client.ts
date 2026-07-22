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

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

function readErrorMessage(body: string) {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
    if (parsed.detail && typeof parsed.detail === "object") {
      const detail = parsed.detail as { message?: unknown; errors?: unknown };
      if (typeof detail.message === "string") {
        const errors = Array.isArray(detail.errors)
          ? detail.errors
              .filter((item) => item && typeof item === "object")
              .slice(0, 3)
              .map((item) => {
                const error = item as { path?: unknown; message?: unknown };
                return `${typeof error.path === "string" && error.path ? `${error.path}: ` : ""}${String(error.message ?? "")}`;
              })
              .filter(Boolean)
          : [];
        return [detail.message, ...errors].join(" · ");
      }
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
  login_name: string;
};

export type UserProfile = {
  user_id: string;
  email: string;
  display_name: string;
  roles: string[];
  login_name: string;
  is_active: boolean;
  uses_initial_password: boolean;
};

export type DataAsset = {
  id: string;
  owner_id: string;
  name: string;
  source_type: string;
  format: string;
  logical_id: string;
  version_number: number;
  version_stage: "source" | "intermediate" | "final" | "view";
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

export type ArtifactDependency = {
  direction: "upstream" | "downstream";
  role: string;
  artifact_id: string;
  artifact_type: string;
  reference_id: string;
  business_case_id: string;
  pipeline_id: string;
  pipeline_version_id: string;
  pipeline_run_id: string;
  pipeline_step_id: string;
};

export function temporaryPipelineOutputId(runId: string, outputId: string, pipelineStepId = "") {
  const parts = [encodeURIComponent(runId)];
  if (pipelineStepId) parts.push(encodeURIComponent(pipelineStepId));
  parts.push(encodeURIComponent(outputId));
  return `dry-run-output:${parts.join(":")}`;
}

function datasetRouteId(datasetId: string) {
  return encodeURIComponent(datasetId);
}

export type DatasetColumn = {
  name: string;
  type: "text" | "number" | "date" | "boolean" | "empty" | "mixed" | "unsupported";
  storage_type?: string;
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
  owner_id: string;
  training_job_id: string;
  name: string;
  version: string;
  logical_id: string;
  version_number: number;
  algorithm: string;
  stage: string;
  artifact_uri: string;
  metrics: Record<string, unknown>;
  business_case_id: string;
  pipeline_id: string;
  pipeline_version_id: string;
  pipeline_run_id: string;
  pipeline_step_id: string;
  problem_type: string;
  target_column: string;
  feature_columns: string[];
  model_hash: string;
  training_config: Record<string, unknown>;
  model_parameters: {
    weights?: Array<{ class: unknown; feature: string; weight: number }>;
    intercepts?: number[];
    total_weight_count?: number;
    returned_weight_count?: number;
    truncated?: boolean;
  };
  lineage: Record<string, unknown>;
  fitted_transform_artifact_id: string;
  data_engineering_definition: Record<string, unknown>;
  feature_engineering_definition: Record<string, unknown>;
  created_at: string;
};

export type ScoringReport = {
  id: string;
  owner_id: string;
  name: string;
  logical_id: string;
  version_number: number;
  business_case_id: string;
  pipeline_id: string;
  pipeline_version_id: string;
  pipeline_run_id: string;
  pipeline_step_id: string;
  problem_type: string;
  prediction_dataset_id: string;
  prediction_artifact_id: string;
  model_artifact_id: string;
  evaluated_row_count: number;
  evaluation: ModelEvaluationSnapshot;
  lineage: Record<string, unknown>;
  created_at: string;
};

export type DatasetLineageReference = {
  artifact_id: string;
  artifact_type: string;
  dataset_id: string;
  logical_id: string;
  version_number: number;
  name: string;
  role: string;
  stage: string;
  format: string;
  row_count: number | null;
  pipeline_step_id: string;
  pipeline_run_id: string;
  depth: number;
};

export type Deployment = {
  id: string;
  owner_id: string;
  business_case_id: string;
  name: string;
  slug: string;
  status: "requested" | "building" | "running" | "degraded" | "failed" | "stopped" | "archived";
  active_revision_id: string;
  endpoint_url: string | null;
  retention_days: number;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  active_revision: DeploymentRevision | null;
};

export type DeploymentRole = "champion" | "challenger" | "shadow" | "fallback";

export type DeploymentRevision = {
  id: string;
  deployment_id: string;
  version_number: number;
  assignments: Array<{ model_id: string; role: DeploymentRole }>;
  created_by: string;
  reason: string;
  created_at: string;
};

export type ModelServingUsage = {
  model_id: string;
  deployment_id: string;
  deployment_name: string;
  deployment_slug: string;
  deployment_status: Deployment["status"];
  endpoint_url: string | null;
  revision_id: string;
  revision_version: number;
  role: DeploymentRole;
};

export type ScoreResponse = {
  request_id: string;
  correlation_id: string;
  deployment_id: string;
  deployment_revision_id: string;
  model_id: string;
  served_role: DeploymentRole;
  fallback_used: boolean;
  predictions: Array<{ prediction_id: string; record_id: string; prediction: unknown; outputs: Record<string, unknown> }>;
  warnings: string[];
};

export type InferenceInputField = {
  name: string;
  value_type: "number" | "integer" | "string" | "boolean";
  required: boolean;
  default_value: unknown;
  description: string;
  minimum: number | null;
  maximum: number | null;
  options: unknown[];
};

export type InferenceInputContract = {
  deployment_id: string;
  deployment_revision_id: string;
  model_id: string;
  role: DeploymentRole;
  fields: InferenceInputField[];
  example_features: Record<string, unknown>;
};

export type DeploymentModelOption = {
  model_id: string;
  name: string;
  version: string;
  business_case_id: string;
  stage: string;
  contract_signature: string;
  compatible_with_active_champion: boolean;
  allowed_roles: DeploymentRole[];
};

export type InferenceRequest = {
  id: string;
  deployment_id: string;
  deployment_revision_id: string;
  requested_by: string;
  correlation_id: string;
  status: "accepted" | "succeeded" | "failed";
  record_count: number;
  request_payload: Record<string, unknown>;
  response_payload: Record<string, unknown>;
  warnings: string[];
  error_code: string;
  error_message: string;
  champion_model_id: string;
  served_model_id: string;
  served_role: string;
  fallback_used: boolean;
  latency_ms: number | null;
  created_at: string;
  completed_at: string | null;
};

export type InferenceRequestSummary = Omit<
  InferenceRequest,
  "request_payload" | "response_payload"
>;

export type InferencePage = {
  items: InferenceRequest[];
  next_cursor: string | null;
};

export type InferenceSummaryPage = {
  items: InferenceRequestSummary[];
  next_cursor: string | null;
};

export type ChallengerReplay = {
  id: string;
  deployment_id: string;
  deployment_revision_id: string;
  challenger_model_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  max_requests: number;
  processed_requests: number;
  processed_records: number;
  failed_requests: number;
  error_message: string;
  created_at: string;
};

export type OnlineMonitoringRun = {
  id: string;
  deployment_id: string;
  business_case_id: string;
  owner_id: string;
  requested_by: string;
  status: "queued" | "running" | "succeeded" | "failed";
  since: string;
  until: string;
  source_before: string;
  actuals_dataset_id: string;
  aggregation_granularity: "none" | "hour" | "day" | "week" | "month";
  actuals_artifact_id: string;
  join_strategy: "auto" | "prediction_id" | "request_record_id" | "record_id" | "not_applicable";
  actuals_prediction_id_column: string;
  actuals_request_id_column: string;
  actuals_record_id_column: string;
  actuals_target_column: string;
  problem_type: string;
  target_column: string;
  time_basis: "scored_at";
  processed_request_count: number;
  processed_row_count: number;
  matched_row_count: number;
  missing_actuals_count: number;
  unmatched_actuals_count: number;
  snapshot_dataset_id: string;
  joined_dataset_id: string;
  report_artifact_id: string;
  report: Record<string, unknown>;
  warnings: string[];
  error_message: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  archived_at: string | null;
  archived_by: string;
  archive_reason: string;
};

export type OnlineMonitoringBucketEvaluation = {
  bucket_start: string;
  bucket_end: string;
  label: string;
  evaluation: ModelEvaluationSnapshot;
};

export type BusinessCase = {
  id: string;
  owner_id: string;
  name: string;
  description: string;
  problem_type: string;
  status: string;
  business_owner: string;
  primary_metric: string;
  target_column: string;
  business_goal: string;
  success_criteria: string;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  access_role: "report_viewer" | "reader" | "contributor" | "manager" | "owner";
};

export type DirectoryUser = {
  id: string;
  user_id?: string;
  login_name: string;
  email: string;
  display_name: string;
  roles?: string[];
  is_active: boolean;
  is_technical?: boolean;
  session_version?: number;
  created_at?: string;
};

export type AccessGroup = {
  id: string;
  name: string;
  description: string;
  is_active: boolean;
  owner_id: string;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
};

export type GroupMembership = {
  id: string;
  group_id: string;
  user_id: string;
  membership_role: "member" | "manager" | "owner";
  added_by: string;
  created_at: string;
};

export type BusinessCaseGrant = {
  id: string;
  business_case_id: string;
  subject_type: "user" | "group";
  subject_id: string;
  access_role: BusinessCase["access_role"];
  granted_by: string;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
};

export type ResourceGrant = {
  id: string;
  resource_kind: "dataset" | "data_view" | "analysis" | "report";
  resource_id: string;
  subject_type: "user" | "group";
  subject_id: string;
  access_role: "reader" | "editor" | "owner";
  granted_by: string;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
};

export type BusinessCaseDataAttachment = {
  id: string;
  owner_id: string;
  business_case_id: string;
  artifact_id: string;
  data_asset_id: string;
  data_asset_kind: "dataset" | "data_view";
  role: string;
  context_note: string;
  primary_key_column: string;
  target_column: string;
  created_by: string;
  created_at: string;
};

export type Pipeline = {
  id: string;
  owner_id: string;
  business_case_id: string;
  name: string;
  description: string;
  type: string;
  status: string;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  latest_published_version_number: number | null;
  published_version_count: number;
  draft_version_number: number | null;
  template: string;
};

export type PipelineVersion = {
  id: string;
  owner_id: string;
  pipeline_id: string;
  business_case_id: string;
  version_number: number;
  status: string;
  definition: Record<string, unknown>;
  definition_hash: string;
  created_by: string;
  created_at: string;
  published_by: string;
  published_at: string | null;
};

export type ModelEvaluationMetric = {
  id: string;
  label: string;
  value: number;
  direction: "higher" | "lower" | "target_zero" | string;
  unit: string;
};

export type ModelEvaluationSnapshot = {
  contract_version: string;
  kind: "model_performance";
  status: "available" | "target_unavailable";
  problem_type: string;
  generated_at: string;
  data_scope: {
    mode: "full";
    scanned_row_count?: number;
    evaluated_row_count: number;
    excluded_row_count: number;
  };
  columns?: { target?: string; prediction?: string; score?: string | null };
  metrics: ModelEvaluationMetric[];
  class_metrics?: Array<{
    label: unknown;
    support: number;
    predicted_count: number;
    precision: number;
    recall: number;
    f1: number;
  }>;
  class_count?: number;
  positive_class?: unknown;
  confusion_matrix?: {
    labels: unknown[];
    values: number[][];
    truncated: boolean;
    total_class_count: number;
  };
  curves?: Record<string, {
    x_label: string;
    y_label: string;
    points: Array<{ x: number; y: number; threshold?: number | null; count?: number }>;
    rendering: string;
  }>;
  distributions?: {
    score_by_actual?: Array<{
      lower: number;
      upper: number;
      negative_count: number;
      positive_count: number;
    }>;
  };
  residuals?: {
    summary: {
      mean: number;
      standard_deviation: number;
      p05: number;
      median: number;
      p95: number;
    };
    histogram: Array<{ lower: number; upper: number; count: number }>;
    qq_plot?: {
      points: Array<{ theoretical: number; observed: number }>;
      x_label: string;
      y_label: string;
      rendering: string;
    };
    actual_vs_predicted: {
      points: Array<{ actual: number; predicted: number }>;
      rendering: string;
    };
  };
  warnings: string[];
  monitoring: {
    baseline_eligible: boolean;
    requires_actuals: boolean;
    comparison_dimensions?: string[];
  };
};

export type PipelineRun = {
  id: string;
  owner_id: string;
  pipeline_id: string;
  pipeline_version_id: string;
  business_case_id: string;
  status: string;
  trigger_type: string;
  runtime_parameters: Record<string, unknown>;
  is_dry_run: boolean;
  requested_step_id: string;
  input_row_count: number | null;
  processed_row_count: number | null;
  output_row_count: number | null;
  rejected_row_count: number | null;
  warnings: string[];
  events: PipelineRunEvent[];
  output_artifact_ids: string[];
  output_manifest: Array<{
    output_id: string;
    artifact_type?: "dataset" | "prediction_dataset" | "feature_transform" | "model_version" | "metrics" | "report";
    materialization: "temporary" | "dataset" | "artifact";
    location_uri: string;
    row_count?: number;
    schema?: Array<{ name: string; type: string }>;
    schema_hash?: string;
    state_hash?: string;
    feature_manifest?: Array<Record<string, unknown>>;
    data_scope: "full";
    is_dry_run: boolean;
    dataset_name?: string;
    business_case_role?: string;
    dataset_id?: string;
    logical_id?: string;
    version_number?: number;
    artifact_id?: string;
    pipeline_step_id?: string;
    output_stage?: "intermediate" | "final";
    quality_output_kind?: "rejected_records";
    source_output_id?: string;
    evaluation?: ModelEvaluationSnapshot | Record<string, unknown>;
    report_type?: "training_evaluation_report" | "monitoring_performance_report";
    report_name?: string;
    report?: TrainingEvaluationReport | Record<string, unknown>;
    score_contract?: Record<string, unknown>;
    row_id_column?: string;
    prediction_column?: string;
    split_evaluation?: Record<string, unknown>;
    model_name?: string;
    algorithm?: string;
    problem_type?: string;
    target_column?: string;
    feature_columns?: string[];
    model_hash?: string;
    metrics?: Record<string, number>;
    training_config?: Record<string, unknown>;
    model_parameters?: ModelArtifact["model_parameters"];
    quality?: {
      status: "not_configured" | "passed" | "issues_detected";
      data_scope: "full";
      checked_row_count?: number;
      rejected_row_count?: number;
      checks: Array<{
        column: string;
        check: string;
        policy: "fail" | "warn" | "reject";
        violation_count: number;
        passed: boolean;
      }>;
      schema_drift: Array<Record<string, unknown>>;
    };
    file_size_bytes?: number;
    preview?: {
      records: Array<Record<string, unknown>>;
      returned_count: number;
      limit: number;
      sampled: boolean;
    };
  }>;
  error_message: string;
  created_by: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type TrainingEvaluationReport = {
  contract_version: "1.0";
  report_type: "training_evaluation_report";
  name: string;
  created_at: string;
  data_scope: {
    mode: "full" | "sample";
    row_count: number;
    sampled: boolean;
    sample_size: number;
    sampling_method: string;
    seed: number | null;
  };
  sections: {
    summary?: Record<string, unknown>;
    metrics?: Record<string, unknown>;
    validation?: Record<string, unknown>;
    search?: Record<string, unknown>;
    feature_engineering?: Record<string, unknown>;
    model_parameters?: Record<string, unknown>;
    explainability?: {
      status?: string;
      reason?: string;
      scope?: Record<string, unknown>;
      permutation_importance?: Array<{ feature: string; mean_importance: number; std?: number }>;
      shap?: {
        status?: string;
        explainer?: string;
        reason?: string;
        values?: Array<{ feature: string; mean_absolute_shap: number }>;
      };
      notes?: string[];
    };
  };
  diagnostics: Array<Record<string, unknown>>;
  warnings: string[];
};

export type PipelineStepRun = {
  id: string;
  owner_id: string;
  pipeline_run_id: string;
  pipeline_step_id: string;
  step_type: string;
  status: string;
  input_row_count: number | null;
  processed_row_count: number | null;
  output_row_count: number | null;
  warnings: string[];
  events: PipelineRunEvent[];
  output_manifest: PipelineRun["output_manifest"];
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
};

export type PipelineRunEvent = {
  timestamp: string;
  level: "info" | "warning" | "error" | string;
  type: string;
  step_id: string;
  message: string;
  details: Record<string, unknown>;
};

export type PipelineRunDetails = {
  run: PipelineRun;
  pipeline_version: {
    id: string;
    version_number: number;
    definition_hash: string;
    status: string;
  };
  resolved_inputs: Array<{
    input_id: string;
    step_id: string;
    logical_id: string;
    version_policy: string;
    dataset_id: string;
    version_number: number;
    dataset_name: string;
  }>;
  steps: PipelineStepRun[];
  outputs: PipelineRun["output_manifest"];
  lineage: Array<{
    artifact_id: string;
    artifact_type: string;
    reference_id: string;
    origin: string;
    lineage: Record<string, unknown>;
  }>;
};

export type PipelineRunOutputPreview = {
  output_id: string;
  pipeline_step_id: string;
  row_count: number;
  limit: number;
  offset: number;
  returned_count: number;
  records: Array<Record<string, unknown>>;
  has_next: boolean;
  has_previous: boolean;
  columns: Array<{ name: string; type: string }>;
};

export type PipelineRunOutputProfile = {
  output_id: string;
  pipeline_step_id: string;
  row_count: number;
  profiled_column_count: number;
  total_column_count: number;
  columns: Array<{
    name: string;
    null_count: number;
    non_null_count: number;
    approx_distinct_count: number;
    top_values: Array<{ value: unknown; count: number; share: number }>;
  }>;
};

export const api = {
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
  listDatasets: () => request<DataAsset[]>("/datasets"),
  listDatasetSummaries: () => request<DataAsset[]>("/datasets?summary=true"),
  listDatasetVersions: (logicalId: string) =>
    request<DataAsset[]>(`/datasets/${datasetRouteId(logicalId)}/versions`),
  listBusinessCases: () => request<BusinessCase[]>("/business-cases"),
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
  updateBusinessCaseDataAttachment: (businessCaseId: string, attachmentId: string, payload: Record<string, unknown>) =>
    request<BusinessCaseDataAttachment>(`/business-cases/${businessCaseId}/data-attachments/${attachmentId}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  deleteBusinessCaseDataAttachment: (businessCaseId: string, attachmentId: string) =>
    request<{ deleted: boolean }>(`/business-cases/${businessCaseId}/data-attachments/${attachmentId}`, {
      method: "DELETE"
    }),
  listPipelines: (businessCaseId?: string) =>
    request<Pipeline[]>(businessCaseId ? `/pipelines?business_case_id=${encodeURIComponent(businessCaseId)}` : "/pipelines"),
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
  listPipelineRuns: (pipelineId: string) =>
    request<PipelineRun[]>(`/pipelines/${pipelineId}/runs`),
  listPipelineRunHistory: (limit = 200) =>
    request<PipelineRun[]>(`/pipelines/runs/history?limit=${limit}`),
  getPipelineRun: (pipelineId: string, runId: string) =>
    request<PipelineRun>(`/pipelines/${pipelineId}/runs/${runId}`),
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
  listModelSummaries: () => request<ModelArtifact[]>("/models?summary=true"),
  promoteModel: (modelId: string, stage: "developed" | "staging" | "production" | "archived") =>
    request<ModelArtifact>(`/models/${encodeURIComponent(modelId)}/stage`, {
      method: "PATCH",
      body: JSON.stringify({ stage })
    }),
  listModelVersions: (logicalId: string) =>
    request<ModelArtifact[]>(`/models/${encodeURIComponent(logicalId)}/versions`),
  listModelServingUsage: (logicalId: string) =>
    request<ModelServingUsage[]>(`/serving/model-families/${encodeURIComponent(logicalId)}/usage`),
  getModel: (modelId: string) =>
    request<ModelArtifact>(`/models/${encodeURIComponent(modelId)}`),
  getModelDataLineage: (modelId: string) =>
    request<DatasetLineageReference[]>(`/models/${encodeURIComponent(modelId)}/data-lineage`),
  listScoringReports: (businessCaseId?: string) =>
    request<ScoringReport[]>(
      businessCaseId
        ? `/scoring-reports?business_case_id=${encodeURIComponent(businessCaseId)}`
        : "/scoring-reports"
    ),
  listScoringReportSummaries: (businessCaseId?: string) =>
    request<ScoringReport[]>(
      businessCaseId
        ? `/scoring-reports?business_case_id=${encodeURIComponent(businessCaseId)}&summary=true`
        : "/scoring-reports?summary=true"
    ),
  listScoringReportVersions: (logicalId: string) =>
    request<ScoringReport[]>(`/scoring-reports/${encodeURIComponent(logicalId)}/versions?summary=true`),
  getScoringReport: (reportId: string) =>
    request<ScoringReport>(`/scoring-reports/${encodeURIComponent(reportId)}`),
  getScoringReportDataLineage: (reportId: string) =>
    request<DatasetLineageReference[]>(`/scoring-reports/${encodeURIComponent(reportId)}/data-lineage`),
  getArtifactDependencies: (referenceId: string, artifactType: string) =>
    request<ArtifactDependency[]>(
      `/business-cases/dependencies/${encodeURIComponent(referenceId)}?artifact_type=${encodeURIComponent(artifactType)}`
    ),
  createDeployment: (payload: Record<string, unknown>) =>
    request<Deployment>("/serving/deployments", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listDeployments: (includeArchived = false) => request<Deployment[]>(`/serving/deployments${includeArchived ? "?include_archived=true" : ""}`),
  listDeploymentRevisions: (deploymentId: string) =>
    request<DeploymentRevision[]>(`/serving/deployments/${encodeURIComponent(deploymentId)}/revisions`),
  createDeploymentRevision: (deploymentId: string, assignments: Array<{ model_id: string; role: DeploymentRole }>, reason: string) =>
    request<DeploymentRevision>(`/serving/deployments/${encodeURIComponent(deploymentId)}/revisions`, {
      method: "POST",
      body: JSON.stringify({ assignments, reason })
    }),
  setDeploymentStatus: (deploymentId: string, status: "running" | "stopped" | "archived", reason: string) =>
    request<Deployment>(`/serving/deployments/${encodeURIComponent(deploymentId)}/status`, {
      method: "POST",
      body: JSON.stringify({ status, reason })
    }),
  rollbackDeployment: (deploymentId: string, revisionId: string, reason: string) =>
    request<DeploymentRevision>(`/serving/deployments/${encodeURIComponent(deploymentId)}/revisions/${encodeURIComponent(revisionId)}/rollback`, {
      method: "POST",
      body: JSON.stringify({ reason })
    }),
  score: (
    deploymentId: string,
    instances: Array<{ record_id?: string; features: Record<string, unknown> }>,
    challengerModelId?: string
  ) =>
    request<ScoreResponse>(
      challengerModelId
        ? `/serving/deployments/${encodeURIComponent(deploymentId)}/challengers/${encodeURIComponent(challengerModelId)}/predictions`
        : `/serving/deployments/${encodeURIComponent(deploymentId)}/predictions`,
      {
        method: "POST",
        body: JSON.stringify({ instances })
      }
    ),
  deploymentInputContract: (deploymentId: string, challengerModelId?: string) => {
    const params = new URLSearchParams();
    if (challengerModelId) params.set("challenger_model_id", challengerModelId);
    const query = params.size ? `?${params}` : "";
    return request<InferenceInputContract>(`/serving/deployments/${encodeURIComponent(deploymentId)}/input-contract${query}`);
  },
  deploymentModelOptions: (deploymentId: string) =>
    request<DeploymentModelOption[]>(`/serving/deployments/${encodeURIComponent(deploymentId)}/model-options`),
  inferenceLog: (deploymentId: string, limit = 50, cursor = "", recordId = "") => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    if (recordId) params.set("record_id", recordId);
    return request<InferencePage>(`/serving/deployments/${encodeURIComponent(deploymentId)}/inference-log?${params}`);
  },
  inferenceLogSummary: (deploymentId: string, limit = 50, cursor = "", recordId = "") => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    if (recordId) params.set("record_id", recordId);
    return request<InferenceSummaryPage>(`/serving/deployments/${encodeURIComponent(deploymentId)}/inference-log-summary?${params}`);
  },
  inferenceDetail: (deploymentId: string, requestId: string) =>
    request<Record<string, unknown>>(`/serving/deployments/${encodeURIComponent(deploymentId)}/inference-log/${encodeURIComponent(requestId)}`),
  createChallengerReplay: (deploymentId: string, challengerModelId: string, maxRequests = 1000) =>
    request<ChallengerReplay>(`/serving/deployments/${encodeURIComponent(deploymentId)}/challenger-replays`, {
      method: "POST",
      body: JSON.stringify({ challenger_model_id: challengerModelId, max_requests: maxRequests })
    }),
  listChallengerReplays: (deploymentId: string) =>
    request<ChallengerReplay[]>(`/serving/deployments/${encodeURIComponent(deploymentId)}/challenger-replays`),
  createOnlineMonitoringRun: (
    deploymentId: string,
    payload: {
      since: string;
      until: string;
      actuals_dataset_id?: string;
      aggregation_granularity?: "none" | "hour" | "day" | "week" | "month";
      actuals_target_column?: string;
      join?: {
        strategy?: "auto" | "prediction_id" | "request_record_id" | "record_id";
        actuals_prediction_id_column?: string;
        actuals_request_id_column?: string;
        actuals_record_id_column?: string;
      };
    }
  ) => request<OnlineMonitoringRun>(`/serving/deployments/${encodeURIComponent(deploymentId)}/monitoring-runs`, {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  listDeploymentMonitoringRuns: (deploymentId: string, limit = 100, includeArchived = false) =>
    request<OnlineMonitoringRun[]>(`/serving/deployments/${encodeURIComponent(deploymentId)}/monitoring-runs?limit=${limit}&include_archived=${includeArchived}`),
  listOnlineMonitoringRuns: (limit = 200, includeArchived = false) =>
    request<OnlineMonitoringRun[]>(`/serving/monitoring-runs?limit=${limit}&include_archived=${includeArchived}`),
  getOnlineMonitoringRun: (runId: string) =>
    request<OnlineMonitoringRun>(`/serving/monitoring-runs/${encodeURIComponent(runId)}`),
  getOnlineMonitoringBucketEvaluations: (runId: string, bucketStarts: string[]) => {
    const params = new URLSearchParams();
    bucketStarts.forEach((value) => params.append("bucket_start", value));
    return request<OnlineMonitoringBucketEvaluation[]>(
      `/serving/monitoring-runs/${encodeURIComponent(runId)}/bucket-evaluations?${params}`
    );
  },
  archiveOnlineMonitoringRun: (runId: string, reason = "Archived from monitoring history") =>
    request<OnlineMonitoringRun>(`/serving/monitoring-runs/${encodeURIComponent(runId)}/archive`, {
      method: "POST",
      body: JSON.stringify({ reason })
    }),
  archiveDeploymentMonitoringHistory: (deploymentId: string, reason = "Archived from monitoring history") =>
    request<{ archived_run_count: number }>(`/serving/deployments/${encodeURIComponent(deploymentId)}/monitoring-runs/archive`, {
      method: "POST",
      body: JSON.stringify({ reason })
    }),
  createApiCredential: (name: string, expiresAt: string | null) =>
    request<Record<string, unknown>>("/auth/api-credentials", {
      method: "POST",
      body: JSON.stringify({ name, expires_at: expiresAt })
    }),
  listDirectoryUsers: () => request<DirectoryUser[]>("/sharing/directory/users"),
  listAdminUsers: () => request<DirectoryUser[]>("/users"),
  updateAdminUser: (userId: string, payload: { roles: string[]; is_active: boolean }) =>
    request<DirectoryUser>(`/users/${encodeURIComponent(userId)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  resetUserPassword: (userId: string, newPassword: string) =>
    request<void>(`/users/${encodeURIComponent(userId)}/reset-password`, { method: "POST", body: JSON.stringify({ new_password: newPassword }) }),
  listGroups: () => request<AccessGroup[]>("/sharing/groups"),
  createGroup: (payload: { name: string; description: string }) =>
    request<AccessGroup>("/sharing/groups", { method: "POST", body: JSON.stringify(payload) }),
  updateGroup: (groupId: string, payload: { name: string; description: string; is_active: boolean }) =>
    request<AccessGroup>(`/sharing/groups/${encodeURIComponent(groupId)}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteGroup: (groupId: string) =>
    request<void>(`/sharing/groups/${encodeURIComponent(groupId)}`, { method: "DELETE" }),
  listGroupMembers: (groupId: string) =>
    request<GroupMembership[]>(`/sharing/groups/${encodeURIComponent(groupId)}/members`),
  upsertGroupMember: (groupId: string, payload: { user_id: string; membership_role: "member" | "manager" }) =>
    request<GroupMembership>(`/sharing/groups/${encodeURIComponent(groupId)}/members`, { method: "PUT", body: JSON.stringify(payload) }),
  removeGroupMember: (groupId: string, userId: string) =>
    request<void>(`/sharing/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(userId)}`, { method: "DELETE" }),
  listBusinessCaseGrants: (businessCaseId: string) =>
    request<BusinessCaseGrant[]>(`/sharing/business-cases/${encodeURIComponent(businessCaseId)}/grants`),
  grantBusinessCase: (businessCaseId: string, payload: Record<string, unknown>) =>
    request<BusinessCaseGrant>(`/sharing/business-cases/${encodeURIComponent(businessCaseId)}/grants`, { method: "PUT", body: JSON.stringify(payload) }),
  revokeBusinessCaseGrant: (businessCaseId: string, grantId: string) =>
    request<void>(`/sharing/business-cases/${encodeURIComponent(businessCaseId)}/grants/${encodeURIComponent(grantId)}`, { method: "DELETE" }),
  listResourceGrants: (kind: string, resourceId: string) =>
    request<ResourceGrant[]>(`/sharing/resources/${encodeURIComponent(kind)}/${encodeURIComponent(resourceId)}/grants`),
  grantResource: (payload: Record<string, unknown>) =>
    request<ResourceGrant>("/sharing/resources/grants", { method: "PUT", body: JSON.stringify(payload) }),
  revokeResourceGrant: (grantId: string) =>
    request<void>(`/sharing/resources/grants/${encodeURIComponent(grantId)}`, { method: "DELETE" }),
  exportResource: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/exports", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
