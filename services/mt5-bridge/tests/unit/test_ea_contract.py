"""Contract between the MQL5 EA (``ea/TradingJournalBridge.mq5``) and the bridge request schemas.

The EA cannot be compiled or run in CI, so this test pins what it must send: the sample payloads
in ``ea/sample_payloads`` are exactly what the EA builds, and the EA source keeps the
contract-critical constants (paths, auth header, batch cap, heartbeat interval) in sync.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from mt5_bridge_service.adapters.inbound.http.schemas import DealIn, HeartbeatIn, IngestDealsIn
from mt5_bridge_service.domain.deal import MAX_DEALS_PER_REQUEST

EA_DIR = Path(__file__).resolve().parents[2] / "ea"
EA_SOURCE = EA_DIR / "TradingJournalBridge.mq5"
DEALS_FIXTURE = EA_DIR / "sample_payloads" / "deals.json"
HEARTBEAT_FIXTURE = EA_DIR / "sample_payloads" / "heartbeat.json"

UTC_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DECIMAL_STRING = re.compile(r"^-?\d+(\.\d+)?$")
DEAL_DECIMALS = ("volume", "price", "commission", "swap", "fee", "profit")
OPTIONAL_DEAL_DECIMALS = ("sl", "tp")
# Every output call the EA could leak the token through.
OUTPUT_CALLS = ("Print", "PrintFormat", "Alert", "Comment", "MessageBox", "SendNotification")
SECRET_NAMES = ("IngestToken", "g_headers", "Authorization")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _deals_payload() -> dict[str, Any]:
    return _load(DEALS_FIXTURE)


def _ea_source() -> str:
    return EA_SOURCE.read_text(encoding="utf-8")


def _call_arguments(source: str, name: str) -> list[str]:
    """Argument text of every ``name(...)`` call, with nested parentheses balanced."""
    found = []
    for match in re.finditer(rf"\b{name}\s*\(", source):
        depth, start = 1, match.end()
        index = start
        while depth and index < len(source):
            depth += {"(": 1, ")": -1}.get(source[index], 0)
            index += 1
        found.append(source[start : index - 1])
    return found


# --- sample payloads parse with the real request schemas ------------------------------------


def test_deals_fixture_parses_with_bridge_schema():
    body = IngestDealsIn.model_validate(_deals_payload())

    assert body.account_login > 0 and body.server
    assert 0 < len(body.deals) <= MAX_DEALS_PER_REQUEST
    assert all(d.time.utcoffset() == timedelta(0) for d in body.deals)


def test_deals_fixture_uses_utc_iso_times_decimal_strings_and_int_tickets():
    for deal in _deals_payload()["deals"]:
        assert isinstance(deal["ticket"], int) and isinstance(deal["position_id"], int)
        assert isinstance(deal["type"], int) and isinstance(deal["entry"], int)
        assert UTC_ISO.match(deal["time"]), deal["time"]
        for field in DEAL_DECIMALS:
            assert isinstance(deal[field], str) and DECIMAL_STRING.match(deal[field]), field
        for field in OPTIONAL_DEAL_DECIMALS:
            assert deal[field] is None or DECIMAL_STRING.match(deal[field]), field


def test_deals_fixture_sends_every_deal_field():
    for deal in _deals_payload()["deals"]:
        assert set(deal) == set(DealIn.model_fields)


def test_deals_fixture_covers_a_round_trip_and_a_balance_deal():
    deals = _deals_payload()["deals"]
    kinds = {(d["type"], d["entry"]) for d in deals}
    assert {(0, 0), (1, 1)} <= kinds  # BUY in, SELL out
    assert any(d["type"] == 2 for d in deals)  # balance
    trade_positions = [d["position_id"] for d in deals if d["type"] in (0, 1)]
    assert len(set(trade_positions)) < len(trade_positions)  # IN and OUT share position_id


def test_heartbeat_fixture_parses_with_bridge_schema():
    raw = _load(HEARTBEAT_FIXTURE)
    body = HeartbeatIn.model_validate(raw)

    assert set(raw) == set(HeartbeatIn.model_fields)
    assert isinstance(raw["account_login"], int) and isinstance(raw["terminal_build"], int)
    assert isinstance(raw["balance"], str) and isinstance(raw["equity"], str)
    assert body.account_login == _deals_payload()["account_login"]
    assert body.server == _deals_payload()["server"]


# --- batch cap and volume rule --------------------------------------------------------------


def _batch_of(size: int) -> dict[str, Any]:
    payload = _deals_payload()
    template = payload["deals"][0]
    payload["deals"] = [dict(template, ticket=template["ticket"] + i) for i in range(size)]
    return payload


def test_batch_of_200_is_accepted():
    assert len(IngestDealsIn.model_validate(_batch_of(200)).deals) == 200


def test_batch_of_201_is_rejected():
    with pytest.raises(ValidationError):
        IngestDealsIn.model_validate(_batch_of(201))


def _deal(**changes: Any) -> dict[str, Any]:
    payload = copy.deepcopy(_deals_payload())
    payload["deals"] = [dict(payload["deals"][0], **changes)]
    return payload


@pytest.mark.parametrize("deal_type", [0, 1])
def test_buy_or_sell_deal_with_zero_volume_is_rejected(deal_type: int):
    with pytest.raises(ValidationError):
        IngestDealsIn.model_validate(_deal(type=deal_type, volume="0"))


def test_balance_deal_with_zero_volume_is_accepted():
    body = IngestDealsIn.model_validate(
        _deal(type=2, entry=0, symbol="", volume="0", price="0", profit="1000", sl=None, tp=None)
    )
    assert body.deals[0].volume == 0


# --- EA source keeps the contract constants -------------------------------------------------


def test_ea_source_exists():
    assert EA_SOURCE.is_file()


def test_ea_uses_the_bridge_endpoint_paths():
    source = _ea_source()
    assert '"/api/v1/mt5-bridge/ingest/deals"' in source
    assert '"/api/v1/mt5-bridge/ingest/heartbeat"' in source


def test_ea_sends_json_with_bearer_authorization():
    source = _ea_source()
    assert "Authorization: Bearer " in source
    assert "Content-Type: application/json" in source


def test_ea_batch_size_respects_the_bridge_cap():
    match = re.search(r"#define\s+BATCH_SIZE\s+(\d+)", _ea_source())
    assert match, "BATCH_SIZE constant missing"
    assert 0 < int(match.group(1)) <= MAX_DEALS_PER_REQUEST


def test_ea_heartbeat_interval_is_60_seconds():
    source = _ea_source()
    match = re.search(r"#define\s+HEARTBEAT_SECONDS\s+(\d+)", source)
    assert match and int(match.group(1)) == 60
    assert re.search(r"EventSetTimer\s*\(\s*HEARTBEAT_SECONDS\s*\)", source)


def test_ea_serializes_every_schema_field():
    source = _ea_source()
    fields = set(DealIn.model_fields) | set(HeartbeatIn.model_fields) | {"deals"}
    for field in fields:
        assert f'\\"{field}\\":' in source, field


def test_ea_never_outputs_the_token():
    source = _ea_source()
    for call in OUTPUT_CALLS:
        for arguments in _call_arguments(source, call):
            for secret in SECRET_NAMES:
                assert secret not in arguments, f"{call}({arguments}) may leak the token"


def test_ea_never_writes_the_token_to_files():
    source = _ea_source()
    for call in ("FileWrite", "FileWriteString", "GlobalVariableSet"):
        for arguments in _call_arguments(source, call):
            for secret in SECRET_NAMES:
                assert secret not in arguments, f"{call}({arguments}) may persist the token"
