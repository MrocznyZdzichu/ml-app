import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { OffsetPage } from "../api/client";

type Props<T> = {
  value: string;
  onChange: (value: string, item: T | undefined) => void;
  loadPage: (query: { limit: number; offset: number; search: string }) => Promise<OffsetPage<T>>;
  getId: (item: T) => string;
  getLabel: (item: T) => string;
  emptyLabel: string;
  searchPlaceholder: string;
  disabled?: boolean;
  searchable?: boolean;
  onPageLoaded?: (page: OffsetPage<T>) => void;
  selectedItem?: T;
  reloadKey?: string;
};

export function PagedCatalogSelect<T>({
  value,
  onChange,
  loadPage,
  getId,
  getLabel,
  emptyLabel,
  searchPlaceholder,
  disabled = false,
  searchable = true,
  onPageLoaded,
  selectedItem,
  reloadKey = ""
}: Props<T>) {
  const [items, setItems] = useState<T[]>([]);
  const [selectedItems, setSelectedItems] = useState<Record<string, T>>({});
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState({ reloadKey, offset: 0 });
  const offset = page.reloadKey === reloadKey ? page.offset : 0;
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const loadPageRef = useRef(loadPage);
  loadPageRef.current = loadPage;
  const onPageLoadedRef = useRef(onPageLoaded);
  onPageLoadedRef.current = onPageLoaded;
  const limit = 30;

  useEffect(() => {
    if (query.trim() === search) return;
    const timer = window.setTimeout(() => {
      setSearch(query.trim());
      setPage({ reloadKey, offset: 0 });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, reloadKey, search]);

  useEffect(() => {
    let current = true;
    setLoading(true);
    loadPageRef.current({ limit, offset, search })
      .then((result) => {
        if (!current) return;
        setItems(result.items);
        setTotal(result.total);
        onPageLoadedRef.current?.(result);
      })
      .catch(() => {
        if (!current) return;
        setItems([]);
        setTotal(0);
      })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [offset, reloadKey, search]);

  useEffect(() => {
    setPage((current) => current.reloadKey === reloadKey ? current : { reloadKey, offset: 0 });
  }, [reloadKey]);

  const options = useMemo(() => {
    const selected = value
      ? selectedItems[value] ?? (
          selectedItem && getId(selectedItem) === value ? selectedItem : undefined
        )
      : undefined;
    return selected && !items.some((item) => getId(item) === value)
      ? [selected, ...items]
      : items;
  }, [getId, items, selectedItem, selectedItems, value]);

  return (
    <div className="paged-catalog-select">
      {searchable && (
        <span className="paged-catalog-search">
          <Search size={14} />
          <input
            aria-label={searchPlaceholder}
            placeholder={searchPlaceholder}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            disabled={disabled}
          />
        </span>
      )}
      <select
        value={value}
        disabled={disabled || loading}
        onChange={(event) => {
          const next = event.target.value;
          const item = items.find((candidate) => getId(candidate) === next)
            ?? selectedItems[next];
          if (item) {
            setSelectedItems((current) => ({ ...current, [next]: item }));
          }
          onChange(next, item);
        }}
      >
        <option value="">{loading && !items.length ? "Loading…" : emptyLabel}</option>
        {options.map((item) => (
          <option key={getId(item)} value={getId(item)}>{getLabel(item)}</option>
        ))}
      </select>
      {total > limit && (
        <span className="paged-catalog-navigation">
          <button type="button" onClick={() => setPage({ reloadKey, offset: Math.max(0, offset - limit) })} disabled={loading || offset === 0}>
            Previous
          </button>
          <small>{offset + 1}–{Math.min(total, offset + limit)} of {total}</small>
          <button type="button" onClick={() => setPage({ reloadKey, offset: offset + limit })} disabled={loading || offset + limit >= total}>
            Next
          </button>
        </span>
      )}
    </div>
  );
}
