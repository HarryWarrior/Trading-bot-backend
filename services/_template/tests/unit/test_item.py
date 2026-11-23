import pytest

from template_service.domain.errors import InvalidItemName
from template_service.domain.item import Item


def test_create_strips_name():
    assert Item.create("user-a", "  EURUSD  ").name == "EURUSD"


def test_create_rejects_blank_name():
    with pytest.raises(InvalidItemName):
        Item.create("user-a", "   ")


def test_create_rejects_name_over_100_chars():
    with pytest.raises(InvalidItemName):
        Item.create("user-a", "x" * 101)
