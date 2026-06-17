from typing import Protocol

from app.modules.sharing.domain import ShareGrant


class SharingRepository(Protocol):
    def add(self, grant: ShareGrant) -> ShareGrant:
        ...

    def list_for_owner(self, owner_id: str) -> list[ShareGrant]:
        ...


class InMemorySharingRepository:
    def __init__(self) -> None:
        self._items: dict[str, ShareGrant] = {}

    def add(self, grant: ShareGrant) -> ShareGrant:
        self._items[grant.id] = grant
        return grant

    def list_for_owner(self, owner_id: str) -> list[ShareGrant]:
        return [grant for grant in self._items.values() if grant.owner_id == owner_id]
