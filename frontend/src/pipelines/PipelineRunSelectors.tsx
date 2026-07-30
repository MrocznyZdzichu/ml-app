import { useState } from "react";

import { api } from "../api/client";
import type { DataAsset, ModelArtifact } from "../api/client";
import { PagedCatalogSelect } from "../components/PagedCatalogSelect";
import { inferenceBundleSummary } from "../shared/catalogLabels";
import { formatDateTime, shortId } from "../shared/formatters";
import { requiresRuntimeDatasetSelection } from "./dataContractOptions";
import type { PipelineRunInput, PipelineRunModel } from "./pipelineRunInputs";

export function PipelineRunModelSelector({
  model,
  value,
  onChange
}: {
  model: PipelineRunModel;
  value: string;
  onChange: (value: string) => void;
}) {
  const [snapshot, setSnapshot] = useState<ModelArtifact | undefined>(
    model.versions.find((version) => version.id === value)
  );
  return (
    <label>
      Inference bundle — {model.name}
      <PagedCatalogSelect<ModelArtifact>
        value={value}
        selectedItem={snapshot}
        searchable={false}
        loadPage={(query) => api.pageModelVersions(model.logicalId, query)}
        getId={(version) => version.id}
        getLabel={(version) =>
          `v${version.version_number} · ${version.algorithm}${version.stage === "production" ? " · production" : ""}`
        }
        emptyLabel="Select model version…"
        searchPlaceholder="Model versions"
        onPageLoaded={(page) => {
          if (!value && page.offset === 0 && page.items.length) {
            setSnapshot(page.items[0]);
            onChange(page.items[0].id);
          }
        }}
        onChange={(nextValue, version) => {
          setSnapshot(version);
          onChange(nextValue);
        }}
      />
      <small>
        {snapshot
          ? inferenceBundleSummary(snapshot)
          : "The selected model version determines the complete immutable inference bundle."}
      </small>
    </label>
  );
}

export function PipelineRunDatasetInputSelector({
  input,
  businessCaseId,
  value,
  onChange
}: {
  input: PipelineRunInput;
  businessCaseId: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [anyLogicalId, setAnyLogicalId] = useState("");
  const [familySnapshot, setFamilySnapshot] = useState<DataAsset | undefined>();
  const [versionSnapshot, setVersionSnapshot] = useState<DataAsset | undefined>();
  const logicalId = input.policy === "select_at_run_any"
    ? anyLogicalId
    : input.logicalId;

  if (!requiresRuntimeDatasetSelection(input.policy)) {
    return (
      <label>
        {input.name}
        <input
          readOnly
          value={input.policy === "pinned"
            ? `Pinned immutable dataset · ${shortId(input.datasetId)}`
            : "Latest active version · resolved when the run starts"}
        />
        <small>
          {input.policy === "pinned"
            ? "This exact immutable version is pinned in the pipeline definition."
            : "The resolved version is recorded when the run is created."}
        </small>
      </label>
    );
  }

  return (
    <label>
      {input.name}
      {input.policy === "select_at_run_any" && (
        <PagedCatalogSelect<DataAsset>
          value={anyLogicalId}
          selectedItem={familySnapshot}
          loadPage={async (query) => {
            const page = await api.pageDatasets({
              ...query,
              business_case_id: businessCaseId,
              asset_kind: "dataset",
              families: true
            });
            return {
              ...page,
              items: page.items.map((item) => ({
                ...item,
                id: item.logical_id || item.id
              }))
            };
          }}
          getId={(dataset) => dataset.id}
          getLabel={(dataset) => `${dataset.name} · latest v${dataset.version_number}`}
          emptyLabel="Select dataset family…"
          searchPlaceholder="Search Business Case datasets"
          onChange={(nextLogicalId, dataset) => {
            setAnyLogicalId(nextLogicalId);
            setFamilySnapshot(dataset);
            setVersionSnapshot(undefined);
            onChange("");
          }}
        />
      )}
      <PagedCatalogSelect<DataAsset>
        value={value}
        selectedItem={versionSnapshot}
        reloadKey={logicalId}
        disabled={!logicalId}
        searchable={false}
        loadPage={(query) => logicalId
          ? api.pageDatasetVersions(logicalId, query)
          : Promise.resolve({
              items: [],
              total: 0,
              limit: query.limit,
              offset: query.offset,
              has_next: false
            })}
        getId={(dataset) => dataset.id}
        getLabel={(dataset) =>
          `v${dataset.version_number} · ${dataset.row_count ?? "?"} rows · ${formatDateTime(dataset.created_at)}`
        }
        emptyLabel="Select immutable version…"
        searchPlaceholder="Filter versions"
        onChange={(nextValue, dataset) => {
          setVersionSnapshot(dataset);
          onChange(nextValue);
        }}
      />
      <small>This run requires an explicit immutable version.</small>
    </label>
  );
}
