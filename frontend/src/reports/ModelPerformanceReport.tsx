import type { ModelEvaluationSnapshot } from "../api/contracts/modelEvaluation";
import {
  ActualPredictedScatter,
  ComparisonCurveChart,
  ComparisonDistributionChart,
  ComparisonLegend,
  ComparisonQqChart,
  ComparisonScatterChart,
  ConfusionMatrix,
  EvaluationLineChart,
  ResidualHistogram,
  ResidualQqPlot,
  StackedHistogram,
  evaluationCurveMetric,
  evaluationCurveTitle,
  formatEvaluationHeadlineMetric,
  formatEvaluationMetric
} from "./ModelPerformanceCharts";

export function ModelPerformanceReport({ report }: { report: ModelEvaluationSnapshot }) {
  if (report.kind !== "model_performance") {
    return (
      <div className="evaluation-empty">
        <strong>Scoring report is unavailable</strong>
        <p>This result does not contain a model-performance report.</p>
      </div>
    );
  }
  if (report.status !== "available") {
    return (
      <div className="evaluation-empty">
        <strong>Performance needs actual target values</strong>
        <p>{report.warnings?.[0] ?? "Assign the target column in the Scoring step."}</p>
      </div>
    );
  }
  const curves = report.curves ?? {};
  const metricsById = new Map(report.metrics.map((metric) => [metric.id, metric]));
  return (
    <div className="evaluation-report">
      <div className="evaluation-scope">
        <span><strong>{report.data_scope.evaluated_row_count.toLocaleString()}</strong> evaluated rows</span>
        <span><strong>Full dataset</strong> metrics scope</span>
        <span><strong>{report.problem_type.replaceAll("_", " ")}</strong> problem</span>
        {report.monitoring.baseline_eligible && <span><strong>Monitoring-ready</strong> baseline snapshot</span>}
      </div>
      <div className="evaluation-metrics">
        {report.metrics.map((metric) => (
          <article key={metric.id}>
            <span>{metric.label}</span>
            <strong>{formatEvaluationMetric(metric.value, metric.unit)}</strong>
            <small>{metric.direction === "higher" ? "higher is better" :
              metric.direction === "lower" ? "lower is better" : "target: zero"}</small>
          </article>
        ))}
      </div>
      {report.confusion_matrix && report.confusion_matrix.labels.length > 0 && (
        <section className="evaluation-section">
          <header><div><h4>Confusion matrix</h4><p>Rows are actual classes; columns are predictions.</p></div></header>
          <ConfusionMatrix matrix={report.confusion_matrix} />
        </section>
      )}
      {report.class_metrics && report.class_metrics.length > 0 && (
        <section className="evaluation-section">
          <header><div><h4>Per-class quality</h4><p>Support and error balance for every reported class.</p></div></header>
          <div className="evaluation-class-table">
            <table>
              <thead><tr><th>Class</th><th>Support</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead>
              <tbody>{report.class_metrics.map((item, index) => (
                <tr key={`${String(item.label)}-${index}`}>
                  <td>{String(item.label)}</td>
                  <td>{item.support.toLocaleString()}</td>
                  <td>{formatEvaluationMetric(item.precision, "ratio")}</td>
                  <td>{formatEvaluationMetric(item.recall, "ratio")}</td>
                  <td>{formatEvaluationMetric(item.f1, "ratio")}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      )}
      {Object.keys(curves).length > 0 && (
        <div className="evaluation-chart-grid">
          {Object.entries(curves).map(([key, curve]) => (
            <section className="evaluation-section" key={key}>
              <header>
                <div><h4>{evaluationCurveTitle(key)}</h4><p>{curve.rendering}</p></div>
                {evaluationCurveMetric(key, metricsById) && (
                  <div className="evaluation-chart-kpi">
                    <span>{evaluationCurveMetric(key, metricsById)!.label}</span>
                    <strong>{formatEvaluationHeadlineMetric(
                      evaluationCurveMetric(key, metricsById)!
                    )}</strong>
                  </div>
                )}
              </header>
              <EvaluationLineChart curve={curve} curveKind={key}
                diagonal={key === "roc" || key === "calibration"} />
            </section>
          ))}
        </div>
      )}
      {report.distributions?.score_by_actual && (
        <section className="evaluation-section">
          <header><div><h4>Score distribution</h4><p>Full-data histogram split by actual class.</p></div></header>
          <StackedHistogram bins={report.distributions.score_by_actual} />
        </section>
      )}
      {report.residuals && (
        <>
          <section className="evaluation-section">
            <header><div><h4>Residual distribution</h4><p>Prediction minus actual, calculated over all evaluated rows.</p></div></header>
            <ResidualHistogram bins={report.residuals.histogram} />
            <div className="evaluation-residual-summary">
              <span>p05 <strong>{report.residuals.summary.p05.toPrecision(4)}</strong></span>
              <span>median <strong>{report.residuals.summary.median.toPrecision(4)}</strong></span>
              <span>p95 <strong>{report.residuals.summary.p95.toPrecision(4)}</strong></span>
              <span>std. dev. <strong>{report.residuals.summary.standard_deviation.toPrecision(4)}</strong></span>
            </div>
          </section>
          <section className="evaluation-section">
            <header><div><h4>Actual vs predicted</h4><p>{report.residuals.actual_vs_predicted.rendering}</p></div></header>
            <ActualPredictedScatter points={report.residuals.actual_vs_predicted.points} />
          </section>
          {report.residuals.qq_plot && (
            <section className="evaluation-section">
              <header><div><h4>Residual QQ-plot</h4><p>{report.residuals.qq_plot.rendering}</p></div></header>
              <ResidualQqPlot plot={report.residuals.qq_plot} summary={report.residuals.summary} />
            </section>
          )}
        </>
      )}
      {report.warnings.length > 0 && (
        <div className="evaluation-notes">
          {report.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </div>
      )}
    </div>
  );
}

export function ModelPerformanceSeriesReport({
  series
}: {
  series: Array<{ label: string; evaluation: ModelEvaluationSnapshot }>;
}) {
  const available = series.filter((item) => item.evaluation.status === "available");
  if (!available.length) return <div className="evaluation-empty"><strong>No chart series available</strong><p>Select a period containing matched actuals.</p></div>;
  const curveKeys = Array.from(new Set(available.flatMap((item) => Object.keys(item.evaluation.curves ?? {}))));
  const hasScoreDistribution = available.some((item) => item.evaluation.distributions?.score_by_actual?.length);
  const hasResiduals = available.some((item) => item.evaluation.residuals);
  return <div className="evaluation-report evaluation-series-report">
    <ComparisonLegend series={available} />
    {curveKeys.length > 0 && <div className="evaluation-chart-grid">{curveKeys.map((key) => {
      const curves = available.flatMap((item, index) => {
        const curve = item.evaluation.curves?.[key];
        return curve ? [{ label: item.label, curve, index }] : [];
      });
      return <section className="evaluation-section" key={key}><header><div><h4>{evaluationCurveTitle(key)}</h4><p>Selected aggregation periods on a shared scale.</p></div></header><ComparisonCurveChart series={curves} diagonal={key === "roc" || key === "calibration"} /></section>;
    })}</div>}
    {hasScoreDistribution && <section className="evaluation-section"><header><div><h4>Score distribution</h4><p>Normalized distribution for every selected period.</p></div></header><ComparisonDistributionChart series={available.flatMap((item, index) => {
      const bins = item.evaluation.distributions?.score_by_actual;
      return bins?.length ? [{ label: item.label, index, bins: bins.map((bin) => ({ lower: bin.lower, upper: bin.upper, count: bin.negative_count + bin.positive_count })) }] : [];
    })} xLabel="Prediction score" /></section>}
    {hasResiduals && <>
      <section className="evaluation-section"><header><div><h4>Residual distribution</h4><p>Normalized residual distribution for every selected period.</p></div></header><ComparisonDistributionChart series={available.flatMap((item, index) => item.evaluation.residuals ? [{ label: item.label, index, bins: item.evaluation.residuals.histogram }] : [])} xLabel="Residual (predicted − actual)" /></section>
      <section className="evaluation-section"><header><div><h4>Actual vs predicted</h4><p>Deterministic rendering samples, colored by selected period.</p></div></header><ComparisonScatterChart series={available.flatMap((item, index) => item.evaluation.residuals ? [{ label: item.label, index, points: item.evaluation.residuals.actual_vs_predicted.points }] : [])} /></section>
      <section className="evaluation-section"><header><div><h4>Residual QQ-plot</h4><p>Full-data residual quantiles, colored by selected period.</p></div></header><ComparisonQqChart series={available.flatMap((item, index) => item.evaluation.residuals?.qq_plot ? [{ label: item.label, index, points: item.evaluation.residuals.qq_plot.points }] : [])} /></section>
    </>}
  </div>;
}
