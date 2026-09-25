from __future__ import annotations

import shlex
from pathlib import Path
from .base import Harness
from .common import execute_command
from ..models import HarnessResult

class CommandHarness(Harness):
    """Adapter for any non-interactive coding-agent CLI configured by command template.

    Config example:
      {"command": ["myagent", "run", "{prompt}"],
       "review_command": ["myagent", "review", "{prompt}"]}
    """
    def __init__(self, name: str, config: dict):
        self.name=name
        self.config=config
        command=config.get("command")
        if not command:
            raise KeyError(f"Custom harness {name!r} requires harness.{name}.command")
        self.executable = command[0] if isinstance(command,list) else shlex.split(command)[0]

    def command_preview(self, prompt: str, *, read_only: bool=False, extra: dict|None=None) -> list[str]:
        spec=self.config.get("review_command") if read_only and self.config.get("review_command") else self.config["command"]
        parts=spec if isinstance(spec,list) else shlex.split(spec)
        out=[]
        inserted=False
        for p in parts:
            if "{prompt}" in p:
                out.append(p.replace("{prompt}",prompt)); inserted=True
            else: out.append(p)
        if not inserted: out.append(prompt)
        return out

    def execute(self, root: Path, prompt: str, *, read_only: bool=False, extra: dict|None=None) -> HarnessResult:
        return execute_command(self.name,self.command_preview(prompt,read_only=read_only,extra=extra),root,read_only)
