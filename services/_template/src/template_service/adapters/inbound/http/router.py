from fastapi import APIRouter, Depends, status

from template_service.adapters.inbound.http.dependencies import get_container, get_current_user_id
from template_service.adapters.inbound.http.schemas import CreateItemRequest, ItemOut
from template_service.bootstrap import Container
from template_service.domain.errors import DomainError
from trading_shared.envelope import (
    Page,
    PageParams,
    SuccessResponse,
    build_pagination,
    ok,
    page_params,
)
from trading_shared.errors import AppError

router = APIRouter(prefix="/api/v1/template", tags=["template"])


@router.post("/items", status_code=status.HTTP_201_CREATED, response_model=SuccessResponse[ItemOut])
async def create_item(
    body: CreateItemRequest,
    user_id: str = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> SuccessResponse[ItemOut]:
    try:
        item = await container.create_item.execute(user_id, body.name)
    except DomainError as exc:
        raise AppError(exc.code, str(exc), 400) from exc
    return ok(ItemOut.from_domain(item), container.settings.version, "Item created")


@router.get("/items", response_model=SuccessResponse[Page[ItemOut]])
async def list_items(
    params: PageParams = Depends(page_params),
    user_id: str = Depends(get_current_user_id),
    container: Container = Depends(get_container),
) -> SuccessResponse[Page[ItemOut]]:
    items, total = await container.list_items.execute(user_id, params)
    page = Page[ItemOut](
        items=[ItemOut.from_domain(item) for item in items],
        pagination=build_pagination(params.page, params.page_size, total),
    )
    return ok(page, container.settings.version)
