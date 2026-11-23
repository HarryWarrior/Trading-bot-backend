"""FastAPI-specific helpers. Inbound adapters only — application code imports ``envelope`` instead."""

from typing import Literal

from fastapi import Query

from trading_shared.envelope import PageParams


def page_params(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str | None = Query(default=None),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    q: str | None = Query(default=None),
) -> PageParams:
    """FastAPI dependency: validates pagination query params (422 on violation).

    Use ``params: PageParams = Depends(page_params)``; a bare ``Depends()`` on the model
    does not enforce the limits at the query level.
    """
    return PageParams(page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir, q=q)
