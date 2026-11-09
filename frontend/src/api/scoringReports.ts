import { request, withQuery } from "./http";
import type { OffsetPage, PageQuery } from "./pagination";
import type { DatasetLineageReference } from "./contracts/artifacts";
import type { ScoringReport } from "./contracts/scoringReports";

export const scoringReportsApi = {
  listScoringReports: (businessCaseId?: string) =>
    request<ScoringReport[]>(
      businessCaseId
        ? `/scoring-reports?business_case_id=${encodeURIComponent(businessCaseId)}`
        : "/scoring-reports"
    ),
  listScoringReportSummaries: (businessCaseId?: string) =>
    request<ScoringReport[]>(
      businessCaseId
        ? `/scoring-reports?business_case_id=${encodeURIComponent(businessCaseId)}&summary=true`
        : "/scoring-reports?summary=true"
    ),
  pageScoringReports: (
    query: PageQuery & {
      business_case_id?: string;
      problem_type?: string;
      pipeline_id?: string;
      pipeline_type?: string;
      sort_by?: "report" | "business_case" | "pipeline" | "problem" | "created" | "scope";
      sort_direction?: "asc" | "desc";
    } = {}
  ) => request<OffsetPage<{ latest: ScoringReport; version_count: number }>>(
    withQuery("/scoring-reports/page", query)
  ),
  listScoringReportVersions: (logicalId: string) =>
    request<ScoringReport[]>(`/scoring-reports/${encodeURIComponent(logicalId)}/versions?summary=true`),
  pageScoringReportVersions: (logicalId: string, query: PageQuery = {}) =>
    request<OffsetPage<ScoringReport>>(
      withQuery(`/scoring-reports/${encodeURIComponent(logicalId)}/versions/page`, {
        summary: true,
        ...query
      })
    ),
  getScoringReport: (reportId: string) =>
    request<ScoringReport>(`/scoring-reports/${encodeURIComponent(reportId)}`),
  getScoringReportDataLineage: (reportId: string) =>
    request<DatasetLineageReference[]>(`/scoring-reports/${encodeURIComponent(reportId)}/data-lineage`)
};
