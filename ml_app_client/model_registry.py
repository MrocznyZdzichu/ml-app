"""Model registry lookup and lifecycle-stage workflows."""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import quote

from .errors import ResourceAmbiguousError, ResourceNotFoundError
from .models import CatalogPage, PipelineRun
from .pagination import iter_offset_items
from .resolution import _friendly_name_key, _model_stage, _named_candidates
from .transport import TransportClientMixin


class ModelRegistryClientMixin(TransportClientMixin):
    """Model registry operations composed into :class:`MLAppClient`."""

    def list_models(self) -> list[Mapping[str, Any]]:
        """List model versions visible through the current Business Case grants."""
        return self._request("GET", "/models")

    def list_model_summaries(self) -> list[Mapping[str, Any]]:
        """List model registry/workflow fields without experiment-heavy payloads."""
        return self._request("GET", "/models", params={"summary": True})

    def page_models(
        self,
        *,
        limit: int = 30,
        offset: int = 0,
        search: str = "",
        business_case_id: str = "",
        stage: str = "",
        pipeline_id: str = "",
    ) -> CatalogPage[Mapping[str, Any]]:
        """Search latest model families and retain their server-side version counts."""
        payload = self._request("GET", "/models/page", params={
            "limit": limit,
            "offset": offset,
            "search": search,
            "business_case_id": business_case_id,
            "stage": stage,
            "pipeline_id": pipeline_id,
        })
        return CatalogPage.from_api(payload, lambda item: item)

    def model_by_name(
        self,
        *,
        business_case_name: str,
        model_name: str,
        version: str | int | None = None,
    ) -> Mapping[str, Any]:
        """Resolve an immutable model version by its user-facing coordinates.

        The newest visible version is returned when ``version`` is omitted. Pass
        ``version="v3"`` or ``version=3`` when a workflow must pin an older
        version explicitly.
        """
        business_case = self.business_case_by_name(business_case_name)
        candidates = self._model_family_candidates(
            model_name,
            business_case_id=str(business_case["id"]),
        )
        matches = _named_candidates(candidates, model_name)
        logical_ids = {
            str(item.get("logical_id") or item.get("id") or "")
            for item in matches
        }
        if len(logical_ids) > 1:
            choices = ", ".join(
                f"{item.get('name')} {item.get('version')} ({item.get('id')})"
                for item in matches[:8]
            )
            raise ResourceAmbiguousError(
                f"Model {model_name!r} is ambiguous in Business Case "
                f"{business_case_name!r}; candidates: {choices}"
            )
        if version is not None and len(logical_ids) == 1:
            logical_id = next(iter(logical_ids))
            if any(item.get("logical_id") for item in matches):
                matches = _named_candidates(
                    list(iter_offset_items(
                        lambda limit, offset: self.page_model_versions(
                            logical_id,
                            limit=limit,
                            offset=offset,
                        )
                    )),
                    model_name,
                )
            else:
                matches = _named_candidates(
                    [
                        item for item in self.list_models()
                        if str(item.get("business_case_id") or "")
                        == str(business_case["id"])
                    ],
                    model_name,
                )
        if version is not None:
            normalized_version = str(version).strip().casefold()
            if normalized_version.isdigit():
                normalized_version = f"v{normalized_version}"
            matches = [
                item for item in matches
                if str(item.get("version") or "").casefold() == normalized_version
                or str(item.get("version_number") or "") == str(version)
            ]
        if not matches:
            suffix = "" if version is None else f" version {version!r}"
            raise ResourceNotFoundError(
                f"Model {model_name!r}{suffix} was not found in Business Case "
                f"{business_case_name!r}"
            )
        return max(matches, key=lambda item: int(item.get("version_number") or 0))

    def model_for_pipeline_run(self, run: str | PipelineRun) -> Mapping[str, Any]:
        """Resolve the single immutable model artifact created by a pipeline run."""
        run_id = run.id if isinstance(run, PipelineRun) else run
        matches = [
            item for item in self.list_models()
            if str(item.get("pipeline_run_id") or "") == run_id
        ]
        if not matches:
            raise ResourceNotFoundError(
                f"Pipeline run {run_id!r} did not create a visible model artifact"
            )
        if len(matches) > 1:
            raise ResourceAmbiguousError(
                f"Pipeline run {run_id!r} created {len(matches)} model artifacts"
            )
        return matches[0]

    def list_model_versions(self, logical_model_id: str) -> list[Mapping[str, Any]]:
        """List the complete version history of one logical model family."""
        path = f"/models/{quote(logical_model_id, safe='')}/versions"
        return self._request("GET", path)

    def page_model_versions(
        self,
        logical_model_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> CatalogPage[Mapping[str, Any]]:
        """Browse one logical model family with a bounded response."""
        payload = self._request(
            "GET",
            f"/models/{quote(logical_model_id, safe='')}/versions/page",
            params={"limit": limit, "offset": offset},
        )
        return CatalogPage.from_api(payload, lambda item: item)

    def promote_model(
        self,
        model: str,
        stage: str,
        *,
        version: str | int | None = None,
    ) -> Mapping[str, Any]:
        """Change a model version lifecycle stage using an ID or friendly name.

        When ``model`` is a name, the newest version is selected by default.
        Pass ``version="v5"`` or ``version=5`` to choose an explicit version.
        """
        stage = _model_stage(stage)
        matches, resolved_by_id = self._resolve_model_reference(model)
        if not matches:
            suffix = "" if version is None else f" version {version!r}"
            raise ResourceNotFoundError(f"Model {model!r}{suffix} was not found")

        matching_families = {
            str(item.get("logical_id") or _friendly_name_key(str(item.get("name") or "")))
            for item in matches
        }
        if len(matching_families) > 1:
            candidates = ", ".join(
                f"{item.get('name')} {item.get('version') or 'v' + str(item.get('version_number'))} ({item.get('id')})"
                for item in matches[:8]
            )
            raise ResourceAmbiguousError(
                f"Model {model!r} is ambiguous; use an exact model ID. Candidates: {candidates}"
            )

        logical_ids = {
            str(item["logical_id"])
            for item in matches
            if item.get("logical_id")
        }
        if not resolved_by_id and len(logical_ids) == 1:
            matches = self._model_family_versions(next(iter(logical_ids)))
        elif not resolved_by_id and not logical_ids and version is not None:
            matches = _named_candidates(self.list_models(), model)
        available_versions = matches
        if version is not None:
            normalized_version = str(version).strip().casefold()
            if normalized_version.isdigit():
                normalized_version = f"v{normalized_version}"
            matches = [
                item for item in matches
                if str(item.get("version") or "").casefold() == normalized_version
                or str(item.get("version_number") or "") == str(version)
            ]
        if not matches:
            suffix = "" if version is None else f" version {version!r}"
            available_versions = (
                self._model_family_versions(next(iter(logical_ids)))
                if resolved_by_id and len(logical_ids) == 1
                else available_versions
            )
            if available_versions:
                available = ", ".join(sorted({
                    str(item.get("version") or f"v{item.get('version_number')}")
                    for item in available_versions
                }))
                raise ResourceNotFoundError(
                    f"Model {model!r}{suffix} was not found; available versions: {available}"
                )
            raise ResourceNotFoundError(f"Model {model!r}{suffix} was not found")
        if version is not None and len(matches) > 1:
            candidates = ", ".join(
                f"{item.get('name')} {item.get('version') or 'v' + str(item.get('version_number'))} ({item.get('id')})"
                for item in matches[:8]
            )
            raise ResourceAmbiguousError(
                f"Model {model!r} is ambiguous; use an exact model ID. Candidates: {candidates}"
            )
        selected = max(matches, key=lambda item: int(item.get("version_number") or 0))
        return self._request(
            "PATCH",
            f"/models/{selected['id']}/stage",
            json={"stage": stage},
        )

    def promote_model_versions(
        self,
        model: str,
        stage: str,
        *,
        versions: list[str | int] | tuple[str | int, ...],
    ) -> list[Mapping[str, Any]]:
        """Change several versions in one family without repeatedly resolving it.

        Every version still uses the standard audited stage-change endpoint. The
        optimization only removes redundant registry and family-history reads.
        Results preserve the order supplied in ``versions``.
        """
        stage = _model_stage(stage)
        requested = list(versions)
        if not requested:
            raise ValueError("versions must contain at least one model version")

        matches, _ = self._resolve_model_reference(model)
        if not matches:
            raise ResourceNotFoundError(f"Model {model!r} was not found")
        family_ids = {
            str(item.get("logical_id") or _friendly_name_key(str(item.get("name") or "")))
            for item in matches
        }
        if len(family_ids) > 1:
            candidates = ", ".join(
                f"{item.get('name')} {item.get('version') or 'v' + str(item.get('version_number'))} ({item.get('id')})"
                for item in matches[:8]
            )
            raise ResourceAmbiguousError(
                f"Model {model!r} is ambiguous; use an exact model ID. Candidates: {candidates}"
            )

        logical_ids = {str(item["logical_id"]) for item in matches if item.get("logical_id")}
        family = (
            self._model_family_versions(next(iter(logical_ids)))
            if len(logical_ids) == 1
            else _named_candidates(self.list_models(), model)
        )
        by_version: dict[str, list[Mapping[str, Any]]] = {}
        for item in family:
            labels = {
                str(item.get("version") or "").strip().casefold(),
                str(item.get("version_number") or "").strip().casefold(),
            }
            for label in labels:
                if label:
                    by_version.setdefault(label, []).append(item)
                    if label.isdigit():
                        by_version.setdefault(f"v{label}", []).append(item)

        selected: list[Mapping[str, Any]] = []
        missing: list[str] = []
        for version in requested:
            normalized = str(version).strip().casefold()
            if normalized.isdigit():
                normalized = f"v{normalized}"
            candidates = {
                str(item.get("id")): item for item in by_version.get(normalized, [])
            }
            if not candidates:
                missing.append(str(version))
                continue
            if len(candidates) > 1:
                raise ResourceAmbiguousError(
                    f"Model {model!r} version {version!r} is ambiguous; use exact model IDs"
                )
            selected.append(next(iter(candidates.values())))
        if missing:
            available = ", ".join(
                str(item.get("version") or f"v{item.get('version_number')}")
                for item in family
            )
            raise ResourceNotFoundError(
                f"Model {model!r} versions {', '.join(missing)} were not found; "
                f"available versions: {available}"
            )

        return [
            self._request(
                "PATCH",
                f"/models/{item['id']}/stage",
                json={"stage": stage},
            )
            for item in selected
        ]

    def _model_family_candidates(
        self,
        name: str,
        *,
        business_case_id: str = "",
        stage: str = "",
    ) -> list[Mapping[str, Any]]:
        normalized = _friendly_name_key(name)
        tokens = normalized.split()
        search = max(tokens, key=len) if tokens else name
        families = iter_offset_items(
            lambda limit, offset: self.page_models(
                limit=limit,
                offset=offset,
                search=search,
                business_case_id=business_case_id,
                stage=stage,
            )
        )
        latest_models: list[Mapping[str, Any]] = []
        for family in families:
            latest = family.get("latest") if isinstance(family, Mapping) else None
            if isinstance(latest, Mapping):
                latest_models.append(latest)
        return latest_models

    def _model_family_versions(
        self,
        logical_model_id: str,
    ) -> list[Mapping[str, Any]]:
        return list(iter_offset_items(
            lambda limit, offset: self.page_model_versions(
                logical_model_id,
                limit=limit,
                offset=offset,
            )
        ))

    def _resolve_model_reference(
        self,
        model: str,
    ) -> tuple[list[Mapping[str, Any]], bool]:
        candidates = self._model_family_candidates(model)
        matches = _named_candidates(candidates, model)
        if matches:
            return matches, False
        try:
            direct = self._request(
                "GET",
                f"/models/{quote(model, safe='')}",
            )
        except ResourceNotFoundError:
            return [], False
        return [direct], True
