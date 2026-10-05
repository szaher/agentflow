from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import HarnessResult

class Harness(ABC):
    name: str
    executable: str
    # Real adapters stay false until a version-scoped recipe applies the planned bounds.
    session_launch_verified = False

    @abstractmethod
    def execute(self, root: Path, prompt: str, *, read_only: bool = False, extra: dict | None = None,
                env: dict[str, str] | None = None) -> HarnessResult:
        """Run in ``root`` (the run's workspace). ``env`` adds variables such as AGENTFLOW_ROOT."""
        raise NotImplementedError

    @abstractmethod
    def command_preview(self, prompt: str, *, read_only: bool = False, extra: dict | None = None) -> list[str]:
        raise NotImplementedError

    def execute_session(self, root: Path, prompt: str, *, permissions: dict,
                        read_only: bool = False, extra: dict | None = None,
                        env: dict[str, str] | None = None) -> HarnessResult:
        """Launch with the approved permission recipe; real adapters must implement this explicitly."""

        raise NotImplementedError("verified session launch recipe is unavailable")
