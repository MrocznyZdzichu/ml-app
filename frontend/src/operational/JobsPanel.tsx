import { CheckCircle2, History, RotateCcw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { BusinessCase, Pipeline, PipelineRun } from "../api/client";
import { PagedCatalogSelect } from "../components/PagedCatalogSelect";
import { PaginationControls } from "../components/PaginationControls";
import { PipelineRunDetailsDialog } from "../pipelines/PipelineRunDialogs";
import { durationLabel, formatDateTime, shortId } from "../shared/formatters";
import { Metric } from "../workspace/Overview";

type JobsPanelProps = {
  businessCases: BusinessCase[];
  pipelines: Pipeline[];
  onRefreshCatalog: () => Promise<void>;
  onRegisterRefresh: (handler: (() => Promise<void>) | null) => void;
  setNotice: (message: string) => void;
};

export function JobsPanel({
  businessCases,
  pipelines,
  onRefreshCatalog,
  onRegisterRefresh,
  setNotice
}: JobsPanelProps) {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [runTotal, setRunTotal] = useState(0);
  const [runOffset, setRunOffset] = useState(0);
  const [runSummary, setRunSummary] = useState({ active: 0, dryRuns: 0, failed: 0 });
  const [statusFilter, setStatusFilter] = useState("active");
  const [scopeFilter, setScopeFilter] = useState("");
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [busyRunId, setBusyRunId] = useState<string | null>(null);
  const [selectedRunDetails, setSelectedRunDetails] = useState<PipelineRun | null>(null);

  const loadRuns = useCallback(async () => {
    setIsLoading(true);
    try {
      const baseQuery = {
        limit: 30,
        offset: runOffset,
        search: search.trim(),
        business_case_id: scopeFilter
      };
      const filterQuery = statusFilter === "dry-run"
        ? { ...baseQuery, dry_run: true }
        : statusFilter === "all"
          ? baseQuery
          : { ...baseQuery, status: statusFilter };
      const [page, activePage, dryRunPage, failedPage] = await Promise.all([
        api.pagePipelineRunHistory(filterQuery),
        api.pagePipelineRunHistory({ limit: 1, status: "active" }),
        api.pagePipelineRunHistory({ limit: 1, dry_run: true }),
        api.pagePipelineRunHistory({ limit: 1, status: "failed" })
      ]);
      setRuns(page.items);
      setRunTotal(page.total);
      setRunSummary({
        active: activePage.total,
        dryRuns: dryRunPage.total,
        failed: failedPage.total
      });
      if (page.total > 0 && page.offset >= page.total) {
        setRunOffset(Math.max(0, Math.floor((page.total - 1) / page.limit) * page.limit));
      }
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not load jobs");
    } finally {
      setIsLoading(false);
    }
  }, [runOffset, scopeFilter, search, setNotice, statusFilter]);

  const refreshAllJobs = useCallback(async () => {
    await Promise.all([onRefreshCatalog(), loadRuns()]);
  }, [loadRuns, onRefreshCatalog]);

  useEffect(() => {
    onRegisterRefresh(refreshAllJobs);
    return () => onRegisterRefresh(null);
  }, [onRegisterRefresh, refreshAllJobs]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadRuns(), 250);
    return () => window.clearTimeout(timer);
  }, [loadRuns]);

  useEffect(() => {
    setRunOffset(0);
  }, [scopeFilter, search, statusFilter]);

  useEffect(() => {
    if (!runs.some((run) => run.status === "queued" || run.status === "running")) return;
    const interval = window.setInterval(() => void loadRuns(), 2500);
    return () => window.clearInterval(interval);
  }, [loadRuns, runs]);

  async function cancelRun(run: PipelineRun) {
    setBusyRunId(run.id);
    try {
      await api.cancelPipelineRun(run.pipeline_id, run.id);
      await loadRuns();
      setNotice(`Cancellation requested for job ${shortId(run.id)}.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not cancel job");
    } finally {
      setBusyRunId(null);
    }
  }

  async function rerun(run: PipelineRun) {
    setBusyRunId(run.id);
    try {
      const retried = await api.retryPipelineRun(run.pipeline_id, run.id);
      await loadRuns();
      setNotice(`Rerun queued as job ${shortId(retried.id)}.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not rerun job");
    } finally {
      setBusyRunId(null);
    }
  }

  return (
    <section className="section jobs-panel">
      <div className="section-header">
        <div>
          <span>EXECUTION</span>
          <h2>Jobs</h2>
          <p>Pipeline runs across the workspace, including dry-runs and step runs.</p>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={() => void loadRuns()}
          disabled={isLoading}
        >
          <RotateCcw size={16} />
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      <div className="job-summary-grid">
        <Metric icon={History} label="Active" value={runSummary.active} tone="teal" />
        <Metric icon={CheckCircle2} label="Dry-runs" value={runSummary.dryRuns} tone="amber" />
        <Metric icon={X} label="Failed" value={runSummary.failed} tone="rose" />
      </div>

      <div className="job-filters">
        <label>
          Search
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Run, pipeline, Business Case or step"
          />
        </label>
        <label>
          Status
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="active">Active</option>
            <option value="all">All statuses</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="succeeded">Succeeded</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
            <option value="dry-run">Dry-runs</option>
          </select>
        </label>
        <label>
          Business Case
          <PagedCatalogSelect
            value={scopeFilter}
            onChange={setScopeFilter}
            loadPage={api.pageBusinessCases}
            getId={(item) => item.id}
            getLabel={(item) => item.name}
            emptyLabel="All Business Cases"
            searchPlaceholder="Search Business Cases"
          />
        </label>
      </div>

      <div className="jobs-table" role="table" aria-label="Jobs">
        <div className="jobs-row head" role="row">
          <span>Job</span>
          <span>Status</span>
          <span>Pipeline</span>
          <span>Started</span>
          <span>Finished</span>
          <span>Duration</span>
          <span>Rows</span>
          <span>Actions</span>
        </div>
        {runs.map((run) => {
          const canCancel = run.status === "queued" || run.status === "running";
          const canRerun = run.status === "failed" || run.status === "cancelled";
          return (
            <div className="jobs-row" role="row" key={run.id}>
              <span>
                <strong>{shortId(run.id)} {run.is_dry_run && <i>dry-run</i>}</strong>
                <small>
                  {run.requested_step_id ? `step ${run.requested_step_id}` : "full pipeline"}
                  {" · "}
                  {run.trigger_type}
                </small>
              </span>
              <span><i className={`pipeline-status ${run.status}`}>{run.status}</i></span>
              <span>
                <strong>{pipelineName(pipelines, run.pipeline_id)}</strong>
                <small>{businessCaseName(businessCases, run.business_case_id)}</small>
              </span>
              <span>{run.started_at ? formatDateTime(run.started_at) : "not started"}</span>
              <span>{run.finished_at ? formatDateTime(run.finished_at) : "in progress"}</span>
              <span>{durationLabel(run.started_at, run.finished_at)}</span>
              <span>
                <strong>{run.processed_row_count ?? 0}</strong>
                <small>
                  out {run.output_row_count ?? 0} · rejected {run.rejected_row_count ?? 0}
                </small>
              </span>
              <span>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setSelectedRunDetails(run)}
                >
                  <History size={14} /> Logs
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => void cancelRun(run)}
                  disabled={!canCancel || busyRunId === run.id}
                >
                  <X size={14} /> Cancel
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => void rerun(run)}
                  disabled={!canRerun || busyRunId === run.id}
                >
                  <RotateCcw size={14} /> Rerun
                </button>
              </span>
            </div>
          );
        })}
        {!runs.length && (
          <div className="empty-state">No jobs match the current filters.</div>
        )}
      </div>
      <PaginationControls
        total={runTotal}
        limit={30}
        offset={runOffset}
        onOffsetChange={setRunOffset}
        disabled={isLoading}
        label="jobs"
      />

      {selectedRunDetails && (
        <PipelineRunDetailsDialog
          run={selectedRunDetails}
          onClose={() => setSelectedRunDetails(null)}
          onChanged={loadRuns}
        />
      )}
    </section>
  );
}

function businessCaseName(businessCases: BusinessCase[], businessCaseId: string) {
  return businessCases.find((item) => item.id === businessCaseId)?.name ?? "unknown BC";
}

function pipelineName(pipelines: Pipeline[], pipelineId: string) {
  return pipelines.find((item) => item.id === pipelineId)?.name ?? "unknown pipeline";
}
