import {
  Activity,
  BarChart3,
  GripVertical,
  LayoutDashboard,
  LineChart,
  Maximize2,
  Move,
  Plus,
  RotateCcw,
  ScatterChart,
  Settings2,
  Sparkles,
  Trash2,
  ZoomIn,
  ZoomOut
} from "lucide-react";
import type { DragEvent, PointerEvent as ReactPointerEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type {
  DataAsset,
  DatasetColumn,
  DatasetPreview,
  DatasetVisualizationRequest,
  VisualizationAggregation,
  VisualizationKind
} from "../api/client";
import { useVisualizationResult } from "./useVisualizationResult";

type CellValue = string | number | boolean | null;
type RecordRow = Record<string, CellValue>;
type ChartKind = VisualizationKind;
type ChartSize = "compact" | "medium" | "wide";
type Aggregation = VisualizationAggregation;
type ChartLayout = { x: number; y: number; w: number; h: number };

type ChartConfig = {
  id: string;
  kind: ChartKind;
  title: string;
  x: string;
  y: string;
  xEpsilon: number;
  group: string;
  aggregation: Aggregation;
  comparisonAggregations: Aggregation[];
  selectedGroups: string[] | null;
  layout: ChartLayout;
};

type LayoutInteraction = {
  type: "move" | "resize";
  id: string;
  startClientX: number;
  startClientY: number;
  initial: ChartLayout;
  preview: ChartLayout;
  colliding: boolean;
};

type AlignmentGuides = { vertical: number | null; horizontal: number | null };

type Tooltip = { x: number; y: number; title: string; value: string } | null;

type VisualizationDashboardProps = {
  datasets: DataAsset[];
  setNotice: (message: string) => void;
};

const SAMPLE_LIMIT = 1000;
const GRID_COLUMNS = 48;
const GRID_ROW_HEIGHT = 7;
const GRID_GAP = 2;
const CANVAS_PADDING = { top: 12, right: 12, bottom: 12, left: 12 };
const LAYOUT_VERSION = 2;
const PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#7A5AF8", "#8C564B", "#E7298A", "#66A61E", "#17BECF"];
const aggregationOptions: Array<{ value: Aggregation; label: string }> = [
  { value: "average", label: "Average" },
  { value: "median", label: "Median" },
  { value: "std", label: "Standard deviation" },
  { value: "sum", label: "Sum" },
  { value: "count", label: "Count" },
  { value: "min", label: "Minimum" },
  { value: "max", label: "Maximum" }
];
const chartCatalog: Array<{ kind: ChartKind; label: string; description: string; icon: typeof Activity }> = [
  { kind: "line", label: "Trend line", description: "Time and ordered change", icon: LineChart },
  { kind: "bar", label: "Category bars", description: "Compare grouped values", icon: BarChart3 },
  { kind: "scatter", label: "Scatter plot", description: "Explore relationships", icon: ScatterChart },
  { kind: "histogram", label: "Distribution", description: "Shape, spread and outliers", icon: Activity },
  { kind: "kpi", label: "KPI", description: "A single key measure", icon: Maximize2 }
];

const kindLabels: Record<ChartKind, string> = {
  line: "Trend line",
  bar: "Category bars",
  scatter: "Scatter plot",
  histogram: "Distribution",
  kpi: "KPI"
};

export function VisualizationDashboard({ datasets, setNotice }: VisualizationDashboardProps) {
  const [datasetId, setDatasetId] = useState("");
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [charts, setCharts] = useState<ChartConfig[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [interaction, setInteraction] = useState<LayoutInteraction | null>(null);
  const [guides, setGuides] = useState<AlignmentGuides>({ vertical: null, horizontal: null });
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const canvasRef = useRef<HTMLElement | null>(null);
  const columns = preview?.columns ?? [];
  const rows = preview?.records ?? [];
  const selectedChart = charts.find((chart) => chart.id === selectedId) ?? null;
  const canvasRows = Math.max(64, ...charts.map((chart) => {
    const layout = interaction?.id === chart.id ? interaction.preview : chart.layout;
    return layout.y + layout.h + 1;
  }));

  useEffect(() => {
    if (!datasetId) {
      setPreview(null);
      setCharts([]);
      setSelectedId(null);
      return;
    }
    let current = true;
    setPreview(null);
    setCharts([]);
    setSelectedId(null);
    setIsLoading(true);
    setLoadError("");
    api.previewDataset(datasetId, SAMPLE_LIMIT)
      .then((result) => {
        if (!current) return;
        setPreview(result);
        const next = readSessionDashboard(datasetId, result.columns) ?? [];
        setCharts(next);
        setSelectedId(next[0]?.id ?? null);
        setNotice(next.length
          ? `Restored ${next.length} visualization${next.length === 1 ? "" : "s"} from this session`
          : `Dataset ready — add a chart or use Smart start`
        );
      })
      .catch((error: unknown) => {
        if (!current) return;
        setLoadError(error instanceof Error ? error.message : "Could not load visualization data");
        setPreview(null);
      })
      .finally(() => current && setIsLoading(false));
    return () => { current = false; };
  }, [datasetId, setNotice]);

  useEffect(() => {
    if (!datasetId || !preview || preview.dataset_id !== datasetId) return;
    window.sessionStorage.setItem(storageKey(datasetId), JSON.stringify({ version: LAYOUT_VERSION, charts }));
  }, [charts, datasetId, preview]);

  useEffect(() => {
    if (!interaction) return;
    const handlePointerMove = (event: PointerEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      setInteraction((current) => {
        if (!current) return null;
        const next = calculateInteractionLayout(current, event, canvas, charts);
        setGuides(next.guides);
        return { ...current, preview: next.layout, colliding: hasLayoutCollision(next.layout, current.id, charts) };
      });
    };
    const handlePointerUp = () => {
      setInteraction((current) => {
        if (!current) return null;
        if (current.colliding) {
          setNotice("That position overlaps another chart — move it to a free area");
        } else {
          setCharts((items) => items.map((chart) => chart.id === current.id ? { ...chart, layout: current.preview } : chart));
        }
        return null;
      });
      setGuides({ vertical: null, horizontal: null });
    };
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [interaction?.id, charts, setNotice]);

  function addChart(kind: ChartKind, preferredPosition?: Pick<ChartLayout, "x" | "y">) {
    if (!preview) return;
    const chart = createChart(kind, columns, rows, charts.length);
    const preferred = preferredPosition ? { ...chart.layout, ...preferredPosition } : chart.layout;
    chart.layout = findOpenLayout(preferred, charts);
    setCharts((current) => [...current, chart]);
    setSelectedId(chart.id);
  }

  function updateChart(id: string, patch: Partial<ChartConfig>) {
    setCharts((current) => current.map((chart) => chart.id === id ? { ...chart, ...patch } : chart));
  }

  function removeChart(id: string) {
    setCharts((current) => current.filter((chart) => chart.id !== id));
    if (selectedId === id) setSelectedId(charts.find((chart) => chart.id !== id)?.id ?? null);
  }

  function smartStart() {
    if (!preview) return;
    const next = buildSmartDashboard(columns, rows);
    setCharts(next);
    setSelectedId(next[0]?.id ?? null);
    setNotice("Smart layout rebuilt from column types and data cardinality");
  }

  function tidyLayout() {
    setCharts((current) => tidyChartLayouts(current));
    setNotice("Charts aligned to a balanced grid");
  }

  function clearCanvas() {
    setCharts([]);
    setSelectedId(null);
    setNotice("Visualization canvas cleared");
  }

  function handlePaletteDrag(event: DragEvent<HTMLButtonElement>, kind: ChartKind) {
    event.dataTransfer.setData("application/x-chart-kind", kind);
    event.dataTransfer.effectAllowed = "copy";
  }

  function handleCanvasDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    const kind = event.dataTransfer.getData("application/x-chart-kind") as ChartKind;
    if (!chartCatalog.some((item) => item.kind === kind)) return;
    const metrics = canvasMetrics(event.currentTarget);
    const x = Math.max(0, Math.min(GRID_COLUMNS - 3, Math.floor((event.clientX - metrics.rect.left - CANVAS_PADDING.left) / metrics.pitchX)));
    const y = Math.max(0, Math.round((event.clientY - metrics.rect.top - CANVAS_PADDING.top) / metrics.pitchY));
    addChart(kind, { x, y });
  }

  function startLayoutInteraction(event: ReactPointerEvent<HTMLElement>, chart: ChartConfig, type: LayoutInteraction["type"]) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    setSelectedId(chart.id);
    setInteraction({
      type,
      id: chart.id,
      startClientX: event.clientX,
      startClientY: event.clientY,
      initial: chart.layout,
      preview: chart.layout,
      colliding: false
    });
  }

  return (
    <div className="visualization-panel">
      <header className="viz-hero panel">
        <div>
          <p className="eyebrow">Interactive analysis canvas</p>
          <h2>Visualization and Trends</h2>
          <p>Compose a dashboard, connect columns and investigate values without leaving the workspace.</p>
        </div>
        <div className="viz-hero-actions">
          <label>
            Dataset
            <select value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
              <option value="">Choose a dataset…</option>
              {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}
            </select>
          </label>
          <button className="secondary-button" onClick={smartStart} disabled={!preview} type="button">
            <Sparkles size={16} /> Smart start
          </button>
          <button className="secondary-button" onClick={tidyLayout} disabled={!charts.length} type="button">
            <LayoutDashboard size={16} /> Tidy layout
          </button>
          <button className="secondary-button viz-clear-button" onClick={clearCanvas} disabled={!charts.length} type="button">
            <Trash2 size={16} /> Clear canvas
          </button>
        </div>
      </header>

      {!datasetId && <div className="panel empty-state">Add a dataset to start building a dashboard.</div>}
      {isLoading && <div className="panel viz-loading"><Activity size={20} /> Reading the dataset and choosing useful views…</div>}
      {loadError && <div className="panel empty-state error-state">{loadError}</div>}

      {preview && !isLoading && (
        <>
          <div className="viz-context-strip" aria-label="Dataset context">
            <span><strong>{formatInteger(preview.row_count)}</strong> rows analyzed</span>
            <span><strong>{columns.length}</strong> columns</span>
            <span className="full-data-badge">Full dataset · server-side</span>
            <span className="autosave-state">● Layout saved automatically</span>
          </div>

          <div className="viz-workbench">
            <aside className="panel viz-sidebar">
              <div className="viz-sidebar-heading">
                <div><p className="eyebrow">Chart library</p><h2>Add a view</h2></div>
                <Plus size={18} />
              </div>
              <p className="viz-help">Drag onto the canvas or click to add.</p>
              <div className="chart-library">
                {chartCatalog.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      draggable
                      key={item.kind}
                      onClick={() => addChart(item.kind)}
                      onDragStart={(event) => handlePaletteDrag(event, item.kind)}
                      type="button"
                    >
                      <Icon size={18} />
                      <span><strong>{item.label}</strong><small>{item.description}</small></span>
                      <GripVertical size={15} />
                    </button>
                  );
                })}
              </div>

              {selectedChart && (
                  <ChartInspector
                    chart={selectedChart}
                    columns={columns}
                    datasetId={datasetId}
                    rows={rows}
                  onChange={(patch) => updateChart(selectedChart.id, patch)}
                />
              )}
            </aside>

            <main
              className={charts.length ? "viz-canvas" : "viz-canvas empty"}
              ref={canvasRef}
              style={{ minHeight: Math.max(620, CANVAS_PADDING.top + canvasRows * (GRID_ROW_HEIGHT + GRID_GAP)) }}
              onDragOver={(event) => event.preventDefault()}
              onDrop={handleCanvasDrop}
            >
              {guides.vertical !== null && <div className="alignment-guide vertical" style={{ left: guides.vertical }} />}
              {guides.horizontal !== null && <div className="alignment-guide horizontal" style={{ top: guides.horizontal }} />}
              {charts.length === 0 && (
                <button type="button" onClick={smartStart}>
                  <LayoutDashboard size={28} />
                  <strong>Drop a chart here</strong>
                  <span>or create a balanced starter dashboard</span>
                </button>
              )}
              {charts.map((chart) => {
                const layout = interaction?.id === chart.id ? interaction.preview : chart.layout;
                const isActiveInteraction = interaction?.id === chart.id;
                return (
                <article
                  className={`viz-card ${selectedId === chart.id ? "selected" : ""} ${isActiveInteraction ? interaction.type : ""} ${isActiveInteraction && interaction.colliding ? "colliding" : ""}`}
                  key={chart.id}
                  onClick={() => setSelectedId(chart.id)}
                  style={{ gridColumn: `${layout.x + 1} / span ${layout.w}`, gridRow: `${layout.y + 1} / span ${layout.h}` }}
                >
                  <header className="viz-card-header" onPointerDown={(event) => startLayoutInteraction(event, chart, "move")} title="Drag to move chart">
                    <div className="viz-card-title">
                      <Move size={15} />
                      <div><strong>{chart.title}</strong><span>{describeEncoding(chart)}</span></div>
                    </div>
                    <div className="viz-card-actions">
                      <button aria-label={`Remove ${chart.title}`} onPointerDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); removeChart(chart.id); }} type="button"><Trash2 size={15} /></button>
                    </div>
                  </header>
                  <ChartView chart={chart} datasetId={datasetId} />
                  <button className="viz-resize-handle" aria-label={`Resize ${chart.title}`} onPointerDown={(event) => startLayoutInteraction(event, chart, "resize")} title="Drag to resize" type="button"><Maximize2 size={14} /></button>
                </article>
              );})}
            </main>
          </div>
        </>
      )}
    </div>
  );
}

function ChartInspector({ chart, columns, datasetId, rows, onChange }: { chart: ChartConfig; columns: DatasetColumn[]; datasetId: string; rows: RecordRow[]; onChange: (patch: Partial<ChartConfig>) => void }) {
  const numericColumns = columns.filter((column) => column.type === "number");
  const xColumn = columns.find((column) => column.name === chart.x);
  const groupingColumns = columns.filter((column) => column.name !== chart.x && column.name !== chart.y && cardinality(rows, column.name) <= 20);
  const [availableGroups, setAvailableGroups] = useState<string[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupsTruncated, setGroupsTruncated] = useState(false);
  const effectiveSelectedGroups = chart.selectedGroups ?? availableGroups;

  useEffect(() => {
    if (!chart.group) {
      setAvailableGroups([]);
      setGroupsTruncated(false);
      return;
    }
    let current = true;
    setGroupsLoading(true);
    const timeout = window.setTimeout(() => {
      api.visualizationGroups(datasetId, chart.group)
        .then((result) => {
          if (!current) return;
          setAvailableGroups(result.values.sort((a, b) => a.localeCompare(b)));
          setGroupsTruncated(result.truncated);
        })
        .catch(() => current && setAvailableGroups([]))
        .finally(() => current && setGroupsLoading(false));
    }, 250);
    return () => {
      current = false;
      window.clearTimeout(timeout);
    };
  }, [chart.group, datasetId]);
  return (
    <div className="chart-inspector">
      <div className="viz-sidebar-heading"><div><p className="eyebrow">Selected view</p><h2>Configure</h2></div><Settings2 size={17} /></div>
      <label>Title<input value={chart.title} onChange={(event) => onChange({ title: event.target.value })} /></label>
      {chart.kind !== "kpi" && (
        <label>{chart.kind === "histogram" ? "Measure" : "Horizontal axis"}
          <select value={chart.x} onChange={(event) => onChange({ x: event.target.value, xEpsilon: 0 })}>
            {(chart.kind === "histogram" ? numericColumns : columns).map((column) => <option key={column.name} value={column.name}>{column.name} · {column.type}</option>)}
          </select>
        </label>
      )}
      {(chart.kind === "line" || chart.kind === "bar") && xColumn?.type === "number" && (
        <label>X epsilon
          <input
            min="0"
            onChange={(event) => onChange({ xEpsilon: Math.max(0, Number(event.target.value) || 0) })}
            step="any"
            type="number"
            value={chart.xEpsilon ?? 0}
          />
          <span className="epsilon-hint">0 keeps exact X values. A positive value groups [center − ε, center + ε).</span>
        </label>
      )}
      {chart.kind !== "histogram" && (
        <label>{chart.kind === "kpi" ? "Measure" : "Vertical axis"}
          <select value={chart.y} onChange={(event) => onChange({ y: event.target.value })}>
            {numericColumns.map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}
          </select>
        </label>
      )}
      {(chart.kind === "line" || chart.kind === "bar" || chart.kind === "kpi") && (
        <label>Primary aggregation<select value={chart.aggregation} onChange={(event) => {
          const aggregation = event.target.value as Aggregation;
          onChange({ aggregation, comparisonAggregations: (chart.comparisonAggregations ?? []).filter((item) => item !== aggregation) });
        }}>
          {aggregationOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select></label>
      )}
      {(chart.kind === "line" || chart.kind === "bar") && (
        <fieldset className="metric-series-fieldset">
          <legend>Additional metrics</legend>
          <div className="metric-series-options">
            {aggregationOptions.filter((option) => option.value !== chart.aggregation).map((option) => (
              <label key={option.value}>
                <input
                checked={(chart.comparisonAggregations ?? []).includes(option.value)}
                  onChange={(event) => onChange({
                    comparisonAggregations: event.target.checked
                      ? [...(chart.comparisonAggregations ?? []), option.value]
                      : (chart.comparisonAggregations ?? []).filter((item) => item !== option.value)
                  })}
                  type="checkbox"
                />
                {option.label}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      {(chart.kind === "line" || chart.kind === "scatter") && (
        <label>Color / series<select value={chart.group} onChange={(event) => onChange({ group: event.target.value, selectedGroups: null })}>
          <option value="">Single series</option>{groupingColumns.map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}
        </select></label>
      )}
      {chart.group && (
        <fieldset className="group-selection-fieldset">
          <legend>Group selection</legend>
          <div className="group-selection-actions">
            <span>{groupsLoading ? "Loading full dataset…" : chart.selectedGroups == null ? `All (${availableGroups.length})` : `${effectiveSelectedGroups.length} of ${availableGroups.length}`}</span>
            <button onClick={() => onChange({ selectedGroups: null })} type="button">All</button>
            <button onClick={() => onChange({ selectedGroups: [] })} type="button">None</button>
          </div>
          <div className="group-selection-options">
            {availableGroups.map((group) => (
              <label key={group}>
                <input
                  checked={effectiveSelectedGroups.includes(group)}
                  onChange={(event) => onChange({
                    selectedGroups: event.target.checked
                      ? unique([...effectiveSelectedGroups, group])
                      : effectiveSelectedGroups.filter((item) => item !== group)
                  })}
                  type="checkbox"
                />
                <span title={group}>{group}</span>
              </label>
            ))}
          </div>
          {groupsTruncated && <p className="group-selection-note">Showing the 100 most frequent values.</p>}
        </fieldset>
      )}
      <p className="inspector-tip"><Sparkles size={14} /> Colors are assigned consistently and optimized for contrast.</p>
    </div>
  );
}

function ChartView({ chart, datasetId }: { chart: ChartConfig; datasetId: string }) {
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState(0);
  const [tooltip, setTooltip] = useState<Tooltip>(null);
  const [pointerStart, setPointerStart] = useState<number | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const lastWheelAtRef = useRef(0);
  const groupColorsRef = useRef<Map<string, string>>(new Map());
  const query = useMemo<DatasetVisualizationRequest>(() => ({
    kind: chart.kind,
    x: chart.x,
    y: chart.y,
    group: chart.group,
    aggregations: unique([chart.aggregation, ...(chart.comparisonAggregations ?? [])]),
    selected_groups: chart.selectedGroups ?? null,
    x_epsilon: chart.xEpsilon ?? 0,
    max_points: 2000,
    bins: 16
  }), [chart.aggregation, chart.comparisonAggregations, chart.group, chart.kind, chart.selectedGroups, chart.x, chart.xEpsilon, chart.y]);
  const { result, loading: chartLoading, error: chartError } = useVisualizationResult(datasetId, query);
  const metricOrder = useMemo(
    () => unique([chart.aggregation, ...(chart.comparisonAggregations ?? [])]),
    [chart.aggregation, chart.comparisonAggregations]
  );

  useEffect(() => {
    if (!result) return;
    setOffset(0);
    setZoom(1);
  }, [result]);

  const points = result?.points ?? [];
  const series = result?.series ?? [];
  const groupColors = useMemo(() => assignDistinctGroupColors(points, groupColorsRef.current), [points]);
  const seriesVisuals = useMemo(() => buildSeriesVisuals(points, series, metricOrder, groupColors), [groupColors, metricOrder, points, series]);
  const xDomain = useMemo(() => Array.from(new Set(points.map((point) => point.x))), [points]);
  const length = xDomain.length;
  const visibleCount = Math.max(3, Math.ceil(length / zoom));
  const maxOffset = Math.max(0, length - visibleCount);
  const safeOffset = Math.min(offset, maxOffset);
  const visible = useMemo(() => {
    const visibleX = new Set(xDomain.slice(safeOffset, safeOffset + visibleCount));
    return points.filter((point) => visibleX.has(point.x));
  }, [points, safeOffset, visibleCount, xDomain]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const handleNativeWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const now = performance.now();
      if (now - lastWheelAtRef.current < 90) return;
      lastWheelAtRef.current = now;
      const direction = event.deltaY < 0 ? 1 : -1;
      const bounds = viewport.getBoundingClientRect();
      const cursorRatio = Math.max(0, Math.min(1, (event.clientX - bounds.left) / Math.max(1, bounds.width)));
      setZoom((current) => {
        const next = Math.max(1, Math.min(8, current + direction));
        const currentVisible = Math.max(3, Math.ceil(length / current));
        const nextVisible = Math.max(3, Math.ceil(length / next));
        setOffset((currentOffset) => {
          const anchor = currentOffset + cursorRatio * currentVisible;
          return Math.max(0, Math.min(length - nextVisible, Math.round(anchor - cursorRatio * nextVisible)));
        });
        return next;
      });
    };
    viewport.addEventListener("wheel", handleNativeWheel, { passive: false });
    return () => viewport.removeEventListener("wheel", handleNativeWheel);
  }, [length]);

  function changeZoom(next: number) {
    const clamped = Math.max(1, Math.min(8, next));
    setZoom(clamped);
    setOffset((current) => Math.min(current, Math.max(0, length - Math.ceil(length / clamped))));
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (pointerStart === null || maxOffset === 0) return;
    const movement = pointerStart - event.clientX;
    if (Math.abs(movement) > 8) {
      setOffset((current) => Math.max(0, Math.min(maxOffset, current + Math.round(movement / 18))));
      setPointerStart(event.clientX);
    }
  }

  if (!result && chartLoading) {
    return <div className="viz-chart-empty"><Activity size={22} /><span>Aggregating the full dataset…</span></div>;
  }

  if (chartError) {
    return <div className="viz-chart-empty error-state"><Activity size={22} /><span>{chartError}</span></div>;
  }

  if (!result || (result.kpi === null && result.points.length === 0)) {
    return <div className="viz-chart-empty"><Activity size={22} /><span>Select compatible columns in the inspector.</span></div>;
  }

  if (chart.kind === "kpi") {
    return (
      <div className="kpi-view">
        <span>{chart.aggregation}</span>
        <strong>{formatNumber(result.kpi ?? 0)}</strong>
        <small>{chart.y} · {formatInteger(result.valid_count)} valid rows</small>
      </div>
    );
  }

  return (
    <div className="chart-stage">
      <div className="chart-toolbar" aria-label="Chart navigation">
        <span>
          {chartLoading
            ? "Refreshing…"
            : `${formatInteger(result.scanned_row_count)} rows · full dataset${result.truncated ? ` · display capped at ${formatInteger(points.length)} points` : ""}`}
          {" · Wheel to zoom · drag to pan"}
        </span>
        <button aria-label="Zoom out" disabled={zoom === 1} onClick={() => changeZoom(zoom - 1)} type="button"><ZoomOut size={14} /></button>
        <strong>{zoom}×</strong>
        <button aria-label="Zoom in" disabled={zoom === 8 || length < 4} onClick={() => changeZoom(zoom + 1)} type="button"><ZoomIn size={14} /></button>
        <button aria-label="Reset view" onClick={() => { setZoom(1); setOffset(0); }} type="button"><RotateCcw size={14} /></button>
      </div>
      <div
        className="chart-viewport"
        ref={viewportRef}
        tabIndex={0}
        onContextMenu={(event) => event.preventDefault()}
        onPointerDown={(event) => setPointerStart(event.clientX)}
        onPointerEnter={(event) => event.currentTarget.focus({ preventScroll: true })}
        onPointerLeave={() => { setPointerStart(null); setTooltip(null); }}
        onPointerMove={handlePointerMove}
        onPointerUp={() => setPointerStart(null)}
      >
        <SvgChart chart={chart} points={visible} series={result.series} seriesVisuals={seriesVisuals} setTooltip={setTooltip} />
        {tooltip && <div className="chart-tooltip" style={{ left: tooltip.x, top: tooltip.y }}><strong>{tooltip.title}</strong><span>{tooltip.value}</span></div>}
      </div>
      {maxOffset > 0 && <input aria-label="Visible data range" className="chart-scroll" max={maxOffset} min={0} onChange={(event) => setOffset(Number(event.target.value))} type="range" value={safeOffset} />}
      {result.series.length > 1 && <div aria-label="Chart legend" className="chart-legend">{seriesVisuals.map((visual) => <span key={visual.name} title={visual.name}><svg aria-hidden="true" className="legend-line" viewBox="0 0 30 6"><line stroke={visual.color} strokeDasharray={visual.dash} strokeWidth="3" x1="0" x2="30" y1="3" y2="3" /></svg>{visual.name}</span>)}</div>}
    </div>
  );
}

type PlotPoint = { x: number; y: number; xLabel: string; xRange?: [number, number]; series: string; group?: string; aggregation?: Aggregation; count?: number };
type SeriesVisual = { name: string; color: string; dash: string | undefined };

function SvgChart({ chart, points, series, seriesVisuals, setTooltip }: { chart: ChartConfig; points: PlotPoint[]; series: string[]; seriesVisuals: SeriesVisual[]; setTooltip: (tooltip: Tooltip) => void }) {
  const width = 720;
  const height = 270;
  const pad = { left: 64, right: 18, top: 18, bottom: 58 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const xValues = points.map((point) => point.x);
  const yValues = points.map((point) => point.y);
  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);
  const rawYMin = Math.min(0, ...yValues);
  const rawYMax = Math.max(...yValues);
  const xRange = xMax - xMin || 1;
  const yRange = rawYMax - rawYMin || 1;
  const visualBySeries = new Map(seriesVisuals.map((visual) => [visual.name, visual]));
  const pointsBySeries = new Map(series.map((seriesName) => [seriesName, [] as PlotPoint[]]));
  for (const point of points) {
    const seriesPoints = pointsBySeries.get(point.series);
    if (seriesPoints) seriesPoints.push(point);
  }
  const xPx = (value: number) => pad.left + ((value - xMin) / xRange) * plotWidth;
  const yPx = (value: number) => pad.top + plotHeight - ((value - rawYMin) / yRange) * plotHeight;
  const setPointTooltip = (event: ReactPointerEvent<SVGElement>, point: PlotPoint) => {
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!rect) return;
    const range = point.xRange ? ` · [${formatNumber(point.xRange[0])}, ${formatNumber(point.xRange[1])})` : "";
    setTooltip({ x: Math.min(rect.width - 150, event.clientX - rect.left + 10), y: Math.max(8, event.clientY - rect.top - 48), title: `${point.xLabel}${range}`, value: `${point.series} · ${chart.y || "Count"}: ${formatNumber(point.y)}${point.count ? ` · n=${point.count}` : ""}` });
  };
  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const xGroups = [...points.reduce((groups, point, index) => {
    const existing = groups.get(point.x) ?? { x: point.x, label: point.xLabel, indices: [] as number[] };
    existing.indices.push(index);
    groups.set(point.x, existing);
    return groups;
  }, new Map<number, { x: number; label: string; indices: number[] }>()).values()].sort((a, b) => a.x - b.x);
  const xTicks = sampleAxisTicks(xGroups, chart.layout.w <= 16 ? 4 : chart.layout.w <= 28 ? 6 : 8);
  const xTickPosition = (tick: typeof xGroups[number]) => {
    if (chart.kind === "bar" || chart.kind === "histogram") {
      const averageIndex = tick.indices.reduce((sum, index) => sum + index, 0) / tick.indices.length;
      return pad.left + ((averageIndex + 0.5) / Math.max(points.length, 1)) * plotWidth;
    }
    return xPx(tick.x);
  };
  const xAxisLabel = chart.x || "Rows";
  const yAxisLabel = chart.kind === "histogram"
    ? "Count"
    : chart.kind === "scatter"
      ? chart.y
      : chart.y && (chart.comparisonAggregations ?? []).length > 0
        ? `${chart.y} · multiple metrics`
        : chart.y
        ? `${aggregationLabel(chart.aggregation)} of ${chart.y}`
        : "Count";

  return (
    <svg aria-label={`${chart.title}, interactive ${kindLabels[chart.kind]}`} preserveAspectRatio="none" role="img" viewBox={`0 0 ${width} ${height}`}>
      {yTicks.map((tick) => {
        const value = rawYMin + yRange * tick;
        return <g key={tick}><line className="chart-gridline" x1={pad.left} x2={width - pad.right} y1={yPx(value)} y2={yPx(value)} /><text className="chart-axis-label" x={pad.left - 8} y={yPx(value) + 4} textAnchor="end">{formatCompact(value)}</text></g>;
      })}
      {xTicks.map((tick) => <g key={`${tick.x}-${tick.label}`}><line className="chart-gridline vertical" x1={xTickPosition(tick)} x2={xTickPosition(tick)} y1={pad.top} y2={pad.top + plotHeight} /><text className="chart-axis-label" textAnchor="middle" x={xTickPosition(tick)} y={height - 29}>{shortAxisLabel(chart.kind === "scatter" ? formatCompact(tick.x) : tick.label)}</text></g>)}
      {chart.kind === "bar" || chart.kind === "histogram" ? points.map((point, index) => {
        const barWidth = Math.max(4, plotWidth / Math.max(points.length, 1) * 0.7);
        const x = pad.left + index * (plotWidth / Math.max(points.length, 1)) + (plotWidth / Math.max(points.length, 1) - barWidth) / 2;
        return <rect className="chart-bar" fill={visualBySeries.get(point.series)?.color ?? PALETTE[0]} height={Math.max(1, yPx(rawYMin) - yPx(point.y))} key={`${point.xLabel}-${index}`} onPointerEnter={(event) => setPointTooltip(event, point)} onPointerMove={(event) => setPointTooltip(event, point)} rx={3} width={barWidth} x={x} y={yPx(point.y)} />;
      }) : chart.kind === "scatter" ? points.map((point, index) => <circle className="chart-point" cx={xPx(point.x)} cy={yPx(point.y)} fill={visualBySeries.get(point.series)?.color ?? PALETTE[0]} key={`${point.x}-${point.y}-${index}`} onPointerEnter={(event) => setPointTooltip(event, point)} onPointerMove={(event) => setPointTooltip(event, point)} r={4.5} />) : series.map((seriesName) => {
        const seriesPoints = pointsBySeries.get(seriesName) ?? [];
        const line = seriesPoints.map((point, index) => `${index === 0 ? "M" : "L"}${xPx(point.x)},${yPx(point.y)}`).join(" ");
        const visual = visualBySeries.get(seriesName) ?? { color: PALETTE[0], dash: undefined };
        return <g key={seriesName}><path className="chart-line" d={line} stroke={visual.color} strokeDasharray={visual.dash} />{seriesPoints.map((point, index) => <circle className="chart-point" cx={xPx(point.x)} cy={yPx(point.y)} fill={visual.color} key={`${point.x}-${index}`} onPointerEnter={(event) => setPointTooltip(event, point)} onPointerMove={(event) => setPointTooltip(event, point)} r={4} />)}</g>;
      })}
      <text className="chart-axis-title" textAnchor="middle" x={pad.left + plotWidth / 2} y={height - 7}>{xAxisLabel}</text>
      <text className="chart-axis-title" textAnchor="middle" transform={`rotate(-90 14 ${pad.top + plotHeight / 2})`} x={14} y={pad.top + plotHeight / 2}>{yAxisLabel}</text>
    </svg>
  );
}

function buildSmartDashboard(columns: DatasetColumn[], rows: RecordRow[]): ChartConfig[] {
  const numeric = columns.filter((column) => column.type === "number");
  const temporal = columns.filter((column) => column.type === "date");
  const categorical = columns.filter((column) => column.type === "text" || column.type === "boolean").filter((column) => cardinality(rows, column.name) <= 30);
  const charts: ChartConfig[] = [];
  if (temporal[0] && numeric[0]) charts.push(makeConfig("line", temporal[0].name, numeric[0].name, "", `Trend of ${numeric[0].name}`, defaultLayout("line", charts.length)));
  else if (categorical[0] && numeric[0]) charts.push(makeConfig("bar", categorical[0].name, numeric[0].name, "", `${numeric[0].name} by ${categorical[0].name}`, defaultLayout("bar", charts.length)));
  if (numeric[0]) charts.push(makeConfig("histogram", numeric[0].name, "", "", `${numeric[0].name} distribution`, defaultLayout("histogram", charts.length)));
  if (numeric[0] && numeric[1]) charts.push(makeConfig("scatter", numeric[0].name, numeric[1].name, categorical[0]?.name ?? "", `${numeric[1].name} vs ${numeric[0].name}`, defaultLayout("scatter", charts.length)));
  if (numeric[0]) charts.push(makeConfig("kpi", "", numeric[0].name, "", `Average ${numeric[0].name}`, defaultLayout("kpi", charts.length)));
  if (!charts.length && columns[0]) charts.push(makeConfig("bar", columns[0].name, "", "", `${columns[0].name} frequency`, defaultLayout("bar", charts.length)));
  return tidyChartLayouts(charts.slice(0, 4));
}

function createChart(kind: ChartKind, columns: DatasetColumn[], rows: RecordRow[], index: number) {
  const numeric = columns.filter((column) => column.type === "number");
  const categorical = columns.find((column) => column.type !== "number" && cardinality(rows, column.name) < 40);
  const x = kind === "histogram" ? numeric[0]?.name ?? "" : kind === "scatter" ? numeric[0]?.name ?? columns[0]?.name ?? "" : categorical?.name ?? columns[0]?.name ?? "";
  const y = kind === "scatter" ? numeric[1]?.name ?? numeric[0]?.name ?? "" : numeric[0]?.name ?? "";
  return makeConfig(kind, x, y, "", `${kindLabels[kind]} ${index + 1}`, defaultLayout(kind, index));
}

function makeConfig(kind: ChartKind, x: string, y: string, group: string, title: string, layout: ChartLayout): ChartConfig {
  return { id: `${kind}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, kind, title, x, y, xEpsilon: 0, group, aggregation: "average", comparisonAggregations: [], selectedGroups: null, layout };
}

function readSessionDashboard(datasetId: string, columns: DatasetColumn[]): ChartConfig[] | null {
  try {
    const saved = window.sessionStorage.getItem(storageKey(datasetId));
    if (saved === null) return null;
    const decoded = JSON.parse(saved) as unknown;
    const isLegacyArray = Array.isArray(decoded);
    const stored = isLegacyArray ? decoded : (decoded as { version?: number; charts?: unknown }).charts;
    if (!Array.isArray(stored)) return null;
    const looksLikeLegacyGrid = stored.some((item) => {
      const layout = (item as { layout?: ChartLayout } | null)?.layout;
      return Boolean(layout && (layout.w < 12 || layout.h < 24));
    });
    const shouldScaleLegacyGrid = isLegacyArray || (decoded as { version?: number }).version !== LAYOUT_VERSION || looksLikeLegacyGrid;
    const parsed = stored as Array<ChartConfig & { layout?: ChartLayout; size?: ChartSize }>;
    const names = new Set(columns.map((column) => column.name));
    return parsed
      .filter((chart) => chart && kindLabels[chart.kind] && (!chart.x || names.has(chart.x)) && (!chart.y || names.has(chart.y)))
      .map((chart, index) => ({
        ...chart,
        xEpsilon: chart.xEpsilon ?? 0,
        comparisonAggregations: chart.comparisonAggregations ?? [],
        selectedGroups: chart.selectedGroups ?? null,
        layout: normalizeLayout(chart.layout
          ? shouldScaleLegacyGrid ? scaleLegacyGridLayout(chart.layout) : chart.layout
          : legacyLayout(chart.size, index)
        )
      }));
  } catch {
    return null;
  }
}

function describeEncoding(chart: ChartConfig) {
  if (chart.kind === "histogram") return `${chart.x} · binned count`;
  if (chart.kind === "kpi") return `${chart.aggregation} of ${chart.y}`;
  return `${chart.x || "row"} → ${chart.y || "count"}${chart.xEpsilon > 0 ? ` · ε=${formatNumber(chart.xEpsilon)}` : ""}${chart.group ? ` · by ${chart.group}` : ""}`;
}

function defaultLayout(kind: ChartKind, index: number): ChartLayout {
  const isKpi = kind === "kpi";
  return {
    x: (index % 2) * 24,
    y: Math.floor(index / 2) * 40,
    w: isKpi ? 16 : 24,
    h: isKpi ? 28 : 40
  };
}

function legacyLayout(size: ChartSize | undefined, index: number): ChartLayout {
  const width = size === "wide" ? 48 : size === "compact" ? 16 : 24;
  return { x: width === 48 ? 0 : index % 2 ? 48 - width : 0, y: Math.floor(index / 2) * 40, w: width, h: size === "compact" ? 28 : 40 };
}

function scaleLegacyGridLayout(layout: ChartLayout): ChartLayout {
  return { x: layout.x * 4, y: layout.y * 4, w: layout.w * 4, h: layout.h * 4 };
}

function normalizeLayout(layout: ChartLayout): ChartLayout {
  const w = Math.max(12, Math.min(GRID_COLUMNS, Math.round(layout.w)));
  const h = Math.max(24, Math.round(layout.h));
  return {
    x: Math.max(0, Math.min(GRID_COLUMNS - w, Math.round(layout.x))),
    y: Math.max(0, Math.round(layout.y)),
    w,
    h
  };
}

function tidyChartLayouts(charts: ChartConfig[]) {
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

function findOpenLayout(preferred: ChartLayout, charts: ChartConfig[]) {
  let candidate = normalizeLayout(preferred);
  while (hasLayoutCollision(candidate, "", charts)) {
    candidate = { ...candidate, y: candidate.y + 1 };
  }
  return candidate;
}

function hasLayoutCollision(layout: ChartLayout, chartId: string, charts: ChartConfig[]) {
  return charts.some((chart) => chart.id !== chartId
    && layout.x < chart.layout.x + chart.layout.w
    && layout.x + layout.w > chart.layout.x
    && layout.y < chart.layout.y + chart.layout.h
    && layout.y + layout.h > chart.layout.y
  );
}

function canvasMetrics(canvas: HTMLElement) {
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

function calculateInteractionLayout(
  interaction: LayoutInteraction,
  event: PointerEvent,
  canvas: HTMLElement,
  charts: ChartConfig[]
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

function sampleAxisTicks<T>(values: T[], limit: number) {
  if (values.length <= limit) return values;
  const indices = new Set<number>();
  for (let index = 0; index < limit; index += 1) {
    indices.add(Math.round(index * (values.length - 1) / (limit - 1)));
  }
  return [...indices].map((index) => values[index]);
}

function buildSeriesVisuals(points: PlotPoint[], series: string[], metricOrder: Aggregation[], groupColors: Map<string, string>): SeriesVisual[] {
  return series.map((name) => {
    const point = points.find((item) => item.series === name);
    const metricIndex = point?.aggregation ? Math.max(0, metricOrder.indexOf(point.aggregation)) : 0;
    const group = point?.group ?? name;
    return {
      name,
      color: groupColors.get(group) ?? PALETTE[0],
      dash: seriesDash(metricIndex)
    };
  });
}

function assignDistinctGroupColors(points: PlotPoint[], assignments: Map<string, string>) {
  const groups = unique(points.map((point) => point.group ?? point.series)).sort((left, right) => left.localeCompare(right));
  for (const group of groups) {
    if (assignments.has(group)) continue;
    const used = new Set(assignments.values());
    const available = PALETTE.filter((color) => !used.has(color));
    if (available.length === 0) {
      assignments.set(group, generatedGroupColor(group, used));
      continue;
    }
    if (used.size === 0) {
      assignments.set(group, available[stableHash(group) % available.length]);
      continue;
    }
    assignments.set(group, available.reduce((best, candidate) =>
      minimumColorDistance(candidate, used) > minimumColorDistance(best, used) ? candidate : best
    ));
  }
  return assignments;
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

function shortAxisLabel(value: string) {
  return value.length > 16 ? `${value.slice(0, 14)}…` : value;
}

function storageKey(datasetId: string) { return `ml-app:visual-dashboard:${datasetId}`; }
function unique<T>(values: T[]) { return [...new Set(values)]; }
function cardinality(rows: RecordRow[], column: string) { return new Set(rows.slice(0, 1000).map((row) => displayValue(row[column]))).size; }
function displayValue(value: CellValue) { return value === null || value === "" ? "Missing" : String(value); }
function aggregationLabel(aggregation: Aggregation) {
  if (aggregation === "std") return "Std. dev.";
  return aggregation.charAt(0).toUpperCase() + aggregation.slice(1);
}
function formatInteger(value: number) { return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value); }
function formatNumber(value: number) { return new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(value); }
function formatCompact(value: number) { return new Intl.NumberFormat(undefined, { notation: Math.abs(value) >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value); }
