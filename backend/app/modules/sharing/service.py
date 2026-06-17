from uuid import uuid4

from app.core.security import Principal
from app.modules.sharing.domain import ShareGrant
from app.modules.sharing.repository import InMemorySharingRepository, SharingRepository
from app.modules.sharing.schemas import ShareGrantCreate


class SharingService:
    def __init__(self, repository: SharingRepository | None = None) -> None:
        self.repository = repository or InMemorySharingRepository()

    def share(self, payload: ShareGrantCreate, principal: Principal) -> ShareGrant:
        grant = ShareGrant(
            id=str(uuid4()),
            owner_id=principal.user_id,
            target_user_id=payload.target_user_id,
            resource_kind=payload.resource_kind,
            resource_id=payload.resource_id,
            permission=payload.permission,
        )
        return self.repository.add(grant)

    def list_grants(self, principal: Principal) -> list[ShareGrant]:
        return self.repository.list_for_owner(principal.user_id)
