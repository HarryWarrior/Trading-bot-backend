from typing import Protocol


class TerminalProcessProbe(Protocol):
    """Finds MT5 terminals that are already running on this machine (never starts one)."""

    def running_terminals(self) -> list[str]:
        """Executable paths of the running terminal64.exe processes (one entry per process)."""
        ...
