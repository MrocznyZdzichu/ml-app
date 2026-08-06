import { API_ROOT_URL, request, withQuery } from "./http";
import type { OffsetPage, PageQuery } from "./pagination";
import type { ModelEvaluationSnapshot } from "./contracts/modelEvaluation";
import type { ModelServingUsage } from "./contracts/serving";
import type {
  BusinessCaseAccessRequest,
  BusinessCaseAccessRole,
  BusinessCaseCatalogEntry
} from "./contracts/businessCaseAccess";
import type { CreatedPersonalAccessToken, PersonalAccessToken } from "./contracts/personalAccessToken";
import { servingApi } from "./serving";

export { getAccessToken, setAccessToken } from "./http";
export type { OffsetPage, PageQuery } from "./pagination";
export type { ModelEvaluationMetric, ModelEvaluationSnapshot } from "./contracts/modelEvaluation";
export type {
  BusinessCaseAccessRequest,
  BusinessCaseAccessRole,
  BusinessCaseCatalogEntry
} from "./contracts/businessCaseAccess";
export type { CreatedPersonalAccessToken, PersonalAccessToken } from "./contracts/personalAccessToken";
export type {
  ChallengerReplay,
  Deployment,
  DeploymentModelOption,
  DeploymentRevision,
  DeploymentRole,
  InferenceInputContract,
  InferenceInputField,
  InferencePage,
  InferenceRequest,
  InferenceRequestSummary,
  InferenceSummaryPage,
  ModelServingUsage,
  OnlineMonitoringBucketEvaluation,
  OnlineMonitoringRun,
  ScoreResponse
} from "./contracts/serving";

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
  access_role: BusinessCaseAccessRole;
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
  subject_name: string;
  subject_email: string;
  business_case_name: string;
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
  data_asset_name?: string;
  data_asset_status?: string;
  data_asset_source_type?: string;
  data_asset_logical_id?: string;
  data_asset_version_number?: number;
  data_asset_pipeline_id?: string;
  data_asset_pipeline_template?: string;
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

export type PipelineRunStatus = Pick<
  PipelineRun,
  | "id"
  | "pipeline_id"
  | "pipeline_version_id"
  | "business_case_id"
  | "status"
  | "trigger_type"
  | "is_dry_run"
  | "requested_step_id"
  | "input_row_count"
  | "processed_row_count"
  | "output_row_count"
  | "rejected_row_count"
  | "error_message"
  | "created_at"
  | "started_at"
  | "finished_at"
>;

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
  } = {}) =>
    request<OffsetPage<DataAsset>>(withQuery("/datasets/page", { summary: true, ...query })),
  listDatasetVersions: (logicalId: string) =>
    request<DataAsset[]>(`/datasets/${datasetRouteId(logicalId)}/versions`),
  pageDatasetVersions: (logicalId: string, query: PageQuery = {}) =>
    request<OffsetPage<DataAsset>>(
      withQuery(`/datasets/${datasetRouteId(logicalId)}/versions/page`, query)
    ),
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
  pageScoringReports: (
    query: PageQuery & {
      business_case_id?: string;
      problem_type?: string;
      pipeline_id?: string;
      pipeline_type?: string;
      sort_by?: "report" | "business_case" | "pipeline" | "problem" | "created" | "scope";
      sort_direction?: "asc" | "desc";
    } = {}
  ) => request<OffsetPage<{ latest: ScoringReport; version_count: number }>>(
    withQuery("/scoring-reports/page", query)
  ),
  listScoringReportVersions: (logicalId: string) =>
    request<ScoringReport[]>(`/scoring-reports/${encodeURIComponent(logicalId)}/versions?summary=true`),
  pageScoringReportVersions: (logicalId: string, query: PageQuery = {}) =>
    request<OffsetPage<ScoringReport>>(
      withQuery(`/scoring-reports/${encodeURIComponent(logicalId)}/versions/page`, {
        summary: true,
        ...query
      })
    ),
  getScoringReport: (reportId: string) =>
    request<ScoringReport>(`/scoring-reports/${encodeURIComponent(reportId)}`),
  getScoringReportDataLineage: (reportId: string) =>
    request<DatasetLineageReference[]>(`/scoring-reports/${encodeURIComponent(reportId)}/data-lineage`),
  getArtifactDependencies: (referenceId: string, artifactType: string) =>
    request<ArtifactDependency[]>(
      `/business-cases/dependencies/${encodeURIComponent(referenceId)}?artifact_type=${encodeURIComponent(artifactType)}`
    ),
  ...servingApi,
  createPersonalAccessToken: (name: string, expiresAt: string | null) =>
    request<CreatedPersonalAccessToken>("/auth/api-credentials", {
      method: "POST",
      body: JSON.stringify({ name, expires_at: expiresAt })
    }),
  listPersonalAccessTokens: () => request<PersonalAccessToken[]>("/auth/api-credentials"),
  revokePersonalAccessToken: (tokenId: string) =>
    request<void>(`/auth/api-credentials/${encodeURIComponent(tokenId)}`, { method: "DELETE" }),
  listDirectoryUsers: () => request<DirectoryUser[]>("/sharing/directory/users"),
  pageDirectoryUsers: (query: PageQuery = {}) =>
    request<OffsetPage<DirectoryUser>>(withQuery("/sharing/directory/users/page", query)),
  listAdminUsers: () => request<DirectoryUser[]>("/users"),
  pageAdminUsers: (
    query: PageQuery & { is_active?: boolean; is_technical?: boolean } = {}
  ) => request<OffsetPage<DirectoryUser>>(withQuery("/users/page", query)),
  updateAdminUser: (userId: string, payload: { roles: string[]; is_active: boolean }) =>
    request<DirectoryUser>(`/users/${encodeURIComponent(userId)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  resetUserPassword: (userId: string, newPassword: string) =>
    request<void>(`/users/${encodeURIComponent(userId)}/reset-password`, { method: "POST", body: JSON.stringify({ new_password: newPassword }) }),
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
    request<void>(`/sharing/resources/grants/${encodeURIComponent(grantId)}`, { method: "DELETE" }),
  exportResource: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/exports", {
      method: "POST",
      body: JSON.stringify(payload)
    })
};
