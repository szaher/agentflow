from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Literal

StageKind = Literal["agent", "gate", "review", "human", "noop"]

@dataclass(slots=True)
class Stage:
    id: str
    kind: StageKind
    title: str
    role: str = "implementer"
    instruction: str = ""
    gate_profile: str | None = None
    reviewers: int = 0
    on_success: str | None = None
    on_failure: str | None = None
    max_attempts: int = 1
    require_clean_reviewer: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Stage":
        return cls(**data)

@dataclass(slots=True)
class Pattern:
    name: str
    description: str
    version: str
    entry: str
    stages: list[Stage]
    tags: list[str] = field(default_factory=list)
    defaults: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Pattern":
        d = dict(data)
        d["stages"] = [Stage.from_dict(x) for x in d.get("stages", [])]
        return cls(**d)

    def stage(self, stage_id: str) -> Stage:
        for stage in self.stages:
            if stage.id == stage_id:
                return stage
        raise KeyError(stage_id)

@dataclass(slots=True)
class ProjectConfig:
    version: int = 1
    pattern: str = "standard"
    executor: str = "claude"
    reviewers: list[str] = field(default_factory=lambda: ["codex"])
    gate_profile: str = "standard"
    max_repair_attempts: int = 3
    auto_approve_low_risk: bool = True
    human_approval_for: list[str] = field(default_factory=lambda: ["high", "critical"])
    harness: dict[str, dict[str, Any]] = field(default_factory=dict)
    gates: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectConfig":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(slots=True)
class RunState:
    run_id: str
    task: str
    pattern: str
    stage: str
    status: str = "running"
    attempt: int = 0
    attempts_by_stage: dict[str, int] = field(default_factory=dict)
    executor: str = "claude"
    reviewers: list[str] = field(default_factory=list)
    fingerprint: str | None = None
    plan_hash: str | None = None
    awaiting_reason: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunState":
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(slots=True)
class HarnessResult:
    harness: str
    returncode: int
    stdout: str
    stderr: str
    command: list[str]
    changed: bool | None = None

@dataclass(slots=True)
class GateResult:
    name: str
    command: str
    returncode: int
    stdout: str
    stderr: str
    duration_s: float

    @property
    def passed(self) -> bool:
        return self.returncode == 0

@dataclass(slots=True)
class Project:
    root: Path
    config: ProjectConfig
