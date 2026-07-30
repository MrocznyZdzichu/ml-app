import type { DatasetPreview } from "../../api/client";
import type { BrowserFilterConfig } from "../../analysis/drillContext";


export type SortDirection = "asc" | "desc";
export type SortRule = {
  column: string;
  direction: SortDirection;
};
export type FilterOperator = BrowserFilterConfig["operator"];
export type ColumnFilterConfig = BrowserFilterConfig;
export const DATA_BROWSER_DRILL_PREVIEW_LIMIT = 5_000;
export type GroupingRole = "none" | "group" | "aggregate";
export type AggregationFunction =
  | "count"
  | "count_non_empty"
  | "unique_count"
  | "sum"
  | "average"
  | "min"
  | "max"
  | "median"
  | "mode"
  | "first"
  | "last";

export type GroupingColumnConfig = {
  role: GroupingRole;
  aggregate: AggregationFunction;
};

export type AggregatedColumn = {
  name: string;
  type: DatasetPreview["columns"][number]["type"];
  sourceColumn?: string;
};

export const groupingRoleOptions: Array<{ value: GroupingRole; label: string }> = [
  { value: "none", label: "Not used" },
  { value: "group", label: "Group column" },
  { value: "aggregate", label: "Aggregate column" }
];

export const aggregationFunctionLabels: Record<AggregationFunction, string> = {
  count: "Count rows",
  count_non_empty: "Count values",
  unique_count: "Unique count",
  sum: "Sum",
  average: "Average",
  min: "Minimum",
  max: "Maximum",
  median: "Median",
  mode: "Most frequent",
  first: "First value",
  last: "Last value"
};

export const filterOperatorLabels: Record<FilterOperator, string> = {
  contains: "Contains",
  equals: "Equals",
  not_equals: "Not equals",
  in: "In",
  regex: "Regex",
  starts_with: "Starts with",
  ends_with: "Ends with",
  gt: ">",
  gte: ">=",
  lt: "<",
  lte: "<=",
  between: "Between",
  empty: "Is empty",
  not_empty: "Is not empty"
};
