import { Eye, GitBranch, History, Pencil, Play, Trash2 } from "lucide-react";

export type AssetListItem = {
  id: string;
  name: string;
  meta: string;
  status: string;
  canDelete?: boolean;
  onDelete?: () => void;
  actionLabel?: string;
  onAction?: () => void;
  actions?: Array<{
    label: string;
    onClick: () => void;
    icon?: "view" | "versions" | "run" | "edit" | "dependencies";
    disabled?: boolean;
  }>;
};

export function AssetList({
  title,
  assets
}: {
  title: string;
  assets: AssetListItem[];
}) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>{title}</h2>
      </div>
      <div className="asset-list">
        {assets.map((asset) => (
          <div className="asset-row" key={asset.id}>
            <div>
              <strong>{asset.name}</strong>
              <span>{asset.meta}</span>
            </div>
            <div className="asset-actions">
              <em>{asset.status}</em>
              {asset.actions?.map((action) => {
                const Icon = action.icon === "versions" ? History
                  : action.icon === "dependencies" ? GitBranch
                  : action.icon === "run" ? Play
                    : action.icon === "view" ? Eye : Pencil;
                return (
                  <button className="secondary-button compact-button" type="button"
                    key={action.label} onClick={action.onClick} disabled={action.disabled}>
                    <Icon size={14} /> {action.label}
                  </button>
                );
              })}
              {asset.actionLabel && asset.onAction && (
                <button
                  className="secondary-button compact-button"
                  onClick={asset.onAction}
                  type="button"
                >
                  <Pencil size={14} />
                  {asset.actionLabel}
                </button>
              )}
              {asset.canDelete && asset.onDelete && (
                <button
                  aria-label={`Delete ${asset.name}`}
                  className="icon-button danger-icon"
                  onClick={asset.onDelete}
                  title="Delete dataset"
                  type="button"
                >
                  <Trash2 size={16} />
                </button>
              )}
            </div>
          </div>
        ))}
        {assets.length === 0 && <div className="empty-state">Nothing registered yet</div>}
      </div>
    </div>
  );
}
