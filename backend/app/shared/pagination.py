from typing import Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class OffsetPage(BaseModel, Generic[T]):
    """Stable offset-page contract for bounded catalog reads."""

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    has_next: bool

    @classmethod
    def build(
        cls,
        items: list[T],
        *,
        total: int,
        limit: int,
        offset: int,
    ) -> "OffsetPage[T]":
        return cls(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_next=offset + len(items) < total,
        )
