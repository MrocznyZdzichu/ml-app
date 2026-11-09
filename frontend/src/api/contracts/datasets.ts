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

export type FullDescriptiveProfileResponse = {
  dataset_id: string;
  columns: DatasetColumn[];
  row_count: number;
  profile: Record<string, unknown>;
};

export type DataViewCreatePayload = {
  name: string;
  source_dataset_id: string;
  definition: Record<string, unknown>;
  description?: string;
  tags?: string[];
};
