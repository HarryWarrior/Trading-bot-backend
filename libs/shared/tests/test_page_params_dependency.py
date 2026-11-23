from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from trading_shared.envelope import PageParams
from trading_shared.errors import register_error_handlers
from trading_shared.http import page_params


def _build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/items")
    async def items(params: PageParams = Depends(page_params)):
        return params.model_dump()

    return app


def test_page_params_dependency_rejects_page_size_over_100():
    response = TestClient(_build_app()).get("/items?page_size=101")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_page_params_dependency_applies_defaults():
    response = TestClient(_build_app()).get("/items")
    assert response.json()["page"] == 1
    assert response.json()["page_size"] == 20
    assert response.json()["sort_dir"] == "desc"
