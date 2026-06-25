import { Activity, Check, ChevronDown, ChevronRight, Clock3, Play, RotateCcw, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { DatasetColumn, TimeSeriesAnalysis } from "../api/client";
import { formatInteger, formatNumber } from "./visualizationFormatters";


type Props = {
  columns: DatasetColumn[];
  datasetId: string;
  defaultTimeColumn?: string;
  defaultValueColumn?: string;
  mode: "browser" | "descriptive";
  onChronologicalSort?: (column: string) => void;
};

type ChartLine = { name: string; values: Array<number | null> };

export function TimeSeriesWorkbench({ columns, datasetId, defaultTimeColumn = "", defaultValueColumn = "", mode, onChronologicalSort }: Props) {
  const timeCandidates = columns.filter((column) => column.type === "date" || /time|date/i.test(column.name));
  const valueCandidates = columns.filter((column) => column.type === "number");
  const inferredTime = columns.some((column) => column.name === defaultTimeColumn)
    ? defaultTimeColumn
    : timeCandidates[0]?.name ?? "";
  const inferredValue = valueCandidates.some((column) => column.name === defaultValueColumn)
    ? defaultValueColumn
    : valueCandidates.find((column) => /target|temperature|temp|value|signal|output/i.test(column.name))?.name ?? valueCandidates[0]?.name ?? "";
  const [timeColumn, setTimeColumn] = useState(inferredTime);
  const [valueColumn, setValueColumn] = useState(inferredValue);
  const [driverColumns, setDriverColumns] = useState<string[]>([]);
  const [driversOpen, setDriversOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [maxLag, setMaxLag] = useState(48);
  const [rollingWindow, setRollingWindow] = useState(12);
  const [seasonalPeriod, setSeasonalPeriod] = useState(0);
  const [result, setResult] = useState<TimeSeriesAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setTimeColumn(inferredTime);
    setValueColumn(inferredValue);
    setResult(null);
    setDriverColumns([]);
    setDriversOpen(false);
    setError("");
  }, [datasetId, inferredTime, inferredValue]);

  async function run() {
    if (!datasetId || !timeColumn || !valueColumn) return;
    setLoading(true);
    setError("");
    try {
      setResult(await api.analyzeTimeSeries(datasetId, {
        time_column: timeColumn,
        value_column: valueColumn,
        max_lag: maxLag,
        seasonal_period: seasonalPeriod,
        rolling_window: rollingWindow,
        max_points: mode === "browser" ? 300 : 600,
        driver_column: driverColumns[0] ?? "",
        driver_columns: driverColumns,
      }));
    } catch (runError) {
      setResult(null);
      setError(runError instanceof Error ? runError.message : "Time-series analysis failed");
    } finally {
      setLoading(false);
    }
  }

  const suggestedPeriod = result?.summary.suggested_seasonal_period ?? null;
  const canRun = Boolean(datasetId && timeColumn && valueColumn && timeColumn !== valueColumn && !loading);
  const driverOptions = valueCandidates.filter((column) => column.name !== valueColumn && column.name !== timeColumn);
  if (!timeCandidates.length || !valueCandidates.length) {
    return <section className={`panel time-series-workbench ${mode}`}><div className="empty-state">Assign or provide a timestamp column and at least one numeric signal to unlock time-series tools.</div></section>;
  }

  return (
    <section className={`panel time-series-workbench ${mode}`}>
      <header className="time-series-header">
        <button className="time-series-toggle" onClick={() => setCollapsed((current) => !current)} type="button" aria-expanded={!collapsed}>
          {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
          <span><small>Time-series toolkit</small><strong>{mode === "browser" ? "Temporal data check" : "Dynamics and seasonality"}</strong></span>
        </button>
        {result && <span className="status-pill online">{formatInteger(result.valid_count)} full-data observations</span>}
      </header>
      {!collapsed && <>
      <div className="time-series-controls">
        <label>Time axis<select value={timeColumn} onChange={(event) => { setTimeColumn(event.target.value); setResult(null); }}>
          {timeCandidates.map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}
        </select></label>
        <label>Signal<select value={valueColumn} onChange={(event) => { setValueColumn(event.target.value); setResult(null); }}>
          {valueCandidates.filter((column) => column.name !== timeColumn).map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}
        </select></label>
        <DriverPicker
          options={driverOptions.map((column) => column.name)}
          selected={driverColumns}
          open={driversOpen}
          onOpenChange={setDriversOpen}
          onChange={(next) => { setDriverColumns(next); setResult(null); }}
        />
        <label>Maximum lag<input min={1} max={120} type="number" value={maxLag} onChange={(event) => setMaxLag(clampInteger(event.target.value, 1, 120, 48))} /></label>
        <label>Rolling window<input min={2} max={200} type="number" value={rollingWindow} onChange={(event) => setRollingWindow(clampInteger(event.target.value, 2, 200, 12))} /></label>
        {mode === "descriptive" && <label>Seasonal period<input min={0} max={10000} type="number" value={seasonalPeriod} onChange={(event) => setSeasonalPeriod(clampInteger(event.target.value, 0, 10000, 0))} /><small>0 = infer candidate from ACF</small></label>}
        <button className="primary-button" disabled={!canRun} onClick={run} type="button"><Play size={15} />{loading ? "Analyzing" : "Run full analysis"}</button>
        {onChronologicalSort && <button className="secondary-button" disabled={!timeColumn} onClick={() => onChronologicalSort(timeColumn)} type="button"><Clock3 size={15} />Sort preview by time</button>}
      </div>
      {loading && <div className="profiling-status"><Activity size={18} /><strong>Scanning and ordering the full series...</strong></div>}
      {error && <div className="empty-state error-state">{error}</div>}
      {!loading && !error && !result && <p className="time-series-intro">Checks cadence, duplicates, gaps, trend, differences, autocorrelation, candidate seasonality and rolling behavior without sampling the analysis.</p>}
      {result && <>
        <div className="time-series-metrics">
          <TimeMetric label="Cadence" value={formatDuration(result.summary.median_interval_seconds)} />
          <TimeMetric label="Regular intervals" value={result.summary.regular_interval_ratio == null ? "n/a" : `${formatNumber(result.summary.regular_interval_ratio * 100)}%`} />
          <TimeMetric label="Gaps" value={formatInteger(result.summary.gap_count)} />
          <TimeMetric label="Duplicate times" value={formatInteger(result.summary.duplicate_timestamp_count)} />
          <TimeMetric label="Lag-1 ACF" value={formatNullable(result.summary.lag1_autocorrelation)} />
          <TimeMetric label="Trend / day" value={formatNullable(result.summary.trend_per_day)} />
          <TimeMetric label="Trend R2" value={formatNullable(result.summary.trend_r_squared)} />
          <TimeMetric label="Difference sigma" value={formatNullable(result.summary.difference_std_dev)} />
          <TimeMetric label="Season candidate" value={suggestedPeriod ? `lag ${suggestedPeriod}` : "none"} />
          {result.summary.strongest_driver_lag != null && <TimeMetric label="Strongest driver lag" value={`${result.summary.strongest_driver_column ?? result.summary.driver_column}: ${result.summary.strongest_driver_lag} / r ${formatNullable(result.summary.strongest_driver_correlation ?? null)}`} />}
        </div>
        <TimeSeriesGuide result={result} />
        <div className="time-series-notes">{result.quality_notes.map((note) => <p key={note}>{note}</p>)}</div>
        {result.driver_relationships.length > 0 && <DriverRelationshipTable result={result} />}
        {mode === "browser" && <FeaturePreview result={result} />}
        {mode === "descriptive" && <div className="time-series-charts">
          <MiniSeriesChart result={result} />
          {result.decomposition.length > 0 && <DecompositionChart result={result} />}
          {result.difference_series.length > 0 && <DifferenceChart result={result} />}
          <AcfChart result={result} />
          {result.cross_correlation.length > 0 && <CorrelationChart title={`Driver lag relationship / ${result.summary.driver_column}`} points={result.cross_correlation} />}
          {result.seasonal_profile.length > 0 && <SeasonalChart result={result} />}
        </div>}
        {mode === "descriptive" && <p className="muted-text">Dashed correlation bounds use the approximate +/-1.96/sqrt(N) white-noise reference. Treat ACF and cross-correlation as diagnostics, not causal evidence.</p>}
        {suggestedPeriod && seasonalPeriod !== suggestedPeriod && mode === "descriptive" && <button className="secondary-button compact-button" onClick={() => setSeasonalPeriod(suggestedPeriod)} type="button"><RotateCcw size={14} />Use suggested period {suggestedPeriod} and rerun</button>}
      </>}
      </>}
    </section>
  );
}

function DriverPicker({ options, selected, open, onOpenChange, onChange }: { options: string[]; selected: string[]; open: boolean; onOpenChange: (open: boolean) => void; onChange: (selected: string[]) => void }) {
  function toggle(value: string) {
    onChange(selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value]);
  }
  const label = selected.length === 0 ? "No candidates" : selected.length === 1 ? selected[0] : `${selected.length} candidates`;
  return <div className="ts-driver-picker">
    <span>Candidate drivers</span>
    <button className="secondary-button ts-driver-picker-button" type="button" onClick={() => onOpenChange(!open)}>
      <Check size={14} />{label}<ChevronDown size={14} />
    </button>
    {selected.length > 0 && <small>{selected.join(", ")}</small>}
    {open && <div className="ts-driver-menu">
      <div className="ts-driver-menu-actions">
        <button type="button" onClick={() => onChange(options)}>All</button>
        <button type="button" onClick={() => onChange([])}>None</button>
        <button type="button" onClick={() => onOpenChange(false)} aria-label="Close driver picker"><X size={14} /></button>
      </div>
      <div className="ts-driver-options">
        {options.map((option) => <label key={option}>
          <input checked={selected.includes(option)} onChange={() => toggle(option)} type="checkbox" />
          <span>{option}</span>
        </label>)}
        {options.length === 0 && <p>No numeric candidate columns.</p>}
      </div>
    </div>}
  </div>;
}

function TimeMetric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function TimeSeriesGuide({ result }: { result: TimeSeriesAnalysis }) {
  const regularity = result.summary.regular_interval_ratio;
  const lag1 = result.summary.lag1_autocorrelation;
  const hints = [
    regularity != null && regularity < 0.95
      ? "The time axis is irregular. Treat ACF and rolling windows as exploratory until the data is explicitly resampled."
      : "The time axis looks regular enough for basic lag and seasonality diagnostics.",
    lag1 != null && Math.abs(lag1) >= 0.7
      ? "Lag-1 ACF is high, so nearby rows are similar. Use chronological validation later; random splits would leak time structure."
      : "Lag-1 ACF is not dominant, so the series has less immediate memory at the tested cadence.",
    result.summary.suggested_seasonal_period
      ? `ACF found a candidate cycle near lag ${result.summary.suggested_seasonal_period}. Validate that against the business cadence.`
      : "No seasonal candidate means ACF did not find a clear local peak above the current threshold within the tested lag range.",
    "Decomposition and differences are descriptive diagnostics: use them to see trend, repeated shape and instability before deciding whether a modeling workflow is needed.",
  ];
  return <div className="time-series-guide">{hints.map((hint) => <p key={hint}>{hint}</p>)}</div>;
}

function DriverRelationshipTable({ result }: { result: TimeSeriesAnalysis }) {
  return <div className="ts-driver-ranking"><div><strong>Candidate driver scan</strong><span>Ranked by absolute correlation between driver(t-lag) and signal(t)</span></div><div className="data-table-wrap"><table className="data-table"><thead><tr>
    <th>Driver</th><th>Best lag</th><th>Correlation</th><th>Strength</th><th>Direction</th><th>Pairs</th><th>Reading</th>
  </tr></thead><tbody>{result.driver_relationships.map((row) => <tr key={row.driver_column}>
    <td>{row.driver_column}</td>
    <td>{row.strongest_lag == null ? "n/a" : row.strongest_lag}</td>
    <td>{formatNullable(row.strongest_correlation)}</td>
    <td>{row.strength}</td>
    <td>{row.direction}</td>
    <td>{formatInteger(row.pair_count)}</td>
    <td>{driverReading(row)}</td>
  </tr>)}</tbody></table></div></div>;
}

function driverReading(row: TimeSeriesAnalysis["driver_relationships"][number]) {
  if (row.strongest_lag == null || row.strongest_correlation == null) return "Not enough paired observations.";
  const timing = row.strongest_lag === 0 ? "same timestamp" : `${row.strongest_lag} step(s) earlier`;
  const sign = row.strongest_correlation >= 0 ? "higher driver tends to align with higher signal" : "higher driver tends to align with lower signal";
  return `${timing}: ${sign}. Diagnostic only, not causality.`;
}

function FeaturePreview({ result }: { result: TimeSeriesAnalysis }) {
  return <div className="ts-feature-preview"><div><strong>Derived-feature preview</strong><span>First and last 50 ordered observations / preview only</span></div><div className="data-table-wrap"><table className="data-table"><thead><tr>
    <th>Position</th><th>Timestamp</th><th>Value</th><th>Lag 1</th><th>Seasonal lag</th><th>Difference</th><th>Rolling mean</th><th>Rolling sigma</th>
  </tr></thead><tbody>{result.feature_preview.map((row) => <tr key={row.position}>
    <td>{row.position}</td><td>{row.timestamp}</td><td>{formatNumber(row.value)}</td><td>{formatNullable(row.lag_1)}</td><td>{formatNullable(row.seasonal_lag)}</td><td>{formatNullable(row.difference)}</td><td>{formatNullable(row.rolling_mean)}</td><td>{formatNullable(row.rolling_std_dev)}</td>
  </tr>)}</tbody></table></div></div>;
}

function MiniSeriesChart({ result }: { result: TimeSeriesAnalysis }) {
  return <LineChartSvg
    title="Aggregated series and rolling mean"
    xLabels={result.series.map((point) => point.timestamp)}
    series={[
      { name: "Observed", values: result.series.map((point) => point.value) },
      { name: "Rolling mean", values: result.series.map((point) => point.rolling_mean) },
    ]}
  />;
}

function DecompositionChart({ result }: { result: TimeSeriesAnalysis }) {
  return <LineChartSvg
    title="Trend / seasonal / residual decomposition"
    xLabels={result.decomposition.map((point) => point.timestamp)}
    series={[
      { name: "Observed", values: result.decomposition.map((point) => point.observed) },
      { name: "Trend", values: result.decomposition.map((point) => point.trend) },
      { name: "Seasonal", values: result.decomposition.map((point) => point.seasonal) },
      { name: "Residual", values: result.decomposition.map((point) => point.residual) },
    ]}
  />;
}

function DifferenceChart({ result }: { result: TimeSeriesAnalysis }) {
  return <LineChartSvg
    title="First differences and rolling movement"
    xLabels={result.difference_series.map((point) => point.timestamp)}
    series={[
      { name: "Average difference", values: result.difference_series.map((point) => point.difference) },
      { name: "Rolling |difference|", values: result.difference_series.map((point) => point.rolling_abs_difference) },
    ]}
  />;
}

function AcfChart({ result }: { result: TimeSeriesAnalysis }) {
  return <CorrelationChart title="Autocorrelation (ACF)" points={result.autocorrelation} />;
}

function CorrelationChart({ title, points: source }: { title: string; points: TimeSeriesAnalysis["autocorrelation"] }) {
  const points = source.filter((point) => point.correlation != null);
  const width = 640; const height = 220; const pad = 28;
  const x = (index: number) => pad + index / Math.max(1, points.length - 1) * (width - pad * 2);
  const y = (value: number) => pad + (1 - (value + 1) / 2) * (height - pad * 2);
  const confidence = points.length ? 1.96 / Math.sqrt(Math.max(...points.map((point) => point.pair_count))) : 0;
  return <figure><figcaption>{title}</figcaption><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
    <line className="ts-zero" x1={pad} x2={width - pad} y1={y(0)} y2={y(0)} />
    <line className="ts-confidence" x1={pad} x2={width - pad} y1={y(confidence)} y2={y(confidence)} />
    <line className="ts-confidence" x1={pad} x2={width - pad} y1={y(-confidence)} y2={y(-confidence)} />
    {points.map((point, index) => <line className="ts-acf-bar" key={point.lag} x1={x(index)} x2={x(index)} y1={y(0)} y2={y(point.correlation ?? 0)}><title>Lag {point.lag}: {formatNumber(point.correlation ?? 0)}</title></line>)}
  </svg></figure>;
}

function SeasonalChart({ result }: { result: TimeSeriesAnalysis }) {
  return <LineChartSvg
    title={`Seasonal profile / period ${result.summary.seasonal_period}`}
    xLabels={result.seasonal_profile.map((point) => String(point.phase))}
    series={[{ name: "Phase mean", values: result.seasonal_profile.map((point) => point.mean) }]}
  />;
}

function LineChartSvg({ title, series, xLabels }: { title: string; series: ChartLine[]; xLabels: string[] }) {
  const width = 640; const height = 220; const pad = 28;
  const concrete = series.flatMap((item) => item.values).filter((value): value is number => value != null);
  const minimum = Math.min(...concrete); const maximum = Math.max(...concrete); const range = maximum - minimum || 1;
  const length = Math.max(1, ...series.map((item) => item.values.length));
  const x = (index: number) => pad + index / Math.max(1, length - 1) * (width - pad * 2);
  const y = (value: number) => pad + (maximum - value) / range * (height - pad * 2);
  const path = (items: Array<number | null>) => items.map((value, index) => value == null ? "" : `${index === 0 ? "M" : "L"}${x(index)},${y(value)}`).join(" ");
  return <figure><figcaption>{title}</figcaption><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
    {series.map((item, index) => <path className={`ts-multi-line line-${index}`} d={path(item.values)} key={item.name} />)}
    <title>{xLabels[0]} - {xLabels[xLabels.length - 1]}</title>
  </svg><div className="ts-chart-legend">{series.map((item, index) => <span key={item.name}><i className={`line-${index}`} />{item.name}</span>)}</div></figure>;
}

function clampInteger(value: string, minimum: number, maximum: number, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(minimum, Math.min(maximum, Math.trunc(parsed))) : fallback;
}

function formatNullable(value: number | null) { return value == null ? "n/a" : formatNumber(value); }
function formatDuration(seconds: number | null) {
  if (seconds == null) return "n/a";
  if (seconds < 60) return `${formatNumber(seconds)} s`;
  if (seconds < 3600) return `${formatNumber(seconds / 60)} min`;
  if (seconds < 86400) return `${formatNumber(seconds / 3600)} h`;
  return `${formatNumber(seconds / 86400)} d`;
}
