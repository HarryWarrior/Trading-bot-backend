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
# Identifiers that hold the token: the input, the header string and the local in ValidateInputs.
SECRET_IDENTIFIERS = re.compile(r"\b(IngestToken|g_headers|token)\b")
# Comments, string literals and char literals, removed before looking at code structure.
_NOT_CODE = re.compile(r"""//[^\n]*|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])'""")
_FUNCTION = re.compile(r"^[A-Za-z_]\w*\s+(\w+)\s*\(", re.M)


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


def _code_only(source: str) -> str:
    """Source without comments and literals (literals become ``""``), so parentheses and braces
    inside messages or JSON templates do not confuse the structural checks."""

    def replace(match: re.Match[str]) -> str:
        text = match.group(0)
        return "" if text.startswith("//") else '""'

    return _NOT_CODE.sub(replace, source)


def _function_bodies(code: str) -> dict[str, str]:
    """Body (between the outer braces) of every top-level function of the code-only source."""
    bodies = {}
    for match in _FUNCTION.finditer(code):
        open_brace = code.find("{", match.end())
        if open_brace < 0 or ";" in code[match.end() : open_brace]:
            continue  # a declaration or a call, not a definition
        depth, index = 1, open_brace + 1
        while depth and index < len(code):
            depth += {"{": 1, "}": -1}.get(code[index], 0)
            index += 1
        bodies[match.group(1)] = code[open_brace + 1 : index - 1]
    return bodies


def _ea_functions() -> dict[str, str]:
    return _function_bodies(_code_only(_ea_source()))


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
    code = _code_only(_ea_source())
    for call in OUTPUT_CALLS:
        for arguments in _call_arguments(code, call):
            assert not SECRET_IDENTIFIERS.search(arguments), f"{call}({arguments}) may leak it"


def test_ea_never_writes_the_token_to_files():
    code = _code_only(_ea_source())
    for call in ("FileWrite", "FileWriteString", "GlobalVariableSet"):
        for arguments in _call_arguments(code, call):
            assert not SECRET_IDENTIFIERS.search(arguments), f"{call}({arguments}) may persist it"


def test_authorization_header_is_built_in_one_place_only():
    lines = [line for line in _ea_source().splitlines() if "Authorization: Bearer" in line]
    code_lines = [line for line in lines if not line.lstrip().startswith("//")]
    assert len(code_lines) == 1 and "g_headers =" in code_lines[0]


def test_header_string_is_used_only_to_reset_build_and_send():
    code = _code_only(_ea_source())
    functions = _function_bodies(code)
    name = re.compile(r"\bg_headers\b")
    users = {fn for fn, body in functions.items() if name.search(body)}
    assert users == {"ResetState", "ValidateInputs", "Post"}
    in_functions = sum(len(name.findall(body)) for body in functions.values())
    assert len(name.findall(code)) == in_functions + 1  # + the global declaration
    post = functions["Post"]
    webrequest_args = _call_arguments(post, "WebRequest")
    assert len(name.findall(post)) == 1
    assert len(webrequest_args) == 1 and name.search(webrequest_args[0])


# --- EA queue never loses deals on write errors ---------------------------------------------


def test_every_queue_write_is_checked():
    code = _code_only(_ea_source())
    writes = re.findall(r"\bFileWriteString\s*\(", code)
    checked = re.findall(r"\bFileWriteString\s*\([^()]*\)\s*(?:==|>)\s*0", code)
    assert writes and len(checked) == len(writes)


def test_rewrite_queue_flushes_before_replacing_and_keeps_the_old_queue_on_failure():
    body = _ea_functions()["RewriteQueue"]
    flush, move = body.find("FileFlush("), body.find("FileMove(")
    delete_temp = body.find("FileDelete(temp)")
    assert 0 <= flush < move
    assert 0 <= delete_temp < move
    assert "return" in body[delete_temp:move]  # the failure branch never reaches FileMove


def test_append_failure_returns_false_and_does_not_advance_the_high_water_mark():
    functions = _ea_functions()
    append = functions["AppendToQueue"]
    assert append.count("return false") == 2  # cannot open, cannot write
    # A fresh line first, so a torn last line is never joined to the new deals.
    seek = append.find("FileSeek(")
    first_write = re.search(r"FileWriteString\s*\(\s*handle\s*,\s*\"\"\s*\)\s*>\s*0", append)
    assert first_write and seek < first_write.start()
    raw = _ea_source()
    assert 'FileWriteString(handle, "\\r\\n") > 0' in raw
    collect = functions["CollectNewDeals"]
    guard = re.search(r"if\s*\(\s*!\s*AppendToQueue\s*\([^)]*\)\s*\)\s*return\s*;", collect)
    assert guard
    assert guard.end() < collect.find("RememberQueued(") < collect.find("GlobalVariableSet(")


def test_queue_lines_must_be_exactly_one_json_object():
    functions = _ea_functions()
    assert "IsSingleJsonObject(" in functions["CleanLine"]
    check = functions["IsSingleJsonObject"]
    for piece in ("in_string", "escaped", "depth++", "depth--", "depth == 0 && i != len - 1"):
        assert piece in check, piece


def _function_body(code: str, name: str) -> str:
    start = code.index(name + "(")
    return code[start : code.index("\n  }\n", start)]


def test_event_handlers_check_login_and_server_of_the_started_account():
    code = _code_only(_ea_source())
    for handler in ("void OnTimer", "void OnTradeTransaction"):
        body = _function_body(code, handler)
        assert "ACCOUNT_LOGIN" in body and "g_login" in body, handler
        assert "ACCOUNT_SERVER" in body and "g_server" in body, handler


def test_no_backfill_or_flush_before_the_first_heartbeat_succeeded():
    code = _code_only(_ea_source())
    assert "g_heartbeat_ok = true" in code
    for name in ("bool Startup", "void OnTimer", "void OnTradeTransaction"):
        body = _function_body(code, name)
        assert "g_heartbeat_ok" in body, name
        assert body.index("g_heartbeat_ok") < body.index("CollectNewDeals"), name
