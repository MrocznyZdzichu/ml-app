import type { BusinessCase, BusinessCaseDataAttachment, DatasetColumn } from "../api/client";
import type { FeatureEngineeringDefinition } from "./featureEngineeringContract";

export type TrainingDefinition = {
  contract_version: "1.0";
  problem_type: "binary_classification" | "multiclass_classification" | "regression";
  algorithm: TrainingAlgorithm;
  target_column: string;
  feature_columns: string[];
  model_name: string;
  epochs: number;
  early_stopping: boolean;
  early_stopping_patience: number;
  early_stopping_min_delta: number;
  batch_size: number;
  random_seed: number;
  parameters: Record<string, unknown>;
};

export type TrainingAlgorithm =
  | "sgd_classifier"
  | "passive_aggressive_classifier"
  | "perceptron_classifier"
  | "sgd_regressor"
  | "passive_aggressive_regressor";

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
  row_id_column: string;
  target_column: string;
  prediction_column: string;
  dataset_name: string;
  batch_size: number;
};

export const emptyTrainingDefinition = (): TrainingDefinition => ({
  contract_version: "1.0",
  problem_type: "binary_classification",
  algorithm: "sgd_classifier",
  target_column: "",
  feature_columns: [],
  model_name: "Trained model",
  epochs: 50,
  early_stopping: false,
  early_stopping_patience: 5,
  early_stopping_min_delta: 0.0001,
  batch_size: 10000,
  random_seed: 42,
  parameters: defaultTrainingParameters("sgd_classifier")
});

export const emptyScoringDefinition = (): ScoringDefinition => ({
  contract_version: "1.0",
  row_id_column: "",
  target_column: "",
  prediction_column: "prediction",
  dataset_name: "Test predictions",
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
    has_validation: hasValidation
  };
}

export function trainingWithDefaults(
  defaults: ModelingDefaults,
  current: TrainingDefinition = emptyTrainingDefinition()
): TrainingDefinition {
  const unconfigured = !current.target_column && current.feature_columns.length === 0;
  const problem_type = unconfigured ? defaults.problem_type : current.problem_type;
  const allowedAlgorithms = problem_type === "regression"
    ? regressionAlgorithms
    : classificationAlgorithms;
  const algorithm = allowedAlgorithms.includes(current.algorithm)
    ? current.algorithm
    : allowedAlgorithms[0];
  return {
    ...current,
    problem_type,
    algorithm,
    target_column: current.target_column || defaults.target_column,
    feature_columns: current.feature_columns.length ? current.feature_columns : defaults.feature_columns,
    epochs: unconfigured && current.epochs === 5 ? 50 : current.epochs,
    early_stopping: unconfigured && defaults.has_validation
      ? true
      : current.early_stopping && defaults.has_validation,
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
    target_column: current.target_column || defaults.target_column,
    dataset_name: current.dataset_name === "Test predictions"
      ? `${defaults.model_name.replace(/ model$/, "")} test predictions`
      : current.dataset_name
  };
}

export function normalizeTrainingDefinition(value: unknown): TrainingDefinition {
  const raw = record(value);
  const problem = raw.problem_type === "regression"
    ? "regression"
    : raw.problem_type === "multiclass_classification"
      ? "multiclass_classification"
      : "binary_classification";
  const allowedAlgorithms = problem === "regression" ? regressionAlgorithms : classificationAlgorithms;
  const requestedAlgorithm = String(raw.algorithm ?? "");
  const algorithm = allowedAlgorithms.includes(requestedAlgorithm as TrainingAlgorithm)
    ? requestedAlgorithm as TrainingAlgorithm
    : allowedAlgorithms[0];
  return {
    contract_version: "1.0",
    problem_type: problem,
    algorithm,
    target_column: String(raw.target_column ?? ""),
    feature_columns: Array.isArray(raw.feature_columns) ? raw.feature_columns.map(String) : [],
    model_name: String(raw.model_name ?? "Trained model"),
    epochs: boundedNumber(raw.epochs, 50, 1, 100),
    early_stopping: raw.early_stopping === true,
    early_stopping_patience: boundedNumber(raw.early_stopping_patience, 5, 1, 50),
    early_stopping_min_delta: boundedNumber(raw.early_stopping_min_delta, 0.0001, 0, 1),
    batch_size: boundedNumber(raw.batch_size, 10000, 100, 100000),
    random_seed: boundedNumber(raw.random_seed, 42, -2147483648, 2147483647),
    parameters: Object.keys(record(raw.parameters)).length
      ? record(raw.parameters)
      : defaultTrainingParameters(algorithm)
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
  return {
    alpha: 0.0001,
    penalty: "l2",
    learning_rate: "optimal",
    fit_intercept: true
  };
}

export function normalizeScoringDefinition(value: unknown): ScoringDefinition {
  const raw = record(value);
  return {
    contract_version: "1.0",
    row_id_column: String(raw.row_id_column ?? ""),
    target_column: String(raw.target_column ?? ""),
    prediction_column: String(raw.prediction_column ?? "prediction"),
    dataset_name: String(raw.dataset_name ?? "Test predictions"),
    batch_size: boundedNumber(raw.batch_size, 10000, 100, 100000)
  };
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
