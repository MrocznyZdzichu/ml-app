import type { CSSProperties } from "react";

import type { ModelEvaluationSnapshot } from "../api/contracts/modelEvaluation";

export function ComparisonLegend({ series }: { series: Array<{ label: string }> }) {
  return <div className="evaluation-comparison-legend" aria-label="Selected period series">{series.map((item, index) => <span key={item.label} className={`comparison-series-${index % 8}`}><i />{item.label}</span>)}</div>;
}

export function ComparisonCurveChart({ series, diagonal }: {
  series: Array<{ label: string; index: number; curve: NonNullable<ModelEvaluationSnapshot["curves"]>[string] }>;
  diagonal: boolean;
}) {
  const plot = { left: 58, right: 535, top: 20, bottom: 250 };
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return <div className="evaluation-line-chart"><svg viewBox="0 0 560 300" role="img" aria-label="Comparison of selected period curves">
    {ticks.map((tick) => <g key={tick}><line x1={plot.left + tick * (plot.right - plot.left)} y1={plot.top} x2={plot.left + tick * (plot.right - plot.left)} y2={plot.bottom} className="grid" /><line x1={plot.left} y1={plot.bottom - tick * (plot.bottom - plot.top)} x2={plot.right} y2={plot.bottom - tick * (plot.bottom - plot.top)} className="grid" /><text x={plot.left + tick * (plot.right - plot.left)} y={plot.bottom + 18} className="tick" textAnchor="middle">{tick.toFixed(2)}</text><text x={plot.left - 10} y={plot.bottom - tick * (plot.bottom - plot.top) + 4} className="tick" textAnchor="end">{tick.toFixed(2)}</text></g>)}
    <line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.bottom} className="axis" /><line x1={plot.left} y1={plot.top} x2={plot.left} y2={plot.bottom} className="axis" />{diagonal && <line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.top} className="baseline" />}
    {series.map((item) => <polyline key={item.label} className={`comparison-line comparison-series-${item.index % 8}`} points={[...item.curve.points].sort((a, b) => a.x - b.x).map((point) => `${plot.left + point.x * (plot.right - plot.left)},${plot.bottom - point.y * (plot.bottom - plot.top)}`).join(" ")} />)}
    <text x={(plot.left + plot.right) / 2} y="292" className="axis-title" textAnchor="middle">{series[0]?.curve.x_label ?? "X"}</text><text x="15" y={(plot.top + plot.bottom) / 2} className="axis-title" textAnchor="middle" transform={`rotate(-90 15 ${(plot.top + plot.bottom) / 2})`}>{series[0]?.curve.y_label ?? "Y"}</text>
  </svg></div>;
}

export function ComparisonDistributionChart({ series, xLabel }: {
  series: Array<{ label: string; index: number; bins: Array<{ lower: number; upper: number; count: number }> }>;
  xLabel: string;
}) {
  const plot = { left: 62, right: 690, top: 28, bottom: 250 };
  const allBins = series.flatMap((item) => item.bins);
  if (!allBins.length) return <div className="catalog-empty">No distribution data.</div>;
  const min = Math.min(...allBins.map((bin) => bin.lower));
  const max = Math.max(...allBins.map((bin) => bin.upper));
  const span = max - min || 1;
  return <div className="evaluation-histogram-chart"><svg viewBox="0 0 720 300" role="img" aria-label={`${xLabel} comparison`}>
    {[0, 0.25, 0.5, 0.75, 1].map((tick) => <g key={tick}><line x1={plot.left} y1={plot.bottom - tick * (plot.bottom - plot.top)} x2={plot.right} y2={plot.bottom - tick * (plot.bottom - plot.top)} className="grid" /><text x={plot.left - 10} y={plot.bottom - tick * (plot.bottom - plot.top) + 4} className="tick" textAnchor="end">{`${Math.round(tick * 100)}%`}</text></g>)}
    <line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.bottom} className="axis" /><line x1={plot.left} y1={plot.top} x2={plot.left} y2={plot.bottom} className="axis" />
    {series.map((item) => { const total = item.bins.reduce((sum, bin) => sum + bin.count, 0) || 1; return <polyline key={item.label} className={`comparison-line comparison-series-${item.index % 8}`} points={item.bins.map((bin) => `${plot.left + (((bin.lower + bin.upper) / 2 - min) / span) * (plot.right - plot.left)},${plot.bottom - (bin.count / total) * (plot.bottom - plot.top)}`).join(" ")} />; })}
    {[0, 0.5, 1].map((tick) => <text key={tick} x={plot.left + tick * (plot.right - plot.left)} y={plot.bottom + 19} className="tick" textAnchor="middle">{formatChartTick(min + tick * span)}</text>)}<text x={(plot.left + plot.right) / 2} y="292" className="axis-title" textAnchor="middle">{xLabel}</text><text x="16" y={(plot.top + plot.bottom) / 2} className="axis-title" textAnchor="middle" transform={`rotate(-90 16 ${(plot.top + plot.bottom) / 2})`}>Share of rows</text>
  </svg></div>;
}

export function ComparisonScatterChart({ series }: { series: Array<{ label: string; index: number; points: Array<{ actual: number; predicted: number }> }> }) {
  const points = series.flatMap((item) => item.points);
  if (!points.length) return <div className="catalog-empty">No scatter points available.</div>;
  const values = points.flatMap((point) => [point.actual, point.predicted]);
  const min = Math.min(...values); const max = Math.max(...values); const span = max - min || 1;
  const plot = { left: 72, right: 535, top: 22, bottom: 345 };
  return <div className="evaluation-line-chart regression-chart"><svg viewBox="0 0 560 400" role="img" aria-label="Actual versus predicted by period"><line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.bottom} className="axis" /><line x1={plot.left} y1={plot.top} x2={plot.left} y2={plot.bottom} className="axis" /><line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.top} className="baseline" />{series.flatMap((item) => item.points.map((point, index) => <circle key={`${item.label}-${index}`} cx={plot.left + (point.actual - min) / span * (plot.right - plot.left)} cy={plot.bottom - (point.predicted - min) / span * (plot.bottom - plot.top)} r="2.2" className={`comparison-point comparison-series-${item.index % 8}`} />))}<text x={(plot.left + plot.right) / 2} y="392" className="axis-title" textAnchor="middle">Actual value</text><text x="16" y={(plot.top + plot.bottom) / 2} className="axis-title" textAnchor="middle" transform={`rotate(-90 16 ${(plot.top + plot.bottom) / 2})`}>Predicted value</text></svg></div>;
}

export function ComparisonQqChart({ series }: { series: Array<{ label: string; index: number; points: Array<{ theoretical: number; observed: number }> }> }) {
  const points = series.flatMap((item) => item.points);
  if (!points.length) return <div className="catalog-empty">No residual quantiles available.</div>;
  const xMin = Math.min(...points.map((point) => point.theoretical)); const xMax = Math.max(...points.map((point) => point.theoretical));
  const yMin = Math.min(...points.map((point) => point.observed)); const yMax = Math.max(...points.map((point) => point.observed));
  const xSpan = xMax - xMin || 1; const ySpan = yMax - yMin || 1; const plot = { left: 72, right: 535, top: 22, bottom: 345 };
  return <div className="evaluation-line-chart regression-chart"><svg viewBox="0 0 560 400" role="img" aria-label="Residual QQ comparison"><line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.bottom} className="axis" /><line x1={plot.left} y1={plot.top} x2={plot.left} y2={plot.bottom} className="axis" />{series.map((item) => <polyline key={item.label} className={`comparison-line comparison-series-${item.index % 8}`} points={item.points.map((point) => `${plot.left + (point.theoretical - xMin) / xSpan * (plot.right - plot.left)},${plot.bottom - (point.observed - yMin) / ySpan * (plot.bottom - plot.top)}`).join(" ")} />)}<text x={(plot.left + plot.right) / 2} y="392" className="axis-title" textAnchor="middle">Theoretical normal quantile</text><text x="16" y={(plot.top + plot.bottom) / 2} className="axis-title" textAnchor="middle" transform={`rotate(-90 16 ${(plot.top + plot.bottom) / 2})`}>Observed residual quantile</text></svg></div>;
}

export function ConfusionMatrix({ matrix }: {
  matrix: NonNullable<ModelEvaluationSnapshot["confusion_matrix"]>;
}) {
  const maximum = Math.max(1, ...matrix.values.flat());
  return (
    <div className="evaluation-confusion">
      <table>
        <thead><tr><th>Actual ↓ / Predicted →</th>{matrix.labels.map((label) => <th key={String(label)}>{String(label)}</th>)}</tr></thead>
        <tbody>{matrix.values.map((row, rowIndex) => (
          <tr key={String(matrix.labels[rowIndex])}>
            <th>{String(matrix.labels[rowIndex])}</th>
            {row.map((value, columnIndex) => (
              <td key={`${rowIndex}-${columnIndex}`} style={{ "--cell-strength": value / maximum } as CSSProperties}>
                {value.toLocaleString()}
              </td>
            ))}
          </tr>
        ))}</tbody>
      </table>
      {matrix.truncated && <small>Matrix limited to {matrix.labels.length} of {matrix.total_class_count} classes.</small>}
    </div>
  );
}

export function EvaluationLineChart({
  curve,
  curveKind,
  diagonal
}: {
  curve: NonNullable<ModelEvaluationSnapshot["curves"]>[string];
  curveKind: string;
  diagonal: boolean;
}) {
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const plot = { left: 58, right: 535, top: 20, bottom: 250 };
  const orderedPoints = [...curve.points].sort((left, right) => {
    if (left.x !== right.x) return left.x - right.x;
    return curveKind === "precision_recall" ? right.y - left.y : left.y - right.y;
  });
  const points = orderedPoints.map((point) =>
    `${plot.left + point.x * (plot.right - plot.left)},${plot.bottom - point.y * (plot.bottom - plot.top)}`
  ).join(" ");
  return (
    <div className="evaluation-line-chart">
      <svg viewBox="0 0 560 300" role="img" aria-label={`${curve.y_label} by ${curve.x_label}`}>
        {ticks.map((tick) => {
          const x = plot.left + tick * (plot.right - plot.left);
          const y = plot.bottom - tick * (plot.bottom - plot.top);
          return <g key={tick}>
            <line x1={x} y1={plot.top} x2={x} y2={plot.bottom} className="grid" />
            <line x1={plot.left} y1={y} x2={plot.right} y2={y} className="grid" />
            <text x={x} y={plot.bottom + 18} className="tick" textAnchor="middle">
              {tick.toFixed(2)}
            </text>
            <text x={plot.left - 10} y={y + 4} className="tick" textAnchor="end">
              {tick.toFixed(2)}
            </text>
          </g>;
        })}
        <line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.bottom} className="axis" />
        <line x1={plot.left} y1={plot.top} x2={plot.left} y2={plot.bottom} className="axis" />
        {diagonal && <line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.top} className="baseline" />}
        <polyline points={points} className="series" />
        <text x={(plot.left + plot.right) / 2} y="292" className="axis-title" textAnchor="middle">
          {curve.x_label}
        </text>
        <text x="15" y={(plot.top + plot.bottom) / 2} className="axis-title"
          textAnchor="middle" transform={`rotate(-90 15 ${(plot.top + plot.bottom) / 2})`}>
          {curve.y_label}
        </text>
      </svg>
    </div>
  );
}

export function StackedHistogram({
  bins
}: {
  bins: NonNullable<NonNullable<ModelEvaluationSnapshot["distributions"]>["score_by_actual"]>;
}) {
  if (!bins.length) return <div className="catalog-empty">No score distribution is available.</div>;
  const maximum = Math.max(
    1,
    ...bins.flatMap((bin) => [bin.negative_count, bin.positive_count])
  );
  const plot = { left: 62, right: 690, top: 28, bottom: 250 };
  const width = (plot.right - plot.left) / bins.length;
  const barWidth = Math.max(2, width * 0.36);
  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const scoreTicks = [
    bins[0].lower,
    bins[Math.floor(bins.length / 2)].lower,
    bins.at(-1)!.upper
  ];
  const positiveTotal = bins.reduce((sum, bin) => sum + bin.positive_count, 0);
  const negativeTotal = bins.reduce((sum, bin) => sum + bin.negative_count, 0);
  return (
    <div className="evaluation-histogram-chart" aria-label="Score distribution by actual class">
      <div className="histogram-summary">
        <span className="positive">Actual positive <strong>{positiveTotal.toLocaleString()}</strong></span>
        <span className="negative">Actual negative <strong>{negativeTotal.toLocaleString()}</strong></span>
      </div>
      <svg viewBox="0 0 720 300" role="img" aria-label="Score distribution histogram">
        {yTicks.map((tick) => {
          const y = plot.bottom - tick * (plot.bottom - plot.top);
          return <g key={tick}>
            <line x1={plot.left} y1={y} x2={plot.right} y2={y} className="grid" />
            <text x={plot.left - 10} y={y + 4} className="tick" textAnchor="end">
              {Math.round(maximum * tick).toLocaleString()}
            </text>
          </g>;
        })}
        {bins.map((bin, index) => {
          const center = plot.left + (index + 0.5) * width;
          const positiveHeight = bin.positive_count / maximum * (plot.bottom - plot.top);
          const negativeHeight = bin.negative_count / maximum * (plot.bottom - plot.top);
          return <g key={index}>
            <title>
              {`${bin.lower.toPrecision(3)}–${bin.upper.toPrecision(3)}: `
                + `${bin.positive_count} positive, ${bin.negative_count} negative`}
            </title>
            <rect className="positive" x={center - barWidth}
              y={plot.bottom - positiveHeight} width={barWidth} height={positiveHeight} />
            <rect className="negative" x={center}
              y={plot.bottom - negativeHeight} width={barWidth} height={negativeHeight} />
          </g>;
        })}
        <line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.bottom} className="axis" />
        <line x1={plot.left} y1={plot.top} x2={plot.left} y2={plot.bottom} className="axis" />
        {scoreTicks.map((tick, index) => {
          const ratio = index / (scoreTicks.length - 1);
          return <text key={`${tick}-${index}`}
            x={plot.left + ratio * (plot.right - plot.left)}
            y={plot.bottom + 19} className="tick" textAnchor="middle">
            {tick.toFixed(2)}
          </text>;
        })}
        <text x={(plot.left + plot.right) / 2} y="292" className="axis-title" textAnchor="middle">
          Prediction score
        </text>
        <text x="16" y={(plot.top + plot.bottom) / 2} className="axis-title"
          textAnchor="middle" transform={`rotate(-90 16 ${(plot.top + plot.bottom) / 2})`}>
          Row count
        </text>
      </svg>
    </div>
  );
}

export function ResidualHistogram({
  bins
}: {
  bins: NonNullable<ModelEvaluationSnapshot["residuals"]>["histogram"];
}) {
  if (!bins.length) return <div className="catalog-empty">No residual distribution is available.</div>;
  const maximum = Math.max(1, ...bins.map((bin) => bin.count));
  const plot = { left: 68, right: 690, top: 24, bottom: 345 };
  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const xTickIndexes = [0, Math.floor((bins.length - 1) / 2), bins.length - 1];
  const width = (plot.right - plot.left) / bins.length;
  return <div className="evaluation-histogram-chart regression-chart" aria-label="Residual distribution">
    <svg viewBox="0 0 720 400" role="img" aria-label="Residual distribution histogram">
      {yTicks.map((tick) => {
        const y = plot.bottom - tick * (plot.bottom - plot.top);
        return <g key={tick}>
          <line x1={plot.left} y1={y} x2={plot.right} y2={y} className="grid" />
          <text x={plot.left - 10} y={y + 4} className="tick" textAnchor="end">
            {Math.round(maximum * tick).toLocaleString()}
          </text>
        </g>;
      })}
      {bins.map((bin, index) => {
        const height = bin.count / maximum * (plot.bottom - plot.top);
        return <rect key={index} className="residual-bar" x={plot.left + index * width + 1}
          y={plot.bottom - height} width={Math.max(1, width - 2)} height={height}>
          <title>{`${formatChartTick(bin.lower)}–${formatChartTick(bin.upper)}: ${bin.count.toLocaleString()} rows`}</title>
        </rect>;
      })}
      <line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.bottom} className="axis" />
      <line x1={plot.left} y1={plot.top} x2={plot.left} y2={plot.bottom} className="axis" />
      {xTickIndexes.map((index) => <text key={index} x={plot.left + (index + 0.5) * width}
        y={plot.bottom + 18} className="tick" textAnchor="middle">
        {formatChartTick((bins[index].lower + bins[index].upper) / 2)}
      </text>)}
      <text x={(plot.left + plot.right) / 2} y="392" className="axis-title" textAnchor="middle">Residual (predicted − actual)</text>
      <text x="16" y={(plot.top + plot.bottom) / 2} className="axis-title" textAnchor="middle"
        transform={`rotate(-90 16 ${(plot.top + plot.bottom) / 2})`}>Row count</text>
    </svg>
  </div>;
}

export function ActualPredictedScatter({
  points
}: {
  points: NonNullable<ModelEvaluationSnapshot["residuals"]>["actual_vs_predicted"]["points"];
}) {
  if (!points.length) return <div className="catalog-empty">No scatter points available.</div>;
  const values = points.flatMap((point) => [point.actual, point.predicted]);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const span = maximum - minimum || 1;
  const plot = { left: 72, right: 535, top: 22, bottom: 345 };
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return <div className="evaluation-line-chart regression-chart">
    <svg viewBox="0 0 560 400" role="img" aria-label="Actual versus predicted values">
      {ticks.map((tick) => {
        const x = plot.left + tick * (plot.right - plot.left);
        const y = plot.bottom - tick * (plot.bottom - plot.top);
        return <g key={tick}>
          <line x1={x} y1={plot.top} x2={x} y2={plot.bottom} className="grid" />
          <line x1={plot.left} y1={y} x2={plot.right} y2={y} className="grid" />
          <text x={x} y={plot.bottom + 18} className="tick" textAnchor="middle">{formatChartTick(minimum + tick * span)}</text>
          <text x={plot.left - 10} y={y + 4} className="tick" textAnchor="end">{formatChartTick(minimum + tick * span)}</text>
        </g>;
      })}
      <line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.bottom} className="axis" />
      <line x1={plot.left} y1={plot.top} x2={plot.left} y2={plot.bottom} className="axis" />
      <line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.top} className="baseline" />
      {points.map((point, index) => (
        <circle key={index} cx={plot.left + (point.actual - minimum) / span * (plot.right - plot.left)}
          cy={plot.bottom - (point.predicted - minimum) / span * (plot.bottom - plot.top)} r="2.2" className="scatter-point" />
      ))}
      <text x={(plot.left + plot.right) / 2} y="392" className="axis-title" textAnchor="middle">Actual value</text>
      <text x="16" y={(plot.top + plot.bottom) / 2} className="axis-title" textAnchor="middle"
        transform={`rotate(-90 16 ${(plot.top + plot.bottom) / 2})`}>Predicted value</text>
    </svg>
  </div>;
}

export function ResidualQqPlot({ plot: qqPlot, summary }: {
  plot: NonNullable<NonNullable<ModelEvaluationSnapshot["residuals"]>["qq_plot"]>;
  summary: NonNullable<ModelEvaluationSnapshot["residuals"]>["summary"];
}) {
  if (!qqPlot.points.length) return <div className="catalog-empty">No residual quantiles are available.</div>;
  const frame = { left: 72, right: 535, top: 22, bottom: 345 };
  const xMin = qqPlot.points[0].theoretical;
  const xMax = qqPlot.points.at(-1)!.theoretical;
  const observed = qqPlot.points.map((point) => point.observed);
  const reference = [xMin, xMax].map((x) => summary.mean + summary.standard_deviation * x);
  const yMin = Math.min(...observed, ...reference);
  const yMax = Math.max(...observed, ...reference);
  const xSpan = xMax - xMin || 1;
  const ySpan = yMax - yMin || 1;
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return <div className="evaluation-line-chart regression-chart">
    <svg viewBox="0 0 560 400" role="img" aria-label="Residual normal quantile plot">
      {ticks.map((tick) => {
        const x = frame.left + tick * (frame.right - frame.left);
        const y = frame.bottom - tick * (frame.bottom - frame.top);
        return <g key={tick}>
          <line x1={x} y1={frame.top} x2={x} y2={frame.bottom} className="grid" />
          <line x1={frame.left} y1={y} x2={frame.right} y2={y} className="grid" />
          <text x={x} y={frame.bottom + 18} className="tick" textAnchor="middle">{(xMin + tick * xSpan).toFixed(2)}</text>
          <text x={frame.left - 10} y={y + 4} className="tick" textAnchor="end">{formatChartTick(yMin + tick * ySpan)}</text>
        </g>;
      })}
      <line x1={frame.left} y1={frame.bottom} x2={frame.right} y2={frame.bottom} className="axis" />
      <line x1={frame.left} y1={frame.top} x2={frame.left} y2={frame.bottom} className="axis" />
      <line x1={frame.left} y1={frame.bottom - (reference[0] - yMin) / ySpan * (frame.bottom - frame.top)}
        x2={frame.right} y2={frame.bottom - (reference[1] - yMin) / ySpan * (frame.bottom - frame.top)} className="baseline" />
      {qqPlot.points.map((point, index) => <circle key={index}
        cx={frame.left + (point.theoretical - xMin) / xSpan * (frame.right - frame.left)}
        cy={frame.bottom - (point.observed - yMin) / ySpan * (frame.bottom - frame.top)} r="2.5" className="scatter-point" />)}
      <text x={(frame.left + frame.right) / 2} y="392" className="axis-title" textAnchor="middle">{qqPlot.x_label}</text>
      <text x="16" y={(frame.top + frame.bottom) / 2} className="axis-title" textAnchor="middle"
        transform={`rotate(-90 16 ${(frame.top + frame.bottom) / 2})`}>{qqPlot.y_label}</text>
    </svg>
  </div>;
}

function formatChartTick(value: number) {
  const magnitude = Math.abs(value);
  if (magnitude >= 1_000_000 || (magnitude > 0 && magnitude < 0.01)) return value.toExponential(1);
  return value.toLocaleString(undefined, { maximumFractionDigits: magnitude >= 100 ? 0 : 2 });
}

export function formatEvaluationMetric(value: number, unit: string) {
  if (!Number.isFinite(value)) return "—";
  return unit === "ratio" ? `${(value * 100).toFixed(1)}%` : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

export function formatEvaluationHeadlineMetric(
  metric: ModelEvaluationSnapshot["metrics"][number]
) {
  if (!Number.isFinite(metric.value)) return "—";
  return metric.value.toLocaleString(undefined, {
    minimumFractionDigits: 3,
    maximumFractionDigits: 4
  });
}

export function evaluationCurveTitle(key: string) {
  return key === "roc" ? "ROC curve" :
    key === "precision_recall" ? "Precision–recall curve" :
      key === "calibration" ? "Calibration" : key.replaceAll("_", " ");
}

export function evaluationCurveMetric(
  key: string,
  metrics: Map<string, ModelEvaluationSnapshot["metrics"][number]>
) {
  const metricId = key === "roc"
    ? "roc_auc"
    : key === "precision_recall"
      ? "average_precision"
      : key === "calibration"
        ? "brier_score"
        : "";
  return metricId ? metrics.get(metricId) : undefined;
}
