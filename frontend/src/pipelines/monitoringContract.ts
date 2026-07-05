export type MonitoringDefinition = {
  contract_version: "2.0";
  row_id_column: string;
  target_column: string;
  prediction_column: string;
  problem_type: "binary_classification" | "multiclass_classification" | "regression";
  report_name: string;
};

export function emptyMonitoringDefinition(): MonitoringDefinition {
  return {
    contract_version: "2.0",
    row_id_column: "row_id",
    target_column: "target",
    prediction_column: "prediction",
    problem_type: "binary_classification",
    report_name: "Model performance monitoring"
  };
}

export function normalizeMonitoringDefinition(value: unknown): MonitoringDefinition {
  const defaults = emptyMonitoringDefinition();
  if (!value || typeof value !== "object") return defaults;
  const raw = value as Record<string, unknown>;
  const problemType = raw.problem_type;
  return {
    contract_version: "2.0",
    row_id_column: String(raw.row_id_column ?? raw.prediction_key_column ?? "row_id"),
    target_column: String(raw.target_column ?? "target"),
    prediction_column: String(raw.prediction_column ?? "prediction"),
    problem_type: problemType === "regression" || problemType === "multiclass_classification"
      ? problemType
      : "binary_classification",
    report_name: String(raw.report_name ?? defaults.report_name)
  };
}
