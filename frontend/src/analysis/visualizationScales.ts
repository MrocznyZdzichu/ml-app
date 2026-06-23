export type NumericScale = { min: number; max: number; step: number; ticks: number[] };

export function selectCategoricalAxisTicks<T extends { label: string }>(values: T[], plotWidth: number) {
  if (values.length < 2) return values;
  const slotWidth = plotWidth / values.length;
  for (let stride = 1; stride < values.length; stride += 1) {
    const indices = Array.from({ length: Math.ceil(values.length / stride) }, (_, index) => index * stride)
      .filter((index) => index < values.length);
    if (indices[indices.length - 1] !== values.length - 1) indices.push(values.length - 1);
    if (axisLabelsFit(indices, values, slotWidth)) return indices.map((index) => values[index]);
  }
  return [values[0], values[values.length - 1]];
}

export function createNumericScale(dataMin: number, dataMax: number, targetTickCount: number, includeZero: boolean): NumericScale {
  let min = Number.isFinite(dataMin) ? dataMin : 0;
  let max = Number.isFinite(dataMax) ? dataMax : 1;
  if (min > max) [min, max] = [max, min];
  if (includeZero) {
    min = Math.min(0, min);
    max = Math.max(0, max);
  }
  if (min === max) {
    const padding = Math.abs(min) * 0.1 || 1;
    if (includeZero) max = min + padding;
    else {
      min -= padding;
      max += padding;
    }
  } else if (!includeZero) {
    const padding = (max - min) * 0.05;
    min -= padding;
    max += padding;
  }

  const step = niceAxisStep((max - min) / Math.max(1, targetTickCount - 1));
  const scaleMin = roundAxisValue(Math.floor(min / step) * step);
  const scaleMax = roundAxisValue(Math.ceil(max / step) * step);
  const tickCount = Math.max(1, Math.round((scaleMax - scaleMin) / step));
  const ticks = Array.from({ length: tickCount + 1 }, (_, index) => roundAxisValue(scaleMin + index * step));
  return { min: scaleMin, max: scaleMax, step, ticks };
}

export function formatAxisTick(value: number, step: number) {
  const absoluteValue = Math.abs(value);
  if (absoluteValue >= 1_000_000) {
    return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 2 }).format(value);
  }
  if (absoluteValue > 0 && (absoluteValue < 0.000001 || Math.abs(step) < 0.000001)) {
    return new Intl.NumberFormat(undefined, { notation: "scientific", maximumFractionDigits: 2 }).format(value);
  }
  const exponent = Math.floor(Math.log10(Math.abs(step) || 1));
  const normalizedStep = Math.abs(step) / 10 ** exponent;
  const fractionAdjustment = Number.isInteger(roundAxisValue(normalizedStep)) ? 0 : 1;
  const fractionDigits = Math.max(0, Math.min(8, -exponent + fractionAdjustment));
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: fractionDigits }).format(value);
}

export function shortAxisLabel(value: string) {
  return value.length > 16 ? `${value.slice(0, 14)}…` : value;
}

function axisLabelsFit<T extends { label: string }>(indices: number[], values: T[], slotWidth: number) {
  const minimumGap = 9;
  let previousRight = Number.NEGATIVE_INFINITY;
  for (const index of indices) {
    const center = (index + 0.5) * slotWidth;
    const width = estimateAxisLabelWidth(shortAxisLabel(values[index].label));
    const left = center - width / 2;
    if (left < previousRight + minimumGap) return false;
    previousRight = center + width / 2;
  }
  return true;
}

function estimateAxisLabelWidth(value: string) {
  return [...value].reduce((width, character) => {
    if ("1ilI.,:;'|".includes(character)) return width + 3;
    if ("MW@%#".includes(character)) return width + 8;
    if (character === " " || character === "-") return width + 3.5;
    return width + 5.5;
  }, 0);
}

function niceAxisStep(roughStep: number) {
  if (!Number.isFinite(roughStep) || roughStep <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const normalized = roughStep / magnitude;
  const niceNormalized = [1, 2, 2.5, 5, 10].find((candidate) => candidate >= normalized) ?? 10;
  return niceNormalized * magnitude;
}

function roundAxisValue(value: number) {
  return Number(value.toPrecision(12));
}
