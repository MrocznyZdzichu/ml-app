import { useEffect, useState } from "react";

import { datasetsApi } from "../../api/datasets";
import type { DataAsset } from "../../api/contracts/datasets";
import type { OffsetPage } from "../../api/pagination";

type Query = NonNullable<Parameters<typeof datasetsApi.pageDatasets>[0]>;

export function useDatasetCatalogPage(query: Query, refreshKey: number, setNotice: (message: string) => void) {
  const [page, setPage] = useState<OffsetPage<DataAsset> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    setLoading(true);
    datasetsApi.pageDatasets(query, signal)
      .then((result) => { if (!signal.aborted) setPage(result); })
      .catch((error) => {
        if (!signal.aborted) {
          setNotice(error instanceof Error ? error.message : "Could not load dataset catalog");
        }
      })
      .finally(() => { if (!signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [query, refreshKey, setNotice]);

  return { page, loading };
}
