import {
  Activity,
  BarChart3,
  Box as BoxIcon,
  GripVertical,
  Info,
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
  VisualizationKind,
  VisualizationTrend,
  VisualizationTrendCurve
} from "../api/client";
import {
  createVisualizationDrillRequest,
  type VisualizationDrillRequest,
} from "./drillContext";
import { TrendFitDetails } from "./TrendFitDetails";
import { useVisualizationResult } from "./useVisualizationResult";
import { formatInteger, formatNumber } from "./visualizationFormatters";
import { createNumericScale, formatAxisTick, selectCategoricalAxisTicks, shortAxisLabel } from "./visualizationScales";
import { assignDistinctColors, buildSeriesVisuals, SERIES_PALETTE as PALETTE, type SeriesVisual } from "./visualizationSeries";
import {
  CANVAS_PADDING,
  calculateInteractionLayout,
  canvasMetrics,
  defaultLayout,
  findOpenLayout,
  GRID_COLUMNS,
  GRID_GAP,
  GRID_ROW_HEIGHT,
  hasLayoutCollision,
  legacyLayout,
  normalizeLayout,
  scaleLegacyGridLayout,
  tidyChartLayouts,
  type AlignmentGuides,
  type ChartLayout,
  type LayoutInteraction,
} from "./visualizationLayout";

type CellValue = string | number | boolean | null;
type RecordRow = Record<string, CellValue>;
type ChartKind = VisualizationKind;
type ChartSize = "compact" | "medium" | "wide";
type Aggregation = VisualizationAggregation;
type KpiCondition = "none" | "eq" | "lt" | "lte" | "gt" | "gte";

type ChartConfig = {
  id: string;
  kind: ChartKind;
  title: string;
  x: string;
  y: string;
  xEpsilon: number;
  yEpsilon: number;
  trend: VisualizationTrend;
  polynomialDegree: number;
  group: string;
  aggregation: Aggregation;
  comparisonAggregations: Aggregation[];
  selectedGroups: string[] | null;
  stacked: boolean;
  kpiCondition: KpiCondition;
  kpiThreshold: number;
  featureColumns: string[];
  targetColumn: string;
  maxLag: number;
  rollingWindow: number;
  driverColumn: string;
  layout: ChartLayout;
};

type Tooltip = { x: number; y: number; title: string; value: string } | null;

type VisualizationDashboardProps = {
  datasets: DataAsset[];
  datasetId: string;
  setDatasetId: (datasetId: string) => void;
  setNotice: (message: string) => void;
  onDrill: (request: VisualizationDrillRequest) => void;
};

const SAMPLE_LIMIT = 1000;
const LAYOUT_VERSION = 2;
const NATURAL_COLLATOR = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
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
  { kind: "boxplot", label: "Box plot", description: "Quartiles, spread and outliers", icon: BoxIcon },
  { kind: "kpi", label: "KPI", description: "A single key measure", icon: Maximize2 },
  { kind: "projection", label: "PCA projection", description: "Reduce many features to a 2-D map", icon: Sparkles },
  { kind: "time_series", label: "Time series", description: "Full-data temporal trend and rolling mean", icon: LineChart },
  { kind: "autocorrelation", label: "Autocorrelation", description: "Correlation across ordered lags", icon: Activity },
  { kind: "lag_relationship", label: "Lag relationship", description: "Driver-to-signal correlation by lag", icon: Activity }
];

const kindLabels: Record<ChartKind, string> = {
  line: "Trend line",
  bar: "Category bars",
  scatter: "Scatter plot",
  histogram: "Distribution",
  boxplot: "Box plot",
  kpi: "KPI",
  projection: "PCA projection",
  time_series: "Time series",
  autocorrelation: "Autocorrelation",
  lag_relationship: "Lag relationship"
};

export function VisualizationDashboard({ datasets, datasetId, setDatasetId, setNotice, onDrill }: VisualizationDashboardProps) {
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
              {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{datasetVersionLabel(dataset, datasets)}</option>)}
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
                  <ChartView chart={chart} datasetId={datasetId} onDrill={onDrill} xType={columns.find((column) => column.name === chart.x)?.type} />
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

function datasetVersionLabel(dataset: DataAsset, datasets: DataAsset[]) {
  const latest = Math.max(
    ...datasets
      .filter((item) => item.logical_id === dataset.logical_id && item.status !== "deleted")
      .map((item) => item.version_number),
    dataset.version_number
  );
  return `${dataset.name} · v${dataset.version_number}${dataset.version_number === latest ? " (latest)" : ""}`;
}

function ChartInspector({ chart, columns, datasetId, rows, onChange }: { chart: ChartConfig; columns: DatasetColumn[]; datasetId: string; rows: RecordRow[]; onChange: (patch: Partial<ChartConfig>) => void }) {
  const numericColumns = columns.filter((column) => column.type === "number");
  const timeColumns = columns.filter((column) => column.type === "date" || /time|date/i.test(column.name));
  const xColumn = columns.find((column) => column.name === chart.x);
  const groupingColumns = columns.filter((column) => column.name !== chart.x && column.name !== chart.y && cardinality(rows, column.name) <= 20);
  const hasSeriesGroup = groupingColumns.some((column) => column.name === chart.group);
  const [availableGroups, setAvailableGroups] = useState<string[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupsTruncated, setGroupsTruncated] = useState(false);
  const effectiveSelectedGroups = chart.selectedGroups ?? availableGroups;

  useEffect(() => {
    if (chart.group && !hasSeriesGroup) {
      onChange({ group: "", selectedGroups: null, stacked: false });
    }
  }, [chart.group, hasSeriesGroup, onChange]);

  useEffect(() => {
    if (!hasSeriesGroup) {
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
          setAvailableGroups(result.values.sort(naturalCompare));
          setGroupsTruncated(result.truncated);
        })
        .catch(() => current && setAvailableGroups([]))
        .finally(() => current && setGroupsLoading(false));
    }, 250);
    return () => {
      current = false;
      window.clearTimeout(timeout);
    };
  }, [chart.group, datasetId, hasSeriesGroup]);
  return (
    <div className="chart-inspector">
      <div className="viz-sidebar-heading"><div><p className="eyebrow">Selected view</p><h2>Configure</h2></div><Settings2 size={17} /></div>
      <label>Title<input value={chart.title} onChange={(event) => onChange({ title: event.target.value })} /></label>
      {chart.kind === "projection" && (
        <fieldset className="metric-series-fieldset projection-fields">
          <legend>Numeric input features</legend>
          <div className="metric-series-options">
            {numericColumns.filter((column) => column.name !== chart.targetColumn).map((column) => (
              <label key={column.name}>
                <input
                  checked={chart.featureColumns.includes(column.name)}
                  disabled={chart.featureColumns.includes(column.name) && chart.featureColumns.length <= 2}
                  onChange={(event) => onChange({
                    featureColumns: event.target.checked
                      ? unique([...chart.featureColumns, column.name]).slice(0, 50)
                      : chart.featureColumns.filter((name) => name !== column.name)
                  })}
                  type="checkbox"
                />
                {column.name}
              </label>
            ))}
          </div>
          <label>Target / color
            <select value={chart.targetColumn} onChange={(event) => onChange({ targetColumn: event.target.value })}>
              <option value="">No target (structure only)</option>
              {columns.filter((column) => !chart.featureColumns.includes(column.name)).map((column) => <option key={column.name} value={column.name}>{column.name} · {column.type}</option>)}
            </select>
          </label>
          <p className="group-selection-note">PCA is fitted on every complete row. Numeric targets use a continuous color scale; categorical targets use class colors.</p>
        </fieldset>
      )}
      {chart.kind !== "kpi" && chart.kind !== "projection" && (
        <label>{chart.kind === "histogram" || chart.kind === "boxplot" ? "Measure" : "Horizontal axis"}
          <select value={chart.x} onChange={(event) => {
            const x = event.target.value;
            onChange(x === chart.group
              ? { x, xEpsilon: 0, group: "", selectedGroups: null, stacked: false }
              : { x, xEpsilon: 0 });
          }}>
            {(chart.kind === "time_series" || chart.kind === "autocorrelation" || chart.kind === "lag_relationship" ? timeColumns : chart.kind === "histogram" || chart.kind === "boxplot" || chart.kind === "scatter" ? numericColumns : columns).map((column) => <option key={column.name} value={column.name}>{column.name} · {column.type}</option>)}
          </select>
        </label>
      )}
      {(chart.kind === "line" || chart.kind === "bar" || chart.kind === "scatter") && xColumn?.type === "number" && (
        <EpsilonField axis="X" automaticAtZero={chart.kind === "scatter"} value={chart.xEpsilon ?? 0} onChange={(xEpsilon) => onChange({ xEpsilon })} />
      )}
      {chart.kind !== "histogram" && chart.kind !== "boxplot" && chart.kind !== "projection" && (
        <label>{chart.kind === "kpi" ? "Measure" : "Vertical axis"}
          <select value={chart.y} onChange={(event) => {
            const y = event.target.value;
            onChange(y === chart.group
              ? { y, yEpsilon: 0, group: "", selectedGroups: null, stacked: false }
              : { y, yEpsilon: 0 });
          }}>
            {numericColumns.map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}
          </select>
        </label>
      )}
      {chart.kind === "scatter" && (
        <EpsilonField axis="Y" automaticAtZero value={chart.yEpsilon ?? 0} onChange={(yEpsilon) => onChange({ yEpsilon })} />
      )}
      {chart.kind === "scatter" && (
        <label>Trend
          <select value={chart.trend ?? "none"} onChange={(event) => onChange({ trend: event.target.value as VisualizationTrend })}>
            <option value="none">None</option>
            <option value="linear">Straight line</option>
            <option value="spline">Spline</option>
            <option value="polynomial">Polynomial</option>
            <option value="exponential">Exponential curve</option>
          </select>
        </label>
      )}
      {chart.kind === "scatter" && chart.trend === "polynomial" && (
        <label>Polynomial degree
          <input min="2" max="5" step="1" type="number" value={chart.polynomialDegree ?? 2} onChange={(event) => onChange({ polynomialDegree: Math.max(2, Math.min(5, Number(event.target.value) || 2)) })} />
        </label>
      )}
      {chart.kind === "time_series" && (
        <label>Rolling window (display bins)<input min="2" max="200" type="number" value={chart.rollingWindow} onChange={(event) => onChange({ rollingWindow: Math.max(2, Math.min(200, Number(event.target.value) || 12)) })} /></label>
      )}
      {(chart.kind === "autocorrelation" || chart.kind === "lag_relationship") && (
        <label>Maximum lag<input min="1" max="120" type="number" value={chart.maxLag} onChange={(event) => onChange({ maxLag: Math.max(1, Math.min(120, Number(event.target.value) || 48)) })} /></label>
      )}
      {chart.kind === "lag_relationship" && (
        <label>Driver signal<select value={chart.driverColumn} onChange={(event) => onChange({ driverColumn: event.target.value })}>
          {numericColumns.filter((column) => column.name !== chart.y).map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}
        </select></label>
      )}
      {(chart.kind === "line" || chart.kind === "bar" || chart.kind === "kpi") && (
        <label>Primary aggregation<select value={chart.aggregation} onChange={(event) => {
          const aggregation = event.target.value as Aggregation;
          onChange({ aggregation, comparisonAggregations: (chart.comparisonAggregations ?? []).filter((item) => item !== aggregation) });
        }}>
          {aggregationOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select></label>
      )}
      {chart.kind === "kpi" && (
        <fieldset className="kpi-threshold-fieldset">
          <legend>Target condition</legend>
          <label>Condition
            <select value={chart.kpiCondition ?? "none"} onChange={(event) => onChange({ kpiCondition: event.target.value as KpiCondition })}>
              <option value="none">No target</option>
              <option value="eq">Equals</option>
              <option value="lt">Less than</option>
              <option value="lte">Less than or equal</option>
              <option value="gt">Greater than</option>
              <option value="gte">Greater than or equal</option>
            </select>
          </label>
          {chart.kpiCondition !== "none" && (
            <label>Threshold
              <input step="any" type="number" value={chart.kpiThreshold ?? 0} onChange={(event) => onChange({ kpiThreshold: Number(event.target.value) || 0 })} />
            </label>
          )}
        </fieldset>
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
      {(chart.kind === "line" || chart.kind === "bar" || chart.kind === "scatter" || chart.kind === "histogram" || chart.kind === "boxplot" || chart.kind === "kpi") && (
        <label>{chart.kind === "kpi" ? "Filter column" : "Color / series"}<select value={hasSeriesGroup ? chart.group : ""} onChange={(event) => {
          const group = event.target.value;
          onChange({ group, selectedGroups: null, stacked: group ? chart.stacked : false });
        }}>
          <option value="">{chart.kind === "kpi" ? "No filter" : "Single series"}</option>{groupingColumns.map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}
        </select></label>
      )}
      {chart.kind === "bar" && hasSeriesGroup && (
        <label className="stacked-bars-toggle">
          <input
            checked={chart.stacked ?? false}
            onChange={(event) => onChange({ stacked: event.target.checked })}
            type="checkbox"
          />
          <span><strong>Stacked</strong><small>Stack groups within each metric</small></span>
        </label>
      )}
      {hasSeriesGroup && (
        <fieldset className="group-selection-fieldset">
          <legend>{chart.kind === "kpi" ? "Filter values" : "Group selection"}</legend>
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

function EpsilonField({ axis, automaticAtZero = false, value, onChange }: { axis: "X" | "Y"; automaticAtZero?: boolean; value: number; onChange: (value: number) => void }) {
  return (
    <label>
      <span className="epsilon-label">{axis} epsilon
        <span className="epsilon-info" tabIndex={0} aria-label={`${axis} epsilon information`}>
          <Info size={13} />
          <span className="epsilon-tooltip">{automaticAtZero ? "0 selects an automatic density-bin width for bounded rendering. " : "0 keeps exact values. "}A positive epsilon groups values into non-overlapping buckets of width 2 × ε: [center − ε, center + ε).</span>
        </span>
      </span>
      <input min="0" onChange={(event) => onChange(Math.max(0, Number(event.target.value) || 0))} step="any" type="number" value={value} />
    </label>
  );
}

function ChartView({ chart, datasetId, onDrill, xType }: { chart: ChartConfig; datasetId: string; onDrill: (request: VisualizationDrillRequest) => void; xType?: DatasetColumn["type"] }) {
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState(0);
  const [tooltip, setTooltip] = useState<Tooltip>(null);
  const [pointerStart, setPointerStart] = useState<number | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const lastWheelAtRef = useRef(0);
  const colorAssignmentsRef = useRef<Map<string, string>>(new Map());
  const requestGroup = chart.group !== chart.x && chart.group !== chart.y ? chart.group : "";
  const query = useMemo<DatasetVisualizationRequest>(() => ({
    kind: chart.kind,
    x: chart.x,
    y: chart.y,
    group: requestGroup,
    aggregations: unique([chart.aggregation, ...(chart.comparisonAggregations ?? [])]),
    selected_groups: requestGroup ? chart.selectedGroups ?? null : null,
    x_epsilon: chart.xEpsilon ?? 0,
    y_epsilon: chart.yEpsilon ?? 0,
    trend: chart.kind === "scatter" ? chart.trend ?? "none" : "none",
    polynomial_degree: chart.polynomialDegree ?? 2,
    max_points: 2000,
    bins: 80,
    feature_columns: chart.kind === "projection" ? chart.featureColumns : [],
    target_column: chart.kind === "projection" ? chart.targetColumn : "",
    reduction_method: "pca",
    max_lag: chart.maxLag,
    rolling_window: chart.rollingWindow,
    driver_column: chart.driverColumn
  }), [chart.aggregation, chart.comparisonAggregations, chart.driverColumn, chart.featureColumns, chart.kind, chart.maxLag, chart.polynomialDegree, chart.rollingWindow, chart.selectedGroups, chart.targetColumn, chart.trend, chart.x, chart.xEpsilon, chart.y, chart.yEpsilon, requestGroup]);
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

  const points = useMemo(() => {
    const source = result?.points ?? [];
    if (chart.kind !== "boxplot") return source;
    return [...source]
      .sort((left, right) => naturalCompare(left.xLabel, right.xLabel))
      .map((point, index) => ({ ...point, x: index }));
  }, [chart.kind, result?.points]);
  const series = useMemo(
    () => [...(result?.series ?? [])].sort(naturalCompare),
    [result?.series]
  );
  const trendValidCount = result?.trends?.reduce((total, trend) => total + trend.valid_count, 0) ?? 0;
  const trendScope = chart.kind === "scatter" && chart.trend !== "none" && result?.trends?.length
    ? ` · ${chart.trend} trend per series · ${formatInteger(trendValidCount)} fitted rows${result.trends.some((trend) => trend.approximate) ? " · spline smoothed from 24 full-data bins" : ""}`
    : "";
  const reductionScope = result?.reduction_metadata
    ? ` · PCA fit on ${formatInteger(result.reduction_metadata.complete_case_rows)} complete rows · PC1/PC2 explain ${formatNumber(100 * (result.reduction_metadata.explained_variance_ratio ?? []).reduce((sum, value) => sum + value, 0))}%`
    : "";
  const colorAssignments = useMemo(
    () => assignDistinctColors(points, chart.kind, colorAssignmentsRef.current),
    [chart.kind, points]
  );
  const seriesVisuals = useMemo(
    () => buildSeriesVisuals(chart.kind, points, series, metricOrder, colorAssignments),
    [chart.kind, colorAssignments, metricOrder, points, series]
  );
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

  if (!result) {
    return <div className="viz-chart-empty"><Activity size={22} /><span>Select compatible columns in the inspector.</span></div>;
  }

  if (result.kpi === null && result.points.length === 0) {
    return <div className="viz-chart-empty"><Activity size={22} /><span>No valid rows match the selected filters.</span></div>;
  }

  if (chart.kind === "kpi") {
    const value = result.kpi ?? 0;
    const condition = chart.kpiCondition ?? "none";
    const hasTarget = condition !== "none";
    const targetMet = !hasTarget || evaluateKpiCondition(value, condition, chart.kpiThreshold ?? 0);
    const filterLabel = chart.group
      ? ` · ${chart.group}: ${chart.selectedGroups == null ? "all" : chart.selectedGroups.join(", ") || "none"}`
      : "";
    return (
      <div className={`kpi-view ${hasTarget ? targetMet ? "target-met" : "target-missed" : ""}`}>
        <span>{chart.aggregation}</span>
        <strong>{formatNumber(value)}</strong>
        <small>{chart.y}{filterLabel} · {formatInteger(result.valid_count)} valid rows</small>
        {hasTarget && <div className="kpi-target-status"><b>{targetMet ? "Target met" : "Target missed"}</b><span>{kpiConditionSymbol(condition)} {formatNumber(chart.kpiThreshold ?? 0)}</span></div>}
      </div>
    );
  }

  return (
    <div className="chart-stage">
      <div className="chart-toolbar" aria-label="Chart navigation">
        <span>
          {chartLoading
            ? "Refreshing…"
            : `${formatInteger(result.scanned_row_count)} rows · full dataset${result.approximation_method === "binned_gaussian_kde" ? " · KDE from full-data aggregates" : ""}${result.truncated ? ` · display capped at ${formatInteger(points.length)} points` : ""}${trendScope}${reductionScope}`}
          {chart.kind === "projection" ? " · Wheel to zoom · drag to pan" : " · Wheel to zoom · drag to pan · Double-click element to drill the data"}
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
        <SvgChart
          chart={chart}
          onPointDoubleClick={(point) => { if (chart.kind !== "projection") onDrill(createVisualizationDrillRequest(datasetId, chart, point, xType)); }}
          points={visible}
          trends={result.trends ?? []}
          series={series}
          seriesVisuals={seriesVisuals}
          setTooltip={setTooltip}
          xType={xType}
        />
        {tooltip && <div className="chart-tooltip" style={{ left: tooltip.x, top: tooltip.y }}><strong>{tooltip.title}</strong><span>{tooltip.value}</span></div>}
      </div>
      {result.trends?.length > 0 && <TrendFitDetails trends={result.trends} />}
      {maxOffset > 0 && <input aria-label="Visible data range" className="chart-scroll" max={maxOffset} min={0} onChange={(event) => setOffset(Number(event.target.value))} type="range" value={safeOffset} />}
      {result.series.length > 1 && <SeriesLegend chartKind={chart.kind} visuals={seriesVisuals} />}
      {chart.kind === "projection" && result.reduction_metadata?.target_type === "continuous" && <ContinuousTargetLegend label={chart.targetColumn} points={points} />}
    </div>
  );
}

type PlotPoint = {
  x: number;
  y: number;
  xLabel: string;
  xRange?: [number, number];
  yRange?: [number, number];
  xRangeInclusive?: boolean;
  yRangeInclusive?: boolean;
  series: string;
  group?: string;
  aggregation?: Aggregation;
  count?: number;
  minimum?: number;
  q1?: number;
  median?: number;
  q3?: number;
  maximum?: number;
  lowerWhisker?: number;
  upperWhisker?: number;
  outlierCount?: number;
  targetValue?: number | null;
};
type AxisTick = { value: number; label: string; categoryIndex?: number };

function SeriesLegend({ chartKind, visuals }: { chartKind: ChartKind; visuals: SeriesVisual[] }) {
  return (
    <div aria-label="Chart legend" className="chart-legend">
      {visuals.map((visual) => (
        <span key={visual.name} title={visual.name}>
          {chartKind === "line" || chartKind === "histogram" ? (
            <svg aria-hidden="true" className="legend-line" viewBox="0 0 30 6">
              <line stroke={visual.color} strokeDasharray={visual.dash} strokeWidth="3" x1="0" x2="30" y1="3" y2="3" />
            </svg>
          ) : (
            <i
              aria-hidden="true"
              className={`legend-color-marker ${chartKind === "scatter" ? "round" : ""}`}
              style={{ backgroundColor: visual.color }}
            />
          )}
          {visual.name}
        </span>
      ))}
    </div>
  );
}

function ContinuousTargetLegend({ label, points }: { label: string; points: PlotPoint[] }) {
  const values = points.map((point) => point.targetValue).filter((value): value is number => value !== null && value !== undefined);
  if (!values.length) return null;
  return <div className="projection-gradient-legend"><span>{label}</span><i /><small>{formatNumber(Math.min(...values))}</small><small>{formatNumber(Math.max(...values))}</small></div>;
}

function SvgChart({ chart, onPointDoubleClick, points, trends, series, seriesVisuals, setTooltip, xType }: { chart: ChartConfig; onPointDoubleClick: (point: PlotPoint) => void; points: PlotPoint[]; trends: VisualizationTrendCurve[]; series: string[]; seriesVisuals: SeriesVisual[]; setTooltip: (tooltip: Tooltip) => void; xType?: DatasetColumn["type"] }) {
  const width = 720;
  const height = 270;
  const pad = { left: 64, right: 18, top: 18, bottom: 58 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const xValues = points.map((point) => point.x);
  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);
  const visibleTrends = trends.map((trend) => ({ ...trend, points: trend.points.filter((point) => point.x >= xMin && point.x <= xMax) }));
  const yValues = [
    ...points.flatMap((point) => chart.kind === "boxplot"
      ? [point.lowerWhisker, point.q1, point.median, point.q3, point.upperWhisker].filter((value): value is number => value !== undefined)
      : [point.y]),
    ...visibleTrends.flatMap((trend) => trend.points.map((point) => point.y)),
  ];
  const stackedBounds = chart.kind === "bar" && chart.stacked ? stackedBarBounds(points) : null;
  const dataYMin = stackedBounds?.[0] ?? Math.min(...yValues);
  const dataYMax = stackedBounds?.[1] ?? Math.max(...yValues);
  const yScale = createNumericScale(dataYMin, dataYMax, 5, chart.kind === "bar" || chart.kind === "histogram");
  const numericXAxis = chart.kind === "scatter" || chart.kind === "projection" || chart.kind === "autocorrelation" || chart.kind === "lag_relationship" || chart.kind === "histogram" || (chart.kind === "line" && xType === "number");
  const xTickLimit = Math.max(2, Math.floor(plotWidth / 90));
  const xScaleIncludesZeroBoundary = chart.kind === "histogram" && (xMin === 0 || xMax === 0);
  const xScale = numericXAxis ? createNumericScale(xMin, xMax, xTickLimit, xScaleIncludesZeroBoundary) : null;
  const categoricalXRange = xMax - xMin || 1;
  const visualBySeries = new Map(seriesVisuals.map((visual) => [visual.name, visual]));
  const targetValues = points.map((point) => point.targetValue).filter((value): value is number => value !== null && value !== undefined);
  const targetMin = targetValues.length ? Math.min(...targetValues) : 0;
  const targetMax = targetValues.length ? Math.max(...targetValues) : 1;
  const pointsBySeries = new Map(series.map((seriesName) => [seriesName, [] as PlotPoint[]]));
  for (const point of points) {
    const seriesPoints = pointsBySeries.get(point.series);
    if (seriesPoints) seriesPoints.push(point);
  }
  const xPx = (value: number) => {
    const scaleMin = xScale?.min ?? xMin;
    const scaleRange = (xScale?.max ?? xMax) - scaleMin || categoricalXRange;
    return pad.left + ((value - scaleMin) / scaleRange) * plotWidth;
  };
  const yPx = (value: number) => pad.top + plotHeight - ((value - yScale.min) / (yScale.max - yScale.min)) * plotHeight;
  const setPointTooltip = (event: ReactPointerEvent<SVGElement>, point: PlotPoint) => {
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!rect) return;
    if (chart.kind === "boxplot") {
      setTooltip({
        x: Math.min(rect.width - 210, event.clientX - rect.left + 10),
        y: Math.max(8, event.clientY - rect.top - 70),
        title: `${point.xLabel} · n=${formatInteger(point.count ?? 0)}`,
        value: `min ${formatNumber(point.minimum ?? 0)} · Q1 ${formatNumber(point.q1 ?? 0)} · median ${formatNumber(point.median ?? 0)} · Q3 ${formatNumber(point.q3 ?? 0)} · max ${formatNumber(point.maximum ?? 0)} · outliers ${formatInteger(point.outlierCount ?? 0)}`,
      });
      return;
    }
    const range = point.xRange
      ? ` · [${formatNumber(point.xRange[0])}, ${formatNumber(point.xRange[1])}${point.xRangeInclusive ? "]" : ")"}`
      : "";
    const measure = chart.kind === "projection" ? "PC2" : chart.kind === "histogram" ? "Density" : point.aggregation === "count" ? `Count of ${chart.y || "rows"}` : chart.y || "Count";
    const targetLabel = chart.kind === "projection" && chart.targetColumn ? ` · ${chart.targetColumn}: ${point.targetValue == null ? point.series : formatNumber(point.targetValue)}` : "";
    setTooltip({ x: Math.min(rect.width - 180, event.clientX - rect.left + 10), y: Math.max(8, event.clientY - rect.top - 48), title: `${point.xLabel}${range}`, value: `${point.series} · ${measure}: ${formatNumber(point.y)}${targetLabel}${point.count ? ` · n=${point.count}` : ""}` });
  };
  const xGroups = [...points.reduce((groups, point, index) => {
    const existing = groups.get(point.x) ?? { x: point.x, label: point.xLabel, indices: [] as number[] };
    existing.indices.push(index);
    groups.set(point.x, existing);
    return groups;
  }, new Map<number, { x: number; label: string; indices: number[] }>()).values()].sort((a, b) => a.x - b.x);
  const xGroupIndex = new Map(xGroups.map((group, index) => [group.x, index]));
  const xTicks: AxisTick[] = xScale
    ? xScale.ticks.map((value) => ({ value, label: formatAxisTick(value, xScale.step) }))
    : selectCategoricalAxisTicks(xGroups, plotWidth).map((tick) => ({
        value: tick.x,
        label: tick.label,
        categoryIndex: xGroupIndex.get(tick.x),
      }));
  const xTickPosition = (tick: AxisTick) => tick.categoryIndex === undefined
    ? xPx(tick.value)
    : pad.left + ((tick.categoryIndex + 0.5) / Math.max(xGroups.length, 1)) * plotWidth;
  const categoricalXPx = (value: number) => pad.left + (((xGroupIndex.get(value) ?? 0) + 0.5) / Math.max(xGroups.length, 1)) * plotWidth;
  const barMarks = chart.kind === "bar"
    ? layoutBarMarks(chart, points, series, plotWidth, pad.left)
    : [];
  const xAxisLabel = chart.kind === "projection" ? "Principal component 1" : chart.kind === "autocorrelation" || chart.kind === "lag_relationship" ? "Lag" : chart.kind === "boxplot" ? chart.group || "Dataset" : chart.x || "Rows";
  const yAxisLabel = chart.kind === "histogram"
    ? "Density"
    : chart.kind === "boxplot"
      ? chart.x
    : chart.kind === "autocorrelation" || chart.kind === "lag_relationship"
      ? "Correlation"
    : chart.kind === "projection"
      ? "Principal component 2"
    : chart.kind === "scatter"
      ? chart.y
      : chart.y && (chart.comparisonAggregations ?? []).length > 0
        ? `${chart.y} · multiple metrics`
        : chart.y
        ? `${aggregationLabel(chart.aggregation)} of ${chart.y}`
        : "Count";

  return (
    <svg aria-label={`${chart.title}, interactive ${kindLabels[chart.kind]}`} preserveAspectRatio="none" role="img" viewBox={`0 0 ${width} ${height}`}>
      {yScale.ticks.map((value) => <g key={value}><line className="chart-gridline" x1={pad.left} x2={width - pad.right} y1={yPx(value)} y2={yPx(value)} /><text className="chart-axis-label" x={pad.left - 8} y={yPx(value) + 4} textAnchor="end">{formatAxisTick(value, yScale.step)}</text></g>)}
      {xTicks.map((tick) => <g key={`${tick.value}-${tick.label}`}><line className="chart-gridline vertical" x1={xTickPosition(tick)} x2={xTickPosition(tick)} y1={pad.top} y2={pad.top + plotHeight} /><text className="chart-axis-label" textAnchor="middle" x={xTickPosition(tick)} y={height - 29}>{shortAxisLabel(tick.label)}</text></g>)}
      {chart.kind === "scatter" && visibleTrends.map((trend) => {
        const path = trend.points.map((point, index) => `${index === 0 ? "M" : "L"}${xPx(point.x)},${yPx(point.y)}`).join(" ");
        return <path className="chart-trend" d={path} key={`${trend.series}-${trend.kind}`} stroke={visualBySeries.get(trend.series)?.color ?? PALETTE[0]} />;
      })}
      {chart.kind === "bar" ? barMarks.map((mark, index) => {
        const startY = yPx(mark.start);
        const endY = yPx(mark.end);
        return <rect className="chart-bar" fill={visualBySeries.get(mark.point.series)?.color ?? PALETTE[0]} height={Math.max(1, Math.abs(startY - endY))} key={`${mark.point.xLabel}-${mark.point.series}-${index}`} onDoubleClick={(event) => { event.stopPropagation(); onPointDoubleClick(mark.point); }} onPointerEnter={(event) => setPointTooltip(event, mark.point)} onPointerMove={(event) => setPointTooltip(event, mark.point)} rx={3} width={mark.width} x={mark.x} y={Math.min(startY, endY)} />;
      }) : chart.kind === "boxplot" ? points.map((point, index) => {
        const q1 = point.q1 ?? point.y;
        const median = point.median ?? point.y;
        const q3 = point.q3 ?? point.y;
        const lower = point.lowerWhisker ?? q1;
        const upper = point.upperWhisker ?? q3;
        const center = categoricalXPx(point.x);
        const boxWidth = Math.min(58, (plotWidth / Math.max(1, xGroups.length)) * 0.48);
        const color = visualBySeries.get(point.series)?.color ?? PALETTE[index % PALETTE.length];
        return <g className="chart-boxplot" key={`${point.xLabel}-${index}`} onDoubleClick={(event) => { event.stopPropagation(); onPointDoubleClick(point); }} onPointerEnter={(event) => setPointTooltip(event, point)} onPointerMove={(event) => setPointTooltip(event, point)}>
          <line className="boxplot-whisker" stroke={color} x1={center} x2={center} y1={yPx(lower)} y2={yPx(upper)} />
          <line className="boxplot-whisker" stroke={color} x1={center - boxWidth * 0.28} x2={center + boxWidth * 0.28} y1={yPx(lower)} y2={yPx(lower)} />
          <line className="boxplot-whisker" stroke={color} x1={center - boxWidth * 0.28} x2={center + boxWidth * 0.28} y1={yPx(upper)} y2={yPx(upper)} />
          <rect className="boxplot-box" fill={color} stroke={color} height={Math.max(2, yPx(q1) - yPx(q3))} width={boxWidth} x={center - boxWidth / 2} y={yPx(q3)} />
          <line className="boxplot-median" x1={center - boxWidth / 2} x2={center + boxWidth / 2} y1={yPx(median)} y2={yPx(median)} />
        </g>;
      }) : chart.kind === "scatter" || chart.kind === "projection" ? points.map((point, index) => <circle className="chart-point" cx={xPx(point.x)} cy={yPx(point.y)} fill={chart.kind === "projection" && point.targetValue != null ? continuousTargetColor(point.targetValue, targetMin, targetMax) : visualBySeries.get(point.series)?.color ?? PALETTE[0]} key={`${point.x}-${point.y}-${index}`} onDoubleClick={(event) => { event.stopPropagation(); onPointDoubleClick(point); }} onPointerEnter={(event) => setPointTooltip(event, point)} onPointerMove={(event) => setPointTooltip(event, point)} r={Math.max(3.5, Math.min(8, 3.5 + Math.log10(point.count ?? 1)))} />) : series.map((seriesName) => {
        const seriesPoints = pointsBySeries.get(seriesName) ?? [];
        const line = seriesPoints.map((point, index) => `${index === 0 ? "M" : "L"}${xPx(point.x)},${yPx(point.y)}`).join(" ");
        const visual = visualBySeries.get(seriesName) ?? { color: PALETTE[0], dash: undefined };
        const area = chart.kind === "histogram" && seriesPoints.length
          ? `M${xPx(seriesPoints[0].x)},${yPx(0)} ${line.replace(/^M/, "L")} L${xPx(seriesPoints[seriesPoints.length - 1].x)},${yPx(0)} Z`
          : "";
        return <g key={seriesName}>{area && <path className="chart-density-area" d={area} fill={visual.color} />}<path className="chart-line" d={line} stroke={visual.color} strokeDasharray={visual.dash} />{seriesPoints.map((point, index) => <circle className="chart-point" cx={xPx(point.x)} cy={yPx(point.y)} fill={visual.color} key={`${point.x}-${index}`} onDoubleClick={(event) => { event.stopPropagation(); onPointDoubleClick(point); }} onPointerEnter={(event) => setPointTooltip(event, point)} onPointerMove={(event) => setPointTooltip(event, point)} r={chart.kind === "histogram" ? 2.5 : 4} />)}</g>;
      })}
      <text className="chart-axis-title" textAnchor="middle" x={pad.left + plotWidth / 2} y={height - 7}>{xAxisLabel}</text>
      <text className="chart-axis-title" textAnchor="middle" transform={`rotate(-90 14 ${pad.top + plotHeight / 2})`} x={14} y={pad.top + plotHeight / 2}>{yAxisLabel}</text>
    </svg>
  );
}

type BarMark = { point: PlotPoint; x: number; width: number; start: number; end: number };

function layoutBarMarks(chart: ChartConfig, points: PlotPoint[], series: string[], plotWidth: number, plotLeft: number): BarMark[] {
  const categories = unique(points.map((point) => point.x));
  const categoryIndex = new Map(categories.map((value, index) => [value, index]));
  const categoryWidth = plotWidth / Math.max(categories.length, 1);
  const innerWidth = categoryWidth * 0.8;
  const categoryInset = (categoryWidth - innerWidth) / 2;

  if (chart.kind !== "bar" || !chart.stacked) {
    const seriesIndex = new Map(series.map((name, index) => [name, index]));
    const slotWidth = innerWidth / Math.max(series.length, 1);
    const width = Math.max(1, slotWidth * 0.86);
    return points.map((point) => {
      const category = categoryIndex.get(point.x) ?? 0;
      const slot = seriesIndex.get(point.series) ?? 0;
      return {
        point,
        x: plotLeft + category * categoryWidth + categoryInset + slot * slotWidth + (slotWidth - width) / 2,
        width,
        start: 0,
        end: point.y,
      };
    });
  }

  const configuredMetrics = unique([chart.aggregation, ...(chart.comparisonAggregations ?? [])]);
  const metrics = configuredMetrics.filter((metric) => points.some((point) => point.aggregation === metric));
  const metricIndex = new Map(metrics.map((metric, index) => [metric, index]));
  const slotWidth = innerWidth / Math.max(metrics.length, 1);
  const width = Math.max(1, slotWidth * 0.86);
  const totals = new Map<string, { positive: number; negative: number }>();

  return points.map((point) => {
    const category = categoryIndex.get(point.x) ?? 0;
    const metric = point.aggregation ?? chart.aggregation;
    const slot = metricIndex.get(metric) ?? 0;
    const totalKey = `${category}:${metric}`;
    const total = totals.get(totalKey) ?? { positive: 0, negative: 0 };
    const start = point.y >= 0 ? total.positive : total.negative;
    const end = start + point.y;
    if (point.y >= 0) total.positive = end;
    else total.negative = end;
    totals.set(totalKey, total);
    return {
      point,
      x: plotLeft + category * categoryWidth + categoryInset + slot * slotWidth + (slotWidth - width) / 2,
      width,
      start,
      end,
    };
  });
}

function stackedBarBounds(points: PlotPoint[]): [number, number] {
  const totals = new Map<string, { positive: number; negative: number }>();
  for (const point of points) {
    const key = `${point.x}:${point.aggregation ?? "value"}`;
    const total = totals.get(key) ?? { positive: 0, negative: 0 };
    if (point.y >= 0) total.positive += point.y;
    else total.negative += point.y;
    totals.set(key, total);
  }
  return [
    Math.min(0, ...[...totals.values()].map((total) => total.negative)),
    Math.max(0, ...[...totals.values()].map((total) => total.positive)),
  ];
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
  const temporal = columns.find((column) => column.type === "date" || /time|date/i.test(column.name));
  const categorical = columns.find((column) => column.type !== "number" && cardinality(rows, column.name) < 40);
  const x = kind === "projection" ? "" : kind === "time_series" || kind === "autocorrelation" || kind === "lag_relationship" ? temporal?.name ?? "" : kind === "histogram" || kind === "boxplot" ? numeric[0]?.name ?? "" : kind === "scatter" ? numeric[0]?.name ?? "" : categorical?.name ?? columns[0]?.name ?? "";
  const y = kind === "scatter" ? numeric[1]?.name ?? numeric[0]?.name ?? "" : numeric[0]?.name ?? "";
  const config = makeConfig(kind, x, kind === "projection" ? "" : y, "", `${kindLabels[kind]} ${index + 1}`, defaultLayout(kind, index));
  if (kind === "projection") {
    config.featureColumns = numeric.slice(0, Math.min(6, numeric.length)).map((column) => column.name);
    config.targetColumn = categorical?.name ?? "";
  }
  if (kind === "lag_relationship") config.driverColumn = numeric.find((column) => column.name !== config.y)?.name ?? "";
  return config;
}

function makeConfig(kind: ChartKind, x: string, y: string, group: string, title: string, layout: ChartLayout): ChartConfig {
  return { id: `${kind}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, kind, title, x, y, xEpsilon: 0, yEpsilon: 0, trend: "none", polynomialDegree: 2, group, aggregation: "average", comparisonAggregations: [], selectedGroups: null, stacked: false, kpiCondition: "none", kpiThreshold: 0, featureColumns: [], targetColumn: "", maxLag: 48, rollingWindow: 12, driverColumn: "", layout };
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
    const columnTypes = new Map(columns.map((column) => [column.name, column.type]));
    return parsed
      .filter((chart) => {
        if (!chart || !kindLabels[chart.kind] || (chart.x && !names.has(chart.x)) || (chart.y && !names.has(chart.y))) return false;
        if (chart.kind === "projection") return (chart.featureColumns ?? []).length >= 2 && (chart.featureColumns ?? []).every((name) => columnTypes.get(name) === "number") && (!chart.targetColumn || names.has(chart.targetColumn));
        if (chart.kind === "time_series" || chart.kind === "autocorrelation" || chart.kind === "lag_relationship") return columnTypes.get(chart.y) === "number" && Boolean(chart.x) && (chart.kind !== "lag_relationship" || columnTypes.get(chart.driverColumn) === "number");
        if (chart.kind === "histogram" || chart.kind === "boxplot") return columnTypes.get(chart.x) === "number";
        if (columnTypes.get(chart.y) !== "number") return false;
        return chart.kind !== "scatter" || columnTypes.get(chart.x) === "number";
      })
      .map((chart, index) => {
        const validGroup = Boolean(chart.group && names.has(chart.group) && chart.group !== chart.x && chart.group !== chart.y);
        return {
          ...chart,
          group: validGroup ? chart.group : "",
          xEpsilon: chart.xEpsilon ?? 0,
          yEpsilon: chart.yEpsilon ?? 0,
          trend: chart.trend ?? "none",
          polynomialDegree: chart.polynomialDegree ?? 2,
          comparisonAggregations: chart.comparisonAggregations ?? [],
          selectedGroups: validGroup ? chart.selectedGroups ?? null : null,
          stacked: validGroup && chart.kind === "bar" ? chart.stacked ?? false : false,
          kpiCondition: chart.kpiCondition ?? "none",
          kpiThreshold: chart.kpiThreshold ?? 0,
          featureColumns: chart.featureColumns ?? [],
          targetColumn: chart.targetColumn ?? "",
          maxLag: chart.maxLag ?? 48,
          rollingWindow: chart.rollingWindow ?? 12,
          driverColumn: chart.driverColumn ?? "",
          layout: normalizeLayout(chart.layout
            ? shouldScaleLegacyGrid ? scaleLegacyGridLayout(chart.layout) : chart.layout
            : legacyLayout(chart.size, index)
          )
        };
      });
  } catch {
    return null;
  }
}

function describeEncoding(chart: ChartConfig) {
  if (chart.kind === "time_series") return `${chart.y} over ${chart.x} · rolling ${chart.rollingWindow} display bins`;
  if (chart.kind === "autocorrelation") return `${chart.y} ACF · lags 1–${chart.maxLag}`;
  if (chart.kind === "lag_relationship") return `${chart.driverColumn}(t−lag) → ${chart.y}(t) · lags 0–${chart.maxLag}`;
  if (chart.kind === "projection") return `PCA of ${chart.featureColumns.length} features${chart.targetColumn ? ` · colored by ${chart.targetColumn}` : ""}`;
  if (chart.kind === "histogram") return `${chart.x} · KDE density${chart.group ? ` · by ${chart.group}` : ""}`;
  if (chart.kind === "boxplot") return `${chart.x} · quartiles${chart.group ? ` · by ${chart.group}` : ""}`;
  if (chart.kind === "kpi") return `${chart.aggregation} of ${chart.y}${chart.group ? ` · filtered by ${chart.group}` : ""}${chart.kpiCondition !== "none" ? ` · target ${kpiConditionSymbol(chart.kpiCondition)} ${formatNumber(chart.kpiThreshold)}` : ""}`;
  return `${chart.x || "row"} → ${chart.y || "count"}${chart.xEpsilon > 0 ? ` · xε=${formatNumber(chart.xEpsilon)}` : ""}${chart.yEpsilon > 0 ? ` · yε=${formatNumber(chart.yEpsilon)}` : ""}${chart.group ? ` · by ${chart.group}` : ""}${chart.kind === "scatter" && chart.trend !== "none" ? ` · ${chart.trend} trend` : ""}${chart.kind === "bar" && chart.stacked ? " · stacked" : ""}`;
}

function evaluateKpiCondition(value: number, condition: KpiCondition, threshold: number) {
  if (condition === "eq") return value === threshold;
  if (condition === "lt") return value < threshold;
  if (condition === "lte") return value <= threshold;
  if (condition === "gt") return value > threshold;
  if (condition === "gte") return value >= threshold;
  return true;
}

function kpiConditionSymbol(condition: KpiCondition) {
  return { none: "", eq: "=", lt: "<", lte: "≤", gt: ">", gte: "≥" }[condition];
}

function storageKey(datasetId: string) { return `ml-app:visual-dashboard:${datasetId}`; }
function unique<T>(values: T[]) { return [...new Set(values)]; }
function naturalCompare(left: string, right: string) { return NATURAL_COLLATOR.compare(left, right); }
function cardinality(rows: RecordRow[], column: string) { return new Set(rows.slice(0, 1000).map((row) => displayValue(row[column]))).size; }
function displayValue(value: CellValue) { return value === null || value === "" ? "Missing" : String(value); }
function continuousTargetColor(value: number, minimum: number, maximum: number) {
  const ratio = maximum === minimum ? 0.5 : Math.max(0, Math.min(1, (value - minimum) / (maximum - minimum)));
  const stops: Array<[number, number, number]> = [[49, 54, 149], [69, 117, 180], [116, 173, 209], [253, 174, 97], [215, 48, 39]];
  const position = ratio * (stops.length - 1);
  const index = Math.min(stops.length - 2, Math.floor(position));
  const local = position - index;
  return `rgb(${stops[index].map((channel, channelIndex) => Math.round(channel + (stops[index + 1][channelIndex] - channel) * local)).join(",")})`;
}
function aggregationLabel(aggregation: Aggregation) {
  if (aggregation === "std") return "Std. dev.";
  return aggregation.charAt(0).toUpperCase() + aggregation.slice(1);
}
