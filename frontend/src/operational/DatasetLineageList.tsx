import { Database, Eye } from "lucide-react";

import type { DatasetLineageReference } from "../api/client";

export function DatasetLineageList({
  items,
  error,
  onOpenDataset
}: {
  items: DatasetLineageReference[];
  error?: string;
  onOpenDataset?: (datasetId: string) => void;
}) {
  return (
    <section className="model-detail-section">
      <h3><Database size={16} /> Related datasets</h3>
      {error && <div className="error-banner">{error}</div>}
      <div className="dataset-lineage-list">
        {items.map((item) => (
          <article key={item.artifact_id}>
            <div>
              <strong>{item.name} · v{item.version_number}</strong>
              <span>{item.role.replaceAll("_", " ")} · {item.stage} · {item.row_count?.toLocaleString() ?? "—"} rows</span>
              <small>{item.pipeline_step_id ? `step ${item.pipeline_step_id}` : "registered source"}</small>
            </div>
            {onOpenDataset && (
              <button
                className="secondary-button compact-button"
                type="button"
                onClick={() => onOpenDataset(item.dataset_id)}
              >
                <Eye size={14} /> Open dataset
              </button>
            )}
          </article>
        ))}
        {!items.length && !error && (
          <div className="empty-state">No resolved dataset lineage is available.</div>
        )}
      </div>
    </section>
  );
}
