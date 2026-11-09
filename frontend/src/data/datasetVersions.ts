import type { DataAsset } from "../api/contracts/datasets";
import { asRecord } from "../shared/values";

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
