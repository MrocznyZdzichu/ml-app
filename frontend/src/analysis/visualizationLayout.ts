import type { VisualizationKind } from "../api/client";

export type ChartLayout = { x: number; y: number; w: number; h: number };

export type LayoutInteraction = {
  type: "move" | "resize";
  id: string;
  startClientX: number;
  startClientY: number;
  initial: ChartLayout;
  preview: ChartLayout;
  colliding: boolean;
};

export type AlignmentGuides = { vertical: number | null; horizontal: number | null };

type LayoutChart = { id: string; kind: VisualizationKind; layout: ChartLayout };

export const GRID_COLUMNS = 48;
export const GRID_ROW_HEIGHT = 7;
export const GRID_GAP = 2;
export const CANVAS_PADDING = { top: 12, right: 12, bottom: 12, left: 12 };

export function defaultLayout(kind: VisualizationKind, index: number): ChartLayout {
  const isKpi = kind === "kpi";
  return {
    x: (index % 2) * 24,
    y: Math.floor(index / 2) * 40,
    w: isKpi ? 16 : 24,
    h: isKpi ? 28 : 40
  };
}

export function legacyLayout(size: "compact" | "medium" | "wide" | undefined, index: number): ChartLayout {
  const width = size === "wide" ? 48 : size === "compact" ? 16 : 24;
  return { x: width === 48 ? 0 : index % 2 ? 48 - width : 0, y: Math.floor(index / 2) * 40, w: width, h: size === "compact" ? 28 : 40 };
}

export function scaleLegacyGridLayout(layout: ChartLayout): ChartLayout {
  return { x: layout.x * 4, y: layout.y * 4, w: layout.w * 4, h: layout.h * 4 };
}

export function normalizeLayout(layout: ChartLayout): ChartLayout {
  const w = Math.max(12, Math.min(GRID_COLUMNS, Math.round(layout.w)));
  const h = Math.max(24, Math.round(layout.h));
  return {
    x: Math.max(0, Math.min(GRID_COLUMNS - w, Math.round(layout.x))),
    y: Math.max(0, Math.round(layout.y)),
    w,
    h
  };
}

export function tidyChartLayouts<T extends LayoutChart>(charts: T[]): T[] {
  let y = 0;
  return charts.map((chart, index) => {
    const isLastOdd = charts.length % 2 === 1 && index === charts.length - 1;
    const rowMate = !isLastOdd && index % 2 === 0 ? charts[index + 1] : null;
    const h = chart.kind === "kpi" ? 28 : 40;
    const layout = { x: isLastOdd ? 0 : index % 2 * 24, y, w: isLastOdd ? 48 : 24, h };
    if (isLastOdd || index % 2 === 1) {
      const mateHeight = rowMate?.kind === "kpi" ? 28 : 40;
      y += Math.max(h, mateHeight);
    }
    return { ...chart, layout };
  });
}

export function findOpenLayout(preferred: ChartLayout, charts: LayoutChart[]) {
  let candidate = normalizeLayout(preferred);
  while (hasLayoutCollision(candidate, "", charts)) {
    candidate = { ...candidate, y: candidate.y + 1 };
  }
  return candidate;
}

export function hasLayoutCollision(layout: ChartLayout, chartId: string, charts: LayoutChart[]) {
  return charts.some((chart) => chart.id !== chartId
    && layout.x < chart.layout.x + chart.layout.w
    && layout.x + layout.w > chart.layout.x
    && layout.y < chart.layout.y + chart.layout.h
    && layout.y + layout.h > chart.layout.y
  );
}

export function canvasMetrics(canvas: HTMLElement) {
  const rect = canvas.getBoundingClientRect();
  const contentWidth = rect.width - CANVAS_PADDING.left - CANVAS_PADDING.right - GRID_GAP * (GRID_COLUMNS - 1);
  const columnWidth = Math.max(1, contentWidth / GRID_COLUMNS);
  return {
    rect,
    columnWidth,
    pitchX: columnWidth + GRID_GAP,
    pitchY: GRID_ROW_HEIGHT + GRID_GAP
  };
}

export function calculateInteractionLayout(
  interaction: LayoutInteraction,
  event: PointerEvent,
  canvas: HTMLElement,
  charts: LayoutChart[]
): { layout: ChartLayout; guides: AlignmentGuides } {
  const metrics = canvasMetrics(canvas);
  const dx = (event.clientX - interaction.startClientX) / metrics.pitchX;
  const dy = (event.clientY - interaction.startClientY) / metrics.pitchY;
  const others = charts.filter((chart) => chart.id !== interaction.id).map((chart) => chart.layout);
  const xTargets = others.flatMap((layout) => [layout.x, layout.x + layout.w / 2, layout.x + layout.w]);
  const yTargets = others.flatMap((layout) => [layout.y, layout.y + layout.h / 2, layout.y + layout.h]);
  let raw: ChartLayout;
  let verticalGuide: number | null = null;
  let horizontalGuide: number | null = null;

  if (interaction.type === "move") {
    const xSnap = snapPosition(interaction.initial.x + dx, [0, interaction.initial.w / 2, interaction.initial.w], xTargets);
    const ySnap = snapPosition(interaction.initial.y + dy, [0, interaction.initial.h / 2, interaction.initial.h], yTargets);
    raw = { ...interaction.initial, x: xSnap.value, y: ySnap.value };
    verticalGuide = xSnap.guide;
    horizontalGuide = ySnap.guide;
  } else {
    const rightSnap = snapEdge(interaction.initial.x + interaction.initial.w + dx, xTargets);
    const bottomSnap = snapEdge(interaction.initial.y + interaction.initial.h + dy, yTargets);
    raw = {
      ...interaction.initial,
      w: rightSnap.value - interaction.initial.x,
      h: bottomSnap.value - interaction.initial.y
    };
    verticalGuide = rightSnap.guide;
    horizontalGuide = bottomSnap.guide;
  }

  const layout = normalizeLayout(raw);
  const alignedX = verticalGuide ?? findAlignedEdge([layout.x, layout.x + layout.w / 2, layout.x + layout.w], xTargets);
  const alignedY = horizontalGuide ?? findAlignedEdge([layout.y, layout.y + layout.h / 2, layout.y + layout.h], yTargets);
  return {
    layout,
    guides: {
      vertical: alignedX === null ? null : CANVAS_PADDING.left + alignedX * metrics.pitchX,
      horizontal: alignedY === null ? null : CANVAS_PADDING.top + alignedY * metrics.pitchY
    }
  };
}

function snapPosition(rawStart: number, ownOffsets: number[], targets: number[]) {
  let best = { distance: Number.POSITIVE_INFINITY, value: rawStart, guide: null as number | null };
  for (const offset of ownOffsets) {
    for (const target of targets) {
      const difference = target - (rawStart + offset);
      if (Math.abs(difference) < 0.8 && Math.abs(difference) < best.distance) {
        best = { distance: Math.abs(difference), value: rawStart + difference, guide: target };
      }
    }
  }
  return best;
}

function snapEdge(rawEdge: number, targets: number[]) {
  const target = targets.reduce<number | null>((best, current) => {
    if (Math.abs(current - rawEdge) >= 0.8) return best;
    return best === null || Math.abs(current - rawEdge) < Math.abs(best - rawEdge) ? current : best;
  }, null);
  return { value: target ?? rawEdge, guide: target };
}

function findAlignedEdge(edges: number[], targets: number[]) {
  return targets.find((target) => edges.some((edge) => Math.abs(edge - target) < 0.01)) ?? null;
}
