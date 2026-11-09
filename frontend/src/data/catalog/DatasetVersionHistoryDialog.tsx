import { BarChart3, X } from "lucide-react";
import { useEffect, useState } from "react";

import { datasetsApi } from "../../api/datasets";
import type { DataAsset } from "../../api/contracts/datasets";
import { PaginationControls } from "../../components/PaginationControls";
import { formatDateTime } from "../../shared/formatters";

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
    datasetsApi.pageDatasetVersions(dataset.logical_id, { limit: 20, offset })
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
