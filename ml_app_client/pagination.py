"""Small helpers for consuming bounded offset-page contracts."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TypeVar

from .errors import ApiError
from .models import CatalogPage


T = TypeVar("T")


def iter_offset_items(
    fetch_page: Callable[[int, int], CatalogPage[T]],
    *,
    page_size: int = 100,
) -> Iterator[T]:
    """Yield a filtered result set without requesting one unbounded response."""
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between 1 and 100")
    offset = 0
    while True:
        page = fetch_page(page_size, offset)
        yield from page.items
        if not page.has_next:
            return
        if not page.items:
            raise ApiError("Paginated API returned has_next=true with an empty page")
        offset = page.offset + len(page.items)
