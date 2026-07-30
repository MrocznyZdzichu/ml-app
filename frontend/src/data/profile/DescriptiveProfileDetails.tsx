import {
  ChevronDown,
  ChevronRight,
  Search,
  Table2,
  X
} from "lucide-react";
import type { ChangeEvent } from "react";
import { useState } from "react";

import type { DatasetPreview } from "../../api/client";
import { Metric } from "../../workspace/Overview";
import type { DataRolesMetadata } from "../../analysis/dataRoles";
import { defaultProfilingRangeSettings } from "../profile/contracts";
import type {
  CategoricalRelationStats,
  ColumnProfile,
  DensityPlot,
  DensitySeries,
  EffectiveTargetType,
  ProfilingRangeSettings,
  ScatterPlot,
  SegmentProfile,
  SegmentResult,
  TargetRelationProfile,
  DatasetCellValue
} from "../profile/contracts";
import {
  columnRoleForColumn,
  columnRoleLabel,
  displayValue,
  roundNumber
} from "../dataValueFormatters";


export type SelectableColumn = {
  name: string;
  meta: string;
};

export function ColumnSelectionSummary({
  columns,
  selected,
  onOpen
}: {
  columns: SelectableColumn[];
  selected: string[];
  onOpen: () => void;
}) {
  const selectedPreview = selected.slice(0, 4).join(", ");
  return (
    <div className="column-selection-summary">
      <div>
        <strong>Columns</strong>
        <span>
          {selected.length} of {columns.length} selected
          {selectedPreview ? ` / ${selectedPreview}${selected.length > 4 ? ", ..." : ""}` : ""}
        </span>
      </div>
      <button className="secondary-button compact-button" onClick={onOpen} type="button">
        <Table2 size={14} />
        Columns selection
      </button>
    </div>
  );
}

export function ColumnSelectionModal({
  columns,
  onChange,
  onClose,
  selected,
  title
}: {
  columns: SelectableColumn[];
  onChange: (columns: string[]) => void;
  onClose: () => void;
  selected: string[];
  title: string;
}) {
  const [searchValue, setSearchValue] = useState("");
  const [draftSelected, setDraftSelected] = useState(selected);
  const [lastClickedIndex, setLastClickedIndex] = useState<number | null>(null);
  const draftSelectedSet = new Set(draftSelected);
  const normalizedSearch = searchValue.trim().toLowerCase();
  const filteredColumns = normalizedSearch
    ? columns.filter((column) =>
        column.name.toLowerCase().includes(normalizedSearch) ||
        column.meta.toLowerCase().includes(normalizedSearch)
      )
    : columns;
  const selectedVisibleCount = filteredColumns.filter((column) => draftSelectedSet.has(column.name)).length;

  function applySelection() {
    onChange(draftSelected);
    onClose();
  }

  function toggleColumn(column: SelectableColumn, filteredIndex: number, event: ChangeEvent<HTMLInputElement>) {
    const nextChecked = event.target.checked;
    const visibleNames = filteredColumns.map((item) => item.name);
    let namesToUpdate = [column.name];
    if (event.nativeEvent instanceof MouseEvent && event.nativeEvent.shiftKey && lastClickedIndex !== null) {
      const start = Math.min(lastClickedIndex, filteredIndex);
      const end = Math.max(lastClickedIndex, filteredIndex);
      namesToUpdate = visibleNames.slice(start, end + 1);
    }
    const updateSet = new Set(namesToUpdate);
    setDraftSelected((current) => {
      const currentSet = new Set(current);
      for (const name of updateSet) {
        if (nextChecked) {
          currentSet.add(name);
        } else {
          currentSet.delete(name);
        }
      }
      return columns.map((item) => item.name).filter((name) => currentSet.has(name));
    });
    setLastClickedIndex(filteredIndex);
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-label={title} className="column-selection-modal" role="dialog">
        <header className="modal-header">
          <div>
            <p className="eyebrow">Columns selection</p>
            <h2>{title}</h2>
          </div>
          <button className="icon-button" onClick={onClose} type="button" aria-label="Close columns selection">
            <X size={18} />
          </button>
        </header>

        <div className="column-selection-body">
          <div className="column-selection-tools">
            <label>
              Search columns
              <div className="input-with-icon">
                <Search size={16} />
                <input
                  value={searchValue}
                  onChange={(event) => {
                    setSearchValue(event.target.value);
                    setLastClickedIndex(null);
                  }}
                  placeholder="Column name or role"
                />
              </div>
            </label>
            <div className="section-actions">
              <button className="secondary-button compact-button" onClick={() => setDraftSelected(columns.map((column) => column.name))} type="button">
                Show all
              </button>
              <button className="secondary-button compact-button" onClick={() => setDraftSelected([])} type="button">
                Hide all
              </button>
            </div>
          </div>

          <div className="selector-filter-summary">
            {draftSelected.length} of {columns.length} selected
            {searchValue.trim() ? ` / ${selectedVisibleCount} of ${filteredColumns.length} matching selected` : ""}
          </div>

          <div className="column-selector-grid modal-selector-grid">
            {filteredColumns.map((column, index) => (
              <label className={draftSelectedSet.has(column.name) ? "selector-column selected" : "selector-column"} key={column.name}>
                <input
                  checked={draftSelectedSet.has(column.name)}
                  onChange={(event) => toggleColumn(column, index, event)}
                  type="checkbox"
                />
                <span>
                  <strong>{column.name}</strong>
                  <em>{column.meta}</em>
                </span>
              </label>
            ))}
            {filteredColumns.length === 0 && (
              <div className="empty-state compact-empty">No columns match current search</div>
            )}
          </div>
        </div>

        <footer className="modal-actions">
          <button className="secondary-button" onClick={onClose} type="button">
            Cancel
          </button>
          <button className="primary-button" onClick={applySelection} type="button">
            Apply selection
          </button>
        </footer>
      </section>
    </div>
  );
}

export function ProfilingRangeModal({
  onApply,
  onClose,
  settings
}: {
  onApply: (settings: ProfilingRangeSettings) => void;
  onClose: () => void;
  settings: ProfilingRangeSettings;
}) {
  const [draftSettings, setDraftSettings] = useState(settings);

  function updateBoolean(key: keyof Pick<
    ProfilingRangeSettings,
    "includeSummary" | "includeUnivariate" | "includeTargetRelations" | "includeSegments" | "includeGraphicSummaries"
  >, value: boolean) {
    setDraftSettings((current) => ({ ...current, [key]: value }));
  }

  function updateNumber(key: keyof Pick<
    ProfilingRangeSettings,
    "rowLimit" | "maxTargetFeatures" | "maxSegmentFeatures"
  >, value: string) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return;
    }
    const minimum = key === "maxSegmentFeatures" ? 2 : 1;
    setDraftSettings((current) => ({
      ...current,
      [key]: Math.max(minimum, Math.trunc(parsed))
    }));
  }

  function applySettings() {
    onApply(draftSettings);
    onClose();
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section aria-label="Profiling range" className="profiling-range-modal" role="dialog">
        <header className="modal-header">
          <div>
            <p className="eyebrow">Profiling range</p>
            <h2>Configure profiling scope</h2>
          </div>
          <button className="icon-button" onClick={onClose} type="button" aria-label="Close profiling range">
            <X size={18} />
          </button>
        </header>

        <div className="profiling-range-body">
          <section className="range-section">
            <div className="panel-header compact-header">
              <h2>Sections</h2>
            </div>
            <div className="range-choice-grid">
              <label className="check-tile">
                <input
                  checked={draftSettings.includeSummary}
                  onChange={(event) => updateBoolean("includeSummary", event.target.checked)}
                  type="checkbox"
                />
                <span>Dataset summary and quality notes</span>
              </label>
              <label className="check-tile">
                <input
                  checked={draftSettings.includeUnivariate}
                  onChange={(event) => updateBoolean("includeUnivariate", event.target.checked)}
                  type="checkbox"
                />
                <span>Univariate column profiles</span>
              </label>
              <label className="check-tile">
                <input
                  checked={draftSettings.includeTargetRelations}
                  onChange={(event) => updateBoolean("includeTargetRelations", event.target.checked)}
                  type="checkbox"
                />
                <span>Target vs feature relations</span>
              </label>
              <label className="check-tile">
                <input
                  checked={draftSettings.includeSegments}
                  onChange={(event) => updateBoolean("includeSegments", event.target.checked)}
                  type="checkbox"
                />
                <span>Multivariate segment scan</span>
              </label>
            </div>
          </section>

          <section className="range-section">
            <div className="panel-header compact-header">
              <h2>Options</h2>
            </div>
            <div className="range-choice-grid">
              <label className="check-tile">
                <input
                  checked={draftSettings.includeGraphicSummaries}
                  onChange={(event) => updateBoolean("includeGraphicSummaries", event.target.checked)}
                  type="checkbox"
                />
                <span>Graphic summaries</span>
              </label>
            </div>
          </section>

          <section className="range-section">
            <div className="panel-header compact-header">
              <h2>Limits</h2>
            </div>
            <div className="range-number-grid">
              <label>
                Graphic source-point limit
                <input
                  min={1}
                  onChange={(event) => updateNumber("rowLimit", event.target.value)}
                  type="number"
                  value={draftSettings.rowLimit}
                />
              </label>
              <label>
                Max target relation features
                <input
                  min={1}
                  onChange={(event) => updateNumber("maxTargetFeatures", event.target.value)}
                  type="number"
                  value={draftSettings.maxTargetFeatures}
                />
              </label>
              <label>
                Max segment scan features
                <input
                  min={2}
                  onChange={(event) => updateNumber("maxSegmentFeatures", event.target.value)}
                  type="number"
                  value={draftSettings.maxSegmentFeatures}
                />
              </label>
            </div>
          </section>

          <div className="insight-item">
            Lighter ranges finish faster. For a quick look, run only Dataset summary or Univariate profiles.
          </div>
        </div>

        <footer className="modal-actions">
          <button className="secondary-button" onClick={onClose} type="button">
            Cancel
          </button>
          <button className="secondary-button" onClick={() => setDraftSettings(defaultProfilingRangeSettings)} type="button">
            Reset defaults
          </button>
          <button className="primary-button" onClick={applySettings} type="button">
            Apply range
          </button>
        </footer>
      </section>
    </div>
  );
}

export function MiniHistogram({ bins }: { bins: Array<{ label: string; count: number; share: number }> }) {
  if (bins.length === 0) {
    return <div className="empty-state compact-empty">No numeric distribution available</div>;
  }
  const maxCount = Math.max(...bins.map((bin) => bin.count), 1);
  return (
    <div className="mini-histogram" aria-label="Mini histogram">
      <div className="histogram-bars">
        {bins.map((bin) => (
          <div className="histogram-bin" key={bin.label} title={`${bin.label}: ${formatInteger(bin.count)}`}>
            <div style={{ height: `${Math.max(6, (bin.count / maxCount) * 100)}%` }} />
          </div>
        ))}
      </div>
      <div className="histogram-axis">
        <span>{bins[0]?.label.split(" - ")[0]}</span>
        <span>{bins.at(-1)?.label.split(" - ").at(-1)}</span>
      </div>
    </div>
  );
}

export function TargetRelationCard({
  collapsed,
  onToggle,
  relation
}: {
  collapsed: boolean;
  onToggle: () => void;
  relation: TargetRelationProfile;
}) {
  return (
    <article className={relation.groupStats.length > 0 || relation.numericStats ? "relation-row relation-row-detailed" : "relation-row"}>
      <button
        aria-expanded={!collapsed}
        className="relation-card-toggle"
        onClick={onToggle}
        type="button"
      >
        <span className="relation-card-title">
          {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
          <span>
            <strong>{relation.feature}</strong>
            <em>{columnRoleLabel(relation.role)} / {relation.kind}</em>
          </span>
        </span>
        <span className="relation-score">
          <span className="mini-bar" aria-hidden="true">
            <span style={{ width: `${Math.max(4, relation.score * 100)}%` }} />
          </span>
          <em>{relation.signal}</em>
        </span>
      </button>
      {!collapsed && (
        <div className="relation-card-body">
          <p>{relation.detail}</p>
          {relation.numericStats && (
            <>
              {relation.scatterPlot && <MiniScatterPlot plot={relation.scatterPlot} />}
              <div className="numeric-relation-table" role="table" aria-label={`${relation.feature} numeric relationship with ${relation.comparisonColumn}`}>
                <div className="numeric-relation-row numeric-relation-head" role="row">
                  <span role="columnheader">Pearson</span>
                  <span role="columnheader">Spearman</span>
                  <span role="columnheader">R²</span>
                  <span role="columnheader">Slope</span>
                  <span role="columnheader">Intercept</span>
                  <span role="columnheader">Covariance</span>
                </div>
                <div className="numeric-relation-row" role="row">
                  <span role="cell">{formatSignedNumber(relation.numericStats.pearson)}</span>
                  <span role="cell">{formatSignedNumber(relation.numericStats.spearman)}</span>
                  <span role="cell">{formatNumber(relation.numericStats.rSquared)}</span>
                  <span role="cell">{formatSignedNumber(relation.numericStats.slope)}</span>
                  <span role="cell">{formatSignedNumber(relation.numericStats.intercept)}</span>
                  <span role="cell">{formatSignedNumber(relation.numericStats.covariance)}</span>
                </div>
              </div>
            </>
          )}
          {relation.groupStats.length > 0 && (
            <>
              {relation.densityPlot && <MiniDensityPlot plot={relation.densityPlot} />}
              <div className="relation-stats-table" role="table" aria-label={`${relation.feature} by ${relation.comparisonColumn}`}>
                <div className="relation-stats-row relation-stats-head" role="row">
                  <span role="columnheader">{relation.comparisonColumn}</span>
                  <span role="columnheader">Rows</span>
                  <span role="columnheader">Min</span>
                  <span role="columnheader">Max</span>
                  <span role="columnheader">Median</span>
                  <span role="columnheader">Average</span>
                  <span role="columnheader">Std</span>
                </div>
                {relation.groupStats.map((group) => (
                  <div className="relation-stats-row" key={group.group} role="row">
                    <span role="cell">
                      <i style={{ background: group.color }} />
                      {group.group}
                    </span>
                    <span role="cell">{formatInteger(group.count)}</span>
                    <span role="cell">{formatNumber(group.minimum)}</span>
                    <span role="cell">{formatNumber(group.maximum)}</span>
                    <span role="cell">{formatNumber(group.median)}</span>
                    <span role="cell">{formatNumber(group.mean)}</span>
                    <span role="cell">{formatNumber(group.stdDev)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
          {relation.categoricalStats && (
            <CategoricalRelationDetails
              comparisonColumn={relation.comparisonColumn}
              feature={relation.feature}
              stats={relation.categoricalStats}
            />
          )}
        </div>
      )}
    </article>
  );
}

export function CategoricalRelationDetails({
  comparisonColumn,
  feature,
  stats
}: {
  comparisonColumn: string;
  feature: string;
  stats: CategoricalRelationStats;
}) {
  return (
    <>
      <div className="categorical-metric-grid">
        <ProfileFact label="Cramer's V" value={formatNumber(stats.cramersV)} />
        <ProfileFact label="Chi-square" value={formatNumber(stats.chiSquare)} />
        <ProfileFact label="Degrees of freedom" value={formatInteger(stats.degreesFreedom)} />
        <ProfileFact label="Sparse expected cells" value={formatPercent(stats.sparseCellShare)} />
      </div>
      {stats.ordinalTrend && (
        <div className="ordinal-trend-summary">
          <strong>Ordinal trend</strong>
          <span>
            Spearman {formatSignedNumber(stats.ordinalTrend.spearman)} for target value {stats.ordinalTrend.focusValue}
          </span>
          <em>Order: {stats.ordinalTrend.orderBasis}</em>
        </div>
      )}
      <div className="categorical-relation-table" role="table" aria-label={`${feature} distribution by ${comparisonColumn}`}>
        <div
          className="categorical-relation-row categorical-relation-head"
          role="row"
          style={{ gridTemplateColumns: `minmax(140px, 1.3fr) 72px repeat(${stats.comparisonValues.length}, minmax(130px, 1fr))` }}
        >
          <span role="columnheader">{feature}</span>
          <span role="columnheader">Rows</span>
          {stats.comparisonValues.map((value) => (
            <span key={value} role="columnheader">{comparisonColumn}={value}</span>
          ))}
        </div>
        {stats.rows.map((row) => (
          <div
            className="categorical-relation-row"
            key={row.featureValue}
            role="row"
            style={{ gridTemplateColumns: `minmax(140px, 1.3fr) 72px repeat(${stats.comparisonValues.length}, minmax(130px, 1fr))` }}
          >
            <strong role="cell">{row.featureValue}</strong>
            <span role="cell">{formatInteger(row.count)}</span>
            {row.cells.map((cell) => (
              <span
                className="categorical-relation-cell"
                key={cell.comparisonValue}
                role="cell"
                style={stats.graphicSummaries ? { backgroundColor: `rgba(46, 163, 154, ${Math.min(0.42, 0.04 + cell.rowShare * 0.42)})` } : undefined}
                title={`Lift ${formatNumber(cell.lift)} / Pearson residual ${formatSignedNumber(cell.residual)}`}
              >
                <b>{formatInteger(cell.count)} ({formatPercent(cell.rowShare)})</b>
                <em>lift {formatNumber(cell.lift)} / resid {formatSignedNumber(cell.residual)}</em>
              </span>
            ))}
          </div>
        ))}
      </div>
      {stats.sparseCellShare > 0.2 && (
        <div className="insight-item">
          Many expected cell counts are below 5; treat chi-square and Cramer's V as exploratory signals.
        </div>
      )}
    </>
  );
}

export function SegmentScanResults({ profile }: { profile: SegmentProfile }) {
  const categorical = profile.targetType === "categorical";
  const maximumDifference = Math.max(...profile.results.map((item) => Math.abs(item.difference)), Number.EPSILON);
  return (
    <>
      <div className="segment-results-table">
        <div className={`segment-result-row segment-result-head ${categorical ? "categorical" : "continuous"}`}>
          <span>Segment</span>
          <span>Rows</span>
          <span>Support</span>
          <span>{categorical ? "Target rate" : "Mean"}</span>
          <span>Baseline</span>
          <span>Difference</span>
          {categorical ? <span title="Segment rate divided by the population rate">Lift</span> : <span title="Difference from the rest of the population in pooled standard deviations">Cohen's d</span>}
          <span title={categorical ? "Weighted Relative Accuracy: support multiplied by the target-rate difference" : "Support multiplied by Cohen's d"}>
            {categorical ? "WRAcc" : "Impact"}
          </span>
          <span>{categorical ? "Rate 95% CI" : "Mean 95% CI"}</span>
        </div>
        {profile.results.map((result) => {
          const barWidth = `${Math.max(2, (Math.abs(result.difference) / maximumDifference) * 50)}%`;
          return (
            <div className={`segment-result-row ${categorical ? "categorical" : "continuous"}`} key={`${result.columns.join("|")}:${result.segment}:${result.targetValue}`}>
              <strong title={result.columns.join(" + ")}>{result.segment}</strong>
              <span>{formatInteger(result.count)}</span>
              <span>{formatPercent(result.support)}</span>
              <span>{formatSegmentMetric(result.segmentValue, result.format)}</span>
              <span>{formatSegmentMetric(result.baseline, result.format)}</span>
              <span className={result.difference >= 0 ? "positive-difference" : "negative-difference"}>
                {profile.graphicSummaries && <i className="segment-difference-bar" style={{ width: barWidth }} />}
                {formatSignedSegmentMetric(result.difference, result.format)}
              </span>
              <span>{categorical ? `${formatNumber(result.relativeLift ?? 0)}x` : formatSignedNumber(result.effectSize ?? 0)}</span>
              <span>{formatSignedNumber(result.score)}</span>
              <span>{result.confidenceInterval ? `${formatSegmentMetric(result.confidenceInterval[0], result.format)} - ${formatSegmentMetric(result.confidenceInterval[1], result.format)}` : "n/a"}</span>
            </div>
          );
        })}
      </div>
      <p className="segment-method-note">
        Minimum segment size: {formatInteger(profile.minimumSegmentSize)} rows. Ranked by coverage-adjusted impact; results are exploratory associations, not causal effects.
      </p>
    </>
  );
}

export function MiniScatterPlot({ plot }: { plot: ScatterPlot }) {
  const width = 640;
  const height = 220;
  const padding = { top: 14, right: 18, bottom: 38, left: 48 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const xRange = plot.xMax - plot.xMin || 1;
  const yRange = plot.yMax - plot.yMin || 1;
  const xToPx = (value: number) => padding.left + ((value - plot.xMin) / xRange) * plotWidth;
  const yToPx = (value: number) => padding.top + plotHeight - ((value - plot.yMin) / yRange) * plotHeight;
  const xTicks = [plot.xMin, plot.xMin + xRange / 2, plot.xMax];
  const yTicks = [plot.yMin, plot.yMin + yRange / 2, plot.yMax];
  const sampledPoints = plot.points.length > 700
    ? plot.points.filter((_, index) => index % Math.ceil(plot.points.length / 700) === 0)
    : plot.points;

  return (
    <div className="scatter-plot" aria-label={`${plot.yColumn} by ${plot.xColumn} scatter plot`}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        <g className="density-grid">
          {yTicks.map((tick) => (
            <line key={`y-${tick}`} x1={padding.left} x2={width - padding.right} y1={yToPx(tick)} y2={yToPx(tick)} />
          ))}
          {xTicks.map((tick) => (
            <line key={`x-${tick}`} x1={xToPx(tick)} x2={xToPx(tick)} y1={padding.top} y2={height - padding.bottom} />
          ))}
        </g>
        <line className="density-axis" x1={padding.left} x2={width - padding.right} y1={height - padding.bottom} y2={height - padding.bottom} />
        <line className="density-axis" x1={padding.left} x2={padding.left} y1={padding.top} y2={height - padding.bottom} />
        {sampledPoints.map((point, index) => (
          <circle
            className="scatter-point"
            cx={xToPx(point.x)}
            cy={yToPx(point.y)}
            key={`${point.x}-${point.y}-${index}`}
            r="2.6"
          />
        ))}
        {plot.trendLine && (
          <line
            className="scatter-trend"
            x1={xToPx(plot.trendLine.x1)}
            x2={xToPx(plot.trendLine.x2)}
            y1={yToPx(plot.trendLine.y1)}
            y2={yToPx(plot.trendLine.y2)}
          />
        )}
        <g className="density-labels">
          {xTicks.map((tick) => (
            <text key={tick} x={xToPx(tick)} y={height - 20} textAnchor="middle">
              {formatNumber(tick)}
            </text>
          ))}
          {yTicks.map((tick) => (
            <text key={tick} x={padding.left - 8} y={yToPx(tick) + 4} textAnchor="end">
              {formatNumber(tick)}
            </text>
          ))}
          <text x={padding.left + plotWidth / 2} y={height - 4} textAnchor="middle">{plot.xColumn}</text>
          <text transform={`translate(12 ${padding.top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">{plot.yColumn}</text>
        </g>
      </svg>
    </div>
  );
}

export function MiniDensityPlot({ plot }: { plot: DensityPlot | null }) {
  if (!plot || plot.series.length === 0 || plot.yMax <= 0) {
    return <div className="empty-state compact-empty">No density distribution available</div>;
  }
  const width = 640;
  const height = 190;
  const padding = { top: 14, right: 18, bottom: 28, left: 42 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const xRange = plot.xMax - plot.xMin || 1;
  const xToPx = (value: number) => padding.left + ((value - plot.xMin) / xRange) * plotWidth;
  const yToPx = (value: number) => padding.top + plotHeight - (value / plot.yMax) * plotHeight;
  const baseline = padding.top + plotHeight;
  const xTicks = [plot.xMin, plot.xMin + xRange / 2, plot.xMax];
  const yTicks = [0, plot.yMax / 2, plot.yMax];

  return (
    <div className="density-plot" aria-label="Grouped density plot">
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        <g className="density-grid">
          {yTicks.map((tick) => (
            <line
              key={tick}
              x1={padding.left}
              x2={width - padding.right}
              y1={yToPx(tick)}
              y2={yToPx(tick)}
            />
          ))}
        </g>
        <line className="density-axis" x1={padding.left} x2={width - padding.right} y1={baseline} y2={baseline} />
        <line className="density-axis" x1={padding.left} x2={padding.left} y1={padding.top} y2={baseline} />
        {plot.series.map((series) => {
          const linePath = densityLinePath(series.points, xToPx, yToPx);
          const areaPath = densityAreaPath(series.points, xToPx, yToPx, baseline);
          return (
            <g key={series.group}>
              <path d={areaPath} fill={series.color} opacity="0.22" />
              <path d={linePath} fill="none" stroke={series.color} strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            </g>
          );
        })}
        <g className="density-labels">
          {xTicks.map((tick) => (
            <text key={tick} x={xToPx(tick)} y={height - 8} textAnchor="middle">
              {formatNumber(tick)}
            </text>
          ))}
          {yTicks.map((tick) => (
            <text key={tick} x={padding.left - 8} y={yToPx(tick) + 4} textAnchor="end">
              {formatNumber(tick)}
            </text>
          ))}
        </g>
      </svg>
      <div className="density-legend">
        {plot.series.map((series) => (
          <span key={series.group}>
            <i style={{ background: series.color }} />
            {series.group}
          </span>
        ))}
      </div>
    </div>
  );
}

export function densityLinePath(
  points: DensitySeries["points"],
  xToPx: (value: number) => number,
  yToPx: (value: number) => number
) {
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${xToPx(point.x).toFixed(2)} ${yToPx(point.y).toFixed(2)}`)
    .join(" ");
}

export function densityAreaPath(
  points: DensitySeries["points"],
  xToPx: (value: number) => number,
  yToPx: (value: number) => number,
  baseline: number
) {
  if (points.length === 0) {
    return "";
  }
  const start = points[0];
  const end = points.at(-1) ?? start;
  return [
    `M ${xToPx(start.x).toFixed(2)} ${baseline.toFixed(2)}`,
    densityLinePath(points, xToPx, yToPx).replace(/^M/, "L"),
    `L ${xToPx(end.x).toFixed(2)} ${baseline.toFixed(2)}`,
    "Z"
  ].join(" ");
}

export function relationCardKey(relation: TargetRelationProfile) {
  return `${relation.comparisonColumn}\u0000${relation.feature}`;
}

export function MiniDiscreteDistribution({
  values,
  limit
}: {
  values: Array<{ value: DatasetCellValue; count: number; share: number }>;
  limit: number;
}) {
  const visibleValues = values.slice(0, limit);
  if (visibleValues.length === 0) {
    return <div className="empty-state compact-empty">No distribution available</div>;
  }

  return (
    <div className="mini-discrete-distribution" aria-label="Value distribution">
      {visibleValues.map((item) => (
        <div className="discrete-bar-row" key={displayValue(item.value)} title={`${displayValue(item.value)}: ${formatInteger(item.count)}`}>
          <span>{displayValue(item.value)}</span>
          <div className="discrete-bar-track" aria-hidden="true">
            <div style={{ width: `${Math.max(4, item.share * 100)}%` }} />
          </div>
          <strong>{formatPercent(item.share)}</strong>
        </div>
      ))}
    </div>
  );
}

export function ProfileFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="profile-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}


export function inferTargetColumn(columns: DatasetPreview["columns"], rolesMetadata: DataRolesMetadata) {
  const names = new Set(columns.map((column) => column.name));
  if (rolesMetadata.target_column && names.has(rolesMetadata.target_column)) {
    return rolesMetadata.target_column;
  }
  const roleTarget = columns.find((column) => rolesMetadata.column_roles[column.name] === "target");
  if (roleTarget) {
    return roleTarget.name;
  }
  const commonTargetNames = new Set(["target", "label", "class", "outcome", "churn", "y"]);
  return columns.find((column) => commonTargetNames.has(column.name.toLowerCase()))?.name ?? "";
}

export function inferTargetType(
  column: DatasetPreview["columns"][number] | null,
  rows: Array<Record<string, DatasetCellValue>>,
  rolesMetadata: DataRolesMetadata
): EffectiveTargetType {
  if (!column) {
    return "categorical";
  }
  const role = columnRoleForColumn(column, rolesMetadata);
  if (["feature_categorical", "feature_ordinal", "boolean", "text"].includes(role)) {
    return "categorical";
  }
  if (role === "feature_continuous") {
    return "continuous";
  }
  if (column.type === "boolean" || column.type === "text") {
    return "categorical";
  }
  if (column.type !== "number") {
    return "categorical";
  }

  const present = rows.map((row) => normalizeCellValue(row[column.name])).filter(isPresentCell);
  const uniqueValues = [...new Set(present.map(displayValue))];
  if (uniqueValues.length <= 2) {
    return "categorical";
  }
  const lowCardinalityLimit = Math.min(20, Math.max(5, Math.floor(present.length * 0.05)));
  if (uniqueValues.length <= lowCardinalityLimit) {
    return "categorical";
  }
  return "continuous";
}

export function usesDiscreteDistribution(profile: ColumnProfile) {
  return profile.mean !== null && profile.unique > 0 && profile.unique <= 12;
}

export function comparisonColor(index: number) {
  const colors = ["#2ea39a", "#4477c2", "#c08522", "#8b6bd6", "#cf5f5f", "#5a9f45"];
  return colors[index % colors.length];
}

export function syncSelectedNames(current: string[] | null, available: string[]) {
  if (current === null) {
    return null;
  }
  const availableSet = new Set(available);
  const next = current.filter((name) => availableSet.has(name));
  if (next.length === current.length && next.every((name, index) => name === current[index])) {
    return current;
  }
  return next;
}

export function normalizeCellValue(value: unknown): DatasetCellValue {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean" || value === null) {
    return value;
  }
  return null;
}

export function isPresentCell(value: DatasetCellValue): value is Exclude<DatasetCellValue, null> {
  return value !== null && value !== "";
}

export function formatInteger(value: number) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

export function formatNumber(value: number) {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(roundNumber(value));
}

export function formatNullableNumber(value: number | null) {
  return value === null ? "null" : formatNumber(value);
}

export function formatSignedNumber(value: number) {
  return `${value >= 0 ? "+" : ""}${formatNumber(value)}`;
}

export function formatPercent(value: number) {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 1,
    style: "percent"
  }).format(value);
}

export function formatSegmentMetric(value: number, format: SegmentResult["format"]) {
  return format === "percent" ? formatPercent(value) : formatNumber(value);
}

export function formatSignedSegmentMetric(value: number, format: SegmentResult["format"]) {
  const formatted = formatSegmentMetric(Math.abs(value), format);
  return `${value >= 0 ? "+" : "-"}${formatted}`;
}
