export type FeatureInputRole = "training" | "validation" | "test" | "scoring_input";
export type FeatureTransformType =
  | "impute"
  | "scale_numeric"
  | "encode_categorical"
  | "datetime_features"
  | "numeric_interaction"
  | "math_transform"
  | "sql_expression"
  | "pca";

export type FeatureInput = {
  input_id: string;
  role: FeatureInputRole;
  dataset_id: string;
  version_policy: DatasetVersionPolicy;
};

export type FeatureTransformation = {
  transform_id: string;
  type: FeatureTransformType;
  columns: string[];
  config: Record<string, unknown>;
};

export type FeatureOutput = {
  output_id: string;
  input_id: string;
  dataset_name: string;
  business_case_role: FeatureInputRole;
};

export type FeatureEvaluation = {
  split_strategy: "predefined" | "random" | "stratified" | "group" | "time";
  validation_size: number;
  test_size: number;
  seed: number;
  stratify_column: string;
  group_column: string;
  time_column: string;
  cross_validation: {
    enabled: boolean;
    strategy: "kfold" | "stratified" | "group" | "time";
    folds: number;
    shuffle: boolean;
    seed: number;
  };
};

export type FeatureEngineeringDefinition = {
  contract_version: "1.0";
  mode: "fit_transform" | "transform";
  inputs: FeatureInput[];
  feature_columns: string[];
  target_column: string;
  row_id_column: string;
  group_column: string;
  event_time_column: string;
  transformations: FeatureTransformation[];
  outputs: FeatureOutput[];
  fitted_state_artifact_id: string;
  evaluation: FeatureEvaluation;
};

export function emptyFeatureEngineeringDefinition(): FeatureEngineeringDefinition {
  return {
    contract_version: "1.0",
    mode: "fit_transform",
    inputs: [{ input_id: "training", role: "training", dataset_id: "", version_policy: "latest" }],
    feature_columns: [],
    target_column: "",
    row_id_column: "",
    group_column: "",
    event_time_column: "",
    transformations: [],
    outputs: [{
      output_id: "training_features",
      input_id: "training",
      dataset_name: "Training features",
      business_case_role: "training"
    }],
    fitted_state_artifact_id: "",
    evaluation: defaultEvaluation()
  };
}

export function normalizeFeatureEngineeringDefinition(value: unknown): FeatureEngineeringDefinition {
  const fallback = emptyFeatureEngineeringDefinition();
  if (!value || typeof value !== "object") return fallback;
  const raw = value as Record<string, unknown>;
  return {
    ...fallback,
    mode: raw.mode === "transform" ? "transform" : "fit_transform",
    inputs: Array.isArray(raw.inputs)
      ? (raw.inputs as FeatureInput[]).map((input) => ({
          ...input,
          version_policy: normalizeDatasetVersionPolicy(input.version_policy)
        }))
      : fallback.inputs,
    feature_columns: stringArray(raw.feature_columns),
    target_column: String(raw.target_column ?? ""),
    row_id_column: String(raw.row_id_column ?? ""),
    group_column: String(raw.group_column ?? ""),
    event_time_column: String(raw.event_time_column ?? ""),
    transformations: Array.isArray(raw.transformations)
      ? raw.transformations as FeatureTransformation[]
      : [],
    outputs: Array.isArray(raw.outputs) ? raw.outputs as FeatureOutput[] : fallback.outputs,
    fitted_state_artifact_id: String(raw.fitted_state_artifact_id ?? ""),
    evaluation: normalizeEvaluation(raw.evaluation)
  };
}

function defaultEvaluation(): FeatureEvaluation {
  return {
    split_strategy: "predefined",
    validation_size: 0.1,
    test_size: 0.2,
    seed: 42,
    stratify_column: "",
    group_column: "",
    time_column: "",
    cross_validation: {
      enabled: false,
      strategy: "kfold",
      folds: 5,
      shuffle: true,
      seed: 42
    }
  };
}

function normalizeEvaluation(value: unknown): FeatureEvaluation {
  const fallback = defaultEvaluation();
  if (!value || typeof value !== "object") return fallback;
  const raw = value as Record<string, unknown>;
  const cv = raw.cross_validation && typeof raw.cross_validation === "object"
    ? raw.cross_validation as Record<string, unknown>
    : {};
  const splitStrategy = ["predefined", "random", "stratified", "group", "time"]
    .includes(String(raw.split_strategy))
    ? raw.split_strategy as FeatureEvaluation["split_strategy"]
    : "predefined";
  const cvStrategy = ["kfold", "stratified", "group", "time"].includes(String(cv.strategy))
    ? cv.strategy as FeatureEvaluation["cross_validation"]["strategy"]
    : "kfold";
  return {
    split_strategy: splitStrategy,
    validation_size: Number(raw.validation_size ?? fallback.validation_size),
    test_size: Number(raw.test_size ?? fallback.test_size),
    seed: Number(raw.seed ?? fallback.seed),
    stratify_column: String(raw.stratify_column ?? ""),
    group_column: String(raw.group_column ?? ""),
    time_column: String(raw.time_column ?? ""),
    cross_validation: {
      enabled: Boolean(cv.enabled),
      strategy: cvStrategy,
      folds: Number(cv.folds ?? fallback.cross_validation.folds),
      shuffle: cv.shuffle === undefined ? true : Boolean(cv.shuffle),
      seed: Number(cv.seed ?? fallback.cross_validation.seed)
    }
  };
}

export function defaultFeatureTransform(type: FeatureTransformType, index: number): FeatureTransformation {
  const configs: Record<FeatureTransformType, Record<string, unknown>> = {
    impute: { method: "median", add_indicator: true },
    scale_numeric: { method: "standard", output_suffix: "__scaled" },
    encode_categorical: {
      method: "ordinal",
      min_frequency: 1,
      max_categories: 50,
      handle_unknown: "other",
      drop_original: true
    },
    datetime_features: {
      features: ["year", "month", "day_of_week"],
      cyclical: false,
      drop_original: false
    },
    numeric_interaction: {
      left: "",
      right: "",
      operator: "multiply",
      output_column: "interaction",
      zero_division: "null"
    },
    math_transform: {
      operation: "square",
      output_suffix: "__squared"
    },
    sql_expression: {
      expression: "",
      output_column: "derived_feature",
      output_type: "number"
    },
    pca: {
      n_components: 2,
      output_prefix: "pca_",
      whiten: false,
      drop_original: false
    }
  };
  return {
    transform_id: `${type}_${index}`,
    type,
    columns: [],
    config: configs[type]
  };
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}
import type { DatasetVersionPolicy } from "./dataContractOptions";
import { normalizeDatasetVersionPolicy } from "./dataContractOptions";
