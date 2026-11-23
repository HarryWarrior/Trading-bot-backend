from fastapi import Header, Request

from template_service.bootstrap import Container
from trading_shared.errors import AppError


def get_current_user_id(x_user_id: str | None = Header(default=None)) -> str:
    """Resolve the calling user.

    Temporary: trusts the ``X-User-Id`` header. Spec 001 replaces this with JWT verification
    from ``trading_shared``. Never trust this header in production.
    """
    if not x_user_id:
        raise AppError("UNAUTHENTICATED", "Missing user identity.", 401)
    return x_user_id


def get_container(request: Request) -> Container:
    return request.app.state.container
