from collections.abc import Callable
from typing import Any

from app.core.errors import AuthorizationError, ResourceNotFoundError
from app.core.identity import Principal
from app.modules.analysis.full_profile import FullDatasetProfiler
from app.modules.auth.repository import UserRepository
from app.modules.datasets.columnar import ColumnarDatasetStore
from app.modules.datasets.domain import DataAsset, SourceType
from app.modules.datasets.repository import DatasetRepository
from app.modules.datasets.schemas import TimeSeriesAnalysisRequest
from app.modules.datasets.temporary import TemporaryPipelineOutputResolver
from app.modules.datasets.time_series import FullDatasetTimeSeriesAnalyzer
from app.modules.sharing.domain import ResourceAccessRole, ResourceKind
from app.modules.sharing.postgres_access import access_policy


class DatasetAnalysisExecutor:
    """Recheck the submitting actor's access before scanning the pinned dataset."""

    def __init__(
        self,
        datasets: DatasetRepository,
        users: UserRepository,
        temporary_outputs: TemporaryPipelineOutputResolver,
    ) -> None:
        self.datasets = datasets
        self.users = users
        self.temporary_outputs = temporary_outputs
        store = ColumnarDatasetStore()
        self.profiler = FullDatasetProfiler(store)
        self.time_series = FullDatasetTimeSeriesAnalyzer(store)

    def profile(self, dataset_id: str, owner_id: str, options: dict, actor_id: str | None) -> dict[str, Any]:
        asset = self._authorized_asset(dataset_id, owner_id, actor_id or owner_id)
        return self.profiler.profile(asset, options, self._source_loader(owner_id))

    def analyze_time_series(
        self, dataset_id: str, owner_id: str, options: dict, actor_id: str | None
    ) -> dict[str, Any]:
        asset = self._authorized_asset(dataset_id, owner_id, actor_id or owner_id)
        request = TimeSeriesAnalysisRequest.model_validate(options)
        return self.time_series.analyze_asset(asset, request, self._source_loader(owner_id))

    def _authorized_asset(self, dataset_id: str, owner_id: str, actor_id: str) -> DataAsset:
        if self.temporary_outputs.recognizes(dataset_id):
            asset = self.temporary_outputs.resolve(dataset_id, owner_id)
        else:
            asset = self.datasets.get(dataset_id)
            if asset is None or asset.owner_id != owner_id:
                raise ResourceNotFoundError("Dataset not found")
        actor = self.users.get(actor_id)
        if actor is None or not actor.is_active:
            raise AuthorizationError("Dataset analysis actor is no longer active")
        principal = Principal(
            user_id=actor.id,
            email=actor.email,
            display_name=actor.display_name,
            login_name=actor.login_name,
            roles=actor.roles,
            session_version=actor.session_version,
        )
        access_policy.require_resource(
            principal,
            ResourceKind.DATA_VIEW if asset.source_type == SourceType.VIEW else ResourceKind.DATASET,
            asset.id,
            asset.owner_id,
            ResourceAccessRole.EDITOR,
        )
        return asset

    def _source_loader(self, owner_id: str) -> Callable[[str], DataAsset]:
        def load(asset_id: str) -> DataAsset:
            asset = self.datasets.get(asset_id)
            if asset is None or asset.owner_id != owner_id:
                raise ResourceNotFoundError("Data View source not found")
            return asset

        return load
