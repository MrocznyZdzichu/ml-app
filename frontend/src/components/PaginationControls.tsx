type Props = {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
  disabled?: boolean;
  label?: string;
};

export function PaginationControls({
  total,
  limit,
  offset,
  onOffsetChange,
  disabled = false,
  label = "objects"
}: Props) {
  if (total <= limit && offset === 0) return null;
  const page = Math.floor(offset / limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const first = total === 0 ? 0 : offset + 1;
  const last = Math.min(total, offset + limit);

  return (
    <nav className="pagination-controls" aria-label={`${label} pagination`}>
      <span>
        {first}–{last} of {total} {label}
      </span>
      <div>
        <button
          className="secondary-button"
          type="button"
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
          disabled={disabled || offset === 0}
        >
          Previous
        </button>
        <strong>Page {page} of {pageCount}</strong>
        <button
          className="secondary-button"
          type="button"
          onClick={() => onOffsetChange(offset + limit)}
          disabled={disabled || offset + limit >= total}
        >
          Next
        </button>
      </div>
    </nav>
  );
}
