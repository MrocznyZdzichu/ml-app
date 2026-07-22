import { BarChart3, Box, Brain, Check, ChevronLeft, ChevronRight, Clipboard, Database, Download, Eye, GitBranch, RotateCcw, Search, X } from "lucide-react";
import type { CSSProperties } from "react";
import { lazy, Suspense, useEffect, useState } from "react";

import { api } from "../api/client";
import { ArtifactDependenciesDialog } from "../operational/ArtifactDependenciesDialog";
import { DialogNavigationActions } from "../components/dialogNavigation";
import type {
  BusinessCase,
  ModelArtifact,
  ModelEvaluationSnapshot,
  TrainingEvaluationReport,
  Pipeline,
  PipelineVersion,
  PipelineRun,
  PipelineRunEvent,
  PipelineRunDetails,
  PipelineRunOutputPreview,
  PipelineRunOutputProfile
} from "../api/client";
const ModelDetailsDialog = lazy(() =>
  import("../operational/LifecyclePanels").then((module) => ({
    default: module.ModelDetailsDialog
  }))
);
const ScoringReportDialog = lazy(() =>
  import("../operational/ScoringReportsPanel").then((module) => ({
    default: module.ScoringReportDialog
  }))
);

export function PipelineVersionHistoryDialog({
  pipeline,
  businessCaseName,
  onClose
}: {
  pipeline: Pipeline;
  businessCaseName: string;
  onClose: () => void;
}) {
  const [versions, setVersions] = useState<PipelineVersion[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<PipelineVersion | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api.listPipelineVersions(pipeline.id)
      .then((items) => {
        if (!active) return;
        setVersions(
          items
            .filter((item) => item.status === "published")
            .sort((left, right) => right.version_number - left.version_number)
        );
      })
      .catch((requestError) => active && setError(
        requestError instanceof Error ? requestError.message : "Could not load pipeline versions"
      ));
    return () => { active = false; };
  }, [pipeline.id]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal-dialog pipeline-version-history-dialog" role="dialog" aria-modal="true" aria-label={`Published versions of ${pipeline.name}`}>
        <div className="modal-header">
          <div>
            <span className="builder-kicker">Published workflow</span>
            <h2>{pipeline.name}</h2>
            <p>{businessCaseName} · immutable definitions used by pipeline runs</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close pipeline versions"><X size={18} /></button>
        </div>
        {error && <div className="error-banner">{error}</div>}
        {!versions.length && !error && <div className="empty-state">Loading published versions…</div>}
        <div className="pipeline-version-history-layout">
          <div className="pipeline-version-list">
            {versions.map((version, index) => (
              <article className={selectedVersion?.id === version.id ? "selected" : ""} key={version.id}>
                <div className="pipeline-version-marker">v{version.version_number}</div>
                <div>
                  <strong>
                    Version {version.version_number}
                    {index === 0 && <i className="pipeline-status published">latest</i>}
                  </strong>
                  <span>{version.published_at ? formatDateTime(version.published_at) : "publication date unavailable"}</span>
                  <small>definition hash {version.definition_hash.slice(0, 12)}</small>
                </div>
                <button className="secondary-button compact-button" type="button" onClick={() => setSelectedVersion(version)}>
                  Inspect
                </button>
              </article>
            ))}
          </div>
        </div>
        {selectedVersion && (
          <PipelineDefinitionDialog
            pipeline={pipeline}
            version={selectedVersion}
            onBack={() => setSelectedVersion(null)}
            onClose={onClose}
          />
        )}
      </div>
    </div>
  );
}

function PipelineDefinitionDialog({
  pipeline,
  version,
  onBack,
  onClose
}: {
  pipeline: Pipeline;
  version: PipelineVersion;
  onBack: () => void;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const definitionJson = JSON.stringify(version.definition, null, 2);

  async function copyDefinition() {
    setError("");
    try {
      await navigator.clipboard.writeText(definitionJson);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Clipboard access was denied by the browser.");
    }
  }

  function downloadDefinition() {
    const blob = new Blob([definitionJson], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${safeDownloadName(pipeline.name)}-v${version.version_number}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  return (
    <div className="modal-backdrop definition-modal-backdrop nested-modal" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="modal-dialog pipeline-definition-dialog" role="dialog" aria-modal="true" aria-label={`Pipeline ${pipeline.name} version ${version.version_number} definition`}>
        <header className="pipeline-definition-header">
          <div>
            <span className="builder-kicker">Immutable pipeline definition</span>
            <h2>{pipeline.name} · v{version.version_number}</h2>
            <p>Hash <code>{version.definition_hash}</code></p>
          </div>
          <div className="pipeline-definition-actions">
            <button className="secondary-button" type="button" onClick={copyDefinition}>
              {copied ? <Check size={15} /> : <Clipboard size={15} />}
              {copied ? "Copied" : "Copy definition"}
            </button>
            <button className="primary-button" type="button" onClick={downloadDefinition}>
              <Download size={15} /> Download JSON
            </button>
            <DialogNavigationActions onBack={onBack} onClose={onClose} closeLabel="Close pipeline version workflow" />
          </div>
        </header>
        {error && <div className="error-banner">{error}</div>}
        <div className="pipeline-definition-code">
          <pre>{definitionJson}</pre>
        </div>
      </section>
    </div>
  );
}

export function PipelineRunHistoryDialog({
  pipelines,
  businessCases,
  refreshKey,
  includeDryRuns = true,
  initialPipelineId = "all",
  title = "Pipeline runs",
  description = "Latest 200 runs across your available pipelines.",
  onClose,
  onDetails,
  onExamineDataset
}: {
  pipelines: Pipeline[];
  businessCases: BusinessCase[];
  refreshKey: number;
  includeDryRuns?: boolean;
  initialPipelineId?: string;
  title?: string;
  description?: string;
  onClose: () => void;
  onDetails: (run: PipelineRun) => void;
  onExamineDataset: (datasetId: string) => void;
}) {
  const [historyRuns, setHistoryRuns] = useState<PipelineRun[]>([]);
  const [pipelineFilter, setPipelineFilter] = useState(initialPipelineId);
  const [statusFilter, setStatusFilter] = useState("all");
  const [reloadKey, setReloadKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [artifactsRun, setArtifactsRun] = useState<PipelineRun | null>(null);
  const [dependenciesRun, setDependenciesRun] = useState<PipelineRun | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api.listPipelineRunHistory(200)
      .then((items) => {
        if (active) setHistoryRuns(items);
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError instanceof Error ? requestError.message : "Could not load run history");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [refreshKey, reloadKey]);

  const allowedPipelineIds = new Set(pipelines.map((pipeline) => pipeline.id));
  const visibleRuns = historyRuns.filter((run) =>
    allowedPipelineIds.has(run.pipeline_id)
    && (includeDryRuns || !run.is_dry_run)
    && (pipelineFilter === "all" || run.pipeline_id === pipelineFilter)
    && (statusFilter === "all" || run.status === statusFilter)
  );
  const pipelineById = new Map(pipelines.map((pipeline) => [pipeline.id, pipeline]));

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        className="modal-dialog run-history-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Pipeline runs history"
      >
        <div className="modal-header">
          <div>
            <span className="builder-kicker">Execution history</span>
            <h2>{title}</h2>
            <p>{description}</p>
          </div>
          <div className="run-details-actions">
            <button
              className="secondary-button compact-button"
              type="button"
              disabled={loading}
              onClick={() => setReloadKey((current) => current + 1)}
            >
              <RotateCcw size={14} /> Refresh
            </button>
            <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
              <X size={18} />
            </button>
          </div>
        </div>
        <div className="run-history-filters">
          <label>
            Pipeline
            <select value={pipelineFilter} onChange={(event) => setPipelineFilter(event.target.value)}>
              <option value="all">All pipelines</option>
              {pipelines.map((pipeline) => (
                <option key={pipeline.id} value={pipeline.id}>{pipeline.name}</option>
              ))}
            </select>
          </label>
          <label>
            Status
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All statuses</option>
              {["queued", "running", "succeeded", "failed", "cancelled"].map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </select>
          </label>
          <span>{visibleRuns.length} shown</span>
        </div>
        {error && <div className="error-banner">{error}</div>}
        {loading ? (
          <div className="empty-state">Loading run history…</div>
        ) : (
          <div className="run-history-table" role="table" aria-label="Pipeline run history">
            <div className="run-history-row head" role="row">
              <span>Pipeline / run</span>
              <span>Business case</span>
              <span>Status</span>
              <span>Started</span>
              <span>Rows</span>
              <span />
            </div>
            {visibleRuns.map((run) => {
              const pipeline = pipelineById.get(run.pipeline_id);
              return (
                <div className="run-history-row" role="row" key={run.id}>
                  <span>
                    <strong>{pipeline?.name ?? `Pipeline ${shortId(run.pipeline_id)}`}</strong>
                    <small>
                      {run.is_dry_run ? "dry-run" : "run"} · {shortId(run.id)}
                      {run.requested_step_id ? ` · step ${run.requested_step_id}` : ""}
                    </small>
                  </span>
                  <span>{pipeline ? businessCaseName(businessCases, pipeline.business_case_id) : "—"}</span>
                  <span><i className={`pipeline-status ${run.status}`}>{run.status}</i></span>
                  <span>
                    <strong>{formatDateTime(run.started_at ?? run.created_at)}</strong>
                    <small>{durationLabel(run.started_at, run.finished_at)}</small>
                  </span>
                  <span>
                    <strong>{run.processed_row_count ?? "—"}</strong>
                    <small>
                      {run.output_row_count ?? "—"} output · {run.rejected_row_count ?? 0} rejected
                    </small>
                  </span>
                  <span>
                    <div className="run-row-actions">
                      <button
                        className="secondary-button compact-button"
                        type="button"
                        onClick={() => setArtifactsRun(run)}
                        disabled={run.status !== "succeeded" || run.is_dry_run}
                      >
                        <Box size={14} /> Generated artifacts
                      </button>
                      <button
                        className="secondary-button compact-button"
                        type="button"
                        onClick={() => onDetails(run)}
                      >
                        Details
                      </button>
                      <button
                        className="secondary-button compact-button"
                        type="button"
                        onClick={() => setDependenciesRun(run)}
                      >
                        <GitBranch size={14} /> Dependencies
                      </button>
                    </div>
                  </span>
                </div>
              );
            })}
            {!visibleRuns.length && (
              <div className="catalog-empty">No runs match the selected filters.</div>
            )}
          </div>
        )}
        {artifactsRun && (
          <GeneratedArtifactsDialog
            run={artifactsRun}
            onClose={() => setArtifactsRun(null)}
            onExamineDataset={(datasetId) => {
              setArtifactsRun(null);
              onClose();
              onExamineDataset(datasetId);
            }}
          />
        )}
        {dependenciesRun && (
          <ArtifactDependenciesDialog
            referenceId={dependenciesRun.id}
            artifactType="pipeline_run"
            title={`Run ${shortId(dependenciesRun.id)}`}
            onClose={() => setDependenciesRun(null)}
            onOpenDataset={(datasetId) => {
              setDependenciesRun(null);
              onClose();
              onExamineDataset(datasetId);
            }}
          />
        )}
      </div>
    </div>
  );
}

function GeneratedArtifactsDialog({
  run,
  onClose,
  onExamineDataset
}: {
  run: PipelineRun;
  onClose: () => void;
  onExamineDataset: (datasetId: string) => void;
}) {
  const [details, setDetails] = useState<PipelineRunDetails | null>(null);
  const [error, setError] = useState("");
  const [selectedModel, setSelectedModel] = useState<ModelArtifact | null>(null);
  const [selectedReport, setSelectedReport] = useState<import("../api/client").ScoringReport | null>(null);
  const [selectedTrainingReport, setSelectedTrainingReport] = useState<TrainingEvaluationReport | null>(null);
  const [openingArtifactId, setOpeningArtifactId] = useState("");

  useEffect(() => {
    let active = true;
    api.getPipelineRunDetails(run.pipeline_id, run.id)
      .then((result) => active && setDetails(result))
      .catch((requestError) => active && setError(
        requestError instanceof Error ? requestError.message : "Could not load generated artifacts"
      ));
    return () => { active = false; };
  }, [run.id, run.pipeline_id]);

  const artifactByReference = new Map(
    (details?.lineage ?? []).map((item) => [item.reference_id, item])
  );

  async function openDomainArtifact(artifactId: string, artifactType: string) {
    setOpeningArtifactId(artifactId);
    setError("");
    try {
      if (artifactType === "model_version") {
        const model = (await api.listModels()).find((item) => item.id === artifactId);
        if (!model) throw new Error("The registered model could not be found");
        setSelectedModel(model);
      } else if (artifactType === "report") {
        const report = (await api.listScoringReports(run.business_case_id)).find((item) => item.id === artifactId);
        if (!report) throw new Error("The registered scoring report could not be found");
        setSelectedReport(report);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not open artifact");
    } finally {
      setOpeningArtifactId("");
    }
  }
  return (
    <div className="modal-backdrop nested-modal" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal-dialog generated-artifacts-dialog" role="dialog" aria-modal="true" aria-label="Generated artifacts">
        <div className="modal-header">
          <div>
            <span className="builder-kicker">Pipeline run {shortId(run.id)}</span>
            <h2>Generated artifacts</h2>
            <p>{details?.run.output_artifact_ids.length ?? 0} registered objects · {details?.run.output_row_count ?? run.output_row_count ?? 0} output rows processed at full scope.</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close generated artifacts"><X size={18} /></button>
        </div>
        {error && <div className="error-banner">{error}</div>}
        {!details && !error && <div className="empty-state">Loading generated artifacts…</div>}
        {details && (
          <div className="generated-artifact-list">
            {details.outputs.filter((output) => output.artifact_id).map((output) => {
              const lineage = details.lineage.find((item) => item.artifact_id === output.artifact_id)
                ?? artifactByReference.get(output.dataset_id ?? "");
              const isDataset = ["dataset", "prediction_dataset"].includes(output.artifact_type ?? "");
              const isBrowsableDomainArtifact = ["model_version", "report"].includes(output.artifact_type ?? "");
              const isTrainingReport = output.report_type === "training_evaluation_report";
              return (
                <article key={`${output.pipeline_step_id}:${output.output_id}`}>
                  <div className="generated-artifact-icon">
                    {isDataset ? <Database size={18} /> : <Box size={18} />}
                  </div>
                  <div>
                    <strong>{output.dataset_name || output.output_id}</strong>
                    <span>
                      {(output.artifact_type ?? "artifact").replaceAll("_", " ")}
                      {" · "}{output.row_count ?? "—"} rows
                      {" · "}{output.data_scope} scope
                    </span>
                    <small>
                      artifact {shortId(output.artifact_id ?? "")}
                      {lineage ? ` · step ${String(lineage.lineage.pipeline_step_id ?? "unknown")}` : ""}
                    </small>
                  </div>
                  {isDataset && output.dataset_id && (
                    <button className="primary-button compact-button" type="button" onClick={() => onExamineDataset(output.dataset_id!)}>
                      <Eye size={14} /> Examine
                    </button>
                  )}
                  {isBrowsableDomainArtifact && output.artifact_id && (
                    <button className="primary-button compact-button" type="button"
                      disabled={openingArtifactId === output.artifact_id}
                      onClick={() => isTrainingReport
                        ? setSelectedTrainingReport(output.report as TrainingEvaluationReport)
                        : void openDomainArtifact(output.artifact_id!, output.artifact_type!)}>
                      <Eye size={14} /> {openingArtifactId === output.artifact_id ? "Opening…" : "View"}
                    </button>
                  )}
                </article>
              );
            })}
            {!details.outputs.some((output) => output.artifact_id) && (
              <div className="empty-state">This run did not register persistent output artifacts.</div>
            )}
          </div>
        )}
        {selectedModel && (
          <Suspense fallback={null}>
            <ModelDetailsDialog
              model={selectedModel}
              businessCaseName={`Business Case ${shortId(run.business_case_id)}`}
              pipelineName={`Pipeline ${shortId(run.pipeline_id)}`}
              onOpenDataset={onExamineDataset}
              onBack={() => setSelectedModel(null)}
              onClose={onClose}
            />
          </Suspense>
        )}
        {selectedReport && (
          <Suspense fallback={null}>
            <ScoringReportDialog
              report={selectedReport}
              onOpenDataset={onExamineDataset}
              onBack={() => setSelectedReport(null)}
              onClose={onClose}
            />
          </Suspense>
        )}
        {selectedTrainingReport && (
          <TrainingReportDialog report={selectedTrainingReport}
            onBack={() => setSelectedTrainingReport(null)} onClose={onClose} />
        )}
      </div>
    </div>
  );
}

export function PipelineRunDetailsDialog({
  run,
  onClose,
  onBack,
  onChanged
}: {
  run: PipelineRun;
  onClose: () => void;
  onBack?: () => void;
  onChanged: () => Promise<void>;
}) {
  const [runId, setRunId] = useState(run.id);
  const [details, setDetails] = useState<PipelineRunDetails | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    setError("");
    api.getPipelineRunDetails(run.pipeline_id, runId)
      .then(setDetails)
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : "Could not load run details");
      });
  };

  useEffect(load, [run.pipeline_id, runId]);

  useEffect(() => {
    const status = details?.run.status;
    if (status !== "queued" && status !== "running") return;
    const interval = window.setInterval(load, 1500);
    return () => window.clearInterval(interval);
  }, [details?.run.status, run.pipeline_id, runId]);

  async function cancelRun() {
    setBusy(true);
    try {
      await api.cancelPipelineRun(run.pipeline_id, runId);
      await onChanged();
      load();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not cancel pipeline run");
    } finally {
      setBusy(false);
    }
  }

  async function retryRun() {
    setBusy(true);
    try {
      const retried = await api.retryPipelineRun(run.pipeline_id, runId);
      await onChanged();
      setRunId(retried.id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not retry pipeline run");
    } finally {
      setBusy(false);
    }
  }

  const current = details?.run;
  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        className="modal-dialog run-details-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Pipeline run details"
      >
        <div className="modal-header">
          <div>
            <span className="eyebrow">Pipeline run</span>
            <h2>{current?.is_dry_run ? "Dry-run" : "Run"} {shortId(runId)}</h2>
            {details && (
              <p>
                v{details.pipeline_version.version_number}
                {" · "}hash {details.pipeline_version.definition_hash.slice(0, 12)}
                {" · "}{durationLabel(current?.started_at, current?.finished_at)}
              </p>
            )}
          </div>
          <div className="run-details-actions">
            {current && ["queued", "running"].includes(current.status) && (
              <button className="secondary-button" type="button" disabled={busy} onClick={cancelRun}>
                <X size={15} /> Cancel
              </button>
            )}
            {current && ["failed", "cancelled"].includes(current.status) && (
              <button className="secondary-button" type="button" disabled={busy} onClick={retryRun}>
                <RotateCcw size={15} /> Retry
              </button>
            )}
            <DialogNavigationActions onBack={onBack} onClose={onClose} closeLabel="Close pipeline run workflow" />
          </div>
        </div>
        {error && <div className="error-banner">{error}</div>}
        {!details && !error && <div className="empty-state">Loading run details…</div>}
        {details && current && (
          <div className="run-details-content">
            <div className="run-details-summary">
              {[
                ["Status", current.status],
                ["Input rows", current.input_row_count ?? "—"],
                ["Processed", current.processed_row_count ?? "—"],
                ["Output rows", current.output_row_count ?? "—"],
                ["Rejected", current.rejected_row_count ?? 0]
              ].map(([label, value]) => (
                <div className="run-detail-metric" key={String(label)}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>

            <section>
              <h3>Execution log</h3>
              <RunEventTimeline events={runDetailEvents(details)} />
            </section>

            <section>
              <h3>Step execution</h3>
              <div className="run-step-timeline">
                {details.steps.map((step) => (
                  <article className={`run-step-card ${step.status}`} key={step.id}>
                    <div><strong>{step.pipeline_step_id}</strong><em>{step.status}</em></div>
                    <span>
                      {step.step_type.replaceAll("_", " ")}
                      {" · "}{durationLabel(step.started_at, step.finished_at)}
                    </span>
                    <small>
                      {step.input_row_count ?? "—"} input
                      {" · "}{step.processed_row_count ?? "—"} processed
                      {" · "}{step.output_row_count ?? "—"} output
                    </small>
                    {step.warnings.map((warning) => (
                      <p className="warning-text" key={warning}>{warning}</p>
                    ))}
                    {step.events.length > 0 && <small>{step.events.length} log events captured</small>}
                    {step.error_message && <p className="error-text">{step.error_message}</p>}
                  </article>
                ))}
                {!details.steps.length && <div className="empty-state">No step has started yet.</div>}
              </div>
            </section>

            <section>
              <h3>Resolved input versions</h3>
              <div className="run-detail-table">
                {details.resolved_inputs.map((input) => (
                  <div key={`${input.step_id}:${input.input_id}`}>
                    <strong>{input.dataset_name}</strong>
                    <span>v{input.version_number} · {input.step_id}:{input.input_id}</span>
                    <code>{input.dataset_id}</code>
                  </div>
                ))}
                {!details.resolved_inputs.length && (
                  <div className="empty-state">No dataset inputs recorded.</div>
                )}
              </div>
            </section>

            <section>
              <h3>Outputs and data quality</h3>
              <div className="run-output-grid">
                {details.outputs.map((output) => (
                  <article key={`${output.pipeline_step_id}:${output.output_id}`}>
                    <div>
                      <strong>{output.dataset_name || output.output_id}</strong>
                      <em>{output.output_stage || "output"}</em>
                    </div>
                    <span>
                      {output.row_count ?? "—"} rows
                      {" · "}{output.materialization}
                      {" · "}{output.data_scope}
                    </span>
                    {output.quality_output_kind === "rejected_records" && (
                      <p className="warning-text">
                        Rejected records dataset · source: {output.source_output_id}
                      </p>
                    )}
                    {output.quality && output.quality.status !== "not_configured" && (
                      <div className="quality-report">
                        <strong>Contract: {output.quality.status.replaceAll("_", " ")}</strong>
                        <span>
                          {output.quality.checked_row_count ?? 0} checked
                          {" · "}{output.quality.rejected_row_count ?? 0} rejected
                          {" · "}{output.quality.schema_drift.length} drift issues
                        </span>
                        {output.quality.checks.filter((check) => !check.passed).map((check) => (
                          <small key={`${check.column}:${check.check}`}>
                            {check.column}.{check.check}: {check.violation_count} · {check.policy}
                          </small>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </section>

            <section>
              <h3>Lineage</h3>
              <div className="run-detail-table">
                {details.lineage.map((item) => (
                  <div key={item.artifact_id}>
                    <strong>{item.artifact_type} · {item.origin}</strong>
                    <span>
                      artifact {shortId(item.artifact_id)}
                      {" → "}reference {shortId(item.reference_id)}
                    </span>
                    <code>
                      {String(item.lineage.pipeline_step_id ?? "")}
                      {" · "}{String(item.lineage.pipeline_definition_hash ?? "").slice(0, 12)}
                    </code>
                  </div>
                ))}
                {!details.lineage.length && (
                  <div className="empty-state">
                    {current.is_dry_run
                      ? "Dry-runs intentionally do not register persistent lineage artifacts."
                      : "No lineage artifacts recorded."}
                  </div>
                )}
              </div>
            </section>

            {(current.warnings.length > 0 || current.error_message) && (
              <section>
                <h3>Warnings and errors</h3>
                {current.warnings.map((warning) => (
                  <p className="warning-text" key={warning}>{warning}</p>
                ))}
                {current.error_message && <p className="error-text">{current.error_message}</p>}
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function DryRunPreview({
  run,
  onClose,
  onExamine
}: {
  run: PipelineRun;
  onClose: () => void;
  onExamine: (outputId: string, pipelineStepId: string) => void;
}) {
  const outputs = browsableDryRunOutputs(run);
  const modelOutput = run.output_manifest.find((item) => item.artifact_type === "model_version");
  const scoringReportOutput = run.output_manifest.find(isScoringReportOutput);
  const trainingReportOutput = run.output_manifest.find(
    (item) => item.report_type === "training_evaluation_report" && item.report
  );
  const [selectedOutputIndex, setSelectedOutputIndex] = useState(0);
  const [selectedModel, setSelectedModel] = useState<ModelArtifact | null>(null);
  const [selectedReport, setSelectedReport] = useState<ModelEvaluationSnapshot | null>(null);
  const [selectedTrainingReport, setSelectedTrainingReport] = useState<TrainingEvaluationReport | null>(null);
  const output = outputs[selectedOutputIndex] ?? outputs[0];
  const outputId = output?.output_id ?? "";
  const pipelineStepId = output?.pipeline_step_id ?? "";
  const [activeView, setActiveView] = useState<"rows" | "profile">("rows");
  const [pageSize, setPageSize] = useState(50);
  const [offset, setOffset] = useState(0);
  const [preview, setPreview] = useState<PipelineRunOutputPreview | null>(null);
  const [profile, setProfile] = useState<PipelineRunOutputProfile | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [isProfileLoading, setIsProfileLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [profileError, setProfileError] = useState("");

  useEffect(() => {
    setSelectedOutputIndex(0);
    setSelectedModel(null);
    setSelectedReport(null);
    setSelectedTrainingReport(null);
  }, [run.id]);

  useEffect(() => {
    setOffset(0);
    setPreview(null);
    setProfile(null);
    setPreviewError("");
    setProfileError("");
    setActiveView("rows");
  }, [run.id, outputId, pipelineStepId]);

  useEffect(() => {
    if (!outputId) return;
    let cancelled = false;
    setIsPreviewLoading(true);
    setPreviewError("");
    api.previewPipelineRunOutput(run.pipeline_id, run.id, outputId, pipelineStepId, pageSize, offset)
      .then((result) => {
        if (!cancelled) setPreview(result);
      })
      .catch((error) => {
        if (!cancelled) {
          setPreviewError(error instanceof Error ? error.message : "Could not load dry-run preview");
        }
      })
      .finally(() => {
        if (!cancelled) setIsPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [run.pipeline_id, run.id, outputId, pipelineStepId, pageSize, offset]);

  useEffect(() => {
    if (activeView !== "profile" || !outputId || profile) return;
    let cancelled = false;
    setIsProfileLoading(true);
    setProfileError("");
    api.profilePipelineRunOutput(run.pipeline_id, run.id, outputId, pipelineStepId)
      .then((result) => {
        if (!cancelled) setProfile(result);
      })
      .catch((error) => {
        if (!cancelled) {
          setProfileError(error instanceof Error ? error.message : "Could not profile dry-run output");
        }
      })
      .finally(() => {
        if (!cancelled) setIsProfileLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeView, run.pipeline_id, run.id, outputId, pipelineStepId, profile]);

  const fallbackRecords = output?.preview?.records ?? [];
  const records = preview?.records ?? fallbackRecords;
  const schemaColumns = preview?.columns?.map((column) => column.name)
    ?? output?.schema?.map((column) => column.name)
    ?? [];
  const columns = schemaColumns.length > 0 ? schemaColumns : Object.keys(records[0] ?? {});
  const rowCount = preview?.row_count ?? output?.row_count ?? run.output_row_count ?? 0;
  const currentPage = rowCount > 0 ? Math.floor(offset / pageSize) + 1 : 0;
  const totalPages = rowCount > 0 ? Math.ceil(rowCount / pageSize) : 0;

  return (
    <section className="panel run-output-panel" aria-label="Dry-run output preview">
      <div className="run-output-heading">
        <div>
          <span className="builder-kicker">Temporary result</span>
          <h3>Dry-run preview</h3>
          <p>Full run: {rowCount} rows. Output: {outputId || "not available"}.</p>
        </div>
        <div className="run-output-heading-actions">
          <button
            className="primary-button compact-button"
            type="button"
            onClick={() => onExamine(outputId, pipelineStepId)}
            disabled={!outputId}
          >
            <Search size={15} /> Examine
          </button>
          <button
            className="icon-button"
            type="button"
            onClick={onClose}
            aria-label="Close dry-run preview"
          >
            <X size={16} />
          </button>
        </div>
      </div>
      {(modelOutput || scoringReportOutput || trainingReportOutput) && (
        <div className="dry-run-artifact-actions" aria-label="Temporary dry-run artifacts">
          <span>Temporary artifacts</span>
          {modelOutput && (
            <button
              className="secondary-button compact-button"
              type="button"
              onClick={() => setSelectedModel(dryRunModel(run, modelOutput))}
            >
              <Brain size={14} /> Preview model
            </button>
          )}
          {scoringReportOutput && (
            <button
              className="secondary-button compact-button"
              type="button"
              onClick={() => setSelectedReport(scoringReportOutput.evaluation as ModelEvaluationSnapshot)}
            >
              <BarChart3 size={14} /> Preview scoring report
            </button>
          )}
          {trainingReportOutput && (
            <button className="secondary-button compact-button" type="button"
              onClick={() => setSelectedTrainingReport(trainingReportOutput.report as TrainingEvaluationReport)}>
              <BarChart3 size={14} /> Preview training report
            </button>
          )}
        </div>
      )}
      {outputs.length > 1 && (
        <label className="dry-run-output-selector">
          <span>Result object <small>{outputs.length} temporary Parquet outputs</small></span>
          <select
            value={selectedOutputIndex}
            onChange={(event) => setSelectedOutputIndex(Number(event.target.value))}
          >
            {outputs.map((item, index) => (
              <option value={index} key={`${item.pipeline_step_id ?? ""}:${item.output_id}:${index}`}>
                {dryRunOutputLabel(item, index)}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="dry-run-view-tabs">
        <button
          className={activeView === "rows" ? "active" : ""}
          type="button"
          onClick={() => setActiveView("rows")}
        >
          Rows
        </button>
        <button
          className={activeView === "profile" ? "active" : ""}
          type="button"
          onClick={() => setActiveView("profile")}
        >
          Column profile
        </button>
      </div>

      {activeView === "rows" && (
        <>
          <div className="run-preview-toolbar">
            <span>
              Page {currentPage} of {totalPages}
              {" · "}{preview?.returned_count ?? records.length} rows shown
            </span>
            <label>
              Rows
              <select
                value={pageSize}
                onChange={(event) => {
                  setPageSize(Number(event.target.value));
                  setOffset(0);
                }}
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={250}>250</option>
              </select>
            </label>
            <button
              className="secondary-button compact-button"
              type="button"
              disabled={isPreviewLoading || !(preview?.has_previous ?? offset > 0)}
              onClick={() => setOffset(Math.max(0, offset - pageSize))}
            >
              <ChevronLeft size={14} /> Previous
            </button>
            <button
              className="secondary-button compact-button"
              type="button"
              disabled={isPreviewLoading || !(preview?.has_next ?? offset + records.length < rowCount)}
              onClick={() => setOffset(offset + pageSize)}
            >
              Next <ChevronRight size={14} />
            </button>
          </div>
          {previewError && <div className="inline-run-feedback failed">{previewError}</div>}
          {isPreviewLoading && !preview ? (
            <div className="catalog-empty">Loading preview page...</div>
          ) : records.length > 0 ? (
            <div className="run-preview-table">
              <table>
                <thead>
                  <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
                </thead>
                <tbody>
                  {records.map((record, rowIndex) => (
                    <tr key={`${offset}-${rowIndex}`}>
                      {columns.map((column) => (
                        <td key={column}>{displayPreviewValue(record[column])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="catalog-empty">The dry-run produced no preview rows.</div>
          )}
        </>
      )}

      {activeView === "profile" && (
        <div className="dry-run-profile">
          {profileError && <div className="inline-run-feedback failed">{profileError}</div>}
          {isProfileLoading && !profile && (
            <div className="catalog-empty">Profiling full dry-run output...</div>
          )}
          {profile && (
            <>
              <div className="run-profile-summary">
                <span>{profile.row_count} rows analyzed</span>
                <span>
                  {profile.profiled_column_count} of {profile.total_column_count} columns profiled
                </span>
              </div>
              <div className="run-profile-grid">
                {profile.columns.map((column) => (
                  <div className="run-profile-column" key={column.name}>
                    <div>
                      <strong>{column.name}</strong>
                      <span>
                        {column.approx_distinct_count} approx. distinct
                        {" · "}{column.null_count} nulls
                      </span>
                    </div>
                    <div className="run-profile-values">
                      {column.top_values.map((item, index) => (
                        <div key={`${column.name}-${index}`}>
                          <code>{displayPreviewValue(item.value)}</code>
                          <span>{item.count} · {(item.share * 100).toFixed(1)}%</span>
                        </div>
                      ))}
                      {column.top_values.length === 0 && <span>No values</span>}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
      <small>Temporary Parquet · no official dataset or artifact was created.</small>
      {selectedModel && (
        <Suspense fallback={null}>
          <ModelDetailsDialog
            model={selectedModel}
            businessCaseName="Dry-run preview"
            pipelineName={`Pipeline ${run.pipeline_id.slice(0, 8)}`}
            onBack={() => setSelectedModel(null)}
            onClose={onClose}
          />
        </Suspense>
      )}
      {selectedReport && (
        <TemporaryScoringReportDialog
          report={selectedReport}
          onBack={() => setSelectedReport(null)}
          onClose={onClose}
        />
      )}
      {selectedTrainingReport && (
        <TrainingReportDialog report={selectedTrainingReport}
          onBack={() => setSelectedTrainingReport(null)} onClose={onClose} />
      )}
    </section>
  );
}

function RunEventTimeline({ events }: { events: PipelineRunEvent[] }) {
  if (!events.length) {
    return <div className="empty-state">No worker log events have been captured yet.</div>;
  }
  return (
    <div className="run-event-log" role="log" aria-label="Pipeline worker execution log">
      {events.slice(-300).map((event, index) => (
        <article className={`run-event ${event.level}`} key={`${event.timestamp}-${event.type}-${index}`}>
          <time dateTime={event.timestamp}>{formatDateTimeWithSeconds(event.timestamp)}</time>
          <div>
            <strong>{event.message}</strong>
            <span>
              {event.type}
              {event.step_id ? ` · ${event.step_id}` : ""}
            </span>
            {eventDetails(event).length > 0 && (
              <dl>
                {eventDetails(event).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key.replaceAll("_", " ")}</dt>
                    <dd>{formatEventValue(value)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

function TrainingReportDialog({
  report,
  onBack,
  onClose
}: {
  report: TrainingEvaluationReport;
  onBack?: () => void;
  onClose: () => void;
}) {
  const summary = report.sections.summary ?? {};
  const metrics = report.sections.metrics ?? {};
  const validation = report.sections.validation ?? {};
  const autoFE = report.sections.feature_engineering ?? {};
  const jointStudy = autoFE.joint_study && typeof autoFE.joint_study === "object"
    ? autoFE.joint_study as Record<string, unknown> : {};
  const explainability = report.sections.explainability ?? {};
  const shapValues = explainability.shap?.values ?? [];
  const permutation = explainability.permutation_importance ?? [];
  return (
    <div className="modal-backdrop nested-modal" role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal-dialog generated-artifacts-dialog" role="dialog" aria-modal="true"
        aria-label="Training evaluation report">
        <div className="modal-header"><div><span className="builder-kicker">Training report</span>
          <h2>{report.name}</h2><p>Immutable model-selection and explainability snapshot.</p></div>
          <DialogNavigationActions onBack={onBack} onClose={onClose} closeLabel="Close training report workflow" />
        </div>
        <div className="evaluation-report">
          <div className="evaluation-scope">
            <span><strong>{report.data_scope.row_count.toLocaleString()}</strong> evaluated rows</span>
            <span><strong>Full dataset</strong> metric scope</span>
            <span><strong>{String(summary.algorithm ?? "model")}</strong> winner</span>
            <span><strong>{String(summary.feature_count ?? "—")}</strong> resolved features</span>
          </div>
          <section className="evaluation-section"><header><div><h4>Selection summary</h4>
            <p>Validation, search and selected AutoFE recipe.</p></div></header>
            <div className="evaluation-residual-summary">
              <span>Strategy <strong>{String(validation.strategy ?? "training")}</strong></span>
              <span>Primary metric <strong>{String(validation.primary_metric ?? "auto")}</strong></span>
              <span>Best score <strong>{formatReportValue(validation.best_score)}</strong></span>
              <span>Recipe <strong>{String(autoFE.recipe_id ?? "manual FE")}</strong></span>
              <span>Candidates <strong>{String(jointStudy.recipe_candidate_count ?? 1)}</strong></span>
            </div>
          </section>
          <section className="evaluation-section"><header><div><h4>Training metrics</h4>
            <p>Full declared evaluation scope.</p></div></header>
            <div className="evaluation-metrics">
              {Object.entries(metrics).filter(([, value]) => typeof value === "number").slice(0, 12).map(([key, value]) =>
                <article key={key}><span>{key.replaceAll("_", " ")}</span>
                  <strong>{formatReportValue(value)}</strong></article>)}
            </div>
          </section>
          <div className="evaluation-chart-grid">
            <ImportanceTable title={`SHAP · ${explainability.shap?.explainer ?? explainability.shap?.status ?? "unavailable"}`}
              rows={shapValues.map((item) => ({ feature: item.feature, value: item.mean_absolute_shap }))} />
            <ImportanceTable title="Permutation importance"
              rows={permutation.map((item) => ({ feature: item.feature, value: item.mean_importance }))} />
          </div>
          <div className="evaluation-notes">
            {explainability.notes?.map((note) => <p key={note}>{note}</p>)}
            {explainability.reason && <p>{explainability.reason}</p>}
            {report.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          </div>
        </div>
      </div>
    </div>
  );
}

function ImportanceTable({ title, rows }: { title: string; rows: Array<{ feature: string; value: number }> }) {
  return <section className="evaluation-section"><header><div><h4>{title}</h4>
    <p>Bounded deterministic explanation sample; metrics above remain full-scope.</p></div></header>
    {rows.length ? <div className="evaluation-class-table"><table><thead><tr><th>Feature</th><th>Importance</th></tr></thead>
      <tbody>{rows.slice(0, 20).map((item) => <tr key={item.feature}><td>{item.feature}</td>
        <td>{item.value.toPrecision(5)}</td></tr>)}</tbody></table></div>
      : <div className="evaluation-empty"><p>No bounded importance output is available for this estimator.</p></div>}
  </section>;
}

function formatReportValue(value: unknown) {
  return typeof value === "number" ? value.toPrecision(6) : String(value ?? "—");
}

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

function ComparisonLegend({ series }: { series: Array<{ label: string }> }) {
  return <div className="evaluation-comparison-legend" aria-label="Selected period series">{series.map((item, index) => <span key={item.label} className={`comparison-series-${index % 8}`}><i />{item.label}</span>)}</div>;
}

function ComparisonCurveChart({ series, diagonal }: {
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

function ComparisonDistributionChart({ series, xLabel }: {
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

function ComparisonScatterChart({ series }: { series: Array<{ label: string; index: number; points: Array<{ actual: number; predicted: number }> }> }) {
  const points = series.flatMap((item) => item.points);
  if (!points.length) return <div className="catalog-empty">No scatter points available.</div>;
  const values = points.flatMap((point) => [point.actual, point.predicted]);
  const min = Math.min(...values); const max = Math.max(...values); const span = max - min || 1;
  const plot = { left: 72, right: 535, top: 22, bottom: 345 };
  return <div className="evaluation-line-chart regression-chart"><svg viewBox="0 0 560 400" role="img" aria-label="Actual versus predicted by period"><line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.bottom} className="axis" /><line x1={plot.left} y1={plot.top} x2={plot.left} y2={plot.bottom} className="axis" /><line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.top} className="baseline" />{series.flatMap((item) => item.points.map((point, index) => <circle key={`${item.label}-${index}`} cx={plot.left + (point.actual - min) / span * (plot.right - plot.left)} cy={plot.bottom - (point.predicted - min) / span * (plot.bottom - plot.top)} r="2.2" className={`comparison-point comparison-series-${item.index % 8}`} />))}<text x={(plot.left + plot.right) / 2} y="392" className="axis-title" textAnchor="middle">Actual value</text><text x="16" y={(plot.top + plot.bottom) / 2} className="axis-title" textAnchor="middle" transform={`rotate(-90 16 ${(plot.top + plot.bottom) / 2})`}>Predicted value</text></svg></div>;
}

function ComparisonQqChart({ series }: { series: Array<{ label: string; index: number; points: Array<{ theoretical: number; observed: number }> }> }) {
  const points = series.flatMap((item) => item.points);
  if (!points.length) return <div className="catalog-empty">No residual quantiles available.</div>;
  const xMin = Math.min(...points.map((point) => point.theoretical)); const xMax = Math.max(...points.map((point) => point.theoretical));
  const yMin = Math.min(...points.map((point) => point.observed)); const yMax = Math.max(...points.map((point) => point.observed));
  const xSpan = xMax - xMin || 1; const ySpan = yMax - yMin || 1; const plot = { left: 72, right: 535, top: 22, bottom: 345 };
  return <div className="evaluation-line-chart regression-chart"><svg viewBox="0 0 560 400" role="img" aria-label="Residual QQ comparison"><line x1={plot.left} y1={plot.bottom} x2={plot.right} y2={plot.bottom} className="axis" /><line x1={plot.left} y1={plot.top} x2={plot.left} y2={plot.bottom} className="axis" />{series.map((item) => <polyline key={item.label} className={`comparison-line comparison-series-${item.index % 8}`} points={item.points.map((point) => `${plot.left + (point.theoretical - xMin) / xSpan * (plot.right - plot.left)},${plot.bottom - (point.observed - yMin) / ySpan * (plot.bottom - plot.top)}`).join(" ")} />)}<text x={(plot.left + plot.right) / 2} y="392" className="axis-title" textAnchor="middle">Theoretical normal quantile</text><text x="16" y={(plot.top + plot.bottom) / 2} className="axis-title" textAnchor="middle" transform={`rotate(-90 16 ${(plot.top + plot.bottom) / 2})`}>Observed residual quantile</text></svg></div>;
}

function TemporaryScoringReportDialog({
  report,
  onBack,
  onClose
}: {
  report: ModelEvaluationSnapshot;
  onBack?: () => void;
  onClose: () => void;
}) {
  return (
    <div
      className="modal-backdrop nested-modal"
      role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        className="modal-dialog scoring-report-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Temporary scoring report"
      >
        <div className="modal-header">
          <div>
            <span className="builder-kicker">Temporary artifact</span>
            <h2>Scoring report</h2>
            <p>Dry-run preview · no report version has been registered.</p>
          </div>
          <DialogNavigationActions onBack={onBack} onClose={onClose} closeLabel="Close scoring report workflow" />
        </div>
        <ModelPerformanceReport report={report} />
      </div>
    </div>
  );
}

function ConfusionMatrix({ matrix }: {
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

function EvaluationLineChart({
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

function StackedHistogram({
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

function ResidualHistogram({
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

function ActualPredictedScatter({
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

function ResidualQqPlot({ plot: qqPlot, summary }: {
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

function formatEvaluationMetric(value: number, unit: string) {
  if (!Number.isFinite(value)) return "—";
  return unit === "ratio" ? `${(value * 100).toFixed(1)}%` : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function formatEvaluationHeadlineMetric(
  metric: ModelEvaluationSnapshot["metrics"][number]
) {
  if (!Number.isFinite(metric.value)) return "—";
  return metric.value.toLocaleString(undefined, {
    minimumFractionDigits: 3,
    maximumFractionDigits: 4
  });
}

function evaluationCurveTitle(key: string) {
  return key === "roc" ? "ROC curve" :
    key === "precision_recall" ? "Precision–recall curve" :
      key === "calibration" ? "Calibration" : key.replaceAll("_", " ");
}

function evaluationCurveMetric(
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

export function browsableDryRunOutputs(run: PipelineRun): PipelineRun["output_manifest"] {
  return run.output_manifest.filter((output) => {
    const artifactType = output.artifact_type ?? "dataset";
    return (
      ["dataset", "prediction_dataset"].includes(artifactType)
      && output.location_uri.toLowerCase().includes(".parquet")
    );
  });
}

function isScoringReportOutput(
  output: PipelineRun["output_manifest"][number]
): boolean {
  const evaluation = output.evaluation as ModelEvaluationSnapshot | undefined;
  return (
    ["prediction_dataset", "report_source"].includes(output.artifact_type ?? "")
    && evaluation?.kind === "model_performance"
  );
}

function dryRunModel(
  run: PipelineRun,
  output: PipelineRun["output_manifest"][number]
): ModelArtifact {
  return {
    id: `dry-run:${run.id}:${output.pipeline_step_id ?? ""}:${output.output_id}`,
    owner_id: run.owner_id,
    training_job_id: run.id,
    name: output.model_name || "Temporary model",
    version: "dry-run",
    logical_id: "",
    version_number: 0,
    algorithm: output.algorithm || "unknown",
    stage: "developed",
    artifact_uri: output.location_uri,
    metrics: output.metrics ?? {},
    business_case_id: run.business_case_id,
    pipeline_id: run.pipeline_id,
    pipeline_version_id: run.pipeline_version_id,
    pipeline_run_id: run.id,
    pipeline_step_id: output.pipeline_step_id ?? "",
    problem_type: output.problem_type ?? "",
    target_column: output.target_column ?? "",
    feature_columns: output.feature_columns ?? [],
    model_hash: output.model_hash ?? "",
    training_config: output.training_config ?? {},
    model_parameters: output.model_parameters ?? {},
    fitted_transform_artifact_id: "",
    data_engineering_definition: {},
    feature_engineering_definition: {},
    lineage: {
      pipeline_id: run.pipeline_id,
      pipeline_version_id: run.pipeline_version_id,
      pipeline_run_id: run.id,
      pipeline_step_id: output.pipeline_step_id,
      temporary: true
    },
    created_at: run.finished_at ?? run.created_at
  };
}

function dryRunOutputLabel(
  output: PipelineRun["output_manifest"][number],
  index: number
) {
  const step = output.pipeline_step_id || "pipeline";
  const name = output.dataset_name || output.output_id || `output ${index + 1}`;
  const rows = output.row_count ?? 0;
  return `${step} · ${name} · ${rows} rows`;
}

function businessCaseName(businessCases: BusinessCase[], businessCaseId: string) {
  return businessCases.find((item) => item.id === businessCaseId)?.name ?? "unknown BC";
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "short",
    timeStyle: "short"
  }).format(new Date(value));
}

function durationLabel(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined
) {
  if (!startedAt) return "not started";
  const start = new Date(startedAt).getTime();
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

function formatDateTimeWithSeconds(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "short",
    timeStyle: "medium"
  }).format(new Date(value));
}

function runDetailEvents(details: PipelineRunDetails): PipelineRunEvent[] {
  const seen = new Set<string>();
  const events = [
    ...(details.run.events ?? []),
    ...details.steps.flatMap((step) => step.events ?? [])
  ];
  return events
    .filter((event) => {
      const key = `${event.timestamp}:${event.type}:${event.step_id}:${event.message}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime());
}

function eventDetails(event: PipelineRunEvent): Array<[string, unknown]> {
  return Object.entries(event.details ?? {}).filter(([key]) => (
    !["metrics"].includes(key)
  )).slice(0, 12);
}

function formatEventValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 6 });
  }
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (Array.isArray(value)) {
    return value.length > 8
      ? `${value.slice(0, 8).map(formatEventValue).join(", ")} … +${value.length - 8}`
      : value.map(formatEventValue).join(", ");
  }
  if (typeof value === "object") {
    const json = JSON.stringify(value);
    return json.length > 320 ? `${json.slice(0, 320)}…` : json;
  }
  return String(value);
}

function shortId(value: string) {
  return value.slice(0, 8);
}

function safeDownloadName(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "pipeline";
}

function displayPreviewValue(value: unknown) {
  if (value === null || value === undefined) return "null";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
