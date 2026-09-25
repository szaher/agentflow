from __future__ import annotations
from pathlib import Path
from .base import Harness
from .common import execute_command
from ..models import HarnessResult

class OpenCodeHarness(Harness):
    name = "opencode"
    executable = "opencode"

    def command_preview(self, prompt: str, *, read_only: bool = False, extra: dict | None = None) -> list[str]:
        cmd = ["opencode", "run", "--standalone"]
        model = (extra or {}).get("model")
        if model: cmd += ["--model", str(model)]
        agent = (extra or {}).get("review_agent" if read_only else "agent")
        if agent: cmd += ["--agent", str(agent)]
        cmd.append(prompt)
        return cmd

    def execute(self, root: Path, prompt: str, *, read_only: bool = False, extra: dict | None = None) -> HarnessResult:
        # Read-only is always verified after execution by Agentflow. Projects can
        # additionally configure a read-only OpenCode agent via review_agent.
        return execute_command(self.name, self.command_preview(prompt, read_only=read_only, extra=extra), root, read_only)
