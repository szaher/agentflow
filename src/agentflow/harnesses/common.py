from __future__ import annotations

from pathlib import Path

from ..git import implementation_fingerprint
from ..models import HarnessResult
from ..util import run_command


def execute_command(name: str, command: list[str], root: Path, read_only: bool,
                    env: dict[str, str] | None = None) -> HarnessResult:
    before = implementation_fingerprint(root)
    cp = run_command(command, root, env=env)
    after = implementation_fingerprint(root)
    return HarnessResult(name, cp.returncode, cp.stdout, cp.stderr, command, changed=(before != after))
