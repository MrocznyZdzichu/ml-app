import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { DatasetVisualization, DatasetVisualizationRequest } from "../api/client";

const QUERY_DEBOUNCE_MS = 180;

type VisualizationQueryState = {
  result: DatasetVisualization | null;
  loading: boolean;
  error: string;
};

export function useVisualizationResult(datasetId: string, request: DatasetVisualizationRequest): VisualizationQueryState {
  const [result, setResult] = useState<DatasetVisualization | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError("");

    const timeout = window.setTimeout(() => {
      api.visualizeDataset(datasetId, request, controller.signal)
        .then((nextResult) => {
          if (active) setResult(nextResult);
        })
        .catch((reason: unknown) => {
          if (!active || isAbortError(reason)) return;
          setError(reason instanceof Error ? reason.message : "Visualization query failed");
          setResult(null);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, QUERY_DEBOUNCE_MS);

    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [datasetId, request]);

  return { result, loading, error };
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}
