import { ArrowLeft, X } from "lucide-react";
import { useState } from "react";

export function DialogNavigationActions({
  onBack,
  onClose,
  backLabel = "Back",
  closeLabel = "Close"
}: {
  onBack?: () => void;
  onClose: () => void;
  backLabel?: string;
  closeLabel?: string;
}) {
  return (
    <div className="dialog-navigation-actions">
      {onBack && (
        <button className="secondary-button compact-button" type="button" onClick={onBack}>
          <ArrowLeft size={15} /> {backLabel}
        </button>
      )}
      <button className="icon-button" type="button" onClick={onClose} aria-label={closeLabel}>
        <X size={18} />
      </button>
    </div>
  );
}

export function useVersionedResourceNavigation<T>() {
  const [history, setHistory] = useState<T | null>(null);
  const [selected, setSelected] = useState<T | null>(null);

  return {
    history,
    selected,
    hasBack: history !== null && selected !== null,
    showHistory: history !== null && selected === null,
    openHistory(resource: T) {
      setHistory(resource);
      setSelected(null);
    },
    openDirect(resource: T) {
      setHistory(null);
      setSelected(resource);
    },
    openVersion(resource: T) {
      setSelected(resource);
    },
    back() {
      setSelected(null);
    },
    closeHistory() {
      setHistory(null);
    },
    closeAll() {
      setSelected(null);
      setHistory(null);
    },
    replaceSelected(resource: T) {
      setSelected(resource);
    }
  };
}
