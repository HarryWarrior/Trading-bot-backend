"""TerminalProcessProbe over ``psutil``: lists running terminal64.exe processes."""

from __future__ import annotations

import psutil

_TERMINAL_EXE = "terminal64.exe"


class PsutilTerminalProbe:
    def running_terminals(self) -> list[str]:
        """Paths of running terminals. A process whose path cannot be read (access denied) is
        skipped: initialize(path=...) could not target it anyway."""
        found: list[str] = []
        for process in psutil.process_iter(["name", "exe"]):
            info = process.info
            name = info.get("name") or ""
            exe = info.get("exe")
            if name.lower() == _TERMINAL_EXE and exe:
                found.append(str(exe))
        return found
