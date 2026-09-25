from __future__ import annotations
from pathlib import Path
from .base import Harness
from .common import execute_command
from ..models import HarnessResult

class ClaudeHarness(Harness):
    name = "claude"
    executable = "claude"

    def command_preview(self, prompt: str, *, read_only: bool = False, extra: dict | None = None) -> list[str]:
        cmd = ["claude", "-p", "--output-format", "text"]
        turns = str((extra or {}).get("max_turns", 40))
        cmd += ["--max-turns", turns]
        if read_only:
            cmd += ["--disallowedTools", "Edit", "Write", "NotebookEdit"]
        model = (extra or {}).get("model")
        if model: cmd += ["--model", str(model)]
        cmd.append(prompt)
        return cmd

    def execute(self, root: Path, prompt: str, *, read_only: bool = False, extra: dict | None = None) -> HarnessResult:
        return execute_command(self.name, self.command_preview(prompt, read_only=read_only, extra=extra), root, read_only)
