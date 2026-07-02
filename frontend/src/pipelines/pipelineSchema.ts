import type { DataAsset, DatasetColumn } from "../api/client";
import type { PipelineDefinition, PipelineStepDefinition } from "./pipelineContract";

export function datasetColumns(
  dataset: DataAsset | undefined,
  cache: Record<string, DatasetColumn[]>
): DatasetColumn[] {
  if (!dataset) return [];
  if (cache[dataset.id]) return cache[dataset.id];
  const stored = dataset.metadata.source_schema;
  if (!Array.isArray(stored)) return [];
  return stored.flatMap((column) => {
    if (!column || typeof column !== "object" || !("name" in column)) return [];
    const value = column as Record<string, unknown>;
    const storageType = String(value.type ?? "VARCHAR");
    return [{
      name: String(value.name),
      type: normalizeColumnType(storageType),
      storage_type: concreteStorageType(storageType)
    }];
  });
}

export function inferPipelineOutputColumns(
  definition: PipelineDefinition | undefined,
  datasets: DataAsset[],
  cache: Record<string, DatasetColumn[]>
): DatasetColumn[] {
  if (!definition) return [];
  const output = definition.outputs[0];
  if (!output) return [];
  return columnsForNode(definition, datasets, cache, output.input.node_id);
}

export function inputDatasetIds(definition: PipelineDefinition | undefined): string[] {
  return definition?.inputs.map((input) => input.dataset_id).filter(Boolean) ?? [];
}

function columnsForNode(
  definition: PipelineDefinition,
  datasets: DataAsset[],
  cache: Record<string, DatasetColumn[]>,
  nodeId: string,
  visited = new Set<string>()
): DatasetColumn[] {
  if (visited.has(nodeId)) return [];
  visited.add(nodeId);
  const input = definition.inputs.find((item) => item.input_id === nodeId);
  if (input) {
    return datasetColumns(datasets.find((item) => item.id === input.dataset_id), cache);
  }
  const step = definition.steps.find((item) => item.step_id === nodeId);
  if (!step) return [];
  const inputColumns = step.inputs.map((item) =>
    columnsForNode(definition, datasets, cache, item.source.node_id, new Set(visited))
  );
  return transformColumns(step, mergeColumns(inputColumns.flat()), inputColumns);
}

function transformColumns(
  step: PipelineStepDefinition,
  upstream: DatasetColumn[],
  inputColumns: DatasetColumn[][]
): DatasetColumn[] {
  if (step.type === "select_columns") {
    const selected = new Set(stringList(step.config.columns));
    return upstream.filter((column) => selected.has(column.name));
  }
  if (step.type === "rename_columns") {
    const renames = recordValue(step.config.renames);
    return upstream.map((column) => ({ ...column, name: String(renames[column.name] ?? column.name) }));
  }
  if (step.type === "cast_columns") {
    const casts = recordValue(step.config.casts);
    return upstream.map((column) => casts[column.name]
      ? {
          ...column,
          type: frontendTypeForCast(String(casts[column.name])),
          storage_type: String(casts[column.name]).toUpperCase()
        }
      : column);
  }
  if (step.type === "derive_column") {
    const expression = recordValue(step.config.expression);
    const left = recordValue(expression.left);
    const source = upstream.find((column) => column.name === left.column);
    return mergeColumns([...upstream, {
      name: String(step.config.name ?? "new_column"),
      type: expression.operator === "concat" ? "text" : source?.type ?? "number",
      storage_type: expression.operator === "concat"
        ? "VARCHAR"
        : source?.storage_type ?? "DOUBLE"
    }]);
  }
  if (step.type === "add_identifier") {
    return mergeColumns([...upstream, {
      name: String(step.config.output_column ?? "row_id"),
      type: step.config.mode === "sequence" ? "number" : "text",
      storage_type: step.config.mode === "sequence" ? "BIGINT" : "VARCHAR"
    }]);
  }
  if (step.type === "aggregate") {
    const groups = stringList(step.config.group_by).map((name) =>
      upstream.find((column) => column.name === name) ?? { name, type: "text" as const }
    );
    const aggregations = recordList(step.config.aggregations).map((item) => ({
      name: String(item.alias ?? "metric"),
      type: "number" as const,
      storage_type: "DOUBLE"
    }));
    return mergeColumns([...groups, ...aggregations]);
  }
  if (step.type === "map_categories" && step.config.output_column) {
    return mergeColumns([...upstream, {
      name: String(step.config.output_column),
      type: "text",
      storage_type: "VARCHAR"
    }]);
  }
  if (step.type === "map_categories") {
    const sourceColumn = String(step.config.column ?? "");
    return upstream.map((column) =>
      column.name === sourceColumn
        ? { ...column, type: "text", storage_type: "VARCHAR" }
        : column
    );
  }
  if (step.type === "impute_missing") {
    const indicators = recordList(step.config.rules)
      .filter((rule) => rule.add_indicator === true)
      .map((rule) => ({
        name: `${String(rule.column)}__was_missing`,
        type: "boolean" as const,
        storage_type: "BOOLEAN"
      }));
    return mergeColumns([...upstream, ...indicators]);
  }
  if (step.type === "join") {
    const left = inputColumns[0] ?? [];
    const right = inputColumns[1] ?? [];
    const rightKeys = new Set(recordList(step.config.keys).map((key) => String(key.right)));
    const leftNames = new Set(left.map((column) => column.name));
    const suffix = String(step.config.right_suffix ?? "_right");
    return [
      ...left,
      ...right
        .filter((column) => !rightKeys.has(column.name))
        .map((column) => ({
          ...column,
          name: leftNames.has(column.name) ? `${column.name}${suffix}` : column.name
        }))
    ];
  }
  if (step.type === "custom_sql") return [];
  return upstream;
}

function normalizeColumnType(value: string): DatasetColumn["type"] {
  const normalized = value.toLowerCase();
  if (["number", "integer", "bigint", "double", "float", "decimal", "smallint", "tinyint"]
    .some((item) => normalized.includes(item))) return "number";
  if (normalized.includes("bool")) return "boolean";
  if (normalized.includes("date") || normalized.includes("time")) return "date";
  if (["text", "varchar", "string"].some((item) => normalized.includes(item))) return "text";
  return "text";
}

function concreteStorageType(value: string): string | undefined {
  const normalized = value.trim().toLowerCase();
  if (["number", "text", "date", "boolean", "empty", "mixed", "unsupported"].includes(normalized)) {
    return undefined;
  }
  return value.trim().toUpperCase() || undefined;
}

function frontendTypeForCast(type: string): DatasetColumn["type"] {
  const upper = type.toUpperCase();
  if (upper.includes("BOOL")) return "boolean";
  if (upper.includes("DATE") || upper.includes("TIME")) return "date";
  if (["INT", "DECIMAL", "DOUBLE", "FLOAT", "REAL"].some((token) => upper.includes(token))) {
    return "number";
  }
  return "text";
}

function mergeColumns(columns: DatasetColumn[]): DatasetColumn[] {
  const result = new Map<string, DatasetColumn>();
  for (const column of columns) if (!result.has(column.name)) result.set(column.name, column);
  return [...result.values()];
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function recordList(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item) => item && typeof item === "object") as Array<Record<string, unknown>>
    : [];
}
