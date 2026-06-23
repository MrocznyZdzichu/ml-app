import type { VisualizationAggregation, VisualizationKind } from "../api/client";

export const SERIES_PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#7A5AF8", "#8C564B", "#E7298A", "#66A61E", "#17BECF"];

export type SeriesPoint = {
  series: string;
  group?: string;
  aggregation?: VisualizationAggregation;
};

export type SeriesVisual = { name: string; color: string; dash: string | undefined };

export function buildSeriesVisuals(
  chartKind: VisualizationKind,
  points: SeriesPoint[],
  series: string[],
  metricOrder: VisualizationAggregation[],
  colorAssignments: Map<string, string>
): SeriesVisual[] {
  const firstPointBySeries = new Map<string, SeriesPoint>();
  for (const point of points) {
    if (!firstPointBySeries.has(point.series)) firstPointBySeries.set(point.series, point);
  }
  const metricIndex = new Map(metricOrder.map((metric, index) => [metric, index]));
  return series.map((name) => {
    const point = firstPointBySeries.get(name);
    const dashIndex = point?.aggregation ? metricIndex.get(point.aggregation) ?? 0 : 0;
    const colorKey = seriesColorKey(chartKind, point, name);
    return {
      name,
      color: colorAssignments.get(colorKey) ?? SERIES_PALETTE[0],
      dash: chartKind === "line" ? seriesDash(dashIndex) : undefined
    };
  });
}

export function assignDistinctColors(
  points: SeriesPoint[],
  chartKind: VisualizationKind,
  assignments: Map<string, string>
) {
  const colorKeys = unique(points.map((point) => seriesColorKey(chartKind, point, point.series)))
    .sort((left, right) => left.localeCompare(right));
  for (const colorKey of colorKeys) {
    if (assignments.has(colorKey)) continue;
    const used = new Set(assignments.values());
    const available = SERIES_PALETTE.filter((color) => !used.has(color));
    if (available.length === 0) {
      assignments.set(colorKey, generatedGroupColor(colorKey, used));
      continue;
    }
    if (used.size === 0) {
      assignments.set(colorKey, available[stableHash(colorKey) % available.length]);
      continue;
    }
    assignments.set(colorKey, available.reduce((best, candidate) =>
      minimumColorDistance(candidate, used) > minimumColorDistance(best, used) ? candidate : best
    ));
  }
  return assignments;
}

function seriesColorKey(chartKind: VisualizationKind, point: SeriesPoint | undefined, seriesName: string) {
  return chartKind === "line" ? point?.group ?? seriesName : seriesName;
}

function minimumColorDistance(candidate: string, used: Set<string>) {
  return Math.min(...[...used].map((color) => colorDistance(candidate, color)));
}

function colorDistance(left: string, right: string) {
  const [leftRed, leftGreen, leftBlue] = hexToRgb(left);
  const [rightRed, rightGreen, rightBlue] = hexToRgb(right);
  const redMean = (leftRed + rightRed) / 2;
  const red = leftRed - rightRed;
  const green = leftGreen - rightGreen;
  const blue = leftBlue - rightBlue;
  return Math.sqrt((2 + redMean / 256) * red ** 2 + 4 * green ** 2 + (2 + (255 - redMean) / 256) * blue ** 2);
}

function hexToRgb(value: string): [number, number, number] {
  return [Number.parseInt(value.slice(1, 3), 16), Number.parseInt(value.slice(3, 5), 16), Number.parseInt(value.slice(5, 7), 16)];
}

function generatedGroupColor(group: string, used: Set<string>) {
  const baseHue = stableHash(group) % 360;
  const candidates = Array.from({ length: 24 }, (_, index) => hslToHex((baseHue + index * 137.508) % 360, 72, index % 2 ? 58 : 46));
  return candidates.reduce((best, candidate) => minimumColorDistance(candidate, used) > minimumColorDistance(best, used) ? candidate : best);
}

function hslToHex(hue: number, saturation: number, lightness: number) {
  const s = saturation / 100;
  const l = lightness / 100;
  const chroma = (1 - Math.abs(2 * l - 1)) * s;
  const section = hue / 60;
  const x = chroma * (1 - Math.abs(section % 2 - 1));
  const [red, green, blue] = section < 1 ? [chroma, x, 0] : section < 2 ? [x, chroma, 0] : section < 3 ? [0, chroma, x] : section < 4 ? [0, x, chroma] : section < 5 ? [x, 0, chroma] : [chroma, 0, x];
  const match = l - chroma / 2;
  return `#${[red, green, blue].map((channel) => Math.round((channel + match) * 255).toString(16).padStart(2, "0")).join("")}`;
}

function stableHash(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  return hash;
}

function seriesDash(index: number) {
  const patterns: Array<string | undefined> = [
    undefined,
    "11 5",
    "11 4 2 4",
    "2 4",
    "15 4 5 4",
    "7 3 2 3 2 3",
    "18 5"
  ];
  return patterns[index % patterns.length];
}

function unique<T>(values: T[]) {
  return [...new Set(values)];
}
