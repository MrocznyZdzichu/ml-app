import { request } from "./http";
import type { AnalysisJob } from "./contracts/analysis";

export const analysisApi = {
  createAnalysis: (payload: Record<string, unknown>) =>
    request<AnalysisJob>("/analysis", { method: "POST", body: JSON.stringify(payload) }),
  describeRecords: (records: Array<Record<string, unknown>>) =>
    request<Record<string, unknown>>("/analysis/descriptive-stats", {
      method: "POST",
      body: JSON.stringify({ records })
    })
};
