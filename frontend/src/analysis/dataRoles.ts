import type { DataAsset, DatasetPreview } from "../api/client";

export type DataRolesMetadata = {
  dataset_roles: string[];
  entity_id_column: string;
  timestamp_column: string;
  period_column: string;
  target_column: string;
  column_roles: Record<string, string>;
  notes: string;
};

export const emptyRolesMetadata: DataRolesMetadata = {
  dataset_roles: [],
  entity_id_column: "",
  timestamp_column: "",
  period_column: "",
  target_column: "",
  column_roles: {},
  notes: ""
};

export const datasetRoleOptions = [
  { value: "training", label: "Training set" },
  { value: "validation", label: "Validation set" },
  { value: "test", label: "Test set" },
  { value: "holdout", label: "Holdout set" },
  { value: "scoring", label: "Scoring set" },
  { value: "targeted", label: "Contains targets" },
  { value: "reference", label: "Reference/baseline set" },
  { value: "monitoring", label: "Monitoring set" }
] as const;

export const columnRoleOptions = [
  { value: "feature_continuous", label: "Continuous feature" },
  { value: "feature_categorical", label: "Categorical feature" },
  { value: "feature_ordinal", label: "Ordinal feature" },
  { value: "identifier", label: "Identifier" },
  { value: "timestamp", label: "Timestamp" },
  { value: "period_id", label: "Period/batch identifier" },
  { value: "target", label: "Target" },
  { value: "sample_weight", label: "Sample weight" },
  { value: "text", label: "Text feature" },
  { value: "boolean", label: "Boolean feature" },
  { value: "ignored", label: "Ignored" }
] as const;

export function readRolesMetadata(
  dataset: DataAsset | null,
  datasets: DataAsset[] = [],
  columnNames: string[] = []
): DataRolesMetadata {
  const source = asRecord(dataset?.metadata?.data_roles);
  const metadata = {
    dataset_roles: asStringArray(source.dataset_roles),
    entity_id_column: asString(source.entity_id_column),
    timestamp_column: asString(source.timestamp_column),
    period_column: asString(source.period_column),
    target_column: asString(source.target_column),
    column_roles: asStringRecord(source.column_roles),
    notes: asString(source.notes)
  };
  if (Object.keys(metadata.column_roles).length > 0 || !dataset || columnNames.length === 0) {
    return metadata;
  }

  const viewMetadata = asRecord(dataset.metadata.data_view);
  const sourceDatasetId = asString(viewMetadata.source_dataset_id);
  const sourceDataset = datasets.find((item) => item.id === sourceDatasetId) ?? null;
  if (!sourceDataset) {
    return metadata;
  }

  return inheritRolesForColumns(readRolesMetadata(sourceDataset), columnNames);
}

export function normalizeRolesMetadata(metadata: DataRolesMetadata, columnNames: string[]) {
  const columnSet = new Set(columnNames);
  const columnRoles = Object.fromEntries(
    Object.entries(metadata.column_roles).filter(([column]) => columnSet.has(column))
  );
  return {
    ...metadata,
    column_roles: columnRoles
  };
}

export function inheritRolesForColumns(metadata: DataRolesMetadata, columnNames: string[]): DataRolesMetadata {
  const columnSet = new Set(columnNames);
  return {
    dataset_roles: metadata.dataset_roles,
    entity_id_column: columnSet.has(metadata.entity_id_column) ? metadata.entity_id_column : "",
    timestamp_column: columnSet.has(metadata.timestamp_column) ? metadata.timestamp_column : "",
    period_column: columnSet.has(metadata.period_column) ? metadata.period_column : "",
    target_column: columnSet.has(metadata.target_column) ? metadata.target_column : "",
    column_roles: Object.fromEntries(
      Object.entries(metadata.column_roles).filter(([column]) => columnSet.has(column))
    ),
    notes: metadata.notes
  };
}

export function defaultColumnRole(type: DatasetPreview["columns"][number]["type"]) {
  if (type === "number") {
    return "feature_continuous";
  }
  if (type === "date") {
    return "timestamp";
  }
  if (type === "boolean") {
    return "boolean";
  }
  if (type === "text") {
    return "feature_categorical";
  }
  return "ignored";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function asStringArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function asStringRecord(value: unknown) {
  const record = asRecord(value);
  return Object.fromEntries(
    Object.entries(record).filter((entry): entry is [string, string] => typeof entry[1] === "string")
  );
}
