from fastapi import Request

from mt5_bridge_service.bootstrap import Container


def get_container(request: Request) -> Container:
    return request.app.state.container
