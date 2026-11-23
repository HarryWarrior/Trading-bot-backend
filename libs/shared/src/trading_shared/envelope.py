"""Standard response envelope and pagination contract (see .agents/rules/api-contracts.md)."""

from datetime import UTC, datetime
from math import ceil
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

DEFAULT_SUCCESS_MESSAGE = "Operation completed successfully"


class Pagination(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class Page(BaseModel, Generic[T]):
    items: list[T]
    pagination: Pagination


class Meta(BaseModel):
    timestamp: datetime
    version: str


class SuccessResponse(BaseModel, Generic[T]):
    success: Literal[True] = True
    data: T
    message: str = DEFAULT_SUCCESS_MESSAGE
    meta: Meta


class PageParams(BaseModel):
    """Query parameters every collection endpoint accepts."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: str | None = None
    sort_dir: Literal["asc", "desc"] = "desc"
    q: str | None = None


def build_pagination(page: int, page_size: int, total_items: int) -> Pagination:
    """Compute pagination metadata for a 1-indexed page."""
    total_pages = ceil(total_items / page_size) if total_items else 0
    return Pagination(
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


def ok(data: T, version: str, message: str = DEFAULT_SUCCESS_MESSAGE) -> SuccessResponse[T]:
    """Wrap ``data`` in the standard success envelope."""
    return SuccessResponse[T](
        data=data,
        message=message,
        meta=Meta(timestamp=datetime.now(UTC), version=version),
    )
