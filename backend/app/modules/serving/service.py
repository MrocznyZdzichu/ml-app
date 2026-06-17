from uuid import uuid4

from fastapi import HTTPException, status

from app.core.security import Principal
from app.modules.serving.domain import BatchScoreJob, Deployment, DeploymentStatus
from app.modules.serving.repository import InMemoryServingRepository, ServingRepository
from app.modules.serving.schemas import BatchScoreRequest, DeploymentCreate, ScoreResponse


class ServingService:
    def __init__(self, repository: ServingRepository | None = None) -> None:
        self.repository = repository or InMemoryServingRepository()

    def create_deployment(self, payload: DeploymentCreate, principal: Principal) -> Deployment:
        deployment_id = str(uuid4())
        deployment = Deployment(
            id=deployment_id,
            owner_id=principal.user_id,
            model_id=payload.model_id,
            name=payload.name,
            image=payload.image,
            endpoint_url=f"http://model-runtime-{deployment_id}:8000",
            status=DeploymentStatus.REQUESTED,
            environment=dict(payload.environment),
        )
        return self.repository.add_deployment(deployment)

    def list_deployments(self, principal: Principal) -> list[Deployment]:
        return self.repository.list_deployments(principal.user_id)

    def get_deployment(self, deployment_id: str, principal: Principal) -> Deployment:
        deployment = self.repository.get_deployment(deployment_id)
        if not deployment or deployment.owner_id != principal.user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
        return deployment

    def score(
        self,
        deployment_id: str,
        records: list[dict],
        principal: Principal,
    ) -> ScoreResponse:
        self.get_deployment(deployment_id, principal)
        predictions = [
            {
                "row": index,
                "prediction": 0.0,
                "explanation": "placeholder scorer; wire to model runtime next",
            }
            for index, _record in enumerate(records)
        ]
        return ScoreResponse(deployment_id=deployment_id, predictions=predictions)

    def enqueue_batch_score(
        self,
        deployment_id: str,
        payload: BatchScoreRequest,
        principal: Principal,
    ) -> BatchScoreJob:
        self.get_deployment(deployment_id, principal)
        job = BatchScoreJob(
            id=str(uuid4()),
            owner_id=principal.user_id,
            deployment_id=deployment_id,
            input_uri=payload.input_uri,
            output_uri=payload.output_uri,
            options=dict(payload.options),
        )
        return self.repository.add_batch_job(job)

    def list_batch_jobs(self, principal: Principal) -> list[BatchScoreJob]:
        return self.repository.list_batch_jobs(principal.user_id)
