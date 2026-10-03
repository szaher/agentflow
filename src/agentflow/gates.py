"""Deterministic verification gates, executed by Agentic Dev.

AgentFlow decides *what* a gate requires; Agentic Dev discovers and runs the
commands (``agentic verify run``). A gate is full-project verification:

- a profile names command kinds: ``fast`` = lint + test; ``standard`` and
  ``strict`` = lint + typecheck + test + build. Every discovered command of
  each of those kinds runs;
- explicit ``gates`` in ``.agentflow/config.json`` replace discovery for that
  profile and still execute through Agentic Dev (no AgentFlow shell fallback);
- a gate with nothing to run fails: zero checks is never success;
- change-aware checks (stage metadata ``include_changed``) can only be added on
  top of the full baseline, using the run-start commit as the base.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agentic import Agentic
from .models import GateResult, ProjectConfig

PROFILE_KINDS: dict[str, tuple[str, ...]] = {
    "fast": ("lint", "test"),
    "standard": ("lint", "typecheck", "test", "build"),
    "strict": ("lint", "typecheck", "test", "build"),
}


@dataclass
class GatePlan:
    profile: str
    kinds: list[str]
    commands: list[str]
    include_changed: bool = False
    base: str | None = None


@dataclass
class GateRun:
    status: str  # passed | failed | no-checks
    results: list[GateResult]
    plan: GatePlan
    reason: str
    verification: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def passed(self) -> bool:
        return self.status == "passed"


def plan_gate(root: Path, config: ProjectConfig, profile: str, *, agentic: Agentic,
              include_changed: bool = False, base: str | None = None) -> GatePlan:
    if profile not in PROFILE_KINDS:
        raise ValueError(f"unknown gate profile {profile!r}; choose one of: {', '.join(PROFILE_KINDS)}")
    custom = config.gates.get(profile)
    if custom:
        return GatePlan(profile, [], list(custom), include_changed, base)
    available = agentic.discovered_kinds(root)
    kinds = [kind for kind in PROFILE_KINDS[profile] if kind in available]
    return GatePlan(profile, kinds, [], include_changed, base)


def run_gates(root: Path, config: ProjectConfig, profile: str, *, agentic: Agentic | None = None,
              include_changed: bool = False, base: str | None = None) -> GateRun:
    agentic = agentic or Agentic()
    plan = plan_gate(root, config, profile, agentic=agentic, include_changed=include_changed, base=base)
    if not plan.kinds and not plan.commands:
        wanted = ", ".join(PROFILE_KINDS[profile])
        return GateRun("no-checks", [], plan,
                       f"no {wanted} commands were discovered; configure .agentflow/config.json -> gates.{profile}")
    document = agentic.verify(root, kinds=plan.kinds, commands=plan.commands,
                              include_changed=plan.include_changed, base=plan.base)
    results = [
        GateResult(
            name=item.get("kind", "check"),
            command=item.get("command") or item.get("test_file") or item.get("capability") or "",
            returncode=item.get("returncode") if item.get("returncode") is not None else (0 if item.get("success") else 1),
            stdout=item.get("stdout", ""),
            stderr=item.get("stderr", "") or item.get("error", ""),
            duration_s=float(item.get("duration_ms", 0.0)) / 1000,
        )
        for item in document.get("results", [])
        if item.get("executed")
    ]
    status = document["status"]
    if document.get("missing_kinds"):
        reason = f"no runnable command for: {', '.join(document['missing_kinds'])}"
    else:
        reason = {"passed": "gates passed", "failed": "gates failed", "no-checks": "no checks were executed"}[status]
    return GateRun(status, results, plan, reason, document)
