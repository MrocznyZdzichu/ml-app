"""Typed, immutable response models exposed by the ML App client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, Iterator, Mapping, TypeVar


T = TypeVar("T")


class ApiModel(Mapping[str, Any]):
    """Typed response model that remains compatible with legacy mapping access."""

    raw: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.raw)

    def __len__(self) -> int:
        return len(self.raw)


@dataclass(frozen=True)
class CatalogPage(Generic[T]):
    """One bounded catalog page together with the exact filtered total."""

    items: tuple[T, ...]
    total: int
    limit: int
    offset: int
    has_next: bool

    @classmethod
    def from_api(
        cls,
        value: Mapping[str, Any],
        decode: Callable[[Mapping[str, Any]], T],
    ) -> "CatalogPage[T]":
        return cls(
            items=tuple(decode(item) for item in value.get("items", [])),
            total=int(value.get("total", 0)),
            limit=int(value.get("limit", 0)),
            offset=int(value.get("offset", 0)),
            has_next=bool(value.get("has_next", False)),
        )


@dataclass(frozen=True)
class Dataset(ApiModel):
    id: str
    logical_id: str
    name: str
    version_number: int
    row_count: int | None
    format: str
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "Dataset":
        return cls(
            id=str(value["id"]),
            logical_id=str(value["logical_id"]),
            name=str(value["name"]),
            version_number=int(value["version_number"]),
            row_count=None if value.get("row_count") is None else int(value["row_count"]),
            format=str(value["format"]),
            raw=value,
        )


@dataclass(frozen=True)
class BusinessCase(ApiModel):
    """A visible Business Case and its lifecycle metadata."""

    id: str
    name: str
    description: str
    problem_type: str
    status: str
    owner_id: str
    access_role: str
    business_owner: str
    primary_metric: str
    target_column: str
    business_goal: str
    success_criteria: str
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "BusinessCase":
        return cls(
            id=str(value["id"]), name=str(value["name"]),
            description=str(value.get("description") or ""),
            problem_type=str(value.get("problem_type") or "custom"),
            status=str(value.get("status") or "draft"),
            owner_id=str(value.get("owner_id") or ""),
            access_role=str(value.get("access_role") or ""),
            business_owner=str(value.get("business_owner") or ""),
            primary_metric=str(value.get("primary_metric") or ""),
            target_column=str(value.get("target_column") or ""),
            business_goal=str(value.get("business_goal") or ""),
            success_criteria=str(value.get("success_criteria") or ""),
            raw=value,
        )


@dataclass(frozen=True)
class BusinessCaseCatalogEntry(ApiModel):
    """Minimal organization-wide Business Case directory entry."""

    id: str
    name: str
    status: str
    access_role: str
    request_status: str
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "BusinessCaseCatalogEntry":
        return cls(
            id=str(value["id"]), name=str(value["name"]),
            status=str(value.get("status") or ""),
            access_role=str(value.get("access_role") or ""),
            request_status=str(value.get("request_status") or ""), raw=value,
        )


@dataclass(frozen=True)
class BusinessCaseAccessRequest(ApiModel):
    """An auditable request for access to a Business Case."""

    id: str
    business_case_id: str
    status: str
    requested_role: str
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "BusinessCaseAccessRequest":
        return cls(
            id=str(value["id"]), business_case_id=str(value["business_case_id"]),
            status=str(value.get("status") or ""),
            requested_role=str(value.get("requested_role") or ""), raw=value,
        )


@dataclass(frozen=True)
class BusinessCaseDataAttachment(ApiModel):
    """A role-specific binding between a Business Case and immutable data."""

    id: str
    business_case_id: str
    data_asset_id: str
    role: str
    context_note: str
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "BusinessCaseDataAttachment":
        return cls(
            id=str(value["id"]), business_case_id=str(value.get("business_case_id") or ""),
            data_asset_id=str(value.get("data_asset_id") or ""), role=str(value.get("role") or ""),
            context_note=str(value.get("context_note") or ""), raw=value,
        )


@dataclass(frozen=True)
class PipelineRun:
    id: str
    pipeline_id: str
    pipeline_version_id: str
    status: str
    processed_row_count: int | None
    error_message: str
    raw: Mapping[str, Any]

    @property
    def finished(self) -> bool:
        return self.status in {"succeeded", "failed", "cancelled"}

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "PipelineRun":
        return cls(
            id=str(value["id"]),
            pipeline_id=str(value["pipeline_id"]),
            pipeline_version_id=str(value["pipeline_version_id"]),
            status=str(value["status"]),
            processed_row_count=(
                None if value.get("processed_row_count") is None
                else int(value["processed_row_count"])
            ),
            error_message=str(value.get("error_message") or ""),
            raw=value,
        )


@dataclass(frozen=True)
class Deployment:
    id: str
    name: str
    slug: str
    business_case_id: str
    status: str
    endpoint_url: str
    active_revision: Mapping[str, Any]
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "Deployment":
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            slug=str(value["slug"]),
            business_case_id=str(value["business_case_id"]),
            status=str(value["status"]),
            endpoint_url=str(value.get("endpoint_url") or ""),
            active_revision=dict(value.get("active_revision") or {}),
            raw=value,
        )


@dataclass(frozen=True)
class ModelServingUsage:
    model_id: str
    deployment_id: str
    deployment_name: str
    deployment_status: str
    revision_version: int
    role: str
    endpoint_url: str
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "ModelServingUsage":
        return cls(
            model_id=str(value["model_id"]),
            deployment_id=str(value["deployment_id"]),
            deployment_name=str(value["deployment_name"]),
            deployment_status=str(value["deployment_status"]),
            revision_version=int(value["revision_version"]),
            role=str(value["role"]),
            endpoint_url=str(value.get("endpoint_url") or ""),
            raw=value,
        )


@dataclass(frozen=True)
class PredictionResult:
    request_id: str
    deployment_id: str
    deployment_revision_id: str
    model_id: str
    served_role: str
    fallback_used: bool
    predictions: tuple[Mapping[str, Any], ...]
    warnings: tuple[str, ...]
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "PredictionResult":
        return cls(
            request_id=str(value["request_id"]),
            deployment_id=str(value["deployment_id"]),
            deployment_revision_id=str(value["deployment_revision_id"]),
            model_id=str(value["model_id"]),
            served_role=str(value["served_role"]),
            fallback_used=bool(value.get("fallback_used")),
            predictions=tuple(value.get("predictions") or ()),
            warnings=tuple(str(item) for item in value.get("warnings") or ()),
            raw=value,
        )


@dataclass(frozen=True)
class OnlineMonitoringRun:
    id: str
    deployment_id: str
    status: str
    since: str
    until: str
    actuals_dataset_id: str
    aggregation_granularity: str
    archived_at: str | None
    processed_request_count: int
    processed_row_count: int
    matched_row_count: int
    missing_actuals_count: int
    unmatched_actuals_count: int
    report: Mapping[str, Any]
    error_message: str
    raw: Mapping[str, Any]

    @property
    def finished(self) -> bool:
        return self.status in {"succeeded", "failed"}

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "OnlineMonitoringRun":
        return cls(
            id=str(value["id"]),
            deployment_id=str(value["deployment_id"]),
            status=str(value["status"]),
            since=str(value["since"]),
            until=str(value["until"]),
            actuals_dataset_id=str(value.get("actuals_dataset_id") or ""),
            aggregation_granularity=str(value.get("aggregation_granularity") or "none"),
            archived_at=(str(value["archived_at"]) if value.get("archived_at") else None),
            processed_request_count=int(value.get("processed_request_count") or 0),
            processed_row_count=int(value.get("processed_row_count") or 0),
            matched_row_count=int(value.get("matched_row_count") or 0),
            missing_actuals_count=int(value.get("missing_actuals_count") or 0),
            unmatched_actuals_count=int(value.get("unmatched_actuals_count") or 0),
            report=dict(value.get("report") or {}),
            error_message=str(value.get("error_message") or ""),
            raw=value,
        )
