import type { DatasetPreview } from "../../api/client";
import type { DataRolesMetadata } from "../../analysis/dataRoles";
import type { DatasetCellValue } from "../profile/contracts";
import {
  columnRoleForColumn,
  compareValues,
  displayValue,
  roundNumber
} from "../dataValueFormatters";
import type {
  AggregatedColumn,
  AggregationFunction,
  ColumnFilterConfig,
  FilterOperator,
  GroupingColumnConfig,
  SortRule
} from "./contracts";
import { aggregationFunctionLabels } from "./contracts";


export function defaultFilterOperator(type: DatasetPreview["columns"][number]["type"] = "text"): FilterOperator {
  return type === "number" || type === "date" || type === "boolean" ? "equals" : "contains";
}

export function filterOperatorsForColumn(type: DatasetPreview["columns"][number]["type"], role = ""): FilterOperator[] {
  if (type === "number") {
    return ["equals", "not_equals", "gt", "gte", "lt", "lte", "between", "empty", "not_empty"];
  }
  if (type === "date") {
    return ["equals", "not_equals", "gt", "gte", "lt", "lte", "empty", "not_empty"];
  }
  if (type === "boolean") {
    return ["equals", "not_equals", "in", "empty", "not_empty"];
  }
  if (["feature_categorical", "feature_ordinal", "target"].includes(role)) {
    return ["equals", "in", "not_equals", "contains", "regex", "empty", "not_empty"];
  }
  return ["contains", "equals", "in", "not_equals", "regex", "starts_with", "ends_with", "empty", "not_empty"];
}

export function operatorDoesNotNeedValue(operator: FilterOperator) {
  return operator === "empty" || operator === "not_empty";
}

export function matchesFilter(value: unknown, config: ColumnFilterConfig | undefined) {
  if (!config) {
    return true;
  }
  const filterValue = config.value.trim();
  const textValue = displayValue(value);
  const normalizedText = textValue.toLowerCase();
  const normalizedFilter = filterValue.toLowerCase();
  const isEmpty = value === null || value === undefined || value === "";

  if (config.operator === "empty") {
    return isEmpty;
  }
  if (config.operator === "not_empty") {
    return !isEmpty;
  }
  if (config.operator === "between") {
    const bounds = config.values?.length === 2
      ? config.values
      : filterValue.split(",").map((item) => item.trim()).filter(Boolean);
    if (bounds.length !== 2) return true;
    const leftNumber = comparableNumber(value);
    const lower = Number(bounds[0]);
    const upper = Number(bounds[1]);
    if (!Number.isFinite(leftNumber) || !Number.isFinite(lower) || !Number.isFinite(upper)) return false;
    return leftNumber >= lower && (config.upperInclusive ? leftNumber <= upper : leftNumber < upper);
  }
  if (!filterValue) {
    return true;
  }
  if (config.operator === "contains") {
    return normalizedText.includes(normalizedFilter);
  }
  if (config.operator === "equals") {
    return normalizedText === normalizedFilter;
  }
  if (config.operator === "not_equals") {
    return normalizedText !== normalizedFilter;
  }
  if (config.operator === "in") {
    const values = config.values?.length ? config.values : filterValue.split(",").map((item) => item.trim()).filter(Boolean);
    return values.map((item) => item.toLowerCase()).includes(normalizedText);
  }
  if (config.operator === "starts_with") {
    return normalizedText.startsWith(normalizedFilter);
  }
  if (config.operator === "ends_with") {
    return normalizedText.endsWith(normalizedFilter);
  }
  if (config.operator === "regex") {
    try {
      return new RegExp(filterValue, "i").test(textValue);
    } catch {
      return false;
    }
  }

  const leftNumber = comparableNumber(value);
  const rightNumber = Number(filterValue);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
    if (config.operator === "gt") {
      return leftNumber > rightNumber;
    }
    if (config.operator === "gte") {
      return leftNumber >= rightNumber;
    }
    if (config.operator === "lt") {
      return leftNumber < rightNumber;
    }
    if (config.operator === "lte") {
      return leftNumber <= rightNumber;
    }
  }

  const comparison = compareValues(value, filterValue);
  if (config.operator === "gt") {
    return comparison > 0;
  }
  if (config.operator === "gte") {
    return comparison >= 0;
  }
  if (config.operator === "lt") {
    return comparison < 0;
  }
  if (config.operator === "lte") {
    return comparison <= 0;
  }
  return true;
}

export function comparableNumber(value: unknown) {
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string") {
    const parsedDate = Date.parse(value);
    if (Number.isFinite(parsedDate)) {
      return parsedDate;
    }
    const parsedNumber = Number(value);
    if (Number.isFinite(parsedNumber)) {
      return parsedNumber;
    }
  }
  return Number.NaN;
}

export function sortLabel(column: string, sortRules: SortRule[]) {
  const index = sortRules.findIndex((rule) => rule.column === column);
  if (index === -1) {
    return "";
  }
  return `${index + 1} ${sortRules[index].direction}`;
}

export function sortRecords<T extends Record<string, unknown>>(records: T[], sortRules: SortRule[]) {
  if (sortRules.length === 0) {
    return records;
  }
  return [...records].sort((left, right) => {
    for (const rule of sortRules) {
      const comparison = compareValues(left[rule.column], right[rule.column]);
      if (comparison !== 0) {
        return rule.direction === "asc" ? comparison : -comparison;
      }
    }
    return 0;
  });
}

export function quoteSqlIdentifier(identifier: string) {
  return `"${identifier.replaceAll('"', '""')}"`;
}

export function buildDataViewDefinition({
  search,
  filters,
  aggregationFilters,
  sortRules,
  grouping,
  visibleColumns,
  customSql,
  isSqlResult
}: {
  search: string;
  filters: Record<string, ColumnFilterConfig>;
  aggregationFilters: Record<string, ColumnFilterConfig>;
  sortRules: SortRule[];
  grouping: Record<string, GroupingColumnConfig>;
  visibleColumns: string[];
  customSql: string;
  isSqlResult: boolean;
}) {
  if (isSqlResult && customSql.trim()) {
    return {
      kind: "sql",
      sql: customSql.trim()
    };
  }

  return {
    kind: "browser",
    search,
    filters: removeEmptyFilterConfigs(filters),
    aggregation_filters: removeEmptyFilterConfigs(aggregationFilters),
    sort_rules: sortRules,
    grouping: Object.fromEntries(
      Object.entries(grouping).filter(([, config]) => config.role !== "none")
    ),
    visible_columns: visibleColumns
  };
}

export function removeEmptyFilterConfigs(filters: Record<string, ColumnFilterConfig>) {
  return Object.fromEntries(
    Object.entries(filters).filter(([, config]) => {
      if (operatorDoesNotNeedValue(config.operator)) {
        return true;
      }
      if (config.operator === "in") {
        return (config.values ?? []).length > 0;
      }
      return config.value.trim() !== "";
    })
  );
}

export function orderAggregatedColumns(
  columns: AggregatedColumn[],
  grouping: Record<string, GroupingColumnConfig>,
  sortRules: SortRule[]
) {
  const recordsColumn = columns.find((column) => column.name === "records");
  const groupColumns = columns.filter((column) => grouping[column.sourceColumn ?? column.name]?.role === "group");
  const aggregateColumns = columns.filter((column) =>
    column.name !== "records" && grouping[column.sourceColumn ?? column.name]?.role !== "group"
  );

  return [
    ...orderColumnsBySortRules(groupColumns, sortRules),
    ...(recordsColumn ? [recordsColumn] : []),
    ...orderColumnsBySortRules(aggregateColumns, sortRules)
  ];
}

export function orderColumnsBySortRules(columns: AggregatedColumn[], sortRules: SortRule[]) {
  const sortIndex = new Map(sortRules.map((rule, index) => [rule.column, index]));
  return [...columns].sort((left, right) => {
    const leftIndex = sortIndex.get(left.name);
    const rightIndex = sortIndex.get(right.name);
    if (leftIndex === undefined && rightIndex === undefined) {
      return 0;
    }
    if (leftIndex === undefined) {
      return 1;
    }
    if (rightIndex === undefined) {
      return -1;
    }
    return leftIndex - rightIndex;
  });
}

export function buildColumnValueOptions(
  rows: Array<Record<string, DatasetCellValue>>,
  columns: DatasetPreview["columns"]
) {
  const options: Record<string, string[]> = {};
  for (const column of columns) {
    if (!["text", "boolean", "date"].includes(column.type)) {
      continue;
    }
    const values = new Set<string>();
    for (const row of rows) {
      const value = row[column.name];
      if (value === null || value === undefined || value === "") {
        continue;
      }
      values.add(displayValue(value));
      if (values.size > 150) {
        break;
      }
    }
    if (values.size > 0 && values.size <= 150) {
      options[column.name] = [...values].sort((left, right) => left.localeCompare(right, undefined, {
        numeric: true,
        sensitivity: "base"
      }));
    }
  }
  return options;
}

export function buildAggregationResult(
  rows: Array<Record<string, DatasetCellValue>>,
  columns: DatasetPreview["columns"],
  grouping: Record<string, GroupingColumnConfig>
): {
  isActive: boolean;
  columns: AggregatedColumn[];
  records: Array<Record<string, DatasetCellValue>>;
} {
  const groupColumns = columns.filter((column) => grouping[column.name]?.role === "group");
  const aggregateColumns = columns.filter((column) => grouping[column.name]?.role === "aggregate");
  const isActive = groupColumns.length > 0 || aggregateColumns.length > 0;

  if (!isActive) {
    return { isActive: false, columns, records: rows };
  }

  const resultColumns: AggregatedColumn[] = [
    ...groupColumns.map((column) => ({ ...column, sourceColumn: column.name })),
    { name: "records", type: "number" },
    ...aggregateColumns.map((column) => ({
      name: `${aggregationFunctionLabels[grouping[column.name].aggregate]} ${column.name}`,
      type: aggregateResultType(grouping[column.name].aggregate, column.type),
      sourceColumn: column.name
    }))
  ];

  const groups = new Map<string, Array<Record<string, DatasetCellValue>>>();
  for (const row of rows) {
    const key = groupColumns.length === 0
      ? "__all__"
      : JSON.stringify(groupColumns.map((column) => displayValue(row[column.name])));
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }

  const records = Array.from(groups.values()).map((groupRows) => {
    const record: Record<string, DatasetCellValue> = {};
    for (const column of groupColumns) {
      record[column.name] = groupRows[0]?.[column.name] ?? null;
    }
    record.records = groupRows.length;
    for (const column of aggregateColumns) {
      const aggregate = grouping[column.name].aggregate;
      record[`${aggregationFunctionLabels[aggregate]} ${column.name}`] = aggregateValues(
        groupRows.map((row) => row[column.name]),
        aggregate
      );
    }
    return record;
  });

  return { isActive, columns: resultColumns, records };
}

export function aggregationFunctionsForColumn(
  column: DatasetPreview["columns"][number],
  rolesMetadata: DataRolesMetadata
): AggregationFunction[] {
  const role = columnRoleForColumn(column, rolesMetadata);
  const numericColumn = column.type === "number" || role === "feature_continuous" || role === "sample_weight";
  const orderedColumn = column.type === "date" || role === "timestamp" || role === "period_id" || role === "feature_ordinal";

  if (numericColumn) {
    return ["count", "count_non_empty", "unique_count", "sum", "average", "min", "max", "median"];
  }
  if (orderedColumn) {
    return ["count", "count_non_empty", "unique_count", "min", "max", "first", "last"];
  }
  if (role === "identifier") {
    return ["count", "count_non_empty", "unique_count", "first", "last"];
  }
  return ["count", "count_non_empty", "unique_count", "mode", "first", "last"];
}

export function defaultAggregationFunction(
  column: DatasetPreview["columns"][number],
  rolesMetadata: DataRolesMetadata
): AggregationFunction {
  const role = columnRoleForColumn(column, rolesMetadata);
  if (role === "sample_weight") {
    return "sum";
  }
  if (column.type === "number" || role === "feature_continuous") {
    return "average";
  }
  if (role === "identifier") {
    return "unique_count";
  }
  return "count_non_empty";
}

export function aggregateResultType(
  aggregate: AggregationFunction,
  fallbackType: DatasetPreview["columns"][number]["type"]
) {
  if (["count", "count_non_empty", "unique_count", "sum", "average", "median"].includes(aggregate)) {
    return "number";
  }
  return fallbackType;
}

export function aggregateValues(values: DatasetCellValue[], aggregate: AggregationFunction): DatasetCellValue {
  const concreteValues = values.filter((value) => value !== null && value !== undefined && value !== "");
  const numericValues = concreteValues
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value))
    .sort((left, right) => left - right);

  if (aggregate === "count") {
    return values.length;
  }
  if (aggregate === "count_non_empty") {
    return concreteValues.length;
  }
  if (aggregate === "unique_count") {
    return new Set(concreteValues.map(displayValue)).size;
  }
  if (aggregate === "sum") {
    return numericValues.reduce((total, value) => total + value, 0);
  }
  if (aggregate === "average") {
    return numericValues.length === 0 ? null : roundNumber(numericValues.reduce((total, value) => total + value, 0) / numericValues.length);
  }
  if (aggregate === "min") {
    return minComparableValue(concreteValues);
  }
  if (aggregate === "max") {
    return maxComparableValue(concreteValues);
  }
  if (aggregate === "median") {
    if (numericValues.length === 0) {
      return null;
    }
    const middle = Math.floor(numericValues.length / 2);
    return numericValues.length % 2 === 0
      ? roundNumber((numericValues[middle - 1] + numericValues[middle]) / 2)
      : numericValues[middle];
  }
  if (aggregate === "mode") {
    return mostCommonValue(concreteValues);
  }
  if (aggregate === "first") {
    return concreteValues[0] ?? null;
  }
  return concreteValues[concreteValues.length - 1] ?? null;
}

export function minComparableValue(values: DatasetCellValue[]) {
  if (values.length === 0) {
    return null;
  }
  return [...values].sort(compareValues)[0] ?? null;
}

export function maxComparableValue(values: DatasetCellValue[]) {
  if (values.length === 0) {
    return null;
  }
  return [...values].sort(compareValues).at(-1) ?? null;
}

export function mostCommonValue(values: DatasetCellValue[]) {
  const counts = new Map<string, { value: DatasetCellValue; count: number }>();
  for (const value of values) {
    const key = displayValue(value);
    const current = counts.get(key);
    counts.set(key, { value, count: (current?.count ?? 0) + 1 });
  }
  return [...counts.values()].sort((left, right) => right.count - left.count)[0]?.value ?? null;
}
