import type { DatasetPreview } from "../../api/client";

export type DatasetCellValue = string | number | boolean | null;

export type ColumnProfile = {
  name: string;
  type: DatasetPreview["columns"][number]["type"];
  role: string;
  count: number;
  missing: number;
  missingRate: number;
  unique: number;
  uniqueRate: number;
  mean: number | null;
  median: number | null;
  minimum: DatasetCellValue;
  maximum: DatasetCellValue;
  stdDev: number | null;
  mode: DatasetCellValue;
  topValues: Array<{ value: DatasetCellValue; count: number; share: number }>;
  histogram: Array<{ label: string; count: number; share: number }>;
  examples: DatasetCellValue[];
  notes: string[];
};

export type TargetRelationProfile = {
  feature: string;
  role: string;
  type: DatasetPreview["columns"][number]["type"];
  kind: string;
  score: number;
  signal: string;
  detail: string;
  comparisonColumn: string;
  groupStats: NumericGroupStats[];
  densityPlot: DensityPlot | null;
  numericStats: NumericRelationStats | null;
  scatterPlot: ScatterPlot | null;
  categoricalStats: CategoricalRelationStats | null;
};

export type CategoricalRelationStats = {
  comparisonValues: string[];
  rows: Array<{
    featureValue: string;
    count: number;
    cells: Array<{
      comparisonValue: string;
      count: number;
      rowShare: number;
      lift: number;
      residual: number;
    }>;
  }>;
  chiSquare: number;
  degreesFreedom: number;
  cramersV: number;
  sparseCellShare: number;
  ordinalTrend: {
    focusValue: string;
    spearman: number;
    orderBasis: string;
  } | null;
  graphicSummaries: boolean;
};

export type NumericGroupStats = {
  group: string;
  count: number;
  minimum: number;
  maximum: number;
  median: number;
  mean: number;
  stdDev: number;
  color: string;
};

export type DensityPlot = {
  xMin: number;
  xMax: number;
  yMax: number;
  series: DensitySeries[];
};

export type DensitySeries = {
  group: string;
  color: string;
  points: Array<{
    x: number;
    y: number;
  }>;
};

export type NumericRelationStats = {
  pearson: number;
  spearman: number;
  rSquared: number;
  covariance: number;
  slope: number;
  intercept: number;
};

export type ScatterPlot = {
  xColumn: string;
  yColumn: string;
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  points: Array<{ x: number; y: number }>;
  trendLine: {
    x1: number;
    y1: number;
    x2: number;
    y2: number;
  } | null;
};

export type SegmentResult = {
  columns: string[];
  segment: string;
  count: number;
  support: number;
  targetValue: string;
  baseline: number;
  segmentValue: number;
  difference: number;
  relativeLift: number | null;
  confidenceInterval: [number, number] | null;
  effectSize: number | null;
  score: number;
  format: "number" | "percent";
};

export type SegmentProfile = {
  targetColumn: string;
  targetType: EffectiveTargetType;
  candidateFeatures: string[];
  pairsScanned: number;
  segmentsEvaluated: number;
  minimumSegmentSize: number;
  graphicSummaries: boolean;
  results: SegmentResult[];
};

export type TargetTypeSetting = "auto" | "categorical" | "continuous";
export type EffectiveTargetType = "categorical" | "continuous";

export type ProfilingRangeSettings = {
  includeSummary: boolean;
  includeUnivariate: boolean;
  includeTargetRelations: boolean;
  includeSegments: boolean;
  includeGraphicSummaries: boolean;
  rowLimit: number;
  maxTargetFeatures: number;
  maxSegmentFeatures: number;
};

export type DescriptiveProfileCacheEntry = {
  datasetUpdatedAt: string;
  preview: DatasetPreview;
  targetColumn: string;
  targetTypeSetting: TargetTypeSetting;
  comparisonColumn: string;
  showIgnoredColumns: boolean;
  profilingRange: ProfilingRangeSettings;
  selectedProfileColumns: string[] | null;
  selectedRelationFeatures: string[] | null;
  collapsedRelationCards: Record<string, boolean>;
  setupCollapsed: boolean;
  univariateCollapsed: boolean;
  targetCollapsed: boolean;
  segmentCollapsed: boolean;
  computedProfile: DescriptiveComputedProfile | null;
};

export type DescriptiveComputedProfile = {
  key: string;
  columnProfiles: ColumnProfile[];
  targetRelations: TargetRelationProfile[];
  segmentProfile: SegmentProfile | null;
  dataQualityNotes: string[];
};

export const defaultProfilingRangeSettings: ProfilingRangeSettings = {
  includeSummary: true,
  includeUnivariate: true,
  includeTargetRelations: true,
  includeSegments: true,
  includeGraphicSummaries: true,
  rowLimit: 50000,
  maxTargetFeatures: 30,
  maxSegmentFeatures: 4
};
