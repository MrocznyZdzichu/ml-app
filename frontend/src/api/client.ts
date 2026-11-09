import { analysisApi } from "./analysis";
import { authApi } from "./auth";
import { businessCasesApi } from "./businessCases";
import { datasetsApi } from "./datasets";
import { modelsApi } from "./models";
import { pipelinesApi } from "./pipelines";
import { scoringReportsApi } from "./scoringReports";
import { servingApi } from "./serving";
import { sharingApi } from "./sharing";
import { usersApi } from "./users";

export { getAccessToken, setAccessToken } from "./http";
export type { OffsetPage, PageQuery } from "./pagination";
export type { ModelEvaluationMetric, ModelEvaluationSnapshot } from "./contracts/modelEvaluation";
export type {
  BusinessCaseAccessRequest,
  BusinessCaseAccessRole,
  BusinessCaseCatalogEntry
} from "./contracts/businessCaseAccess";
export type { CreatedPersonalAccessToken, PersonalAccessToken } from "./contracts/personalAccessToken";
export type {
  ChallengerReplay,
  Deployment,
  DeploymentModelOption,
  DeploymentRevision,
  DeploymentRole,
  InferenceInputContract,
  InferenceInputField,
  InferencePage,
  InferenceRequest,
  InferenceRequestSummary,
  InferenceSummaryPage,
  ModelServingUsage,
  OnlineMonitoringBucketEvaluation,
  OnlineMonitoringRun,
  ScoreResponse
} from "./contracts/serving";
export { temporaryPipelineOutputId } from "./datasets";
export type * from "./contracts/analysis";
export type * from "./contracts/artifacts";
export type * from "./contracts/auth";
export type * from "./contracts/businessCases";
export type * from "./contracts/datasets";
export type * from "./contracts/models";
export type * from "./contracts/pipelines";
export type * from "./contracts/scoringReports";
export type * from "./contracts/sharing";

export const api = {
  ...analysisApi,
  ...authApi,
  ...businessCasesApi,
  ...datasetsApi,
  ...modelsApi,
  ...pipelinesApi,
  ...scoringReportsApi,
  ...servingApi,
  ...sharingApi,
  ...usersApi,
};
