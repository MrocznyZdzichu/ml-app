from uuid import uuid4

from fastapi import HTTPException, status

from app.core.security import Principal
from app.modules.serving.domain import BatchScoreJob, Deployment, DeploymentStatus
from app.modules.serving.repository import InMemoryServingRepository, ServingRepository
from app.modules.serving.schemas import BatchScoreRequest, DeploymentCreate, ScoreResponse
from app.modules.models.service import ModelService
from app.modules.sharing.domain import BC_ROLE_RANK, BusinessCaseAccessRole
from app.modules.sharing.policy import access_policy


class ServingService:
    def __init__(self, repository: ServingRepository | None = None) -> None:
        self.repository = repository or InMemoryServingRepository()
        self.models = ModelService()

    def create_deployment(self, payload: DeploymentCreate, principal: Principal) -> Deployment:
        model = self.models.get_model(payload.model_id, principal)
        if not model.business_case_id:
            raise HTTPException(status_code=409, detail="Deployment requires a Business Case model")
        access_policy.require_business_case(principal, model.business_case_id, BusinessCaseAccessRole.CONTRIBUTOR)
        deployment_id = str(uuid4())
        deployment = Deployment(
            id=deployment_id,
            owner_id=model.owner_id,
            model_id=payload.model_id,
            name=payload.name,
            image=payload.image,
            business_case_id=model.business_case_id,
            endpoint_url=f"http://model-runtime-{deployment_id}:8000",
            status=DeploymentStatus.REQUESTED,
            environment=dict(payload.environment),
        )
        return self.repository.add_deployment(deployment)

    def list_deployments(self, principal: Principal) -> list[Deployment]:
        return [deployment for deployment in self.repository.list_all_deployments()
                if deployment.business_case_id and (
                    (role := access_policy.business_case_role(principal, deployment.business_case_id)) is not None
                    and BC_ROLE_RANK[role] >= BC_ROLE_RANK[BusinessCaseAccessRole.READER]
                )]

    def get_deployment(self, deployment_id: str, principal: Principal) -> Deployment:
        deployment = self.repository.get_deployment(deployment_id)
        if not deployment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
        access_policy.require_business_case(principal, deployment.business_case_id, BusinessCaseAccessRole.READER)
        return deployment

    def score(
        self,
        deployment_id: str,
        records: list[dict],
        principal: Principal,
    ) -> ScoreResponse:
        deployment = self.get_deployment(deployment_id, principal)
        access_policy.require_business_case(principal, deployment.business_case_id, BusinessCaseAccessRole.CONTRIBUTOR)
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
        deployment = self.get_deployment(deployment_id, principal)
        access_policy.require_business_case(principal, deployment.business_case_id, BusinessCaseAccessRole.CONTRIBUTOR)
        job = BatchScoreJob(
            id=str(uuid4()),
            owner_id=deployment.owner_id,
            deployment_id=deployment_id,
            input_uri=payload.input_uri,
            business_case_id=deployment.business_case_id,
            output_uri=payload.output_uri,
            options=dict(payload.options),
        )
        return self.repository.add_batch_job(job)

    def list_batch_jobs(self, principal: Principal) -> list[BatchScoreJob]:
        return [job for deployment in self.list_deployments(principal)
                for job in self.repository.list_batch_jobs(deployment.owner_id)
                if job.deployment_id == deployment.id]
