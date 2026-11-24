from types import SimpleNamespace

import psutil

from mt5_service.adapters.outbound.psutil_probe import PsutilTerminalProbe


def _proc(name, exe):
    return SimpleNamespace(info={"name": name, "exe": exe})


def test_probe_lists_terminal64_processes_case_insensitively(monkeypatch):
    processes = [
        _proc("chrome.exe", r"C:\chrome.exe"),
        _proc("Terminal64.EXE", r"C:\MT5\terminal64.exe"),
        _proc("terminal64.exe", None),  # access denied: path unknown
        _proc(None, None),
        _proc("terminal.exe", r"C:\MT4\terminal.exe"),
    ]
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: iter(processes))
    assert PsutilTerminalProbe().running_terminals() == [r"C:\MT5\terminal64.exe"]
