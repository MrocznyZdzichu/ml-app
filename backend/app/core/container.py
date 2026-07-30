from functools import cached_property, lru_cache

from app.core.database import get_engine
from app.modules.analysis.repository import InMemoryAnalysisRepository
from app.modules.analysis.service import AnalysisService
from app.modules.auth.api_credentials import ApiCredentialRepository, ApiCredentialService
from app.modules.auth.repository import PostgresUserRepository
from app.modules.auth.service import AuthService
from app.modules.business_cases.repository import PostgresBusinessCaseRepository
from app.modules.business_cases.service import BusinessCaseService
from app.modules.datasets.repository import PostgresDatasetRepository
from app.modules.datasets.service import DatasetService
from app.modules.datasets.temporary import TemporaryPipelineOutputResolver
from app.modules.exports.repository import InMemoryExportRepository
from app.modules.exports.service import ExportService
from app.modules.models.repository import InMemoryModelRepository
from app.modules.models.service import ModelService
from app.modules.pipelines.repository import PostgresPipelineRepository
from app.modules.pipelines.run_preview import PipelineRunOutputReader
from app.modules.pipelines.service import PipelineService
from app.modules.scoring_reports.service import ScoringReportService
from app.modules.serving.monitoring import OnlineMonitoringService
from app.modules.serving.repository import PostgresServingRepository
from app.modules.serving.runtime import HttpModelRuntimeGateway
from app.modules.serving.service import ServingService
from app.modules.sharing.repository import PostgresSharingRepository
from app.modules.sharing.service import SharingService
from app.modules.users.service import UserAdministrationService
from app.worker.task_queue import CeleryTaskQueue


class ApplicationContainer:
    """Single composition root for HTTP-facing application services."""

    def __init__(self) -> None:
        engine = get_engine()
        self.task_queue = CeleryTaskQueue()
        self.users = PostgresUserRepository(engine)
        self.sharing_repository = PostgresSharingRepository(engine)
        self.business_case_repository = PostgresBusinessCaseRepository(engine)
        self.dataset_repository = PostgresDatasetRepository(engine)
        self.pipeline_repository = PostgresPipelineRepository(engine)
        self.serving_repository = PostgresServingRepository(engine)

    @cached_property
    def auth(self) -> AuthService:
        return AuthService(self.users, self.sharing_repository)

    @cached_property
    def api_credentials(self) -> ApiCredentialService:
        return ApiCredentialService(
            ApiCredentialRepository(self.users.engine),
            self.sharing_repository,
        )

    @cached_property
    def user_administration(self) -> UserAdministrationService:
        return UserAdministrationService(self.users, self.sharing_repository)

    @cached_property
    def sharing(self) -> SharingService:
        return SharingService(self.sharing_repository)

    @cached_property
    def business_cases(self) -> BusinessCaseService:
        return BusinessCaseService(
            self.business_case_repository,
            self.users,
            self.dataset_repository,
            self.sharing_repository,
        )

    @cached_property
    def datasets(self) -> DatasetService:
        output_reader = PipelineRunOutputReader()
        return DatasetService(
            self.dataset_repository,
            TemporaryPipelineOutputResolver(self.pipeline_repository, output_reader),
            self.task_queue,
        )

    @cached_property
    def pipelines(self) -> PipelineService:
        return PipelineService(
            repository=self.pipeline_repository,
            business_cases=self.business_cases,
            output_reader=PipelineRunOutputReader(),
            datasets=self.dataset_repository,
            artifacts=self.business_case_repository,
            task_queue=self.task_queue,
        )

    @cached_property
    def models(self) -> ModelService:
        return ModelService(
            repository=InMemoryModelRepository(),
            artifacts=self.business_case_repository,
            pipelines=self.pipeline_repository,
            datasets=self.dataset_repository,
            serving_repository=self.serving_repository,
            audit_repository=self.sharing_repository,
        )

    @cached_property
    def scoring_reports(self) -> ScoringReportService:
        return ScoringReportService(self.business_case_repository)

    @cached_property
    def serving(self) -> ServingService:
        return ServingService(
            repository=self.serving_repository,
            runtime=HttpModelRuntimeGateway(),
            models=self.models,
            task_queue=self.task_queue,
            users=self.users,
            audit_repository=self.sharing_repository,
        )

    @cached_property
    def online_monitoring(self) -> OnlineMonitoringService:
        return OnlineMonitoringService(
            repository=self.serving_repository,
            datasets=self.datasets,
            models=self.models,
            task_queue=self.task_queue,
            dataset_repository=self.dataset_repository,
            business_cases=self.business_case_repository,
            sharing_repository=self.sharing_repository,
            users=self.users,
        )

    @cached_property
    def analysis(self) -> AnalysisService:
        return AnalysisService(
            InMemoryAnalysisRepository(),
            self.dataset_repository,
        )

    @cached_property
    def exports(self) -> ExportService:
        return ExportService(
            InMemoryExportRepository(),
            self.dataset_repository,
            self.models,
        )


@lru_cache(maxsize=1)
def get_container() -> ApplicationContainer:
    return ApplicationContainer()
