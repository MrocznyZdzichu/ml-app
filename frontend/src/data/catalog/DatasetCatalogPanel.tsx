import { BarChart3, CheckCircle2, Copy, Filter, Plus, Search, Trash2, Upload, X } from "lucide-react";
import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../../api/client";
import type { BusinessCase, DataAsset, Pipeline } from "../../api/client";
import { ArtifactFilters } from "../../components/ArtifactFilters";
import { AssetList } from "../../components/AssetList";
import { PagedCatalogSelect } from "../../components/PagedCatalogSelect";
import { PaginationControls } from "../../components/PaginationControls";
import { formatDateTime, shortId } from "../../shared/formatters";

export function DatasetVersionHistoryDialog({
  dataset,
  onClose,
  onOpen
}: {
  dataset: DataAsset;
  onClose: () => void;
  onOpen: (datasetId: string) => void;
}) {
  const [versions, setVersions] = useState<DataAsset[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    api.pageDatasetVersions(dataset.logical_id, { limit: 20, offset })
      .then((page) => {
        if (!active) return;
        setVersions(page.items);
        setTotal(page.total);
        setError("");
      })
      .catch((requestError) => active && setError(
        requestError instanceof Error ? requestError.message : "Could not load dataset versions"
      ))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [dataset.logical_id, offset]);
  return (
    <div className="modal-backdrop" role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal-dialog model-version-dialog" role="dialog" aria-modal="true"
        aria-label={`Versions of ${dataset.name}`}>
        <div className="modal-header">
          <div><span className="builder-kicker">Dataset family</span><h2>{dataset.name}</h2>
            <p>{total} immutable versions</p></div>
          <button className="icon-button" type="button" onClick={onClose}
            aria-label="Close dataset versions"><X size={17} /></button>
        </div>
        {error && <div className="error-banner">{error}</div>}
        <div className="model-version-list">
          {versions.map((version, index) => (
            <article key={version.id}>
              <div className="model-version-marker"><span>v{version.version_number}</span></div>
              <div><strong>v{version.version_number}
                {offset === 0 && index === 0 && <i className="pipeline-status published">latest</i>}</strong>
                <span>{formatDateTime(version.created_at)} · {version.row_count ?? "?"} rows</span>
                <small>{version.format.toUpperCase()} · {version.version_stage}</small></div>
              <button className="secondary-button compact-button" type="button"
                onClick={() => onOpen(version.id)}>
                <BarChart3 size={14} /> Analyze
              </button>
            </article>
          ))}
          {!versions.length && loading && <div className="empty-state">Loading dataset versions…</div>}
        </div>
        <PaginationControls
          total={total}
          limit={20}
          offset={offset}
          onOffsetChange={setOffset}
          disabled={loading}
          label="dataset versions"
        />
      </div>
    </div>
  );
}

export function DataPanel({
  businessCases,
  datasets,
  pipelines,
  onAnalyze,
  onRefresh,
  onRegisterRefresh,
  setNotice
}: {
  businessCases: BusinessCase[];
  datasets: DataAsset[];
  pipelines: Pipeline[];
  onAnalyze: (datasetId: string) => void;
  onRefresh: () => Promise<void>;
  onRegisterRefresh: (handler: (() => Promise<void>) | null) => void;
  setNotice: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [uploadLogicalId, setUploadLogicalId] = useState("");
  const [businessCaseFilter, setBusinessCaseFilter] = useState("");
  const [purposeFilter, setPurposeFilter] = useState("");
  const [pipelineFilter, setPipelineFilter] = useState("");
  const [uploadedOnly, setUploadedOnly] = useState(false);
  const [datasetSearch, setDatasetSearch] = useState("");
  const [activeDatasets, setActiveDatasets] = useState<DataAsset[]>([]);
  const [activeDatasetTotal, setActiveDatasetTotal] = useState(0);
  const [activeDatasetOffset, setActiveDatasetOffset] = useState(0);
  const [dataViews, setDataViews] = useState<DataAsset[]>([]);
  const [dataViewTotal, setDataViewTotal] = useState(0);
  const [dataViewOffset, setDataViewOffset] = useState(0);
  const [deletedDatasets, setDeletedDatasets] = useState<DataAsset[]>([]);
  const [deletedDatasetTotal, setDeletedDatasetTotal] = useState(0);
  const [deletedDatasetOffset, setDeletedDatasetOffset] = useState(0);
  const [isDatasetPageLoading, setIsDatasetPageLoading] = useState(false);
  const [datasetRefreshKey, setDatasetRefreshKey] = useState(0);
  const filterPipelines = businessCaseFilter
    ? pipelines.filter((pipeline) => pipeline.business_case_id === businessCaseFilter)
    : pipelines;

  const refreshCatalog = useCallback(async () => {
    await onRefresh();
    setDatasetRefreshKey((value) => value + 1);
  }, [onRefresh]);

  useEffect(() => {
    onRegisterRefresh(refreshCatalog);
    return () => onRegisterRefresh(null);
  }, [onRegisterRefresh, refreshCatalog]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setIsDatasetPageLoading(true);
      const common = {
        limit: 20,
        search: datasetSearch.trim(),
        business_case_id: businessCaseFilter,
        families: true,
        summary: true
      };
      Promise.all([
        api.pageDatasets({
          ...common,
          offset: activeDatasetOffset,
          asset_kind: "dataset",
          include_deleted: false,
          pipeline_id: pipelineFilter,
          pipeline_type: purposeFilter,
          uploaded_only: uploadedOnly
        }),
        api.pageDatasets({
          ...common,
          offset: dataViewOffset,
          asset_kind: "view",
          include_deleted: false
        }),
        api.pageDatasets({
          ...common,
          offset: deletedDatasetOffset,
          families: false,
          status: "deleted"
        })
      ])
        .then(([datasetPage, viewPage, deletedPage]) => {
          setActiveDatasets(datasetPage.items);
          setActiveDatasetTotal(datasetPage.total);
          setDataViews(viewPage.items);
          setDataViewTotal(viewPage.total);
          setDeletedDatasets(deletedPage.items);
          setDeletedDatasetTotal(deletedPage.total);
        })
        .catch((error) => setNotice(error instanceof Error ? error.message : "Could not load dataset catalog"))
        .finally(() => setIsDatasetPageLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [
    activeDatasetOffset,
    businessCaseFilter,
    dataViewOffset,
    datasetRefreshKey,
    datasetSearch,
    deletedDatasetOffset,
    pipelineFilter,
    purposeFilter,
    setNotice,
    uploadedOnly
  ]);

  useEffect(() => {
    setActiveDatasetOffset(0);
    setDataViewOffset(0);
    setDeletedDatasetOffset(0);
  }, [businessCaseFilter, datasetSearch, pipelineFilter, purposeFilter, uploadedOnly]);

  function selectDatasetFile(nextFile: File | null) {
    if (!nextFile) {
      setFile(null);
      return;
    }
    if (!/\.(csv|parquet)$/i.test(nextFile.name)) {
      setNotice("Choose a .csv or .parquet dataset file");
      return;
    }
    setFile(nextFile);
    if (!name.trim()) {
      setName(nextFile.name.replace(/\.(csv|parquet)$/i, ""));
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setNotice("Choose a CSV or Parquet file first");
      return;
    }
    if (!name.trim()) {
      setNotice("Enter dataset name");
      return;
    }

    const formData = new FormData();
    formData.set("file", file);
    formData.set("name", name.trim());
    formData.set("description", description);
    formData.set("tags", tags);
    if (uploadLogicalId) formData.set("logical_id", uploadLogicalId);

    setIsUploadingFile(true);
    try {
      const uploaded = await api.uploadDataset(formData);
      setNotice(
        `Uploaded ${uploaded.name} v${uploaded.version_number}: ${uploaded.row_count ?? 0} rows · ${uploaded.format.toUpperCase()} · full dataset`
      );
      setName("");
      setDescription("");
      setTags("");
      setFile(null);
      setUploadLogicalId("");
      setFileInputKey((current) => current + 1);
      await refreshCatalog();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Dataset upload failed");
    } finally {
      setIsUploadingFile(false);
    }
  }

  async function deleteDataset(dataset: DataAsset) {
    const deleted = await api.deleteDataset(dataset.id);
    setNotice(`Deleted ${deleted.name}`);
    await refreshCatalog();
  }

  function addDatasetVersion(dataset: DataAsset) {
    setUploadLogicalId(dataset.logical_id);
    setName(dataset.name);
    setDescription(dataset.description);
    setTags(dataset.tags.join(", "));
    setFile(null);
    setFileInputKey((current) => current + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <section className="two-column">
      <form className="panel form-panel" onSubmit={submit}>
        <div className="panel-header">
          <div>
            <h2>{uploadLogicalId ? `Add version of ${name}` : "Upload dataset from file"}</h2>
            <p className="dataset-upload-subtitle">
              {uploadLogicalId ? "Register a new immutable version of this logical dataset." : "Register a complete CSV or Parquet dataset."}
            </p>
          </div>
          <Upload size={18} />
        </div>
        <label>
          Dataset name
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Suggested from the selected filename"
            required
            disabled={Boolean(uploadLogicalId)}
          />
        </label>
        <label
          className={`dataset-file-picker ${isDraggingFile ? "dragging" : ""} ${file ? "selected" : ""}`}
          onDragEnter={(event) => {
            event.preventDefault();
            setIsDraggingFile(true);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
              setIsDraggingFile(false);
            }
          }}
          onDrop={(event) => {
            event.preventDefault();
            setIsDraggingFile(false);
            selectDatasetFile(event.dataTransfer.files?.[0] ?? null);
          }}
        >
          <input
            accept=".csv,.parquet,text/csv,application/vnd.apache.parquet"
            className="dataset-file-input"
            key={fileInputKey}
            onChange={(event) => selectDatasetFile(event.target.files?.[0] ?? null)}
            required
            type="file"
          />
          <span className="dataset-file-picker-icon"><Upload size={22} /></span>
          {file ? (
            <span className="dataset-file-selection">
              <strong>{file.name}</strong>
              <small>
                <em>{file.name.toLowerCase().endsWith(".parquet") ? "PARQUET" : "CSV"}</em>
                {formatBytes(file.size)}
              </small>
            </span>
          ) : (
            <span className="dataset-file-selection">
              <strong>Drop a dataset file here</strong>
              <small>or click to browse · CSV and Parquet</small>
            </span>
          )}
        </label>
        <div className="dataset-format-guidance">
          <span><strong>CSV</strong><small>UTF-8 tabular data; converted to a reusable columnar cache for analytics.</small></span>
          <span><strong>Parquet</strong><small>Used natively with schema and column types preserved.</small></span>
        </div>
        <label>
          Description
          <textarea
            className="compact-textarea"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <label>
          Tags
          <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="Comma-separated, optional" />
        </label>
        <div className="dataset-upload-scope">
          <CheckCircle2 size={15} />
          Full file will be registered. Upload does not silently sample rows.
        </div>
        <button className="primary-button" type="submit" disabled={isUploadingFile}>
          <Upload size={16} />
          {isUploadingFile ? "Uploading and validating…" : "Upload dataset"}
        </button>
        {uploadLogicalId && (
          <button className="secondary-button" type="button" onClick={() => {
            setUploadLogicalId("");
            setName("");
            setDescription("");
            setTags("");
            setFile(null);
            setFileInputKey((current) => current + 1);
          }}>
            Cancel new version
          </button>
        )}
      </form>

      <div className="repository-column">
        <div className="panel dataset-catalog-filters">
          <div>
            <h2>Dataset filters</h2>
            <p>
              {isDatasetPageLoading
                ? "Loading Business Case datasets…"
                : `${activeDatasetTotal} dataset families`}
            </p>
          </div>
          <div className="dataset-filter-controls">
            <label className="dataset-business-case-filter">
              <span><Filter size={14} /> Business case</span>
              <PagedCatalogSelect
                value={businessCaseFilter}
                onChange={(value) => {
                  setBusinessCaseFilter(value);
                  setPurposeFilter("");
                  setPipelineFilter("");
                }}
                loadPage={api.pageBusinessCases}
                getId={(item) => item.id}
                getLabel={(item) => item.name}
                emptyLabel="All business cases"
                searchPlaceholder="Search Business Cases"
              />
            </label>
            <ArtifactFilters
              pipelines={filterPipelines}
              purpose={purposeFilter}
              pipelineId={pipelineFilter}
              onPurposeChange={setPurposeFilter}
              onPipelineChange={setPipelineFilter}
              businessCaseId={businessCaseFilter}
              uploadedOnly={uploadedOnly}
              onUploadedOnlyChange={(value) => {
                setUploadedOnly(value);
                if (value) {
                  setPurposeFilter("");
                  setPipelineFilter("");
                }
              }}
            />
          </div>
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Search datasets"
              placeholder="Search datasets and data views"
              value={datasetSearch}
              onChange={(event) => setDatasetSearch(event.target.value)}
            />
          </label>
        </div>
        <VersionedDatasetList
          datasets={activeDatasets}
          onAddVersion={addDatasetVersion}
          onAnalyze={onAnalyze}
          onDelete={deleteDataset}
          setNotice={setNotice}
        />
        <PaginationControls
          total={activeDatasetTotal}
          limit={20}
          offset={activeDatasetOffset}
          onOffsetChange={setActiveDatasetOffset}
          disabled={isDatasetPageLoading}
          label="dataset families"
        />
        <AssetList
          title="Data views"
          assets={dataViews.map((item) => ({
            id: item.id,
            name: item.name,
            meta: dataViewMeta(item),
            status: item.status,
            canDelete: true,
            onDelete: () => deleteDataset(item)
          }))}
        />
        <PaginationControls
          total={dataViewTotal}
          limit={20}
          offset={dataViewOffset}
          onOffsetChange={setDataViewOffset}
          disabled={isDatasetPageLoading}
          label="data views"
        />
        {deletedDatasetTotal > 0 && (
          <details className="panel editor-details deleted-assets-panel">
            <summary>Deleted datasets <span>{deletedDatasetTotal}</span></summary>
            <AssetList
              title=""
              assets={deletedDatasets.map((item) => ({
                id: item.id,
                name: item.name,
                meta: datasetMeta(item),
                status: item.status
              }))}
            />
            <PaginationControls
              total={deletedDatasetTotal}
              limit={20}
              offset={deletedDatasetOffset}
              onOffsetChange={setDeletedDatasetOffset}
              disabled={isDatasetPageLoading}
              label="deleted datasets"
            />
          </details>
        )}
      </div>
    </section>
  );
}

function datasetMeta(item: DataAsset) {
  return [
    item.original_filename ?? `${item.source_type}.${item.format}`,
    `${item.row_count ?? 0} rows`,
    item.file_size_bytes == null ? null : formatBytes(item.file_size_bytes),
    headerLabel(item.has_header),
    item.deleted_at ? `deleted ${formatDateTime(item.deleted_at)}` : null,
    item.deleted_by ? `by ${shortId(item.deleted_by)}` : null
  ].filter(Boolean).join(" / ");
}

function VersionedDatasetList({
  datasets,
  onAddVersion,
  onAnalyze,
  onDelete,
  setNotice
}: {
  datasets: DataAsset[];
  onAddVersion: (dataset: DataAsset) => void;
  onAnalyze: (datasetId: string) => void;
  onDelete: (dataset: DataAsset) => void;
  setNotice: (message: string) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [historyByLogicalId, setHistoryByLogicalId] = useState<
    Record<string, { items: DataAsset[]; total: number; offset: number }>
  >({});
  const [loadingLogicalId, setLoadingLogicalId] = useState("");
  const groups = datasetVersionGroups(datasets);

  async function loadHistory(logicalId: string, offset: number) {
    setLoadingLogicalId(logicalId);
    try {
      const page = await api.pageDatasetVersions(logicalId, { limit: 10, offset });
      setHistoryByLogicalId((current) => ({
        ...current,
        [logicalId]: { items: page.items, total: page.total, offset: page.offset }
      }));
      return true;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not load dataset versions");
      return false;
    } finally {
      setLoadingLogicalId("");
    }
  }

  async function toggleHistory(logicalId: string) {
    if (expanded.has(logicalId)) {
      setExpanded((current) => {
        const next = new Set(current);
        next.delete(logicalId);
        return next;
      });
      return;
    }
    if (!historyByLogicalId[logicalId]) {
      if (!await loadHistory(logicalId, 0)) return;
    }
    setExpanded((current) => new Set(current).add(logicalId));
  }

  return (
    <div className="panel">
      <div className="panel-header"><h2>Active datasets</h2></div>
      <div className="asset-list">
        {groups.map(({ logicalId, latest, versions }) => {
          const isExpanded = expanded.has(logicalId);
          const historyPage = historyByLogicalId[logicalId];
          const history = historyPage?.items ?? versions;
          const versionCount = Math.max(latest.version_number, historyPage?.total ?? history.length);
          return (
            <div className="dataset-version-group" key={logicalId}>
              <div className="asset-row">
                <div>
                  <strong>{latest.name} <i className="version-badge">v{latest.version_number}</i></strong>
                  <span>{datasetMeta(latest)} / {versionCount} version{versionCount === 1 ? "" : "s"} / {latest.version_stage}</span>
                  <div className="dataset-identifiers" aria-label={`Identifiers for ${latest.name}`}>
                    <code>Version ID: {latest.id}</code>
                    <button className="icon-button" type="button" title="Copy version ID"
                      aria-label={`Copy version ID for ${latest.name}`}
                      onClick={() => void navigator.clipboard.writeText(latest.id)}>
                      <Copy size={14} />
                    </button>
                    <code>Family ID: {latest.logical_id}</code>
                    <button className="icon-button" type="button" title="Copy family ID"
                      aria-label={`Copy family ID for ${latest.name}`}
                      onClick={() => void navigator.clipboard.writeText(latest.logical_id)}>
                      <Copy size={14} />
                    </button>
                  </div>
                </div>
                <div className="asset-actions">
                  <em>{latest.status}</em>
                  <button className="secondary-button compact-button" type="button"
                    onClick={() => onAnalyze(latest.id)}>
                    <BarChart3 size={14} /> Analyze latest
                  </button>
                  <button className="secondary-button compact-button" type="button" onClick={() => void toggleHistory(logicalId)}
                    disabled={loadingLogicalId === logicalId}>
                    {loadingLogicalId === logicalId ? "Loading…" : `Versions (${versionCount})`}
                  </button>
                  <button className="secondary-button compact-button" type="button" onClick={() => onAddVersion(latest)}>
                    <Plus size={14} /> Add version
                  </button>
                </div>
              </div>
              {isExpanded && (
                <div className="dataset-version-history">
                  {[...history].sort((a, b) => b.version_number - a.version_number).map((version) => (
                    <div className="asset-row version-row" key={version.id}>
                      <div>
                        <strong>v{version.version_number} {version.id === latest.id ? "· latest" : ""}</strong>
                        <span>{datasetMeta(version)} / created {formatDateTime(version.created_at)}</span>
                      </div>
                      <div className="asset-actions">
                        <em>{version.version_stage}</em>
                        <button className="secondary-button compact-button" type="button"
                          onClick={() => onAnalyze(version.id)}>
                          <BarChart3 size={14} /> Analyze
                        </button>
                        <button
                          aria-label={`Delete ${version.name} v${version.version_number}`}
                          className="icon-button danger-icon"
                          onClick={() => onDelete(version)}
                          title="Delete this dataset version"
                          type="button"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  ))}
                  <PaginationControls
                    total={historyPage?.total ?? history.length}
                    limit={10}
                    offset={historyPage?.offset ?? 0}
                    onOffsetChange={(nextOffset) => void loadHistory(logicalId, nextOffset)}
                    disabled={loadingLogicalId === logicalId}
                    label="dataset versions"
                  />
                </div>
              )}
            </div>
          );
        })}
        {!groups.length && <div className="empty-state">Nothing registered yet</div>}
      </div>
    </div>
  );
}

export function datasetVersionGroups(datasets: DataAsset[]) {
  const grouped = new Map<string, DataAsset[]>();
  for (const dataset of datasets) {
    const logicalId = dataset.logical_id || dataset.id;
    grouped.set(logicalId, [...(grouped.get(logicalId) ?? []), dataset]);
  }
  return [...grouped.entries()]
    .map(([logicalId, versions]) => ({
      logicalId,
      versions,
      latest: [...versions].sort((a, b) => b.version_number - a.version_number)[0]
    }))
    .sort((left, right) => right.latest.created_at.localeCompare(left.latest.created_at));
}

export function latestLogicalDatasetAliases(datasets: DataAsset[]) {
  return datasetVersionGroups(
    datasets.filter((dataset) => dataset.status !== "deleted")
  ).map(({ logicalId, latest }) => ({ ...latest, id: logicalId }));
}

export function datasetVersionLabel(dataset: DataAsset, datasets: DataAsset[]) {
  const versions = datasets.filter(
    (item) => item.logical_id === dataset.logical_id && item.status !== "deleted"
  );
  const latest = Math.max(...versions.map((item) => item.version_number), dataset.version_number);
  return `${dataset.name} · v${dataset.version_number}${dataset.version_number === latest ? " (latest)" : ""}`;
}

export function isDataView(item: DataAsset) {
  return item.source_type === "view" || item.format === "view" || Boolean(asRecord(item.metadata.data_view).source_dataset_id);
}

function dataViewMeta(item: DataAsset) {
  const metadata = asRecord(item.metadata.data_view);
  const sourceName = asString(metadata.source_dataset_name) || "unknown source";
  const rowCount = typeof metadata.row_count === "number" ? metadata.row_count : item.row_count ?? 0;
  const columnCount = typeof metadata.column_count === "number" ? metadata.column_count : 0;
  const createdBy = asString(metadata.created_by) || item.uploaded_by || item.owner_id;
  const createdAt = asString(metadata.created_at) || item.created_at;
  return [
    `source: ${sourceName}`,
    `${rowCount} rows`,
    `${columnCount} columns`,
    `created by ${shortId(createdBy)}`,
    `created ${formatDateTime(createdAt)}`
  ].join(" / ");
}

function headerLabel(hasHeader: boolean | null) {
  if (hasHeader === null) {
    return "headers unknown";
  }
  return hasHeader ? "headers detected" : "no headers detected";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function asString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function formatBytes(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
