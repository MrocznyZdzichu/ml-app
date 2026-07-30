"""Scoring and monitoring report lookup workflows."""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import quote

from .errors import ApiError
from .models import CatalogPage, PipelineRun
from .transport import TransportClientMixin


class ScoringReportClientMixin(TransportClientMixin):
    """Scoring report operations composed into :class:`MLAppClient`."""

    def scoring_report_for_run(
        self,
        run: PipelineRun,
        *,
        business_case_name: str,
    ) -> Mapping[str, Any]:
        """Fetch the report artifact created by a completed scoring or monitoring run."""
        business_case = self._business_case_by_name(business_case_name)
        reports = self._request(
            "GET", "/scoring-reports", params={"business_case_id": business_case["id"]}
        )
        matches = [
            report for report in reports
            if isinstance(report, Mapping) and report.get("pipeline_run_id") == run.id
        ]
        if len(matches) != 1:
            raise ApiError(
                f"Pipeline run {run.id} has {len(matches)} scoring report artifacts; expected one"
            )
        return matches[0]

    def list_scoring_report_summaries(
        self,
        *,
        business_case_id: str | None = None,
    ) -> list[Mapping[str, Any]]:
        """List scoring report catalog fields without full evaluation payloads."""
        params: dict[str, Any] = {"summary": True}
        if business_case_id is not None:
            params["business_case_id"] = business_case_id
        return self._request("GET", "/scoring-reports", params=params)

    def page_scoring_reports(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        business_case_id: str = "",
        problem_type: str = "",
        pipeline_id: str = "",
    ) -> CatalogPage[Mapping[str, Any]]:
        """Search immutable report families using the same bounded API as the UI."""
        payload = self._request("GET", "/scoring-reports/page", params={
            "limit": limit,
            "offset": offset,
            "search": search,
            "business_case_id": business_case_id,
            "problem_type": problem_type,
            "pipeline_id": pipeline_id,
        })
        return CatalogPage.from_api(payload, lambda item: item)

    def get_scoring_report(self, report_id: str) -> Mapping[str, Any]:
        """Fetch one complete immutable scoring report."""
        return self._request("GET", f"/scoring-reports/{report_id}")

    def page_scoring_report_versions(
        self,
        logical_report_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> CatalogPage[Mapping[str, Any]]:
        """Browse summary metadata for one immutable scoring-report family."""
        payload = self._request(
            "GET",
            f"/scoring-reports/{quote(logical_report_id, safe='')}/versions/page",
            params={"limit": limit, "offset": offset, "summary": "true"},
        )
        return CatalogPage.from_api(payload, lambda item: item)
