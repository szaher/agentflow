from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import HarnessResult

class Harness(ABC):
    name: str
    executable: str

    @abstractmethod
    def execute(self, root: Path, prompt: str, *, read_only: bool = False, extra: dict | None = None) -> HarnessResult:
        raise NotImplementedError

    @abstractmethod
    def command_preview(self, prompt: str, *, read_only: bool = False, extra: dict | None = None) -> list[str]:
        raise NotImplementedError
