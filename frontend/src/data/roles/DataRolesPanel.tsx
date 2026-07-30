import { Save } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../../api/client";
import type { DataAsset, DatasetPreview } from "../../api/client";
import {
  columnRoleOptions,
  datasetRoleOptions,
  defaultColumnRole,
  emptyRolesMetadata,
  normalizeRolesMetadata,
  readRolesMetadata
} from "../../analysis/dataRoles";
import type { DataRolesMetadata } from "../../analysis/dataRoles";
import { datasetVersionLabel } from "../catalog/DatasetCatalogPanel";

export function DataRolesPanel({
  datasets,
  datasetId,
  setDatasetId,
  onRefresh,
  setNotice
}: {
  datasets: DataAsset[];
  datasetId: string;
  setDatasetId: (datasetId: string) => void;
  onRefresh: () => Promise<void>;
  setNotice: (message: string) => void;
}) {
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [metadata, setMetadata] = useState<DataRolesMetadata>(emptyRolesMetadata);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const selectedDataset = datasets.find((dataset) => dataset.id === datasetId) ?? null;
  const columns = preview?.columns ?? [];

  useEffect(() => {
    setMetadata(readRolesMetadata(selectedDataset, datasets, columns.map((column) => column.name)));
  }, [columns, datasets, selectedDataset]);

  useEffect(() => {
    if (!datasetId) {
      setPreview(null);
      return;
    }

    let isCurrent = true;
    setIsLoading(true);
    api
      .previewDataset(datasetId)
      .then((result) => {
        if (isCurrent) {
          setPreview(result);
        }
      })
      .catch((error) => {
        if (!isCurrent) {
          return;
        }
        const message = error instanceof Error ? error.message : "Dataset preview failed";
        setPreview(null);
        setNotice(message);
      })
      .finally(() => {
        if (isCurrent) {
          setIsLoading(false);
        }
      });

    return () => {
      isCurrent = false;
    };
  }, [datasetId]);

  function toggleDatasetRole(role: string) {
    setMetadata((current) => ({
      ...current,
      dataset_roles: current.dataset_roles.includes(role)
        ? current.dataset_roles.filter((item) => item !== role)
        : [...current.dataset_roles, role]
    }));
  }

  function updateColumnRole(column: string, role: string) {
    setMetadata((current) => ({
      ...current,
      column_roles: {
        ...current.column_roles,
        [column]: role
      },
      entity_id_column: role === "identifier" ? column : current.entity_id_column,
      timestamp_column: role === "timestamp" ? column : current.timestamp_column,
      period_column: role === "period_id" ? column : current.period_column,
      target_column: role === "target" ? column : current.target_column
    }));
  }

  async function saveMetadata() {
    if (!selectedDataset) {
      setNotice("Choose a dataset first");
      return;
    }
    setIsSaving(true);
    try {
      await api.updateDatasetMetadata(selectedDataset.id, {
        ...selectedDataset.metadata,
        data_roles: normalizeRolesMetadata(metadata, columns.map((column) => column.name))
      });
      await onRefresh();
      setNotice(`Saved Data Roles for ${selectedDataset.name}`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Saving Data Roles failed");
    } finally {
      setIsSaving(false);
    }
  }

  if (datasets.length === 0) {
    return (
      <div className="panel">
        <div className="empty-state">No datasets available</div>
      </div>
    );
  }

  return (
    <div className="panel data-roles-panel">
      <div className="roles-toolbar">
        <label>
          Dataset
          <select value={datasetId} onChange={(event) => setDatasetId(event.target.value)}>
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {datasetVersionLabel(dataset, datasets)}
              </option>
            ))}
          </select>
        </label>
        <button className="primary-button toolbar-button" disabled={isSaving} onClick={saveMetadata} type="button">
          <Save size={16} />
          {isSaving ? "Saving" : "Save roles"}
        </button>
      </div>

      <section className="roles-section">
        <div className="panel-header compact-header">
          <h2>Dataset role</h2>
        </div>
        <div className="role-choice-grid">
          {datasetRoleOptions.map((option) => (
            <label className="check-tile" key={option.value}>
              <input
                checked={metadata.dataset_roles.includes(option.value)}
                onChange={() => toggleDatasetRole(option.value)}
                type="checkbox"
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="roles-section role-shortcuts">
        <label>
          Entity ID
          <ColumnSelect
            columns={columns}
            value={metadata.entity_id_column}
            onChange={(value) => setMetadata((current) => ({ ...current, entity_id_column: value }))}
          />
        </label>
        <label>
          Timestamp
          <ColumnSelect
            columns={columns}
            value={metadata.timestamp_column}
            onChange={(value) => setMetadata((current) => ({ ...current, timestamp_column: value }))}
          />
        </label>
        <label>
          Period/batch
          <ColumnSelect
            columns={columns}
            value={metadata.period_column}
            onChange={(value) => setMetadata((current) => ({ ...current, period_column: value }))}
          />
        </label>
        <label>
          Target
          <ColumnSelect
            columns={columns}
            value={metadata.target_column}
            onChange={(value) => setMetadata((current) => ({ ...current, target_column: value }))}
          />
        </label>
      </section>

      <section className="roles-section">
        <div className="panel-header compact-header">
          <h2>Column roles</h2>
          {isLoading && <span className="muted-text">Loading columns</span>}
        </div>
        <div className="column-role-list">
          {columns.map((column) => (
            <div className="column-role-row" key={column.name}>
              <div>
                <strong>{column.name}</strong>
                <span>{column.type}</span>
              </div>
              <select
                value={metadata.column_roles[column.name] ?? defaultColumnRole(column.type)}
                onChange={(event) => updateColumnRole(column.name, event.target.value)}
              >
                {columnRoleOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          ))}
          {!isLoading && columns.length === 0 && (
            <div className="empty-state">No columns detected for this dataset</div>
          )}
        </div>
      </section>

      <label>
        Notes
        <textarea
          className="compact-textarea"
          value={metadata.notes}
          onChange={(event) => setMetadata((current) => ({ ...current, notes: event.target.value }))}
        />
      </label>
    </div>
  );
}

function ColumnSelect({
  columns,
  value,
  onChange
}: {
  columns: DatasetPreview["columns"];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">Not set</option>
      {columns.map((column) => (
        <option key={column.name} value={column.name}>
          {column.name}
        </option>
      ))}
    </select>
  );
}
