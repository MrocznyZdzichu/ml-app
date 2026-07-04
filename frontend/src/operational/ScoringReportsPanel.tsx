import { BarChart3, Eye, History, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { BusinessCase, DatasetLineageReference, Pipeline, ScoringReport } from "../api/client";
import { ModelPerformanceReport } from "../pipelines/PipelineRunDialogs";
import { DatasetLineageList } from "./LifecyclePanels";

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
  const [selected, setSelected] = useState<ScoringReport | null>(null);
  const [history, setHistory] = useState<ScoringReport | null>(null);
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
  const families = useMemo(() => {
    const grouped = new Map<string, ScoringReport[]>();
    reports.forEach((report) => grouped.set(
      report.logical_id,
      [...(grouped.get(report.logical_id) ?? []), report]
    ));
    return [...grouped.values()].map((versions) => {
      const ordered = [...versions].sort((left, right) => right.version_number - left.version_number);
      return { latest: ordered[0], versions: ordered };
    });
  }, [reports]);
  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return families.filter(({ latest }) =>
      (!businessCaseId || latest.business_case_id === businessCaseId)
      && (!normalized || [
        latest.name,
        latest.problem_type,
        pipelineById.get(latest.pipeline_id)?.name ?? ""
      ].some((value) => value.toLowerCase().includes(normalized)))
    );
  }, [businessCaseId, families, pipelineById, query]);
  const sorted = useMemo(() => [...visible].sort((left, right) => {
    const value = ({ latest }: (typeof visible)[number]) => {
      if (sort.key === "report") return latest.name;
      if (sort.key === "business_case") return businessCaseById.get(latest.business_case_id)?.name ?? "";
      if (sort.key === "pipeline") return pipelineById.get(latest.pipeline_id)?.name ?? "";
      if (sort.key === "problem") return latest.problem_type;
      if (sort.key === "scope") return latest.evaluated_row_count;
      return new Date(latest.created_at).getTime();
    };
    const leftValue = value(left);
    const rightValue = value(right);
    const comparison = typeof leftValue === "number" && typeof rightValue === "number"
      ? leftValue - rightValue
      : String(leftValue).localeCompare(String(rightValue));
    return sort.direction === "asc" ? comparison : -comparison;
  }), [businessCaseById, pipelineById, sort, visible]);

  function toggleSort(key: typeof sort.key) {
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === "asc" ? "desc" : "asc"
    }));
  }

  useEffect(() => setBusinessCaseId(initialBusinessCaseId), [initialBusinessCaseId]);

  return (
    <section className="model-registry-screen">
      <div className="panel model-registry-panel">
        <div className="catalog-toolbar">
          <div>
            <span className="builder-kicker">Evaluation registry</span>
            <h2>Scoring reports</h2>
            <p>{visible.length} of {families.length} report families shown · {reports.length} immutable versions</p>
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
            <select value={businessCaseId} onChange={(event) => setBusinessCaseId(event.target.value)}>
              <option value="">All business cases</option>
              {businessCases.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
        </div>
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
          {sorted.map(({ latest, versions }) => (
            <div className="model-registry-row" role="row" key={latest.id}>
              <span>
                <strong>{latest.name}</strong>
                <small>v{latest.version_number} latest · {versions.length} version{versions.length === 1 ? "" : "s"}</small>
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
                  <button className="secondary-button compact-button" type="button" onClick={() => setHistory(latest)}>
                    <History size={14} /> Versions
                  </button>
                  <button className="secondary-button compact-button" type="button" onClick={() => setSelected(latest)}>
                    <Eye size={14} /> View latest
                  </button>
                </div>
              </span>
            </div>
          ))}
          {!visible.length && <div className="catalog-empty">No scoring reports match these filters.</div>}
        </div>
      </div>
      {selected && <ScoringReportDialog report={selected} onClose={() => setSelected(null)}
        onOpenDataset={onOpenDataset} />}
      {history && (
        <ScoringReportHistoryDialog
          report={history}
          onClose={() => setHistory(null)}
          onView={(version) => {
            setHistory(null);
            setSelected(version);
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
  onOpenDataset
}: {
  report: ScoringReport;
  onClose: () => void;
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
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close scoring report"><X size={18} /></button>
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
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api.listScoringReportVersions(report.logical_id)
      .then((items) => active && setVersions([...items].reverse()))
      .catch((requestError) => active && setError(
        requestError instanceof Error ? requestError.message : "Could not load report versions"
      ));
    return () => { active = false; };
  }, [report.logical_id]);
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
                <strong>v{version.version_number}{index === 0 && <i className="pipeline-status published">latest</i>}</strong>
                <span>{formatDate(version.created_at)} · run {shortId(version.pipeline_run_id)}</span>
                <small>{version.evaluated_row_count.toLocaleString()} evaluated rows</small>
              </div>
              <button className="secondary-button compact-button" type="button" onClick={() => onView(version)}>
                <Eye size={14} /> View
              </button>
            </article>
          ))}
          {!versions.length && !error && <div className="empty-state">Loading report versions…</div>}
        </div>
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
