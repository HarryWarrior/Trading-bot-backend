import pytest
from pydantic import ValidationError

from trading_shared.envelope import PageParams, build_pagination, ok


def test_build_pagination_middle_page():
    pagination = build_pagination(2, 20, 45)
    assert pagination.total_pages == 3
    assert pagination.has_next is True
    assert pagination.has_prev is True


def test_build_pagination_zero_items():
    pagination = build_pagination(1, 20, 0)
    assert pagination.total_pages == 0
    assert pagination.has_next is False
    assert pagination.has_prev is False


def test_build_pagination_beyond_last():
    pagination = build_pagination(5, 20, 45)
    assert pagination.has_next is False
    assert pagination.has_prev is True


def test_page_params_rejects_page_size_over_100():
    with pytest.raises(ValidationError):
        PageParams(page_size=101)


def test_ok_wraps_data():
    body = ok({"a": 1}, "1.0.0").model_dump()
    assert body["success"] is True
    assert body["data"] == {"a": 1}
    assert body["meta"]["version"] == "1.0.0"
