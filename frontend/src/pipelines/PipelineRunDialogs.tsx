import { ChevronLeft, ChevronRight, RotateCcw, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type {
  BusinessCase,
  Pipeline,
  PipelineRun,
  PipelineRunDetails,
  PipelineRunOutputPreview,
  PipelineRunOutputProfile
} from "../api/client";

export function PipelineRunHistoryDialog({
  pipelines,
  businessCases,
  refreshKey,
  onClose,
  onDetails
}: {
  pipelines: Pipeline[];
  businessCases: BusinessCase[];
  refreshKey: number;
  onClose: () => void;
  onDetails: (run: PipelineRun) => void;
}) {
  const [historyRuns, setHistoryRuns] = useState<PipelineRun[]>([]);
  const [pipelineFilter, setPipelineFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [reloadKey, setReloadKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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

  const visibleRuns = historyRuns.filter((run) =>
    (pipelineFilter === "all" || run.pipeline_id === pipelineFilter)
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
            <h2>Pipeline runs</h2>
            <p>Latest 200 runs across your available pipelines.</p>
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
                    <button
                      className="secondary-button compact-button"
                      type="button"
                      onClick={() => onDetails(run)}
                    >
                      Details
                    </button>
                  </span>
                </div>
              );
            })}
            {!visibleRuns.length && (
              <div className="catalog-empty">No runs match the selected filters.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function PipelineRunDetailsDialog({
  run,
  onClose,
  onChanged
}: {
  run: PipelineRun;
  onClose: () => void;
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
            <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
              <X size={18} />
            </button>
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
  onExamine: () => void;
}) {
  const output = run.output_manifest[0];
  const outputId = output?.output_id ?? "";
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
    setOffset(0);
    setPreview(null);
    setProfile(null);
    setPreviewError("");
    setProfileError("");
  }, [run.id, outputId]);

  useEffect(() => {
    if (!outputId) return;
    let cancelled = false;
    setIsPreviewLoading(true);
    setPreviewError("");
    api.previewPipelineRunOutput(run.pipeline_id, run.id, outputId, pageSize, offset)
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
  }, [run.pipeline_id, run.id, outputId, pageSize, offset]);

  useEffect(() => {
    if (activeView !== "profile" || !outputId || profile) return;
    let cancelled = false;
    setIsProfileLoading(true);
    setProfileError("");
    api.profilePipelineRunOutput(run.pipeline_id, run.id, outputId)
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
  }, [activeView, run.pipeline_id, run.id, outputId, profile]);

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
            onClick={onExamine}
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
    </section>
  );
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

function shortId(value: string) {
  return value.slice(0, 8);
}

function displayPreviewValue(value: unknown) {
  if (value === null || value === undefined) return "null";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
