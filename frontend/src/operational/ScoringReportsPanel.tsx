import { BarChart3, Eye, History, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { BusinessCase, DatasetLineageReference, Pipeline, ScoringReport } from "../api/client";
import { ModelPerformanceReport } from "../reports/ModelPerformanceReport";
import { ArtifactFilters } from "../components/ArtifactFilters";
import { DialogNavigationActions, useVersionedResourceNavigation } from "../components/dialogNavigation";
import { PaginationControls } from "../components/PaginationControls";
import { PagedCatalogSelect } from "../components/PagedCatalogSelect";
import { DatasetLineageList } from "./DatasetLineageList";

export function ScoringReportsPanel({
  reports,
  businessCases,
  pipelines,
  initialBusinessCaseId = "",
  onOpenDataset
}: {
  reports: ScoringReport[];
  businessCases: BusinessCase[];
  pipelines: Pipeline[];
  initialBusinessCaseId?: string;
  onOpenDataset?: (datasetId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [businessCaseId, setBusinessCaseId] = useState(initialBusinessCaseId);
  const [purposeFilter, setPurposeFilter] = useState("");
  const [pipelineFilter, setPipelineFilter] = useState("");
  const [families, setFamilies] = useState<Array<{ latest: ScoringReport; version_count: number }>>([]);
  const [familyTotal, setFamilyTotal] = useState(0);
  const [familyOffset, setFamilyOffset] = useState(0);
  const [pageLoading, setPageLoading] = useState(false);
  const [pageError, setPageError] = useState("");
  const reportNavigation = useVersionedResourceNavigation<ScoringReport>();
  const [sort, setSort] = useState<{
    key: "report" | "business_case" | "pipeline" | "problem" | "created" | "scope";
    direction: "asc" | "desc";
  }>({ key: "created", direction: "desc" });
  const businessCaseById = useMemo(
    () => new Map(businessCases.map((item) => [item.id, item])),
    [businessCases]
  );
  const pipelineById = useMemo(
    () => new Map(pipelines.map((item) => [item.id, item])),
    [pipelines]
  );
  const visible = families;
  const availablePipelines = businessCaseId
    ? pipelines.filter((pipeline) => pipeline.business_case_id === businessCaseId)
    : pipelines;
  const sorted = visible;

  function toggleSort(key: typeof sort.key) {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc"
    }));
  }

  useEffect(() => setBusinessCaseId(initialBusinessCaseId), [initialBusinessCaseId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPageLoading(true);
      setPageError("");
      api.pageScoringReports({
        limit: 20,
        offset: familyOffset,
        search: query.trim(),
        business_case_id: businessCaseId,
        pipeline_id: pipelineFilter,
        pipeline_type: purposeFilter,
        sort_by: sort.key,
        sort_direction: sort.direction
      })
        .then((page) => {
          setFamilies(page.items);
          setFamilyTotal(page.total);
        })
        .catch((error) => setPageError(error instanceof Error ? error.message : "Could not load scoring reports"))
        .finally(() => setPageLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [
    businessCaseId,
    familyOffset,
    pipelineFilter,
    purposeFilter,
    query,
    reports,
    sort.direction,
    sort.key
  ]);

  useEffect(() => {
    setFamilyOffset(0);
  }, [businessCaseId, pipelineFilter, purposeFilter, query, sort.direction, sort.key]);

  return (
    <section className="model-registry-screen">
      <div className="panel model-registry-panel">
        <div className="catalog-toolbar">
          <div>
            <span className="builder-kicker">Evaluation registry</span>
            <h2>Scoring reports</h2>
            <p>{familyTotal} report families</p>
          </div>
          <div className="model-registry-summary">
            <BarChart3 size={18} />
            <span>Full-run evaluations ready for comparison and monitoring baselines</span>
          </div>
        </div>
        <div className="model-registry-filters">
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Search scoring reports"
              placeholder="Search by report, pipeline or problem type"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <label>
            <span><SlidersHorizontal size={14} /> Business case</span>
            <PagedCatalogSelect
              value={businessCaseId}
              onChange={(value) => {
                setBusinessCaseId(value);
                setPipelineFilter("");
              }}
              loadPage={api.pageBusinessCases}
              getId={(item) => item.id}
              getLabel={(item) => item.name}
              emptyLabel="All business cases"
              searchPlaceholder="Search Business Cases"
            />
          </label>
        </div>
        <ArtifactFilters
          pipelines={availablePipelines}
          purpose={purposeFilter}
          pipelineId={pipelineFilter}
          onPurposeChange={setPurposeFilter}
          onPipelineChange={setPipelineFilter}
          businessCaseId={businessCaseId}
        />
        <div className="model-registry-table scoring-report-table" role="table" aria-label="Scoring report registry">
          <div className="model-registry-row head" role="row">
            <SortHeader label="Report" active={sort.key === "report"} direction={sort.direction}
              onClick={() => toggleSort("report")} />
            <SortHeader label="Business case" active={sort.key === "business_case"} direction={sort.direction}
              onClick={() => toggleSort("business_case")} />
            <SortHeader label="Pipeline" active={sort.key === "pipeline"} direction={sort.direction}
              onClick={() => toggleSort("pipeline")} />
            <SortHeader label="Problem" active={sort.key === "problem"} direction={sort.direction}
              onClick={() => toggleSort("problem")} />
            <SortHeader label="Created" active={sort.key === "created"} direction={sort.direction}
              onClick={() => toggleSort("created")} />
            <SortHeader label="Scope" active={sort.key === "scope"} direction={sort.direction}
              onClick={() => toggleSort("scope")} />
            <span />
          </div>
          {sorted.map(({ latest, version_count: versionCount }) => (
            <div className="model-registry-row" role="row" key={latest.id}>
              <span>
                <strong>{latest.name}</strong>
                <small>v{latest.version_number} latest · {versionCount} version{versionCount === 1 ? "" : "s"}</small>
              </span>
              <span>
                <strong>{businessCaseById.get(latest.business_case_id)?.name ?? "Unassigned"}</strong>
              </span>
              <span>{pipelineById.get(latest.pipeline_id)?.name ?? "Unknown pipeline"}</span>
              <span>{latest.problem_type.replaceAll("_", " ") || "not recorded"}</span>
              <span>{formatDate(latest.created_at)}</span>
              <span>{latest.evaluated_row_count.toLocaleString()} rows</span>
              <span>
                <div className="model-row-actions">
                  <button className="secondary-button compact-button" type="button" onClick={() => reportNavigation.openHistory(latest)}>
                    <History size={14} /> Versions
                  </button>
                  <button className="secondary-button compact-button" type="button" onClick={() => void api.getScoringReport(latest.id).then(reportNavigation.openDirect)}>
                    <Eye size={14} /> View latest
                  </button>
                </div>
              </span>
            </div>
          ))}
          {pageError && <div className="error-banner">{pageError}</div>}
          {!pageLoading && !visible.length && <div className="catalog-empty">No scoring reports match these filters.</div>}
        </div>
        <PaginationControls
          total={familyTotal}
          limit={20}
          offset={familyOffset}
          onOffsetChange={setFamilyOffset}
          disabled={pageLoading}
          label="report families"
        />
      </div>
      {reportNavigation.selected && <ScoringReportDialog report={reportNavigation.selected}
        onClose={reportNavigation.closeAll}
        onBack={reportNavigation.hasBack ? reportNavigation.back : undefined}
        onOpenDataset={onOpenDataset} />}
      {reportNavigation.showHistory && reportNavigation.history && (
        <ScoringReportHistoryDialog
          report={reportNavigation.history}
          onClose={reportNavigation.closeHistory}
          onView={async (version) => {
            const fullReport = await api.getScoringReport(version.id);
            reportNavigation.openVersion(fullReport);
          }}
        />
      )}
    </section>
  );
}

function SortHeader({
  label,
  active,
  direction,
  onClick
}: {
  label: string;
  active: boolean;
  direction: "asc" | "desc";
  onClick: () => void;
}) {
  return (
    <button className={`registry-sort${active ? " active" : ""}`} type="button" onClick={onClick}>
      {label}{active ? (direction === "asc" ? " ↑" : " ↓") : ""}
    </button>
  );
}

export function ScoringReportDialog({
  report,
  onClose,
  onBack,
  onOpenDataset
}: {
  report: ScoringReport;
  onClose: () => void;
  onBack?: () => void;
  onOpenDataset?: (datasetId: string) => void;
}) {
  const [dataLineage, setDataLineage] = useState<DatasetLineageReference[]>([]);
  const [lineageError, setLineageError] = useState("");
  useEffect(() => {
    let active = true;
    api.getScoringReportDataLineage(report.id)
      .then((items) => active && setDataLineage(items))
      .catch((error) => active && setLineageError(
        error instanceof Error ? error.message : "Could not load report data lineage"
      ));
    return () => { active = false; };
  }, [report.id]);
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal-dialog scoring-report-dialog" role="dialog" aria-modal="true" aria-label={`Scoring report: ${report.name}`}>
        <div className="modal-header">
          <div>
            <span className="builder-kicker">Scoring report · v{report.version_number}</span>
            <h2>{report.name}</h2>
            <p>Run {shortId(report.pipeline_run_id)} · full scope · {report.evaluated_row_count.toLocaleString()} evaluated rows</p>
          </div>
          <DialogNavigationActions onBack={onBack} onClose={onClose} closeLabel="Close scoring report" />
        </div>
        <DatasetLineageList
          items={dataLineage.filter((item) => ["test", "prediction"].includes(item.role))}
          error={lineageError}
          onOpenDataset={onOpenDataset}
        />
        <ModelPerformanceReport report={report.evaluation} />
      </div>
    </div>
  );
}

export function ScoringReportHistoryDialog({
  report,
  onClose,
  onView
}: {
  report: ScoringReport;
  onClose: () => void;
  onView: (report: ScoringReport) => void;
}) {
  const [versions, setVersions] = useState<ScoringReport[]>([]);
  const [versionTotal, setVersionTotal] = useState(0);
  const [versionOffset, setVersionOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    api.pageScoringReportVersions(report.logical_id, { limit: 20, offset: versionOffset })
      .then((page) => {
        if (!active) return;
        setVersions(page.items);
        setVersionTotal(page.total);
      })
      .catch((requestError) => active && setError(
        requestError instanceof Error ? requestError.message : "Could not load report versions"
      ))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [report.logical_id, versionOffset]);
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal-dialog model-version-dialog" role="dialog" aria-modal="true" aria-label={`Versions of ${report.name}`}>
        <div className="modal-header">
          <div><span className="builder-kicker">Report family</span><h2>{report.name}</h2></div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close report versions"><X size={18} /></button>
        </div>
        {error && <div className="error-banner">{error}</div>}
        <div className="model-version-list">
          {versions.map((version, index) => (
            <article key={version.id}>
              <div className="model-version-marker"><span>v{version.version_number}</span></div>
              <div>
                <strong>v{version.version_number}{versionOffset === 0 && index === 0 && <i className="pipeline-status published">latest</i>}</strong>
                <span>{formatDate(version.created_at)} · run {shortId(version.pipeline_run_id)}</span>
                <small>{version.evaluated_row_count.toLocaleString()} evaluated rows</small>
              </div>
              <button className="secondary-button compact-button" type="button" onClick={() => onView(version)}>
                <Eye size={14} /> View
              </button>
            </article>
          ))}
          {!versions.length && !error && loading && <div className="empty-state">Loading report versions…</div>}
        </div>
        <PaginationControls
          total={versionTotal}
          limit={20}
          offset={versionOffset}
          onOffsetChange={setVersionOffset}
          disabled={loading}
          label="report versions"
        />
      </div>
    </div>
  );
}

function formatDate(value: string) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

function shortId(value: string) {
  return value ? value.slice(0, 8) : "unknown";
}
