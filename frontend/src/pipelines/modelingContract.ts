import type { BusinessCase, BusinessCaseDataAttachment, DatasetColumn } from "../api/client";
import type { FeatureEngineeringDefinition } from "./featureEngineeringContract";

export type TrainingDefinition = {
  contract_version: "1.0";
  problem_type: "binary_classification" | "multiclass_classification" | "regression";
  algorithm: TrainingAlgorithm;
  target_column: string;
  feature_columns: string[];
  feature_selection: "upstream_contract" | "explicit";
  model_name: string;
  epochs: number;
  early_stopping: boolean;
  early_stopping_patience: number;
  early_stopping_min_delta: number;
  batch_size: number;
  random_seed: number;
  parameters: Record<string, unknown>;
  optimization: TrainingOptimization;
  resource_limits: TrainingResourceLimits;
  auto_feature_engineering: AutoFeatureEngineeringDefinition;
};

export type AutoFeatureEngineeringDefinition = {
  enabled: boolean;
  strategy: "balanced";
  joint_search_enabled: boolean;
  max_recipe_candidates: number;
  row_id_column: string;
  excluded_columns: string[];
  validation_size: number;
  numeric_scaling: "none" | "standard" | "minmax" | "robust";
  add_missing_indicators: boolean;
  include_datetime_features: boolean;
  detect_identifier_columns: boolean;
  min_category_frequency: number;
  max_one_hot_categories: number;
  max_frequency_categories: number;
};

export type TrainingAlgorithm = string;

export type TrainingOptimization = {
  mode: "single" | "grid_search" | "random_search" | "optuna" | "automl";
  validation_strategy: "auto" | "holdout" | "cross_validation";
  primary_metric: string;
  cv_folds: number;
  max_trials: number;
  timeout_seconds: number;
  candidate_algorithms: string[];
  search_space: Record<string, Record<string, unknown>>;
};

export type TrainingResourceLimits = {
  max_memory_mb: number;
  max_parallel_jobs: number;
};

export type TrainingParameterSpec = {
  id: string;
  label: string;
  kind: "integer" | "number" | "boolean" | "select" | "integer_list";
  default: unknown;
  description: string;
  minimum: number | null;
  maximum: number | null;
  step: number | null;
  options: unknown[];
  nullable: boolean;
  search: Record<string, unknown> | null;
  active_when: Record<string, unknown[]> | null;
};

export type TrainingAlgorithmSpec = {
  id: string;
  label: string;
  family: string;
  problem_types: TrainingDefinition["problem_type"][];
  description: string;
  execution_mode: "incremental" | "in_memory";
  scale_profile: "streaming" | "large" | "medium" | "small";
  dependency: string;
  available: boolean;
  supports_probability: boolean;
  supports_early_stopping: boolean;
  automl_default: boolean;
  feature_capabilities: {
    profile: "scaled_dense" | "tree_unscaled" | "non_negative";
    numeric_scaling: "standard" | "none" | "minmax";
    requires_numeric_matrix: boolean;
    requires_non_negative_features: boolean;
    supports_native_categorical: boolean;
    categorical_strategy: string;
  };
  notes: string[];
  parameters: TrainingParameterSpec[];
};

export type TrainingCatalog = {
  contract_version: "1.0";
  algorithm_count: number;
  algorithms: TrainingAlgorithmSpec[];
  optimization_modes: Array<{ id: TrainingOptimization["mode"]; label: string; description: string }>;
  metrics: Record<TrainingDefinition["problem_type"], Array<{
    id: string;
    label: string;
    direction: "maximize" | "minimize";
  }>>;
};

export const classificationAlgorithms: TrainingAlgorithm[] = [
  "sgd_classifier",
  "passive_aggressive_classifier",
  "perceptron_classifier"
];

export const regressionAlgorithms: TrainingAlgorithm[] = [
  "sgd_regressor",
  "passive_aggressive_regressor"
];

export type ScoringDefinition = {
  contract_version: "1.0";
  purpose: "test" | "batch";
  model_artifact_id: string;
  row_id_column: string;
  target_column: string;
  prediction_column: string;
  dataset_name: string;
  report_name: string;
  batch_size: number;
};

export const emptyTrainingDefinition = (): TrainingDefinition => ({
  contract_version: "1.0",
  problem_type: "binary_classification",
  algorithm: "sgd_classifier",
  target_column: "",
  feature_columns: [],
  feature_selection: "upstream_contract",
  model_name: "Trained model",
  epochs: 50,
  early_stopping: false,
  early_stopping_patience: 5,
  early_stopping_min_delta: 0.0001,
  batch_size: 10000,
  random_seed: 42,
  parameters: defaultTrainingParameters("sgd_classifier"),
  optimization: {
    mode: "single",
    validation_strategy: "auto",
    primary_metric: "auto",
    cv_folds: 5,
    max_trials: 30,
    timeout_seconds: 3600,
    candidate_algorithms: [],
    search_space: {}
  },
  resource_limits: {
    max_memory_mb: 2048,
    max_parallel_jobs: 1
  },
  auto_feature_engineering: {
    enabled: false,
    strategy: "balanced",
    joint_search_enabled: true,
    max_recipe_candidates: 3,
    row_id_column: "",
    excluded_columns: [],
    validation_size: 0.2,
    numeric_scaling: "standard",
    add_missing_indicators: true,
    include_datetime_features: true,
    detect_identifier_columns: true,
    min_category_frequency: 2,
    max_one_hot_categories: 32,
    max_frequency_categories: 500
  }
});

export const emptyScoringDefinition = (): ScoringDefinition => ({
  contract_version: "1.0",
  purpose: "test",
  model_artifact_id: "",
  row_id_column: "",
  target_column: "",
  prediction_column: "prediction",
  dataset_name: "Test predictions",
  report_name: "Test scoring report",
  batch_size: 10000
});

export type ModelingDefaults = {
  problem_type: TrainingDefinition["problem_type"];
  target_column: string;
  row_id_column: string;
  feature_columns: string[];
  available_columns: string[];
  model_name: string;
  has_validation: boolean;
  has_fitted_transformations: boolean;
  has_cv_plan: boolean;
  cv_folds: number;
};

export function deriveModelingDefaults({
  businessCase,
  attachments,
  featureDefinition,
  dagColumns = [],
  hasValidation = false,
  pipelineName
}: {
  businessCase?: BusinessCase;
  attachments: BusinessCaseDataAttachment[];
  featureDefinition?: FeatureEngineeringDefinition;
  dagColumns?: DatasetColumn[];
  hasValidation?: boolean;
  pipelineName: string;
}): ModelingDefaults {
  const attachmentTarget = attachments.find((item) => item.target_column)?.target_column ?? "";
  const attachmentRowId = attachments.find((item) => item.primary_key_column)?.primary_key_column ?? "";
  const target_column = featureDefinition?.target_column
    || businessCase?.target_column
    || attachmentTarget;
  const row_id_column = featureDefinition?.row_id_column || attachmentRowId;
  const configuredFeatures = featureDefinition?.feature_columns ?? [];
  const feature_columns = (configuredFeatures.length
    ? configuredFeatures
    : dagColumns.filter((column) => column.type === "number").map((column) => column.name))
    .filter((name) => name !== target_column && name !== row_id_column);
  const available_columns = Array.from(new Set([
    ...dagColumns.map((column) => column.name),
    ...feature_columns,
    ...(target_column ? [target_column] : []),
    ...(row_id_column ? [row_id_column] : []),
    ...(featureDefinition?.group_column ? [featureDefinition.group_column] : []),
    ...(featureDefinition?.event_time_column ? [featureDefinition.event_time_column] : [])
  ]));
  const problem_type: TrainingDefinition["problem_type"] =
    businessCase?.problem_type === "regression"
      ? "regression"
      : businessCase?.problem_type === "multiclass_classification"
        ? "multiclass_classification"
        : "binary_classification";
  const baseName = businessCase?.name || pipelineName || "Trained model";
  return {
    problem_type,
    target_column,
    row_id_column,
    feature_columns,
    available_columns,
    model_name: `${baseName} model`,
    has_validation: hasValidation,
    has_fitted_transformations: Boolean(featureDefinition?.transformations.length),
    has_cv_plan: Boolean(featureDefinition?.evaluation.cross_validation.enabled),
    cv_folds: featureDefinition?.evaluation.cross_validation.folds ?? 5
  };
}

export function trainingWithDefaults(
  defaults: ModelingDefaults,
  current: TrainingDefinition = emptyTrainingDefinition()
): TrainingDefinition {
  const unconfigured = !current.target_column && current.feature_columns.length === 0;
  const problem_type = unconfigured ? defaults.problem_type : current.problem_type;
  const algorithm = current.algorithm || (problem_type === "regression"
    ? regressionAlgorithms[0]
    : classificationAlgorithms[0]);
  return {
    ...current,
    problem_type,
    algorithm,
    target_column: current.target_column || defaults.target_column,
    feature_columns: current.feature_columns.length ? current.feature_columns : defaults.feature_columns,
    epochs: unconfigured && current.epochs === 5 ? 50 : current.epochs,
    // Step-level early stopping is a single-estimator control. AutoML and
    // other search modes evaluate multiple candidates and must not inherit it
    // merely because an FE validation split exists.
    early_stopping: unconfigured && defaults.has_validation && current.optimization.mode === "single"
      ? true
      : current.early_stopping
        && defaults.has_validation
        && current.optimization.mode === "single",
    parameters: current.parameters && Object.keys(current.parameters).length
      ? current.parameters
      : defaultTrainingParameters(algorithm),
    model_name: !current.model_name || current.model_name === "Trained model"
      ? defaults.model_name
      : current.model_name
  };
}

export function scoringWithDefaults(
  defaults: ModelingDefaults,
  current: ScoringDefinition = emptyScoringDefinition()
): ScoringDefinition {
  return {
    ...current,
    row_id_column: current.row_id_column || defaults.row_id_column,
    target_column: current.purpose === "batch"
      ? ""
      : current.target_column || defaults.target_column,
    dataset_name: current.dataset_name === "Test predictions"
      ? `${defaults.model_name.replace(/ model$/, "")} test predictions`
      : current.dataset_name,
    report_name: current.report_name === "Test scoring report"
      ? `${defaults.model_name.replace(/ model$/, "")} test scoring report`
      : current.report_name
  };
}

export function normalizeTrainingDefinition(value: unknown): TrainingDefinition {
  const raw = record(value);
  const problem = raw.problem_type === "regression"
    ? "regression"
    : raw.problem_type === "multiclass_classification"
      ? "multiclass_classification"
      : "binary_classification";
  const requestedAlgorithm = String(raw.algorithm ?? "");
  const algorithm = requestedAlgorithm || (
    problem === "regression" ? regressionAlgorithms[0] : classificationAlgorithms[0]
  );
  const optimization = normalizeOptimization(raw.optimization);
  return {
    contract_version: "1.0",
    problem_type: problem,
    algorithm,
    target_column: String(raw.target_column ?? ""),
    feature_columns: Array.isArray(raw.feature_columns) ? raw.feature_columns.map(String) : [],
    feature_selection: raw.feature_selection === "explicit" ? "explicit" : "upstream_contract",
    model_name: String(raw.model_name ?? "Trained model"),
    epochs: boundedNumber(raw.epochs, 50, 1, 100),
    // Recover older AutoML/search drafts that stored this single-estimator
    // setting. It is not applicable while candidates are being optimized.
    early_stopping: raw.early_stopping === true && optimization.mode === "single",
    early_stopping_patience: boundedNumber(raw.early_stopping_patience, 5, 1, 50),
    early_stopping_min_delta: boundedNumber(raw.early_stopping_min_delta, 0.0001, 0, 1),
    batch_size: boundedNumber(raw.batch_size, 10000, 100, 100000),
    random_seed: boundedNumber(raw.random_seed, 42, -2147483648, 2147483647),
    parameters: Object.keys(record(raw.parameters)).length
      ? record(raw.parameters)
      : defaultTrainingParameters(algorithm),
    optimization,
    resource_limits: normalizeResourceLimits(raw.resource_limits),
    auto_feature_engineering: normalizeAutoFeatureEngineering(raw.auto_feature_engineering)
  };
}

function normalizeAutoFeatureEngineering(value: unknown): AutoFeatureEngineeringDefinition {
  const raw = record(value);
  const scaling = ["none", "standard", "minmax", "robust"].includes(String(raw.numeric_scaling))
    ? raw.numeric_scaling as AutoFeatureEngineeringDefinition["numeric_scaling"]
    : "standard";
  const oneHot = boundedNumber(raw.max_one_hot_categories, 32, 2, 500);
  return {
    enabled: raw.enabled === true,
    strategy: "balanced",
    joint_search_enabled: raw.joint_search_enabled !== false,
    max_recipe_candidates: boundedNumber(raw.max_recipe_candidates, 3, 1, 3),
    row_id_column: String(raw.row_id_column ?? ""),
    excluded_columns: Array.isArray(raw.excluded_columns) ? raw.excluded_columns.map(String) : [],
    validation_size: boundedNumber(raw.validation_size, 0.2, 0.01, 0.49),
    numeric_scaling: scaling,
    add_missing_indicators: raw.add_missing_indicators !== false,
    include_datetime_features: raw.include_datetime_features !== false,
    detect_identifier_columns: raw.detect_identifier_columns !== false,
    min_category_frequency: boundedNumber(raw.min_category_frequency, 2, 1, 1000000),
    max_one_hot_categories: oneHot,
    max_frequency_categories: Math.max(
      oneHot,
      boundedNumber(raw.max_frequency_categories, 500, 2, 500)
    )
  };
}

function normalizeOptimization(value: unknown): TrainingOptimization {
  const raw = record(value);
  const mode = ["grid_search", "random_search", "optuna", "automl"].includes(String(raw.mode))
    ? raw.mode as TrainingOptimization["mode"]
    : "single";
  const validation = ["holdout", "cross_validation"].includes(String(raw.validation_strategy))
    ? raw.validation_strategy as TrainingOptimization["validation_strategy"]
    : "auto";
  return {
    mode,
    validation_strategy: validation,
    primary_metric: String(raw.primary_metric ?? "auto"),
    cv_folds: boundedNumber(raw.cv_folds, 5, 2, 20),
    max_trials: boundedNumber(raw.max_trials, 30, 1, mode === "grid_search" ? 100000 : 1000),
    timeout_seconds: boundedNumber(raw.timeout_seconds, 3600, 10, 604800),
    candidate_algorithms: Array.isArray(raw.candidate_algorithms)
      ? raw.candidate_algorithms.map(String)
      : [],
    search_space: normalizeSearchSpace(raw.search_space)
  };
}

function normalizeSearchSpace(value: unknown): Record<string, Record<string, unknown>> {
  const raw = record(value);
  return Object.fromEntries(Object.entries(raw)
    .filter(([key, spec]) => key && spec && typeof spec === "object" && !Array.isArray(spec))
    .map(([key, spec]) => [key, record(spec)]));
}

function normalizeResourceLimits(value: unknown): TrainingResourceLimits {
  const raw = record(value);
  return {
    max_memory_mb: boundedNumber(raw.max_memory_mb, 2048, 128, 262144),
    max_parallel_jobs: boundedNumber(raw.max_parallel_jobs, 1, 1, 64)
  };
}

export function defaultTrainingParameters(algorithm: TrainingAlgorithm): Record<string, unknown> {
  if (algorithm === "passive_aggressive_classifier") {
    return { C: 1, loss: "hinge", average: false, fit_intercept: true };
  }
  if (algorithm === "passive_aggressive_regressor") {
    return {
      C: 1,
      epsilon: 0.1,
      loss: "epsilon_insensitive",
      average: false,
      fit_intercept: true
    };
  }
  if (algorithm === "perceptron_classifier") {
    return { alpha: 0.0001, penalty: null, eta0: 1, fit_intercept: true };
  }
  if (algorithm === "sgd_classifier" || algorithm === "sgd_regressor") {
    return {
      alpha: 0.0001,
      penalty: "l2",
      learning_rate: "optimal",
      fit_intercept: true
    };
  }
  return {};
}

export function normalizeScoringDefinition(value: unknown): ScoringDefinition {
  const raw = record(value);
  return {
    contract_version: "1.0",
    purpose: raw.purpose === "batch" ? "batch" : "test",
    model_artifact_id: String(raw.model_artifact_id ?? ""),
    row_id_column: String(raw.row_id_column ?? ""),
    target_column: String(raw.target_column ?? ""),
    prediction_column: String(raw.prediction_column ?? "prediction"),
    dataset_name: String(raw.dataset_name ?? "Test predictions"),
    report_name: String(raw.report_name ?? "Test scoring report"),
    batch_size: boundedNumber(raw.batch_size, 10000, 100, 100000)
  };
}

export function validateTrainingConfiguration(definition: TrainingDefinition): string[] {
  const issues: string[] = [];
  const featureColumns = definition.feature_columns.map((item) => item.trim()).filter(Boolean);
  const uniqueFeatures = new Set(featureColumns);
  if (!definition.model_name.trim()) issues.push("Training model name is required.");
  if (!definition.target_column.trim()) issues.push("Training target column is required before publish or dry-run.");
  if (definition.target_column && uniqueFeatures.has(definition.target_column)) {
    issues.push("Training target column cannot also be selected as a model feature.");
  }
  if (featureColumns.length !== definition.feature_columns.length) {
    issues.push("Training feature list contains an empty column name.");
  }
  if (uniqueFeatures.size !== featureColumns.length) {
    issues.push("Training feature columns must be unique.");
  }
  if (!featureColumns.length && !definition.auto_feature_engineering.enabled) {
    issues.push("Training requires at least one model feature before publish or dry-run.");
  }
  if (definition.auto_feature_engineering.enabled && definition.optimization.mode !== "automl") {
    issues.push("AutoFE is available only with AutoML optimization.");
  }
  if (definition.auto_feature_engineering.enabled
    && definition.optimization.validation_strategy === "cross_validation") {
    issues.push("AutoFE v1 requires holdout validation until fold-local preprocessing is available.");
  }
  if (definition.early_stopping && definition.optimization.mode !== "single") {
    issues.push("Training early stopping cannot be combined with hyperparameter optimization.");
  }
  if (definition.optimization.mode !== "single" && definition.optimization.mode !== "automl") {
    for (const [parameterId, search] of Object.entries(definition.optimization.search_space)) {
      const kind = String(search.kind ?? "");
      if (kind === "categorical") {
        const values = Array.isArray(search.values)
          ? search.values.filter((value) => !(typeof value === "string" && !value.trim()))
          : [];
        if (!values.length) issues.push(`Search space for '${parameterId}' must contain at least one value.`);
      } else if (kind === "int" || kind === "float") {
        const low = Number(search.low);
        const high = Number(search.high);
        const points = Number(search.points ?? 3);
        const step = search.step == null ? null : Number(search.step);
        if (!Number.isFinite(low) || !Number.isFinite(high)) {
          issues.push(`Search space for '${parameterId}' requires numeric From and To values.`);
        }
        if (Number.isFinite(low) && Number.isFinite(high) && low > high) {
          issues.push(`Search space for '${parameterId}' has From greater than To.`);
        }
        if (!Number.isFinite(points) || points < 1) {
          issues.push(`Search space for '${parameterId}' requires at least one value.`);
        }
        if (search.log === true && (low <= 0 || high <= 0)) {
          issues.push(`Search space for '${parameterId}' uses logarithmic scale, so From and To must be greater than zero.`);
        }
        if (step != null && (!Number.isFinite(step) || step <= 0)) {
          issues.push(`Search space for '${parameterId}' uses a step that must be greater than zero.`);
        }
        if (step != null && search.log === true) {
          issues.push(`Search space for '${parameterId}' cannot combine a step with logarithmic scale.`);
        }
      } else {
        issues.push(`Search space for '${parameterId}' has unsupported mode '${kind || "blank"}'.`);
      }
    }
  }
  return issues;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function boundedNumber(value: unknown, fallback: number, minimum: number, maximum: number) {
  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? Math.min(maximum, Math.max(minimum, numeric))
    : fallback;
}
