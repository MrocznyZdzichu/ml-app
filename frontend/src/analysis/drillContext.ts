import type {
  DatasetColumn,
  DatasetDrillFilter,
  DatasetDrillOperator,
  VisualizationKind,
} from "../api/client";

export type VisualizationDrillRequest = {
  id: string;
  datasetId: string;
  filters: Record<string, DatasetDrillFilter>;
};

export type BrowserFilterConfig = {
  operator: DatasetDrillOperator;
  value: string;
  values?: string[];
  upperInclusive?: boolean;
};

type DrillChart = {
  kind: VisualizationKind;
  x: string;
  y: string;
  group: string;
};

type DrillMark = {
  x: number;
  y: number;
  xLabel: string;
  xRange?: [number, number];
  yRange?: [number, number];
  xRangeInclusive?: boolean;
  yRangeInclusive?: boolean;
  group?: string;
};

export function createVisualizationDrillRequest(
  datasetId: string,
  chart: DrillChart,
  mark: DrillMark,
  xType?: DatasetColumn["type"],
): VisualizationDrillRequest {
  const filters: Record<string, DatasetDrillFilter> = {};
  if (chart.x) {
    filters[chart.x] = mark.xRange
      ? rangeFilter(mark.xRange, mark.xRangeInclusive)
      : xType === "number"
        ? numericEqualityFilter(sourceXValue(chart, mark))
        : { operator: "equals", value: mark.xLabel };
  }
  if (chart.kind === "scatter" && chart.y) {
    filters[chart.y] = mark.yRange
      ? rangeFilter(mark.yRange, mark.yRangeInclusive)
      : numericEqualityFilter(mark.y);
  }
  if (chart.group && mark.group !== undefined) {
    filters[chart.group] = { operator: "equals", value: mark.group };
  }
  return {
    id: crypto.randomUUID(),
    datasetId,
    filters,
  };
}

export function browserFiltersFromVisualizationDrill(
  request: VisualizationDrillRequest,
): Record<string, BrowserFilterConfig> {
  return Object.fromEntries(Object.entries(request.filters).map(([column, filter]) => [column, {
    operator: filter.operator,
    value: filter.value ?? filter.values?.join(", ") ?? "",
    values: filter.values,
    upperInclusive: filter.upper_inclusive,
  }]));
}

function numericEqualityFilter(value: number): DatasetDrillFilter {
  return rangeFilter([value, value], true);
}

function sourceXValue(chart: DrillChart, mark: DrillMark) {
  const value = chart.kind === "histogram" ? Number(mark.xLabel) : mark.x;
  return Number.isFinite(value) ? value : mark.x;
}

function rangeFilter(range: [number, number], upperInclusive = false): DatasetDrillFilter {
  return {
    operator: "between",
    values: range.map(String),
    upper_inclusive: upperInclusive,
  };
}
