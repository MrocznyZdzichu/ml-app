import { GitBranch, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api, type ArtifactDependency } from "../api/client";

export function ArtifactDependenciesDialog({
  referenceId,
  artifactType,
  title,
  onClose,
  onOpenDataset
}: {
  referenceId: string;
  artifactType: string;
  title: string;
  onClose: () => void;
  onOpenDataset?: (datasetId: string) => void;
}) {
  const [items, setItems] = useState<ArtifactDependency[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    setItems([]);
    setError("");
    void api.getArtifactDependencies(referenceId, artifactType)
      .then(setItems)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load dependencies"));
  }, [artifactType, referenceId]);

  const groups = [
    ["Upstream dependencies", items.filter((item) => item.direction === "upstream")],
    ["Used by", items.filter((item) => item.direction === "downstream")]
  ] as const;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="modal-dialog form-panel" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div><span className="builder-kicker">Artifact graph</span><h2><GitBranch size={18} /> Dependencies · {title}</h2>
            <p>Direct lineage is resolved against concrete artifacts, pipeline versions and runs.</p></div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close dependencies"><X size={17} /></button>
        </div>
        {error && <div className="error-banner">{error}</div>}
        {groups.map(([heading, group]) => (
          <section className="model-detail-section" key={heading}>
            <h3>{heading}</h3>
            {group.map((item) => (
              <article className="dataset-lineage-list" key={`${item.direction}-${item.artifact_type}-${item.reference_id}-${item.role}`}>
                <div><strong>{item.artifact_type.replaceAll("_", " ")} · {item.reference_id}</strong>
                  <span>{item.role}{item.pipeline_step_id ? ` · step ${item.pipeline_step_id}` : ""}</span>
                  <small>{item.pipeline_version_id ? `version ${item.pipeline_version_id}` : item.pipeline_run_id ? `run ${item.pipeline_run_id}` : ""}</small></div>
                {onOpenDataset && ["dataset", "data_view", "prediction_dataset"].includes(item.artifact_type) && (
                  <button className="secondary-button compact-button" type="button" onClick={() => { onClose(); onOpenDataset(item.reference_id); }}>Open dataset</button>
                )}
              </article>
            ))}
            {!group.length && <div className="empty-state">None recorded.</div>}
          </section>
        ))}
      </section>
    </div>
  );
}
