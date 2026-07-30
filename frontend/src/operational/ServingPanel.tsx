import { Activity, Archive, ArrowLeft, BarChart3, Copy, Eye, GitBranch, History, KeyRound, Play, Plus, Rocket, RotateCcw, Search, Settings2, ShieldCheck, SlidersHorizontal, X } from "lucide-react";
import { useCallback, useEffect, useState, type MouseEvent } from "react";

import { api } from "../api/client";
import type {
  BusinessCaseDataAttachment,
  ChallengerReplay,
  Deployment,
  DeploymentModelOption,
  DeploymentRevision,
  DeploymentRole,
  InferenceRequestSummary,
  InferenceInputContract,
  ModelArtifact,
  ModelEvaluationSnapshot,
  OnlineMonitoringBucketEvaluation,
  OnlineMonitoringRun,
  ScoreResponse
} from "../api/client";
import { PaginationControls } from "../components/PaginationControls";
import { PagedCatalogSelect } from "../components/PagedCatalogSelect";
import { ModelPerformanceReport, ModelPerformanceSeriesReport } from "../reports/ModelPerformanceReport";

import { asRecord as objectValue, formatOptionalDateTime as formatDate, shortIdOrUnknown as shortId } from "../shared/values";

type NoticeSetter = (message: string) => void;

function monitoringDateInput(value: Date) {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function monitoringMetrics(run: OnlineMonitoringRun) {
  const performance = run.report.performance as Record<string, unknown> | undefined;
  const service = performance?.service as Record<string, unknown> | undefined;
  return Array.isArray(service?.metrics)
    ? service.metrics as Array<{ id: string; label: string; value: number | null }>
    : [];
}

function monitoringHasActuals(run: OnlineMonitoringRun) {
  const actuals = run.report.actuals as Record<string, unknown> | undefined;
  return actuals?.status === "provided" || (!actuals?.status && Boolean(run.actuals_dataset_id));
}

type MonitoringBucket = {
  label: string;
  bucket_start: string;
  bucket_end: string;
  request_count: number;
  failed_request_count: number;
  fallback_request_count: number;
  p95_latency_ms: number | null;
  served_prediction_count: number;
};

function monitoringBucketDisplayLabel(bucketStart: string, bucketEnd: string, fallback: string) {
  const start = new Date(bucketStart);
  const end = new Date(bucketEnd);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return fallback;
  const date = new Intl.DateTimeFormat(undefined, {
    year: "numeric", month: "2-digit", day: "2-digit",
  }).format(start);
  const time = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  });
  return `${date} ${time.format(start)}–${time.format(end)}`;
}

function monitoringBuckets(run: OnlineMonitoringRun): MonitoringBucket[] {
  const aggregation = run.report.time_aggregation as Record<string, unknown> | undefined;
  if (!Array.isArray(aggregation?.buckets)) return [];
  return (aggregation.buckets as Array<Record<string, unknown>>).map((bucket) => {
    const bucketStart = String(bucket.bucket_start ?? "");
    const bucketEnd = String(bucket.bucket_end ?? "");
    return {
      label: monitoringBucketDisplayLabel(bucketStart, bucketEnd, String(bucket.label ?? "")),
      bucket_start: bucketStart,
      bucket_end: bucketEnd,
      request_count: Number(bucket.request_count ?? 0),
      failed_request_count: Number(bucket.failed_request_count ?? 0),
      fallback_request_count: Number(bucket.fallback_request_count ?? 0),
      p95_latency_ms: bucket.p95_latency_ms == null ? null : Number(bucket.p95_latency_ms),
      served_prediction_count: Number(bucket.served_prediction_count ?? 0),
    };
  });
}

type MonitoringPerformanceSeries = {
  id: string;
  label: string;
  unit: string;
  direction: string;
  points: Array<{ bucket_start: string; evaluated_row_count: number; value: number | null }>;
};

function monitoringPerformanceSeries(run: OnlineMonitoringRun): MonitoringPerformanceSeries[] {
  const aggregation = objectValue(run.report.time_aggregation);
  const performanceSeries = objectValue(aggregation.performance_series);
  return Array.isArray(performanceSeries.metrics)
    ? performanceSeries.metrics as MonitoringPerformanceSeries[]
    : [];
}

function monitoringBucketKey(value: string) {
  return value.replace(/(?:Z|\+00:00)$/, "");
}

function formatMonitoringMetric(value: number | null, unit: string) {
  if (value == null) return "—";
  return unit === "ratio"
    ? `${(value * 100).toFixed(1)}%`
    : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function MonitoringVisualizationModal({ run, onClose }: { run: OnlineMonitoringRun; onClose: () => void }) {
  const buckets = monitoringBuckets(run);
  const [selectedIndex, setSelectedIndex] = useState(Math.max(0, buckets.length - 1));
  const hasActuals = monitoringHasActuals(run);
  const performance = objectValue(run.report.performance);
  const servicePerformance = objectValue(performance.service);
  const rawFullWindowPerformance = hasActuals && servicePerformance.kind === "model_performance"
    ? servicePerformance as ModelEvaluationSnapshot
    : null;
  const hasInvalidLegacyScoreContract = Boolean(
    rawFullWindowPerformance
    && rawFullWindowPerformance.positive_class == null
    && rawFullWindowPerformance.metrics.some((metric) => metric.id === "roc_auc")
  );
  const invalidScoreMetricIds = new Set(["roc_auc", "average_precision", "brier_score", "log_loss"]);
  const fullWindowPerformance = rawFullWindowPerformance && hasInvalidLegacyScoreContract
    ? {
        ...rawFullWindowPerformance,
        metrics: rawFullWindowPerformance.metrics.filter((metric) => !invalidScoreMetricIds.has(metric.id)),
        curves: {},
        distributions: {},
        warnings: [
          "Score-based charts were omitted because this legacy report did not record a positive class. Run monitoring again to calculate them correctly.",
          ...rawFullWindowPerformance.warnings,
        ],
      }
    : rawFullWindowPerformance;
  const performanceSeries = monitoringPerformanceSeries(run);
  const evaluatedRowsByBucket = new Map(
    (performanceSeries[0]?.points ?? []).map((point) => [
      monitoringBucketKey(point.bucket_start),
      point.evaluated_row_count,
    ])
  );
  const initiallySelectedQualityBuckets = buckets
    .filter((bucket) => (evaluatedRowsByBucket.get(monitoringBucketKey(bucket.bucket_start)) ?? 0) > 0)
    .slice(-2)
    .map((bucket) => bucket.bucket_start);
  const qualityTab = run.problem_type === "regression" ? "regression" : "classification";
  type MonitoringVisualTab = "traffic" | "latency" | "reliability" | "classification" | "regression";
  const [qualityMode, setQualityMode] = useState<"full" | "aggregated">("full");
  const [activeTab, setActiveTab] = useState<MonitoringVisualTab>("traffic");
  const [selectedQualityBuckets, setSelectedQualityBuckets] = useState<string[]>(initiallySelectedQualityBuckets);
  const [bucketEvaluations, setBucketEvaluations] = useState<OnlineMonitoringBucketEvaluation[]>([]);
  const [bucketEvaluationLoading, setBucketEvaluationLoading] = useState(false);
  const [bucketEvaluationError, setBucketEvaluationError] = useState("");
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);
  useEffect(() => {
    if (qualityMode !== "aggregated" || selectedQualityBuckets.length === 0) {
      setBucketEvaluations([]);
      setBucketEvaluationError("");
      setBucketEvaluationLoading(false);
      return;
    }
    let active = true;
    setBucketEvaluationLoading(true);
    setBucketEvaluationError("");
    api.getOnlineMonitoringBucketEvaluations(run.id, selectedQualityBuckets)
      .then((items) => {
        if (active) setBucketEvaluations(items);
      })
      .catch((error) => {
        if (active) {
          setBucketEvaluations([]);
          setBucketEvaluationError(error instanceof Error ? error.message : "Could not load selected period charts");
        }
      })
      .finally(() => {
        if (active) setBucketEvaluationLoading(false);
      });
    return () => { active = false; };
  }, [qualityMode, run.id, selectedQualityBuckets]);
  const selected = buckets[selectedIndex] ?? buckets[0];
  const aggregation = run.report.time_aggregation as Record<string, unknown> | undefined;
  const chartWidth = 1040;
  const plotLeft = 66;
  const plotRight = 1018;
  const xAt = (index: number) => buckets.length <= 1
    ? (plotLeft + plotRight) / 2
    : plotLeft + (index / (buckets.length - 1)) * (plotRight - plotLeft);
  const pickFromPointer = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * chartWidth;
    const ratio = Math.max(0, Math.min(1, (svgX - plotLeft) / (plotRight - plotLeft)));
    setSelectedIndex(Math.round(ratio * Math.max(0, buckets.length - 1)));
  };
  const axisLabels = Array.from(new Set([0, Math.floor((buckets.length - 1) / 2), buckets.length - 1])).filter((index) => index >= 0);

  function lineChart(
    title: string,
    series: Array<{ label: string; values: Array<number | null>; className: string }>,
    valueLabel: (value: number) => string,
  ) {
    const values = series.flatMap((item) => item.values.filter((value): value is number => value != null));
    const min = Math.min(0, ...values);
    const max = Math.max(min === 0 ? 1 : 0, ...values);
    const span = max - min || 1;
    const top = 28;
    const bottom = 166;
    const yAt = (value: number) => bottom - ((value - min) / span) * (bottom - top);
    return <div className="serving-monitoring-chart"><div className="serving-monitoring-chart-title"><strong>{title}</strong><span>{series.map((item) => <span key={item.label} className={item.className}><i />{item.label}</span>)}</span></div><svg viewBox={`0 0 ${chartWidth} 210`} role="img" aria-label={`${title} over ${buckets.length} ${String(aggregation?.granularity ?? "time")} buckets`} onMouseMove={pickFromPointer}>
      {[0, 0.5, 1].map((ratio) => <g key={ratio}><line className="monitoring-chart-grid" x1={plotLeft} x2={plotRight} y1={bottom - ratio * (bottom - top)} y2={bottom - ratio * (bottom - top)} /><text className="monitoring-chart-axis" x={plotLeft - 10} y={bottom - ratio * (bottom - top) + 4} textAnchor="end">{valueLabel(min + span * ratio)}</text></g>)}
      {axisLabels.map((index) => <text key={index} className="monitoring-chart-axis" x={xAt(index)} y={194} textAnchor={index === 0 ? "start" : index === buckets.length - 1 ? "end" : "middle"}>{buckets[index]?.label ?? ""}</text>)}
      {series.map((item) => {
        let drawing = false;
        const path = item.values.map((value, index) => {
          if (value == null) {
            drawing = false;
            return "";
          }
          const command = drawing ? "L" : "M";
          drawing = true;
          return `${command}${xAt(index)},${yAt(value)}`;
        }).join(" ");
        const selectedValue = item.values[selectedIndex];
        return <g key={item.label} className={item.className}><path className="monitoring-chart-line" d={path} fill="none" />{selectedValue != null && <circle className="monitoring-chart-point" cx={xAt(selectedIndex)} cy={yAt(selectedValue)} r="5" />}</g>;
      })}
      <line className="monitoring-chart-cursor" x1={xAt(selectedIndex)} x2={xAt(selectedIndex)} y1={top} y2={bottom} />
    </svg></div>;
  }

  const tabs: Array<{ id: MonitoringVisualTab; label: string }> = [
    { id: "traffic", label: "Traffic" },
    { id: "latency", label: "Latency" },
    { id: "reliability", label: "Failures / fallbacks" },
  ];
  if (hasActuals) tabs.push({
    id: qualityTab,
    label: qualityTab === "regression" ? "Regression" : "Classification",
  });
  const isQualityTab = activeTab === "classification" || activeTab === "regression";
  const formatCountAxis = (value: number) => value.toLocaleString(undefined, {
    maximumFractionDigits: value > 0 && value < 10 ? 1 : 0,
  });
  const metricValue = (metric: MonitoringPerformanceSeries, bucketStart: string) => metric.points.find(
    (point) => monitoringBucketKey(point.bucket_start) === monitoringBucketKey(bucketStart)
  )?.value ?? null;
  const evaluatedRows = (bucketStart: string) => evaluatedRowsByBucket.get(monitoringBucketKey(bucketStart)) ?? 0;
  const toggleQualityBucket = (bucketStart: string) => {
    setSelectedQualityBuckets((current) => current.includes(bucketStart)
      ? current.filter((item) => item !== bucketStart)
      : current.length < 8 ? [...current, bucketStart] : current);
  };

  return <div className="modal-backdrop serving-monitoring-visual-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal-dialog serving-monitoring-visual-dialog" role="dialog" aria-modal="true" aria-labelledby="monitoring-visual-title"><div className="modal-header"><div><span className="builder-kicker">Full-scope monitoring · scored_at · local time</span><h2 id="monitoring-visual-title">Monitoring report visualization</h2><p>{formatDate(run.since)} — {formatDate(run.until)} · {buckets.length} {String(aggregation?.granularity ?? "time")} buckets</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="Close monitoring visualization"><X size={18} /></button></div><div className="serving-monitoring-visual-content">
    <div className="serving-monitoring-visual-tabs" role="tablist" aria-label="Monitoring chart category">
      {tabs.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} aria-controls={`monitoring-panel-${tab.id}`} id={`monitoring-tab-${tab.id}`} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}
    </div>
    <section className="serving-monitoring-visual-panel" role="tabpanel" id={`monitoring-panel-${activeTab}`} aria-labelledby={`monitoring-tab-${activeTab}`}>
      {!isQualityTab && selected && <div className="serving-monitoring-selected-period"><strong>{selected.label}</strong>{activeTab === "traffic" && <><span>{selected.request_count} requests</span><span>{selected.served_prediction_count} served</span></>}{activeTab === "latency" && <span>{selected.p95_latency_ms == null ? "No latency data" : `${Math.round(selected.p95_latency_ms)} ms p95`}</span>}{activeTab === "reliability" && <><span>{selected.failed_request_count} failed</span><span>{selected.fallback_request_count} fallback</span></>}</div>}
      {activeTab === "traffic" && <div className="serving-monitoring-traffic-charts">{lineChart("Requests", [{ label: "Requests", values: buckets.map((item) => item.request_count), className: "series-requests" }], formatCountAxis)}{lineChart("Served predictions", [{ label: "Served predictions", values: buckets.map((item) => item.served_prediction_count), className: "series-served" }], formatCountAxis)}</div>}
      {activeTab === "latency" && lineChart("P95 request latency", [{ label: "P95 latency", values: buckets.map((item) => item.p95_latency_ms), className: "series-latency" }], (value) => `${Math.round(value)} ms`)}
      {activeTab === "reliability" && lineChart("Failed requests and fallback use", [{ label: "Failed", values: buckets.map((item) => item.failed_request_count), className: "series-failed" }, { label: "Fallback", values: buckets.map((item) => item.fallback_request_count), className: "series-fallback" }], formatCountAxis)}
      {isQualityTab && <div className="serving-monitoring-quality-view">
        <div className="serving-monitoring-view-switch" role="group" aria-label="Model quality scope">
          <button type="button" aria-pressed={qualityMode === "full"} onClick={() => setQualityMode("full")}>Full window</button>
          <button type="button" aria-pressed={qualityMode === "aggregated"} disabled={!performanceSeries.length} onClick={() => setQualityMode("aggregated")}>Per {String(aggregation?.granularity ?? "time bucket")}</button>
        </div>
        {qualityMode === "full" && fullWindowPerformance && <ModelPerformanceReport report={fullWindowPerformance} />}
        {qualityMode === "aggregated" && performanceSeries.length > 0 && <>
          <div className="serving-monitoring-metrics-table-wrap">
            <table className="serving-monitoring-metrics-table">
              <thead><tr><th>Period</th><th className="numeric">Evaluated rows</th>{performanceSeries.map((metric) => <th className="numeric" key={metric.id}>{metric.label}</th>)}</tr></thead>
              <tbody>{buckets.map((bucket) => <tr key={bucket.bucket_start}><th scope="row">{bucket.label}</th><td className="numeric">{evaluatedRows(bucket.bucket_start).toLocaleString()}</td>{performanceSeries.map((metric) => <td className="numeric" key={metric.id}>{formatMonitoringMetric(metricValue(metric, bucket.bucket_start), metric.unit)}</td>)}</tr>)}</tbody>
            </table>
          </div>
          <section className="serving-monitoring-series-selector" aria-labelledby="monitoring-series-heading">
            <div><strong id="monitoring-series-heading">Chart series</strong><span>Select up to 8 periods to compare full-bucket chart statistics.</span></div>
            <div className="serving-monitoring-series-options">{buckets.map((bucket, index) => {
              const checked = selectedQualityBuckets.includes(bucket.bucket_start);
              const hasRows = evaluatedRows(bucket.bucket_start) > 0;
              const disabled = !hasRows || (!checked && selectedQualityBuckets.length >= 8);
              const inputId = `monitoring-series-${run.id}-${index}`;
              return <label key={bucket.bucket_start} htmlFor={inputId}><input id={inputId} type="checkbox" checked={checked} disabled={disabled} onChange={() => toggleQualityBucket(bucket.bucket_start)} /><span>{bucket.label}</span><small>{hasRows ? `${evaluatedRows(bucket.bucket_start).toLocaleString()} rows` : "No evaluated rows"}</small></label>;
            })}</div>
          </section>
          {bucketEvaluationLoading && <div className="serving-monitoring-series-status">Calculating chart series for the selected full buckets…</div>}
          {bucketEvaluationError && <div className="serving-inline-warning">{bucketEvaluationError}</div>}
          {!bucketEvaluationLoading && !bucketEvaluationError && selectedQualityBuckets.length === 0 && <div className="serving-monitoring-series-status">Select at least one period to show chart statistics.</div>}
          {!bucketEvaluationLoading && !bucketEvaluationError && bucketEvaluations.length > 0 && <ModelPerformanceSeriesReport series={bucketEvaluations.map((item) => ({ label: monitoringBucketDisplayLabel(item.bucket_start, item.bucket_end, item.label), evaluation: item.evaluation }))} />}
        </>}
        {qualityMode === "aggregated" && !performanceSeries.length && <div className="serving-inline-warning">Aggregated performance series are unavailable in this immutable report. Run monitoring again after this update to calculate them.</div>}
      </div>}
    </section>
    {selected && !isQualityTab && <label className="serving-monitoring-period-slider"><span>Selected period <strong>{selected.label}</strong></span><input type="range" min={0} max={Math.max(0, buckets.length - 1)} value={selectedIndex} onChange={(event) => setSelectedIndex(Number(event.target.value))} aria-label="Select monitoring period" /></label>}
  </div></div></div>;
}

export function ServingPanel({
  deployments,
  models,
  initialDeploymentId = "",
  onRefresh,
  onRegisterRefresh,
  setNotice
}: {
  deployments: Deployment[];
  models: ModelArtifact[];
  initialDeploymentId?: string;
  onRefresh: () => Promise<void>;
  onRegisterRefresh?: (handler: (() => Promise<void>) | null) => void;
  setNotice: NoticeSetter;
}) {
  type ServingTab = "overview" | "test" | "traffic" | "monitoring" | "access";
  type ServingModal = "create" | "revision" | "history" | "lifecycle" | "archive" | "credential" | "replay" | "inference" | null;
  const [serviceName, setServiceName] = useState("");
  const [modelId, setModelId] = useState("");
  const [selectedCreationModel, setSelectedCreationModel] = useState<ModelArtifact | undefined>();
  const [deploymentId, setDeploymentId] = useState("");
  const [selectedDeploymentSnapshot, setSelectedDeploymentSnapshot] = useState<Deployment | undefined>();
  const [activeTab, setActiveTab] = useState<ServingTab>("overview");
  const [modal, setModal] = useState<ServingModal>(null);
  const [recordId, setRecordId] = useState("");
  const [payloadJson, setPayloadJson] = useState("{\n  \"instances\": [\n    {\n      \"record_id\": \"example-1\",\n      \"features\": {}\n    }\n  ]\n}");
  const [testInputMode, setTestInputMode] = useState<"form" | "json">("form");
  const [inputContract, setInputContract] = useState<InferenceInputContract | null>(null);
  const [featureValues, setFeatureValues] = useState<Record<string, unknown>>({});
  const [contractError, setContractError] = useState("");
  const [modelOptions, setModelOptions] = useState<DeploymentModelOption[]>([]);
  const [modelOptionById, setModelOptionById] = useState<Record<string, DeploymentModelOption>>({});
  const [modelOptionSearch, setModelOptionSearch] = useState("");
  const [modelOptionTotal, setModelOptionTotal] = useState(0);
  const [modelOptionOffset, setModelOptionOffset] = useState(0);
  const [revisionError, setRevisionError] = useState("");
  const [scoreTarget, setScoreTarget] = useState("champion");
  const [scoreResult, setScoreResult] = useState<ScoreResponse | null>(null);
  const [scorePhase, setScorePhase] = useState<"idle" | "scoring" | "success" | "error">("idle");
  const [scoreError, setScoreError] = useState("");
  const [scoreElapsedSeconds, setScoreElapsedSeconds] = useState(0);
  const [history, setHistory] = useState<InferenceRequestSummary[]>([]);
  const [historyNextCursor, setHistoryNextCursor] = useState<string | null>(null);
  const [inferenceDetail, setInferenceDetail] = useState<Record<string, unknown> | null>(null);
  const [replays, setReplays] = useState<ChallengerReplay[]>([]);
  const [replayTotal, setReplayTotal] = useState(0);
  const [replayOffset, setReplayOffset] = useState(0);
  const [revisions, setRevisions] = useState<DeploymentRevision[]>([]);
  const [revisionTotal, setRevisionTotal] = useState(0);
  const [revisionOffset, setRevisionOffset] = useState(0);
  const [historyError, setHistoryError] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [roleByModel, setRoleByModel] = useState<Record<string, DeploymentRole | "">>({});
  const [revisionReason, setRevisionReason] = useState("");
  const [lifecycleReason, setLifecycleReason] = useState("");
  const [rollbackRevisionId, setRollbackRevisionId] = useState("");
  const [credential, setCredential] = useState("");
  const [busy, setBusy] = useState(false);
  const [catalogMode, setCatalogMode] = useState<"services" | "monitoring">("services");
  const [serviceSearch, setServiceSearch] = useState("");
  const [serviceStatus, setServiceStatus] = useState("");
  const [catalogDeployments, setCatalogDeployments] = useState<Deployment[]>([]);
  const [deploymentTotal, setDeploymentTotal] = useState(0);
  const [deploymentOffset, setDeploymentOffset] = useState(0);
  const [deploymentPageLoading, setDeploymentPageLoading] = useState(false);
  const [monitoringRuns, setMonitoringRuns] = useState<OnlineMonitoringRun[]>([]);
  const [monitoringRunTotal, setMonitoringRunTotal] = useState(0);
  const [monitoringRunOffset, setMonitoringRunOffset] = useState(0);
  const [monitoringActualsSnapshot, setMonitoringActualsSnapshot] = useState<BusinessCaseDataAttachment | undefined>();
  const [actualsDatasetId, setActualsDatasetId] = useState("");
  const [monitoringSince, setMonitoringSince] = useState(() => monitoringDateInput(new Date(Date.now() - 24 * 60 * 60 * 1000)));
  const [monitoringUntil, setMonitoringUntil] = useState(() => monitoringDateInput(new Date()));
  const [monitoringTargetColumn, setMonitoringTargetColumn] = useState("");
  const [monitoringRecordColumn, setMonitoringRecordColumn] = useState("");
  const [monitoringAggregation, setMonitoringAggregation] = useState<"none" | "hour" | "day" | "week" | "month">("none");
  const [monitoringVisualizationRunId, setMonitoringVisualizationRunId] = useState("");
  const [monitoringError, setMonitoringError] = useState("");
  const [selectedComparisonIds, setSelectedComparisonIds] = useState<string[]>([]);
  const [comparisonDeploymentById, setComparisonDeploymentById] = useState<Record<string, Deployment>>({});
  const selectedDeployment = (
    catalogDeployments.find((item) => item.id === deploymentId)
    ?? deployments.find((item) => item.id === deploymentId)
    ?? selectedDeploymentSnapshot
  );
  const eligibleModels = modelOptions.filter((item) =>
    item.business_case_id === selectedDeployment?.business_case_id
    && ["staging", "production"].includes(item.stage)
  );
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDeploymentPageLoading(true);
      api.pageDeployments({
        limit: 20,
        offset: deploymentOffset,
        search: serviceSearch.trim(),
        status: serviceStatus
      })
        .then((page) => {
          setCatalogDeployments(page.items);
          setDeploymentTotal(page.total);
        })
        .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load model services"))
        .finally(() => setDeploymentPageLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [deploymentOffset, deployments, serviceSearch, serviceStatus, setNotice]);

  useEffect(() => {
    setDeploymentOffset(0);
  }, [serviceSearch, serviceStatus]);

  useEffect(() => {
    let active = true;
    const request = selectedDeployment
      ? api.pageDeploymentMonitoringRuns(selectedDeployment.id, {
          limit: 10,
          offset: monitoringRunOffset
        })
      : api.pageOnlineMonitoringRuns({
          limit: 20,
          offset: monitoringRunOffset
        });
    request
      .then((page) => {
        if (!active) return;
        setMonitoringRuns(page.items);
        setMonitoringRunTotal(page.total);
      })
      .catch((error) => active && setMonitoringError(error instanceof Error ? error.message : "Could not load monitoring reports"));
    return () => { active = false; };
  }, [deployments.length, monitoringRunOffset, selectedDeployment?.id]);

  useEffect(() => {
    setMonitoringRunOffset(0);
  }, [selectedDeployment?.id]);

  useEffect(() => {
    if (!monitoringRuns.some((item) => item.status === "queued" || item.status === "running")) return;
    const timer = window.setInterval(() => {
      const request = selectedDeployment
        ? api.pageDeploymentMonitoringRuns(selectedDeployment.id, {
            limit: 10,
            offset: monitoringRunOffset
          })
        : api.pageOnlineMonitoringRuns({
            limit: 20,
            offset: monitoringRunOffset
          });
      void request
        .then((page) => {
          setMonitoringRuns(page.items);
          setMonitoringRunTotal(page.total);
        })
        .catch((error) => setMonitoringError(error instanceof Error ? error.message : "Could not refresh monitoring runs"));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [monitoringRunOffset, monitoringRuns, selectedDeployment?.id]);

  useEffect(() => {
    setMonitoringActualsSnapshot(undefined);
    setActualsDatasetId("");
    setMonitoringTargetColumn("");
    setMonitoringRecordColumn("");
  }, [selectedDeployment?.id]);

  useEffect(() => {
    setSelectedComparisonIds((current) => current.length ? current : catalogDeployments.slice(0, 2).map((item) => item.id));
    setComparisonDeploymentById((current) => ({
      ...current,
      ...Object.fromEntries(catalogDeployments.map((item) => [item.id, item]))
    }));
  }, [catalogDeployments]);

  async function refreshServingActivity(deployment: Deployment) {
    if (historyLoading) return;
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const [page, replayItems] = await Promise.all([
        api.inferenceLogSummary(deployment.id, 50),
        api.pageChallengerReplays(deployment.id, { limit: 10, offset: replayOffset })
      ]);
      setHistory(page.items);
      setHistoryNextCursor(page.next_cursor);
      setReplays(replayItems.items);
      setReplayTotal(replayItems.total);
      setNotice("Traffic & audit refreshed");
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Could not refresh serving activity");
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadMoreInferenceHistory() {
    if (!selectedDeployment || !historyNextCursor || historyLoading) return;
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const page = await api.inferenceLogSummary(
        selectedDeployment.id,
        50,
        historyNextCursor
      );
      setHistory((current) => [
        ...current,
        ...page.items.filter((item) => !current.some((existing) => existing.id === item.id))
      ]);
      setHistoryNextCursor(page.next_cursor);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Could not load more inference history");
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    if (!initialDeploymentId) return;
    let active = true;
    const cached = [...catalogDeployments, ...deployments].find(
      (item) => item.id === initialDeploymentId
    );
    (cached ? Promise.resolve(cached) : api.getDeployment(initialDeploymentId))
      .then((deployment) => {
        if (!active) return;
        setCatalogDeployments((current) => current.some((item) => item.id === deployment.id)
          ? current
          : [deployment, ...current]);
        setSelectedDeploymentSnapshot(deployment);
        setDeploymentId(deployment.id);
        setActiveTab("overview");
      })
      .catch((error) => active && setNotice(error instanceof Error ? error.message : "Service is no longer available"));
    return () => { active = false; };
  }, [catalogDeployments, deployments, initialDeploymentId, setNotice]);

  useEffect(() => {
    const assignments = selectedDeployment?.active_revision?.assignments ?? [];
    setRoleByModel(Object.fromEntries(assignments.map((item) => [item.model_id, item.role])));
    setScoreTarget("champion");
    if (!selectedDeployment) {
      setHistory([]);
      return;
    }
    setSelectedDeploymentSnapshot(selectedDeployment);
    let active = true;
    setHistoryError("");
    Promise.all([
      api.inferenceLogSummary(selectedDeployment.id, 50),
      api.pageChallengerReplays(selectedDeployment.id, { limit: 10, offset: replayOffset }),
      api.pageDeploymentRevisions(selectedDeployment.id, { limit: 10, offset: revisionOffset })
    ])
      .then(([page, replayItems, revisionItems]) => { if (active) {
        setHistory(page.items);
        setHistoryNextCursor(page.next_cursor);
        setReplays(replayItems.items);
        setReplayTotal(replayItems.total);
        setRevisions(revisionItems.items);
        setRevisionTotal(revisionItems.total);
      } })
      .catch((error) => active && setHistoryError(error instanceof Error ? error.message : "Could not load inference history"));
    return () => { active = false; };
  }, [
    replayOffset,
    revisionOffset,
    selectedDeployment?.id,
    selectedDeployment?.active_revision_id
  ]);

  useEffect(() => {
    setReplayOffset(0);
    setRevisionOffset(0);
    setModelOptionOffset(0);
    setModelOptionSearch("");
    setModelOptionById({});
  }, [selectedDeployment?.id]);

  useEffect(() => {
    if (!selectedDeployment) {
      setModelOptions([]);
      setModelOptionTotal(0);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      const pinnedIds = (
        selectedDeployment.active_revision?.assignments ?? []
      ).map((item) => item.model_id);
      Promise.all([
        api.pageDeploymentModelOptions(selectedDeployment.id, {
          limit: 20,
          offset: modelOptionOffset,
          search: modelOptionSearch.trim()
        }),
        pinnedIds.length
          ? api.pageDeploymentModelOptions(
              selectedDeployment.id,
              { limit: Math.min(100, pinnedIds.length), offset: 0 },
              pinnedIds
            )
          : Promise.resolve({
              items: [],
              total: 0,
              limit: 1,
              offset: 0,
              has_next: false
            })
      ])
        .then(([page, pinned]) => {
          if (!active) return;
          const merged = new Map(
            [...pinned.items, ...page.items].map((item) => [item.model_id, item])
          );
          setModelOptions([...merged.values()]);
          setModelOptionTotal(page.total);
          setModelOptionById((current) => ({
            ...current,
            ...Object.fromEntries([...merged.values()].map((item) => [item.model_id, item]))
          }));
        })
        .catch((error) => active && setRevisionError(
          error instanceof Error ? error.message : "Could not load serving model options"
        ));
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [
    modelOptionOffset,
    modelOptionSearch,
    selectedDeployment?.active_revision_id,
    selectedDeployment?.id
  ]);

  useEffect(() => {
    setModelOptionOffset(0);
  }, [modelOptionSearch]);

  useEffect(() => {
    if (!selectedDeployment) {
      setInputContract(null);
      setFeatureValues({});
      return;
    }
    let active = true;
    setContractError("");
    const challenger = scoreTarget === "champion" ? undefined : scoreTarget;
    api.deploymentInputContract(selectedDeployment.id, challenger)
      .then((contract) => {
        if (!active) return;
        setInputContract(contract);
        setFeatureValues(contract.example_features);
      })
      .catch((error) => {
        if (!active) return;
        setInputContract(null);
        setFeatureValues({});
        setContractError(error instanceof Error ? error.message : "Could not load the model input contract");
      });
    return () => { active = false; };
  }, [selectedDeployment?.id, selectedDeployment?.active_revision_id, scoreTarget]);

  useEffect(() => {
    if (scorePhase !== "scoring") return;
    const startedAt = Date.now();
    setScoreElapsedSeconds(0);
    const interval = window.setInterval(() => {
      setScoreElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 250);
    return () => window.clearInterval(interval);
  }, [scorePhase]);

  async function createDeployment() {
    if (!serviceName.trim() || !modelId) {
      setNotice("Choose a production model and enter a service name");
      return;
    }
    setBusy(true);
    try {
      const created = await api.createDeployment({ model_id: modelId, name: serviceName.trim(), retention_days: 365 });
      setDeploymentId(created.id);
      setActiveTab("overview");
      setModal(null);
      setServiceName("");
      setNotice("Model service created with revision v1");
      await onRefresh();
    } finally {
      setBusy(false);
    }
  }

  async function score() {
    if (!selectedDeployment) {
      setNotice("Create a deployment first");
      return;
    }
    let instances: Array<{ record_id?: string; features: Record<string, unknown> }>;
    if (testInputMode === "json") {
      try {
        const payload = JSON.parse(payloadJson) as { instances?: unknown };
        if (!Array.isArray(payload.instances) || !payload.instances.length) throw new Error();
        instances = payload.instances as Array<{ record_id?: string; features: Record<string, unknown> }>;
        if (instances.some((item) => !item || typeof item.features !== "object" || Array.isArray(item.features))) throw new Error();
      } catch {
        setNotice("Payload must contain a non-empty instances array with a features object in every item");
        return;
      }
    } else {
      const missing = inputContract?.fields.filter((field) => field.required && (featureValues[field.name] === "" || featureValues[field.name] == null)) ?? [];
      if (missing.length) {
        setNotice(`Complete required fields: ${missing.map((field) => field.name).join(", ")}`);
        return;
      }
      instances = [{ record_id: recordId || undefined, features: featureValues }];
    }
    setBusy(true);
    setScoreResult(null);
    setScoreError("");
    setScorePhase("scoring");
    try {
      const challenger = scoreTarget === "champion" ? undefined : scoreTarget;
      const result = await api.score(selectedDeployment.id, instances, challenger);
      setScoreResult(result);
      setScorePhase("success");
      setNotice(`Scored with ${result.served_role} model ${shortId(result.model_id)}`);
      void api.inferenceLogSummary(selectedDeployment.id, 50)
        .then((page) => setHistory(page.items))
        .catch((error) => setHistoryError(error instanceof Error ? error.message : "Prediction returned, but inference history could not be refreshed"));
    } catch (error) {
      const message = error instanceof Error ? error.message : "The scoring request failed";
      setScoreError(message);
      setScorePhase("error");
      setNotice(message);
    } finally {
      setBusy(false);
    }
  }

  function generatePayload() {
    const payload = {
      instances: [{
        ...(recordId.trim() ? { record_id: recordId.trim() } : {}),
        features: featureValues
      }]
    };
    setPayloadJson(JSON.stringify(payload, null, 2));
    setTestInputMode("json");
    setNotice("Payload generated from the form; you can now edit or copy it as JSON");
  }

  function updateFeature(name: string, valueType: string, rawValue: string | boolean) {
    let value: unknown = rawValue;
    if ((valueType === "number" || valueType === "integer") && typeof rawValue === "string") {
      value = rawValue === "" ? "" : Number(rawValue);
    }
    setFeatureValues((current) => ({ ...current, [name]: value }));
  }

  async function activateRevision() {
    if (!selectedDeployment) return;
    const eligibleModelIds = new Set(Object.keys(modelOptionById));
    const assignments = Object.entries(roleByModel)
      .filter((entry): entry is [string, DeploymentRole] => Boolean(entry[1]) && eligibleModelIds.has(entry[0]))
      .map(([assignedModelId, role]) => ({ model_id: assignedModelId, role }));
    if (assignments.filter((item) => item.role === "champion").length !== 1) {
      setNotice("Choose exactly one champion");
      return;
    }
    if (assignments.filter((item) => item.role === "fallback").length > 1) {
      setNotice("Choose at most one fallback");
      return;
    }
    const selectedChampionId = assignments.find((item) => item.role === "champion")?.model_id;
    const championSignature = modelOptionById[selectedChampionId ?? ""]?.contract_signature;
    const incompatible = assignments.filter((item) =>
      item.model_id !== selectedChampionId
      && modelOptionById[item.model_id]?.contract_signature !== championSignature
    );
    if (incompatible.length) {
      const message = "All challenger, shadow and fallback models must have the same input and output contract as the selected champion.";
      setRevisionError(message);
      setNotice(message);
      return;
    }
    setBusy(true);
    setRevisionError("");
    try {
      await api.createDeploymentRevision(selectedDeployment.id, assignments, revisionReason);
      setRevisionReason("");
      setModal(null);
      setNotice("New immutable service revision activated");
      await onRefresh();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not activate the service revision";
      setRevisionError(message);
      setNotice(`Revision was not activated: ${message}`);
    } finally {
      setBusy(false);
    }
  }

  async function changeDeploymentStatus() {
    if (!selectedDeployment || !lifecycleReason.trim()) return;
    const nextStatus = selectedDeployment.status === "running" ? "stopped" : "running";
    setBusy(true);
    try {
      await api.setDeploymentStatus(selectedDeployment.id, nextStatus, lifecycleReason.trim());
      setLifecycleReason("");
      setModal(null);
      setNotice(`Model service ${nextStatus === "running" ? "started" : "stopped"}`);
      await onRefresh();
    } finally {
      setBusy(false);
    }
  }

  async function archiveDeployment() {
    if (!selectedDeployment || !lifecycleReason.trim()) return;
    setBusy(true);
    try {
      await api.setDeploymentStatus(selectedDeployment.id, "archived", lifecycleReason.trim());
      setLifecycleReason("");
      setModal(null);
      setDeploymentId("");
      setNotice("Model service archived; its revisions and inference history were preserved");
      await onRefresh();
    } finally {
      setBusy(false);
    }
  }

  async function rollbackDeployment() {
    if (!selectedDeployment || !rollbackRevisionId || !revisionReason.trim()) return;
    setBusy(true);
    try {
      await api.rollbackDeployment(selectedDeployment.id, rollbackRevisionId, revisionReason.trim());
      setRevisionReason("");
      setRollbackRevisionId("");
      setModal(null);
      setNotice("Rollback activated as a new immutable service revision");
      await onRefresh();
    } finally {
      setBusy(false);
    }
  }

  async function createCredential() {
    setBusy(true);
    try {
      const created = await api.createApiCredential(`${selectedDeployment?.slug ?? "serving"}-client`, null);
      setCredential(String(created.token ?? ""));
      setNotice("Credential created; copy it now because it will not be shown again");
    } finally {
      setBusy(false);
    }
  }

  async function replayChallenger() {
    if (!selectedDeployment || scoreTarget === "champion") {
      setNotice("Select a challenger as the test target first");
      return;
    }
    const job = await api.createChallengerReplay(selectedDeployment.id, scoreTarget, 1000);
    setReplayOffset(0);
    setReplays((current) => [job, ...current.filter((item) => item.id !== job.id)].slice(0, 10));
    setReplayTotal((current) => current + 1);
    setModal(null);
    setNotice("Challenger replay queued over up to 1,000 historical requests");
  }

  async function runOnlineMonitoring() {
    if (!selectedDeployment || !monitoringSince || !monitoringUntil) {
      setNotice("Select a complete monitoring window");
      return;
    }
    setBusy(true);
    setMonitoringError("");
    try {
      const run = await api.createOnlineMonitoringRun(selectedDeployment.id, {
        since: new Date(monitoringSince).toISOString(),
        until: new Date(monitoringUntil).toISOString(),
        aggregation_granularity: monitoringAggregation,
        ...(actualsDatasetId ? { actuals_dataset_id: actualsDatasetId } : {}),
        ...(monitoringTargetColumn.trim() ? { actuals_target_column: monitoringTargetColumn.trim() } : {}),
        join: {
          strategy: "auto",
          ...(monitoringRecordColumn.trim() ? { actuals_record_id_column: monitoringRecordColumn.trim() } : {})
        }
      });
      setMonitoringRunOffset(0);
      setMonitoringRuns((current) => [run, ...current.filter((item) => item.id !== run.id)].slice(0, 10));
      setMonitoringRunTotal((current) => current + 1);
      setNotice(actualsDatasetId
        ? "Full-scope online monitoring report with performance evaluation queued"
        : "Full-scope operational monitoring report queued without actuals");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not queue online monitoring";
      setMonitoringError(message);
      setNotice(message);
    } finally {
      setBusy(false);
    }
  }

  async function refreshMonitoringRuns() {
    try {
      const page = selectedDeployment
        ? await api.pageDeploymentMonitoringRuns(selectedDeployment.id, {
            limit: 10,
            offset: monitoringRunOffset
          })
        : await api.pageOnlineMonitoringRuns({
            limit: 20,
            offset: monitoringRunOffset
          });
      setMonitoringRuns(page.items);
      setMonitoringRunTotal(page.total);
      setMonitoringError("");
      setNotice(selectedDeployment ? "Monitoring tab refreshed" : "Monitoring dashboard refreshed");
    } catch (error) {
      setMonitoringError(error instanceof Error ? error.message : "Could not refresh monitoring reports");
    }
  }

  const refreshAllServingTabs = useCallback(async () => {
    if (!selectedDeployment) {
      const [, runs] = await Promise.all([
        onRefresh(),
        api.pageOnlineMonitoringRuns({ limit: 20, offset: monitoringRunOffset })
      ]);
      setMonitoringRuns(runs.items);
      setMonitoringRunTotal(runs.total);
      setMonitoringError("");
      return;
    }

    const challenger = scoreTarget === "champion" ? undefined : scoreTarget;
    const [, page, replayItems, revisionItems, contract, runs] = await Promise.all([
      onRefresh(),
      api.inferenceLogSummary(selectedDeployment.id, 50),
      api.pageChallengerReplays(selectedDeployment.id, { limit: 10, offset: replayOffset }),
      api.pageDeploymentRevisions(selectedDeployment.id, { limit: 10, offset: revisionOffset }),
      api.deploymentInputContract(selectedDeployment.id, challenger),
      api.pageDeploymentMonitoringRuns(selectedDeployment.id, {
        limit: 10,
        offset: monitoringRunOffset
      })
    ]);
    setHistory(page.items);
    setHistoryNextCursor(page.next_cursor);
    setReplays(replayItems.items);
    setReplayTotal(replayItems.total);
    setRevisions(revisionItems.items);
    setRevisionTotal(revisionItems.total);
    setInputContract(contract);
    setFeatureValues(contract.example_features);
    setMonitoringRuns(runs.items);
    setMonitoringRunTotal(runs.total);
    setHistoryError("");
    setContractError("");
    setMonitoringError("");
  }, [
    monitoringRunOffset,
    onRefresh,
    replayOffset,
    revisionOffset,
    scoreTarget,
    selectedDeployment
  ]);

  useEffect(() => {
    if (!onRegisterRefresh) return;
    onRegisterRefresh(refreshAllServingTabs);
    return () => onRegisterRefresh(null);
  }, [onRegisterRefresh, refreshAllServingTabs]);

  async function archiveMonitoringRun(runId: string) {
    if (!window.confirm("Archive this monitoring run? Its immutable report and lineage will remain available through the API.")) return;
    try {
      await api.archiveOnlineMonitoringRun(runId);
      setMonitoringRuns((current) => current.filter((item) => item.id !== runId));
      setMonitoringRunTotal((current) => Math.max(0, current - 1));
      setNotice("Monitoring run archived");
    } catch (error) {
      setMonitoringError(error instanceof Error ? error.message : "Could not archive monitoring run");
    }
  }

  async function archiveMonitoringHistory() {
    if (!selectedDeployment || !window.confirm("Archive all finished monitoring runs for this service? Reports and lineage will remain available through the API.")) return;
    try {
      const result = await api.archiveDeploymentMonitoringHistory(selectedDeployment.id);
      setMonitoringRuns((current) => current.filter((item) =>
        item.deployment_id !== selectedDeployment.id || !["succeeded", "failed"].includes(item.status)
      ));
      setMonitoringRunOffset(0);
      setMonitoringRunTotal((current) => Math.max(0, current - result.archived_run_count));
      setNotice(`${result.archived_run_count} monitoring run(s) archived`);
    } catch (error) {
      setMonitoringError(error instanceof Error ? error.message : "Could not archive monitoring history");
    }
  }

  function toggleComparisonService(deployment: Deployment) {
    const serviceId = deployment.id;
    setComparisonDeploymentById((current) => ({
      ...current,
      [serviceId]: deployment
    }));
    setSelectedComparisonIds((current) =>
      current.includes(serviceId)
        ? current.filter((item) => item !== serviceId)
        : [...current, serviceId]
    );
    if (!monitoringRuns.some((item) => item.deployment_id === serviceId)) {
      void api.pageDeploymentMonitoringRuns(serviceId, { limit: 1, offset: 0 })
        .then((page) => setMonitoringRuns((current) => [
          ...current.filter((item) => item.deployment_id !== serviceId),
          ...page.items
        ]))
        .catch((error) => setMonitoringError(
          error instanceof Error ? error.message : "Could not load the selected service report"
        ));
    }
  }

  function openDeployment(deployment: Deployment) {
    setSelectedDeploymentSnapshot(deployment);
    setDeploymentId(deployment.id);
    setActiveTab("overview");
    setScoreResult(null);
    setScorePhase("idle");
    setScoreError("");
    setInferenceDetail(null);
    setCatalogMode("services");
  }

  const assignments = selectedDeployment?.active_revision?.assignments ?? [];
  const champion = assignments.find((item) => item.role === "champion");
  const challengers = assignments.filter((item) => item.role === "challenger");
  const shadows = assignments.filter((item) => item.role === "shadow");
  const fallback = assignments.find((item) => item.role === "fallback");
  const configuredChampionId = Object.entries(roleByModel).find(([, role]) => role === "champion")?.[0];
  const configuredChampionSignature = modelOptionById[configuredChampionId ?? ""]?.contract_signature;

  function updateModelRole(assignedModelId: string, role: DeploymentRole | "") {
    setRevisionError("");
    setRoleByModel((current) => {
      const next = { ...current };
      if (role === "champion") {
        for (const [modelId, currentRole] of Object.entries(next)) {
          if (currentRole === "champion" && modelId !== assignedModelId) next[modelId] = "";
        }
      }
      next[assignedModelId] = role;
      return next;
    });
  }

  function modelLabel(assignedModelId: string | undefined) {
    if (!assignedModelId) return "Not configured";
    const option = modelOptionById[assignedModelId];
    if (option) return `${option.name} · ${option.version}`;
    const model = models.find((item) => item.id === assignedModelId);
    return model ? `${model.name} · ${model.version}` : shortId(assignedModelId);
  }

  function closeModal() {
    setModal(null);
    if (modal === "inference") setInferenceDetail(null);
  }

  const comparisonRuns = selectedComparisonIds.flatMap((serviceId) => {
    const deployment = comparisonDeploymentById[serviceId]
      ?? catalogDeployments.find((item) => item.id === serviceId)
      ?? deployments.find((item) => item.id === serviceId);
    if (!deployment) return [];
    const runs = monitoringRuns.filter((item) => item.deployment_id === serviceId);
    const run = runs.find((item) => item.status === "succeeded") ?? runs[0];
    return [{ deployment, run }];
  });
  const monitoringVisualizationRun = monitoringRuns.find((item) => item.id === monitoringVisualizationRunId) ?? null;

  if (!selectedDeployment) {
    return (
      <section className="serving-catalog">
        <div className="serving-page-header">
          <div>
            <span className="builder-kicker">Online inference</span>
            <h2>Model services</h2>
            <p>Publish stable prediction endpoints and manage the models behind them.</p>
          </div>
          <div className="catalog-toolbar-actions">
            <button className="secondary-button" type="button" onClick={() => setCatalogMode(catalogMode === "monitoring" ? "services" : "monitoring")}>
              <Activity size={16} /> {catalogMode === "monitoring" ? "Services" : "Monitoring dashboard"}
            </button>
            <button className="primary-button" type="button" onClick={() => setModal("create")}>
              <Plus size={16} /> New service
            </button>
          </div>
        </div>

        <div className="model-registry-filters">
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Search model services"
              placeholder="Search service name, slug or endpoint"
              value={serviceSearch}
              onChange={(event) => setServiceSearch(event.target.value)}
            />
          </label>
          <label>
            <span><SlidersHorizontal size={14} /> Status</span>
            <select value={serviceStatus} onChange={(event) => setServiceStatus(event.target.value)}>
              <option value="">All active statuses</option>
              <option value="requested">Requested</option>
              <option value="building">Building</option>
              <option value="running">Running</option>
              <option value="stopped">Stopped</option>
              <option value="degraded">Degraded</option>
              <option value="failed">Failed</option>
            </select>
          </label>
          <span>{deploymentTotal} services</span>
        </div>

        {catalogMode === "services" && <div className="serving-guidance" role="note">
          <Rocket size={20} />
          <div><strong>Start with a production model.</strong><span>Create one service, then add challengers, shadows or a fallback from its Overview.</span></div>
        </div>}

        {catalogMode === "monitoring" && <div className="serving-monitoring-dashboard">
          <div className="panel form-panel serving-monitoring-selector">
            <div className="panel-header"><div><span className="builder-kicker">Comparative read model</span><h3>Compare service reports</h3></div><button className="secondary-button compact-button" type="button" onClick={() => void refreshMonitoringRuns()}><RotateCcw size={14} /> Refresh</button></div>
            <p>Select services to compare their latest immutable manual report. Metrics remain tied to their visible window and actuals coverage.</p>
            <div className="serving-monitoring-checkboxes">{catalogDeployments.map((deployment) => {
              const selected = selectedComparisonIds.includes(deployment.id);
              return <label key={deployment.id} className={selected ? "selected" : undefined}><input type="checkbox" checked={selected} onChange={() => toggleComparisonService(deployment)} /><span><strong>{deployment.name}</strong><small>{deployment.status} · revision v{deployment.active_revision?.version_number ?? "—"}</small></span></label>;
            })}</div>
          </div>
          {monitoringError && <div className="error-banner">{monitoringError}</div>}
          <div className="panel serving-monitoring-comparison">
            <div className="panel-header"><div><span className="builder-kicker">Latest completed or active run</span><h3>Service monitoring</h3></div></div>
            <div className="serving-monitoring-comparison-grid">{comparisonRuns.map(({ deployment, run }) => {
              const scope = run?.report.data_scope as Record<string, unknown> | undefined;
              const health = run?.report.service_health as Record<string, unknown> | undefined;
              const metrics = run ? monitoringMetrics(run) : [];
              const hasActuals = run ? monitoringHasActuals(run) : false;
              return <article key={deployment.id}><div><strong>{deployment.name}</strong><button className="secondary-button compact-button" type="button" onClick={() => { openDeployment(deployment); setActiveTab("monitoring"); }}>Open</button></div>{run ? <><span className={`status-pill ${run.status}`}>{run.status}</span><small>{formatDate(run.since)} — {formatDate(run.until)}</small><div className="serving-monitoring-kpis"><span><strong>{Number(scope?.processed_request_count ?? run.processed_request_count)}</strong><small>requests</small></span><span><strong>{Number(health?.failed_request_count ?? 0)}</strong><small>failed requests</small></span><span><strong>{health?.p95_latency_ms == null ? "—" : `${Math.round(Number(health.p95_latency_ms))} ms`}</strong><small>p95 latency</small></span><span><strong>{Number(scope?.served_prediction_count ?? 0)}</strong><small>served predictions</small></span>{hasActuals && <span><strong>{scope ? `${Math.round(Number(scope.actuals_coverage ?? 0) * 100)}%` : "—"}</strong><small>actuals coverage</small></span>}{metrics.slice(0, 3).map((metric) => <span key={metric.id}><strong>{metric.value == null ? "—" : Number(metric.value).toFixed(3)}</strong><small>{metric.label}</small></span>)}</div>{!hasActuals && run.status === "succeeded" && <div className="serving-inline-warning">Performance not evaluated · actuals not provided</div>}{run.error_message && <p>{run.error_message}</p>}</> : <div className="serving-list-empty"><Activity size={20} /><strong>No report</strong><span>Open the service and run monitoring.</span></div>}</article>;
            })}{!comparisonRuns.length && <div className="serving-list-empty"><Activity size={22} /><strong>Select at least one service</strong><span>Checkboxes control which reports appear in the comparison.</span></div>}</div>
          </div>
        </div>}

        {catalogMode === "services" && catalogDeployments.length > 0 && <div className="serving-table-wrap">
          <table className="serving-table">
            <thead><tr><th>Service</th><th>Status</th><th>Champion</th><th>Revision</th><th>Additional roles</th><th className="action-column">Actions</th></tr></thead>
            <tbody>{catalogDeployments.map((deployment) => {
              const activeAssignments = deployment.active_revision?.assignments ?? [];
              const activeChampion = activeAssignments.find((item) => item.role === "champion");
              return <tr key={deployment.id}>
                <td><strong>{deployment.name}</strong><code>{deployment.slug}</code></td>
                <td><span className={`status-pill ${deployment.status}`}>{deployment.status}</span></td>
                <td>{modelLabel(activeChampion?.model_id)}</td>
                <td>v{deployment.active_revision?.version_number ?? "—"}</td>
                <td>{activeAssignments.filter((item) => item.role === "challenger").length} challengers · {activeAssignments.filter((item) => item.role === "shadow").length} shadows</td>
                <td className="serving-table-actions"><button className="secondary-button compact-button" type="button" onClick={() => openDeployment(deployment)}>Open</button><button className="secondary-button compact-button danger-button" type="button" onClick={() => { openDeployment(deployment); setLifecycleReason(""); setModal("archive"); }}><Archive size={14} /> Archive</button></td>
              </tr>;
            })}</tbody>
          </table>
        </div>}
        <PaginationControls
          total={deploymentTotal}
          limit={20}
          offset={deploymentOffset}
          onOffsetChange={setDeploymentOffset}
          disabled={deploymentPageLoading}
          label="model services"
        />
          {catalogMode === "services" && !deploymentPageLoading && !catalogDeployments.length && <div className="panel serving-empty-state">
            <Rocket size={28} />
            <h3>No model services yet</h3>
            <p>Create a stable endpoint backed by your first production model.</p>
            <button className="primary-button" type="button" onClick={() => setModal("create")}><Plus size={16} /> Create first service</button>
          </div>}

        {modal === "create" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}>
          <div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="create-serving-title">
            <div className="modal-header"><div><span className="builder-kicker">New endpoint</span><h2 id="create-serving-title">Create model service</h2><p>The service name and endpoint stay stable when you change model versions later.</p></div><button className="icon-button" type="button" onClick={closeModal} aria-label="Close"><X size={18} /></button></div>
            <div className="serving-modal-body form-panel">
              <label>Service name<input autoFocus value={serviceName} onChange={(event) => setServiceName(event.target.value)} placeholder="Estates Sell Prices Service" /></label>
              <label>
                Initial champion
                <PagedCatalogSelect<ModelArtifact>
                  value={modelId}
                  onChange={(value, item) => {
                    setModelId(value);
                    setSelectedCreationModel(item);
                  }}
                  loadPage={async (query) => {
                    const page = await api.pageModels({ ...query, stage: "production" });
                    return { ...page, items: page.items.map((family) => family.latest) };
                  }}
                  getId={(model) => model.id}
                  getLabel={(model) => `${model.name} · ${model.version}`}
                  selectedItem={selectedCreationModel}
                  emptyLabel="Choose a production model"
                  searchPlaceholder="Search production models"
                  reloadKey={`${models.length}:${models.map((item) => `${item.id}:${item.stage}`).join(",")}`}
                />
                <small>Only production models can receive public traffic as champion.</small>
              </label>
            </div>
            <div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button" onClick={createDeployment} type="button" disabled={busy || !serviceName.trim() || !modelId}><Plus size={16} /> Create service</button></div>
          </div>
        </div>}
      </section>
    );
  }

  return (
    <section className="serving-detail-screen">
      <button className="serving-back-button" type="button" onClick={() => setDeploymentId("")}><ArrowLeft size={16} /> All model services</button>
      <div className="serving-detail-header">
        <div><span className="builder-kicker">Online inference service</span><h2>{selectedDeployment.name}</h2><div className="serving-title-meta"><span className={`status-pill ${selectedDeployment.status}`}>{selectedDeployment.status}</span><span>Revision v{selectedDeployment.active_revision?.version_number ?? "—"}</span><span>Retention {selectedDeployment.retention_days} days</span></div></div>
        <div className="model-row-actions">
          <button className="secondary-button" type="button" onClick={() => setModal("history")}><History size={16} /> Revision history</button>
          <button className="secondary-button" type="button" onClick={() => setModal("lifecycle")}>
            {selectedDeployment.status === "running" ? <X size={16} /> : <Play size={16} />}
            {selectedDeployment.status === "running" ? "Stop service" : selectedDeployment.status === "stopped" ? "Start service" : "Validate & resume"}
          </button>
          <button className="secondary-button" type="button" onClick={() => setModal("revision")}><GitBranch size={16} /> Configure models</button>
          <button className="secondary-button danger-button" type="button" onClick={() => { setLifecycleReason(""); setModal("archive"); }}><Archive size={16} /> Archive</button>
        </div>
      </div>
      <div className="serving-endpoint-bar"><div><small>Stable production endpoint</small><code>{selectedDeployment.endpoint_url}</code></div><button className="icon-button" type="button" aria-label="Copy endpoint" title="Copy endpoint" onClick={() => navigator.clipboard.writeText(selectedDeployment.endpoint_url ?? "")}><Copy size={16} /></button></div>

      <nav className="serving-tabs" aria-label="Model service sections">
        {([
          ["overview", "Overview", Rocket], ["test", "Test endpoint", Play], ["traffic", "Traffic & audit", Activity], ["monitoring", "Monitoring", SlidersHorizontal], ["access", "API access", KeyRound]
        ] as const).map(([tab, label, Icon]) => <button key={tab} className={activeTab === tab ? "active" : ""} type="button" onClick={() => setActiveTab(tab)}><Icon size={16} />{label}{tab === "traffic" && history.length > 0 && <span>{history.length}</span>}</button>)}
      </nav>

      {activeTab === "overview" && <div className="serving-tab-content">
        <div className="serving-summary-grid">
          <article className="panel serving-role-card primary"><span><Rocket size={18} />Champion</span><strong>{modelLabel(champion?.model_id)}</strong><small>Receives all requests sent to the stable endpoint.</small></article>
          <article className="panel serving-role-card"><span><GitBranch size={18} />Challengers</span><strong>{challengers.length}</strong><small>{challengers.length ? challengers.map((item) => modelLabel(item.model_id)).join(", ") : "None configured"}</small></article>
          <article className="panel serving-role-card"><span><Activity size={18} />Shadows</span><strong>{shadows.length}</strong><small>{shadows.length ? shadows.map((item) => modelLabel(item.model_id)).join(", ") : "None configured"}</small></article>
          <article className="panel serving-role-card"><span><ShieldCheck size={18} />Fallback</span><strong>{fallback ? "Ready" : "Not set"}</strong><small>{modelLabel(fallback?.model_id)}</small></article>
        </div>
        <div className="panel serving-next-steps"><div className="panel-header"><div><span className="builder-kicker">Recommended workflow</span><h3>What would you like to do?</h3></div></div><div className="serving-action-grid">
          <button type="button" onClick={() => setActiveTab("test")}><Play size={18} /><span><strong>Test the endpoint</strong><small>Send one example and inspect the response.</small></span></button>
          <button type="button" onClick={() => setModal("revision")}><Settings2 size={18} /><span><strong>Change model roles</strong><small>Add a challenger, shadow or fallback in a new revision.</small></span></button>
          <button type="button" onClick={() => setActiveTab("traffic")}><History size={18} /><span><strong>Review traffic</strong><small>Inspect auditable requests and model executions.</small></span></button>
        </div></div>
      </div>}

      {activeTab === "test" && <div className="serving-tab-content serving-test-layout">
        <div className="panel form-panel"><div className="panel-header"><div><span className="builder-kicker">Single request</span><h3>Test endpoint</h3></div><Play size={18} /></div><p className="serving-section-intro">Use the champion endpoint or call a challenger directly without changing production traffic.</p>
          <label>Target<select value={scoreTarget} onChange={(event) => setScoreTarget(event.target.value)}><option value="champion">Champion · public endpoint</option>{challengers.map((item) => <option key={item.model_id} value={item.model_id}>Challenger · {modelLabel(item.model_id)}</option>)}</select></label>
          <div className="segmented-control serving-input-mode" aria-label="Test request input mode">
            <button type="button" className={testInputMode === "form" ? "active" : ""} onClick={() => setTestInputMode("form")}>Form</button>
            <button type="button" className={testInputMode === "json" ? "active" : ""} onClick={() => setTestInputMode("json")}>JSON payload</button>
          </div>
          {testInputMode === "form" ? <>
            <label>Record ID <span className="optional-label">recommended</span><input value={recordId} onChange={(event) => setRecordId(event.target.value)} placeholder="e.g. customer-1042" /><small>Needed later to join predictions with actual outcomes.</small></label>
            {contractError && <div className="error-banner">{contractError}</div>}
            {!contractError && !inputContract && <div className="serving-contract-loading">Loading model input contract…</div>}
            {inputContract && <div className="serving-feature-form">
              <div className="serving-contract-summary"><strong>{inputContract.fields.length} required features</strong><small>Generated from model {shortId(inputContract.model_id)} in the active revision.</small></div>
              {inputContract.fields.map((field) => <label key={field.name}>
                <span className="serving-feature-label"><code>{field.name}</code><em>{field.value_type}</em>{field.required && <i>required</i>}</span>
                {field.value_type === "boolean"
                  ? <select value={String(Boolean(featureValues[field.name]))} onChange={(event) => updateFeature(field.name, field.value_type, event.target.value === "true")}><option value="false">false</option><option value="true">true</option></select>
                  : <div className="serving-feature-input-wrap"><input
                        type={field.value_type === "number" || field.value_type === "integer" ? "number" : "text"}
                        step={field.value_type === "integer" ? 1 : field.value_type === "number" ? "any" : undefined}
                        min={field.minimum ?? undefined}
                        max={field.maximum ?? undefined}
                        value={String(featureValues[field.name] ?? "")}
                        onChange={(event) => updateFeature(field.name, field.value_type, event.target.value)}
                      />{field.value_type === "string" && field.options.length > 0 && <div className="serving-category-suggest"><button type="button" className="serving-suggest-trigger">Suggest</button><div className="serving-suggest-popover" role="listbox" aria-label={`Suggested values for ${field.name}`}><small>Top categories in the full training set</small>{field.options.map((option) => <button type="button" role="option" key={String(option)} onClick={() => updateFeature(field.name, field.value_type, String(option))}>{String(option)}</button>)}</div></div>}</div>}
                <small>{field.description}</small>
              </label>)}
              <button className="secondary-button" type="button" onClick={generatePayload}><Copy size={15} /> Generate payload</button>
            </div>}
          </> : <label>Request JSON<textarea className="json-input" value={payloadJson} onChange={(event) => setPayloadJson(event.target.value)} rows={18} /><small>Exact request body. It may contain up to 1,000 instances.</small></label>}
          <div className="button-row"><button className="primary-button" onClick={score} type="button" disabled={busy}>{scorePhase === "scoring" ? <span className="serving-score-button-spinner" aria-hidden="true" /> : <Play size={16} />}{scorePhase === "scoring" ? `Scoring… ${scoreElapsedSeconds}s` : "Send test request"}</button>{scoreTarget !== "champion" && <button className="secondary-button" onClick={() => setModal("replay")} type="button"><History size={16} /> Replay history</button>}</div>
        </div>
        <div className="panel serving-response-panel">
          <div className="panel-header"><div><span className="builder-kicker">Response</span><h3>{scorePhase === "scoring" ? "Scoring request" : scorePhase === "error" ? "Request failed" : scoreResult ? "Prediction returned" : "Waiting for a request"}</h3></div>{scoreResult && <span className="status-pill active">{scoreResult.served_role}</span>}</div>
          {scorePhase === "scoring" ? <div className="serving-response-progress" role="status" aria-live="polite"><span className="serving-score-spinner" aria-hidden="true" /><strong>Running the pinned service revision</strong><p>Validating the input contract, transforming features, scoring the champion and configured shadows, then durably writing the Inference Log.</p><small>{scoreElapsedSeconds ? `${scoreElapsedSeconds}s elapsed` : "Request accepted…"}</small></div>
            : scorePhase === "error" ? <div className="serving-response-error" role="alert"><X size={26} /><strong>Prediction was not returned</strong><p>{scoreError}</p><small>No successful result is shown until the auditable inference record is safely persisted.</small></div>
            : scoreResult ? <pre className="json-output">{JSON.stringify(scoreResult, null, 2)}</pre>
              : <div className="serving-response-empty"><Play size={26} /><p>Your prediction, request ID and warnings will appear here.</p></div>}
        </div>
      </div>}

      {activeTab === "traffic" && <div className="serving-tab-content">
        <div className="serving-section-header"><div><span className="builder-kicker">Full payload retention</span><h3>Inference log</h3><p>Every accepted request and model execution is retained for audit and future monitoring.</p></div><div className="catalog-toolbar-actions"><button className="secondary-button" type="button" onClick={() => void refreshServingActivity(selectedDeployment)} disabled={historyLoading}><RotateCcw className={historyLoading ? "run-spinner" : undefined} size={16} /> {historyLoading ? "Refreshing…" : "Refresh"}</button>{challengers.length > 0 && <button className="secondary-button" type="button" onClick={() => { setScoreTarget(challengers[0].model_id); setModal("replay"); }}><History size={16} /> Replay challenger</button>}</div></div>
        {historyError && <div className="error-banner">{historyError}</div>}
        <div className="panel inference-log-list serving-traffic-list">{history.map((item) => <article key={item.id}><span><strong>{item.status}</strong><small>{formatDate(item.created_at)} · {item.record_count} records</small></span><span><code>{shortId(item.served_model_id || item.champion_model_id)}</code><small>{item.served_role || "champion"}{item.fallback_used ? " · fallback used" : ""}</small></span><span><strong>{item.latency_ms ?? "—"} ms</strong><small>{item.warnings[0] ?? item.error_message}</small></span><button className="secondary-button compact-button" type="button" onClick={() => api.inferenceDetail(selectedDeployment.id, item.id).then((detail) => { setInferenceDetail(detail); setModal("inference"); })}><Eye size={14} /> Details</button></article>)}{!history.length && !historyError && <div className="serving-list-empty"><History size={24} /><strong>No requests recorded yet</strong><span>Use Test endpoint or call the REST API to generate the first auditable request.</span></div>}</div>
        {historyNextCursor && <div className="pagination-controls"><span>{history.length} requests loaded</span><button className="secondary-button compact-button" type="button" onClick={() => void loadMoreInferenceHistory()} disabled={historyLoading}>Load next 50</button></div>}
        {replayTotal > 0 && <div className="serving-replay-section"><h3>Challenger replays</h3><div className="panel inference-log-list">{replays.map((item) => <article key={item.id}><span><strong>{item.status}</strong><small>{formatDate(item.created_at)}</small></span><span><code>{shortId(item.challenger_model_id)}</code><small>revision {shortId(item.deployment_revision_id)}</small></span><span><strong>{item.processed_records} records</strong><small>{item.failed_requests} failed request(s)</small></span></article>)}</div><PaginationControls total={replayTotal} limit={10} offset={replayOffset} onOffsetChange={setReplayOffset} label="challenger replays" /></div>}
      </div>}

      {activeTab === "monitoring" && <div className="serving-tab-content serving-monitoring-layout">
        <div className="panel form-panel">
          <div className="panel-header"><div><span className="builder-kicker">Manual full-scope run</span><h3>Generate monitoring report</h3></div><Activity size={18} /></div>
          <p className="serving-section-intro">The platform snapshots every retained public-endpoint execution in the selected scoring-time window. Add immutable actuals to also calculate service and per-model effectiveness.</p>
          <label>
            Actuals dataset · optional
            <PagedCatalogSelect<BusinessCaseDataAttachment>
              value={actualsDatasetId}
              selectedItem={monitoringActualsSnapshot}
              reloadKey={selectedDeployment?.id ?? ""}
              loadPage={(query) => selectedDeployment
                ? api.pageBusinessCaseDataAttachments(selectedDeployment.business_case_id, {
                    ...query,
                    role: "monitoring_actuals"
                  })
                : Promise.resolve({ items: [], total: 0, limit: query.limit, offset: query.offset, has_next: false })}
              getId={(item) => item.data_asset_id}
              getLabel={(item) => `${item.data_asset_name ?? item.data_asset_id} · v${item.data_asset_version_number ?? "?"}${item.target_column ? ` · target ${item.target_column}` : ""}`}
              emptyLabel="No actuals · operational and distribution metrics only"
              searchPlaceholder="Search monitoring actuals"
              disabled={!selectedDeployment}
              onPageLoaded={(page) => {
                if (!actualsDatasetId && page.offset === 0 && page.items.length) {
                  const first = page.items[0];
                  setMonitoringActualsSnapshot(first);
                  setActualsDatasetId(first.data_asset_id);
                  setMonitoringTargetColumn(first.target_column ?? "");
                  setMonitoringRecordColumn(first.primary_key_column ?? "");
                }
              }}
              onChange={(next, attachment) => {
                setActualsDatasetId(next);
                setMonitoringActualsSnapshot(attachment);
                setMonitoringTargetColumn(attachment?.target_column ?? "");
                setMonitoringRecordColumn(attachment?.primary_key_column ?? "");
              }}
            />
            <small>Without actuals, performance metrics are explicitly marked as not evaluated. Eligible actuals must be attached to this Business Case with role monitoring_actuals.</small>
          </label>
          {!actualsDatasetId && <div className="serving-inline-warning">No actuals dataset is selected. You can still run operational, traffic, input and prediction monitoring.</div>}
          <div className="serving-monitoring-window"><label>Since · scoring time<input type="datetime-local" value={monitoringSince} onChange={(event) => setMonitoringSince(event.target.value)} /></label><label><span className="serving-monitoring-time-label"><span>Until · scoring time</span><button type="button" onClick={() => setMonitoringUntil(monitoringDateInput(new Date()))}>Now</button></span><input type="datetime-local" value={monitoringUntil} onChange={(event) => setMonitoringUntil(event.target.value)} /></label></div>
          <label>Time aggregation<select value={monitoringAggregation} onChange={(event) => setMonitoringAggregation(event.target.value as typeof monitoringAggregation)}><option value="none">No aggregation · one summary for the full window</option><option value="hour">Per hour</option><option value="day">Per day</option><option value="week">Per week</option><option value="month">Per month</option></select><small>Calendar buckets use scored_at and include empty intervals, so the report has one row per selected period.</small></label>
          {actualsDatasetId && <details><summary>Join overrides</summary><label>Actuals record ID column<input value={monitoringRecordColumn} onChange={(event) => setMonitoringRecordColumn(event.target.value)} placeholder="Inferred from attachment" /></label><label>Actuals target column<input value={monitoringTargetColumn} onChange={(event) => setMonitoringTargetColumn(event.target.value)} placeholder="Inferred from attachment or model" /></label><small>Auto join prefers prediction_id, then request_id + record ID, then a unique record ID in this window.</small></details>}
          {monitoringError && <div className="error-banner">{monitoringError}</div>}
          <button className="primary-button" type="button" onClick={() => void runOnlineMonitoring()} disabled={busy || !monitoringSince || !monitoringUntil}><Play size={16} /> {busy ? "Queuing…" : "Run monitoring report"}</button>
        </div>
        <div className="panel serving-monitoring-runs">
          <div className="panel-header"><div><span className="builder-kicker">Immutable history</span><h3>Monitoring reports</h3></div><div className="catalog-toolbar-actions"><button className="secondary-button compact-button" type="button" onClick={() => void archiveMonitoringHistory()} disabled={!monitoringRuns.some((item) => item.deployment_id === selectedDeployment.id && ["succeeded", "failed"].includes(item.status))}><Archive size={14} /> Archive history</button><button className="secondary-button compact-button" type="button" onClick={() => void refreshMonitoringRuns()}><RotateCcw size={14} /> Refresh</button></div></div>
          {monitoringRuns.filter((item) => item.deployment_id === selectedDeployment.id).map((run) => {
            const scope = run.report.data_scope as Record<string, unknown> | undefined;
            const health = run.report.service_health as Record<string, unknown> | undefined;
            const metrics = monitoringMetrics(run);
            const hasActuals = monitoringHasActuals(run);
            const performance = run.report.performance as Record<string, unknown> | undefined;
            const modelsReport = Array.isArray(performance?.models) ? performance.models as Array<Record<string, unknown>> : [];
            const aggregation = run.report.time_aggregation as Record<string, unknown> | undefined;
            const buckets = Array.isArray(aggregation?.buckets) ? aggregation.buckets as Array<Record<string, unknown>> : [];
            return <article key={run.id} className="serving-monitoring-run"><div className="serving-monitoring-run-head"><span><strong>{formatDate(run.since)} — {formatDate(run.until)}</strong><small>run {shortId(run.id)} · scored_at · {run.processed_request_count} requests</small></span><span className="serving-monitoring-run-actions"><span className={`status-pill ${run.status}`}>{run.status}</span>{run.status === "succeeded" && <button className="secondary-button compact-button" type="button" onClick={() => setMonitoringVisualizationRunId(run.id)}><BarChart3 size={14} /> Visualize</button>}{["succeeded", "failed"].includes(run.status) && <button className="secondary-button compact-button" type="button" onClick={() => void archiveMonitoringRun(run.id)}><Archive size={13} /> Archive</button>}</span></div>{run.status === "failed" ? <div className="error-banner">{run.error_message}</div> : run.status !== "succeeded" ? <div className="serving-response-progress"><span className="serving-score-spinner" aria-hidden="true" /><strong>Processing retained inference history</strong><small>Full-scope snapshot and bounded aggregates run asynchronously.</small></div> : <><div className="serving-monitoring-kpis"><span><strong>{Number(scope?.processed_request_count ?? run.processed_request_count)}</strong><small>requests</small></span><span><strong>{Number(health?.record_count ?? 0)}</strong><small>records</small></span><span><strong>{Number(health?.failed_request_count ?? 0)}</strong><small>failed requests</small></span><span><strong>{Number(health?.fallback_request_count ?? 0)}</strong><small>fallback requests</small></span><span><strong>{health?.p95_latency_ms == null ? "—" : `${Math.round(Number(health.p95_latency_ms))} ms`}</strong><small>p95 latency</small></span><span><strong>{Number(scope?.served_prediction_count ?? 0)}</strong><small>served predictions</small></span>{hasActuals && <span><strong>{Math.round(Number(scope?.actuals_coverage ?? 0) * 100)}%</strong><small>actuals coverage</small></span>}{metrics.slice(0, 4).map((metric) => <span key={metric.id}><strong>{metric.value == null ? "—" : Number(metric.value).toFixed(3)}</strong><small>{metric.label}</small></span>)}</div>{buckets.length > 0 && <div className="serving-monitoring-buckets"><div className="serving-monitoring-bucket-toolbar"><strong>{String(aggregation?.granularity)} aggregation · scored_at · UTC</strong></div><div className="serving-monitoring-bucket-table"><div className="serving-monitoring-bucket-head"><span>Period</span><span>Requests</span><span>Failed</span><span>Fallback</span><span>P95 latency</span><span>Served</span></div>{buckets.map((bucket) => <div key={String(bucket.bucket_start)}><span>{String(bucket.label)}</span><span>{Number(bucket.request_count ?? 0)}</span><span>{Number(bucket.failed_request_count ?? 0)}</span><span>{Number(bucket.fallback_request_count ?? 0)}</span><span>{bucket.p95_latency_ms == null ? "—" : `${Math.round(Number(bucket.p95_latency_ms))} ms`}</span><span>{Number(bucket.served_prediction_count ?? 0)}</span></div>)}</div></div>}{!hasActuals && <div className="serving-inline-warning">Performance not evaluated · actuals not provided. Operational, input and prediction monitoring cover the full selected window.</div>}{hasActuals && <div className="serving-monitoring-models"><strong>Model and role results</strong>{modelsReport.map((item) => {
              const evaluation = item.evaluation as Record<string, unknown> | undefined;
              const modelMetrics = Array.isArray(evaluation?.metrics) ? evaluation.metrics as Array<{ id: string; label: string; value: number | null }> : [];
              return <span key={`${item.deployment_revision_id}:${item.model_id}:${item.role}`}><code>{shortId(String(item.model_id))}</code><small>{String(item.role)} · revision {shortId(String(item.deployment_revision_id))} · {Number(item.scored_row_count ?? 0)} rows</small>{modelMetrics[0] && <strong>{modelMetrics[0].label}: {modelMetrics[0].value == null ? "—" : Number(modelMetrics[0].value).toFixed(3)}</strong>}</span>;
            })}</div>}{run.warnings.length > 0 && hasActuals && <div className="serving-inline-warning">{run.warnings[0]}</div>}</>}</article>;
          })}
          {!monitoringRuns.some((item) => item.deployment_id === selectedDeployment.id) && <div className="serving-list-empty"><Activity size={24} /><strong>No monitoring report yet</strong><span>Select a retained scoring-time window to create the first immutable report. Actuals are optional.</span></div>}
          <PaginationControls
            total={monitoringRunTotal}
            limit={10}
            offset={monitoringRunOffset}
            onOffsetChange={setMonitoringRunOffset}
            label="monitoring reports"
          />
        </div>
      </div>}

      {activeTab === "access" && <div className="serving-tab-content serving-access-layout">
        <div className="panel"><div className="panel-header"><div><span className="builder-kicker">REST API</span><h3>Call this service directly</h3></div><ShieldCheck size={18} /></div><p className="serving-section-intro">Authenticate as an existing platform account. Business Case grants still determine access.</p><div className="serving-code-block"><code>POST {selectedDeployment.endpoint_url}</code><button className="icon-button" type="button" onClick={() => navigator.clipboard.writeText(selectedDeployment.endpoint_url ?? "")}><Copy size={15} /></button></div><pre className="json-output serving-code-example">{JSON.stringify({ instances: [{ record_id: "property-1042", features: { area: 84, rooms: 4 } }] }, null, 2)}</pre></div>
        <div className="panel"><div className="panel-header"><div><span className="builder-kicker">Python client</span><h3>Create client credential</h3></div><KeyRound size={18} /></div><p className="serving-section-intro">Create a revocable credential for scripts and notebooks. The secret is displayed only once.</p><button className="primary-button" type="button" onClick={() => { setCredential(""); setModal("credential"); }}><KeyRound size={16} /> Generate credential</button></div>
      </div>}

      {monitoringVisualizationRun && <MonitoringVisualizationModal key={monitoringVisualizationRun.id} run={monitoringVisualizationRun} onClose={() => setMonitoringVisualizationRunId("")} />}

      {modal === "revision" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog serving-revision-dialog" role="dialog" aria-modal="true" aria-labelledby="revision-title"><div className="modal-header"><div><span className="builder-kicker">Immutable configuration</span><h2 id="revision-title">Configure model roles</h2><p>Saving creates and immediately activates a new service revision. Only staging and production models with a compatible inference contract can share traffic.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><div className="serving-role-help"><span><strong>Champion</strong> public traffic</span><span><strong>Challenger</strong> direct tests and replay</span><span><strong>Shadow</strong> copied live traffic</span><span><strong>Fallback</strong> technical failures</span></div>{revisionError && <div className="error-banner" role="alert">{revisionError}</div>}<label className="search-field"><Search size={16} /><input aria-label="Search serving model options" placeholder="Search model name, algorithm or ID" value={modelOptionSearch} onChange={(event) => setModelOptionSearch(event.target.value)} /></label><div className="serving-role-grid">{eligibleModels.map((model) => {
          const option = modelOptionById[model.model_id];
          const compatible = !configuredChampionSignature || option?.contract_signature === configuredChampionSignature;
          return <label key={model.model_id} className={!compatible && roleByModel[model.model_id] !== "champion" ? "serving-model-incompatible" : ""}><span>{model.name} · {model.version}<small>{model.stage}{!compatible && roleByModel[model.model_id] !== "champion" ? " · incompatible with selected champion" : ""}</small></span><select value={roleByModel[model.model_id] ?? ""} onChange={(event) => updateModelRole(model.model_id, event.target.value as DeploymentRole | "")}><option value="">Not assigned</option><option value="champion" disabled={!option?.allowed_roles.includes("champion")}>Champion</option><option value="challenger" disabled={!compatible || !option?.allowed_roles.includes("challenger")}>Challenger</option><option value="shadow" disabled={!compatible || !option?.allowed_roles.includes("shadow")}>Shadow</option><option value="fallback" disabled={!compatible || !option?.allowed_roles.includes("fallback")}>Fallback</option></select></label>;
        })}</div><PaginationControls total={modelOptionTotal} limit={20} offset={modelOptionOffset} onOffsetChange={setModelOptionOffset} label="serving model options" />{!eligibleModels.length && <div className="serving-inline-warning">No staging or production models are available in this Business Case.</div>}<label>Reason for change<input value={revisionReason} onChange={(event) => setRevisionReason(event.target.value)} placeholder="e.g. Add validated challenger v6" /></label></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button" type="button" onClick={activateRevision} disabled={busy || !revisionReason.trim()}><GitBranch size={15} /> Activate new revision</button></div></div></div>}

      {modal === "history" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="history-title"><div className="modal-header"><div><span className="builder-kicker">Immutable history</span><h2 id="history-title">Service revisions</h2><p>Rollback copies a historical configuration into a new auditable revision.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><div className="model-version-list">{revisions.map((revision) => <article key={revision.id}><div className="model-version-marker"><span>v{revision.version_number}</span></div><div><strong>Revision v{revision.version_number}</strong><span>{formatDate(revision.created_at)} · {revision.assignments.length} assigned model(s)</span><small>{revision.reason || "No reason recorded"}</small></div>{revision.id === selectedDeployment.active_revision_id ? <i className="pipeline-status published">active</i> : <button className="secondary-button compact-button" type="button" onClick={() => setRollbackRevisionId(revision.id)}>Select rollback</button>}</article>)}</div><PaginationControls total={revisionTotal} limit={10} offset={revisionOffset} onOffsetChange={setRevisionOffset} label="service revisions" />{rollbackRevisionId && <label>Rollback reason<input value={revisionReason} onChange={(event) => setRevisionReason(event.target.value)} placeholder="Why is this revision being restored?" /></label>}</div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Close</button><button className="primary-button" type="button" onClick={rollbackDeployment} disabled={busy || !rollbackRevisionId || !revisionReason.trim()}><History size={15} /> Roll back</button></div></div></div>}

      {modal === "lifecycle" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="lifecycle-title"><div className="modal-header"><div><span className="builder-kicker">Service lifecycle</span><h2 id="lifecycle-title">{selectedDeployment.status === "running" ? "Stop service" : "Validate and resume service"}</h2><p>{selectedDeployment.status === "running" ? "The endpoint will reject scoring while revision history remains available." : "The active revision will be validated before traffic is accepted."}</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><label>Reason<input value={lifecycleReason} onChange={(event) => setLifecycleReason(event.target.value)} placeholder="Reason for this operational change" /></label></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button" type="button" onClick={changeDeploymentStatus} disabled={busy || !lifecycleReason.trim()}>{selectedDeployment.status === "running" ? "Stop service" : "Validate & resume"}</button></div></div></div>}

      {modal === "archive" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="archive-title"><div className="modal-header"><div><span className="builder-kicker">Service lifecycle</span><h2 id="archive-title">Archive {selectedDeployment.name}?</h2><p>The endpoint will be permanently disabled and removed from the active list. Revision and inference history will be preserved for audit.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><label>Reason<input autoFocus value={lifecycleReason} onChange={(event) => setLifecycleReason(event.target.value)} placeholder="Why is this service being archived?" /></label></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button danger-button" type="button" onClick={archiveDeployment} disabled={busy || !lifecycleReason.trim()}><Archive size={16} /> Archive service</button></div></div></div>}

      {modal === "replay" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="replay-title"><div className="modal-header"><div><span className="builder-kicker">Batch evaluation</span><h2 id="replay-title">Replay historical traffic</h2><p>Score up to 1,000 retained requests with a challenger. Production responses are not changed.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body form-panel"><label>Challenger<select value={scoreTarget === "champion" ? "" : scoreTarget} onChange={(event) => setScoreTarget(event.target.value)}><option value="">Choose a challenger</option>{challengers.map((item) => <option key={item.model_id} value={item.model_id}>{modelLabel(item.model_id)}</option>)}</select></label><div className="serving-inline-warning">Replay uses the current immutable revision and retained historical inputs.</div></div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>Cancel</button><button className="primary-button" type="button" onClick={replayChallenger} disabled={busy || scoreTarget === "champion" || !scoreTarget}><History size={16} /> Queue replay</button></div></div></div>}

      {modal === "credential" && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog" role="dialog" aria-modal="true" aria-labelledby="credential-title"><div className="modal-header"><div><span className="builder-kicker">Python client</span><h2 id="credential-title">{credential ? "Copy your credential" : "Generate client credential"}</h2><p>{credential ? "This secret will not be shown again after you close this window." : "The credential inherits your current account and Business Case permissions."}</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body">{credential ? <div className="credential-once"><strong>Copy now — shown once</strong><code>{credential}</code><button className="secondary-button" type="button" onClick={() => navigator.clipboard.writeText(credential)}><Copy size={15} /> Copy credential</button></div> : <div className="serving-credential-explainer"><ShieldCheck size={24} /><p>You can revoke this credential later through the API. Creating it does not bypass platform permissions.</p></div>}</div><div className="modal-actions"><button className="secondary-button" type="button" onClick={closeModal}>{credential ? "Done" : "Cancel"}</button>{!credential && <button className="primary-button" type="button" onClick={createCredential} disabled={busy}><KeyRound size={16} /> Generate credential</button>}</div></div></div>}

      {modal === "inference" && inferenceDetail && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && closeModal()}><div className="modal-dialog serving-action-dialog serving-inference-dialog" role="dialog" aria-modal="true" aria-labelledby="inference-title"><div className="modal-header"><div><span className="builder-kicker">Audited request</span><h2 id="inference-title">Inference details</h2><p>Stored request, response and per-model executions.</p></div><button className="icon-button" type="button" onClick={closeModal}><X size={18} /></button></div><div className="serving-modal-body"><pre className="json-output">{JSON.stringify(inferenceDetail, null, 2)}</pre></div></div></div>}
    </section>
  );
}
