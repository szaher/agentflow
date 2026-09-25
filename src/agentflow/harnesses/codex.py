from __future__ import annotations
from pathlib import Path
from .base import Harness
from .common import execute_command
from ..models import HarnessResult

class CodexHarness(Harness):
    name = "codex"
    executable = "codex"

    def command_preview(self, prompt: str, *, read_only: bool = False, extra: dict | None = None) -> list[str]:
        # Codex CLI supports non-interactive `codex exec`. Sandbox flags have changed
        # across releases, so read-only is additionally enforced by Agentflow's
        # before/after repository fingerprint check.
        cmd = ["codex", "exec"]
        model = (extra or {}).get("model")
        if model: cmd += ["--model", str(model)]
        if read_only:
            cmd += ["--sandbox", "read-only"]
        cmd.append(prompt)
        return cmd

    def execute(self, root: Path, prompt: str, *, read_only: bool = False, extra: dict | None = None) -> HarnessResult:
        return execute_command(self.name, self.command_preview(prompt, read_only=read_only, extra=extra), root, read_only)
