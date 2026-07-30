import { request, withQuery } from "./http";
import type { OffsetPage, PageQuery } from "./pagination";
import type {
  ChallengerReplay,
  Deployment,
  DeploymentModelOption,
  DeploymentRevision,
  DeploymentRole,
  InferenceInputContract,
  InferencePage,
  InferenceSummaryPage,
  OnlineMonitoringBucketEvaluation,
  OnlineMonitoringRun,
  ScoreResponse
} from "./contracts/serving";

export const servingApi = {
  createDeployment: (payload: Record<string, unknown>) =>
    request<Deployment>("/serving/deployments", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listDeployments: (includeArchived = false) =>
    request<Deployment[]>(`/serving/deployments${includeArchived ? "?include_archived=true" : ""}`),
  pageDeployments: (
    query: PageQuery & {
      status?: string;
      business_case_id?: string;
      include_archived?: boolean;
    } = {}
  ) => request<OffsetPage<Deployment>>(withQuery("/serving/deployments/page", query)),
  getDeployment: (deploymentId: string) =>
    request<Deployment>(`/serving/deployments/${encodeURIComponent(deploymentId)}`),
  listDeploymentRevisions: (deploymentId: string) =>
    request<DeploymentRevision[]>(`/serving/deployments/${encodeURIComponent(deploymentId)}/revisions`),
  pageDeploymentRevisions: (deploymentId: string, query: PageQuery = {}) =>
    request<OffsetPage<DeploymentRevision>>(
      withQuery(`/serving/deployments/${encodeURIComponent(deploymentId)}/revisions/page`, query)
    ),
  createDeploymentRevision: (
    deploymentId: string,
    assignments: Array<{ model_id: string; role: DeploymentRole }>,
    reason: string
  ) =>
    request<DeploymentRevision>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/revisions`,
      {
        method: "POST",
        body: JSON.stringify({ assignments, reason })
      }
    ),
  setDeploymentStatus: (
    deploymentId: string,
    status: "running" | "stopped" | "archived",
    reason: string
  ) =>
    request<Deployment>(`/serving/deployments/${encodeURIComponent(deploymentId)}/status`, {
      method: "POST",
      body: JSON.stringify({ status, reason })
    }),
  rollbackDeployment: (deploymentId: string, revisionId: string, reason: string) =>
    request<DeploymentRevision>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/revisions/${encodeURIComponent(revisionId)}/rollback`,
      {
        method: "POST",
        body: JSON.stringify({ reason })
      }
    ),
  score: (
    deploymentId: string,
    instances: Array<{ record_id?: string; features: Record<string, unknown> }>,
    challengerModelId?: string
  ) =>
    request<ScoreResponse>(
      challengerModelId
        ? `/serving/deployments/${encodeURIComponent(deploymentId)}/challengers/${encodeURIComponent(challengerModelId)}/predictions`
        : `/serving/deployments/${encodeURIComponent(deploymentId)}/predictions`,
      {
        method: "POST",
        body: JSON.stringify({ instances })
      }
    ),
  deploymentInputContract: (deploymentId: string, challengerModelId?: string) => {
    const params = new URLSearchParams();
    if (challengerModelId) params.set("challenger_model_id", challengerModelId);
    const query = params.size ? `?${params}` : "";
    return request<InferenceInputContract>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/input-contract${query}`
    );
  },
  deploymentModelOptions: (deploymentId: string) =>
    request<DeploymentModelOption[]>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/model-options`
    ),
  pageDeploymentModelOptions: (
    deploymentId: string,
    query: PageQuery = {},
    modelIds: string[] = []
  ) => {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== "") params.set(key, String(value));
    });
    modelIds.forEach((modelId) => params.append("model_id", modelId));
    const suffix = params.size ? `?${params.toString()}` : "";
    return request<OffsetPage<DeploymentModelOption>>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/model-options/page${suffix}`
    );
  },
  inferenceLog: (deploymentId: string, limit = 50, cursor = "", recordId = "") => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    if (recordId) params.set("record_id", recordId);
    return request<InferencePage>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/inference-log?${params}`
    );
  },
  inferenceLogSummary: (deploymentId: string, limit = 50, cursor = "", recordId = "") => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    if (recordId) params.set("record_id", recordId);
    return request<InferenceSummaryPage>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/inference-log-summary?${params}`
    );
  },
  inferenceDetail: (deploymentId: string, requestId: string) =>
    request<Record<string, unknown>>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/inference-log/${encodeURIComponent(requestId)}`
    ),
  createChallengerReplay: (
    deploymentId: string,
    challengerModelId: string,
    maxRequests = 1000
  ) =>
    request<ChallengerReplay>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/challenger-replays`,
      {
        method: "POST",
        body: JSON.stringify({
          challenger_model_id: challengerModelId,
          max_requests: maxRequests
        })
      }
    ),
  listChallengerReplays: (deploymentId: string) =>
    request<ChallengerReplay[]>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/challenger-replays`
    ),
  pageChallengerReplays: (deploymentId: string, query: PageQuery = {}) =>
    request<OffsetPage<ChallengerReplay>>(
      withQuery(
        `/serving/deployments/${encodeURIComponent(deploymentId)}/challenger-replays/page`,
        query
      )
    ),
  createOnlineMonitoringRun: (
    deploymentId: string,
    payload: {
      since: string;
      until: string;
      actuals_dataset_id?: string;
      aggregation_granularity?: "none" | "hour" | "day" | "week" | "month";
      actuals_target_column?: string;
      join?: {
        strategy?: "auto" | "prediction_id" | "request_record_id" | "record_id";
        actuals_prediction_id_column?: string;
        actuals_request_id_column?: string;
        actuals_record_id_column?: string;
      };
    }
  ) =>
    request<OnlineMonitoringRun>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/monitoring-runs`,
      {
        method: "POST",
        body: JSON.stringify(payload)
      }
    ),
  listDeploymentMonitoringRuns: (
    deploymentId: string,
    limit = 100,
    includeArchived = false
  ) =>
    request<OnlineMonitoringRun[]>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/monitoring-runs?limit=${limit}&include_archived=${includeArchived}`
    ),
  pageDeploymentMonitoringRuns: (
    deploymentId: string,
    query: PageQuery & { include_archived?: boolean } = {}
  ) =>
    request<OffsetPage<OnlineMonitoringRun>>(
      withQuery(
        `/serving/deployments/${encodeURIComponent(deploymentId)}/monitoring-runs/page`,
        query
      )
    ),
  listOnlineMonitoringRuns: (limit = 200, includeArchived = false) =>
    request<OnlineMonitoringRun[]>(
      `/serving/monitoring-runs?limit=${limit}&include_archived=${includeArchived}`
    ),
  pageOnlineMonitoringRuns: (
    query: PageQuery & { include_archived?: boolean } = {}
  ) =>
    request<OffsetPage<OnlineMonitoringRun>>(
      withQuery("/serving/monitoring-runs/page", query)
    ),
  getOnlineMonitoringRun: (runId: string) =>
    request<OnlineMonitoringRun>(
      `/serving/monitoring-runs/${encodeURIComponent(runId)}`
    ),
  getOnlineMonitoringBucketEvaluations: (runId: string, bucketStarts: string[]) => {
    const params = new URLSearchParams();
    bucketStarts.forEach((value) => params.append("bucket_start", value));
    return request<OnlineMonitoringBucketEvaluation[]>(
      `/serving/monitoring-runs/${encodeURIComponent(runId)}/bucket-evaluations?${params}`
    );
  },
  archiveOnlineMonitoringRun: (
    runId: string,
    reason = "Archived from monitoring history"
  ) =>
    request<OnlineMonitoringRun>(
      `/serving/monitoring-runs/${encodeURIComponent(runId)}/archive`,
      {
        method: "POST",
        body: JSON.stringify({ reason })
      }
    ),
  archiveDeploymentMonitoringHistory: (
    deploymentId: string,
    reason = "Archived from monitoring history"
  ) =>
    request<{ archived_run_count: number }>(
      `/serving/deployments/${encodeURIComponent(deploymentId)}/monitoring-runs/archive`,
      {
        method: "POST",
        body: JSON.stringify({ reason })
      }
    )
};
