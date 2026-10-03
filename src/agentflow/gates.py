"""Deterministic verification gates, executed by Agentic Dev.

AgentFlow decides *which verification kinds matter*; Agentic Dev decides which
concrete commands implement each kind and runs them (``agentic verify run``).
AgentFlow holds no repository or tool knowledge of its own:

- a profile names kinds; the gate requests the profile's kinds that Agentic Dev
  actually discovered, and Agentic Dev runs **every** command of each;
- explicit ``gates`` in ``.agentflow/config.json`` replace discovery for that
  profile and still execute through Agentic Dev (``--command``), never a shell;
- a gate with nothing to run fails closed; only an explicit ``passed`` passes;
- change-aware checks (``include_changed``) can only add to the full baseline,
  using the run-start commit as the base. Workflow gate stages are full-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agentic import Agentic
from .models import ProjectConfig

PROFILE_KINDS: dict[str, tuple[str, ...]] = {
    "fast": ("lint", "test"),
    "standard": ("lint", "typecheck", "test"),
    "strict": ("build", "lint", "typecheck", "test"),
}


@dataclass
class GatePlan:
    profile: str
    kinds: list[str]
    commands: list[str]
    include_changed: bool = False
    base: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"profile": self.profile, "kinds": self.kinds, "commands": self.commands,
                "include_changed": self.include_changed, "base": self.base}


@dataclass
class GateRun:
    status: str  # passed | failed | no-checks; Agentic Dev's status when it ran
    plan: GatePlan
    reason: str
    # The validated agentic.verification-run document, unmodified; None when nothing was requested.
    verification: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def results(self) -> list[dict[str, Any]]:
        return list((self.verification or {}).get("results") or [])


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
        return GateRun("no-checks", plan,
                       f"no {wanted} commands were discovered; configure .agentflow/config.json -> gates.{profile}")
    document = agentic.verify(root, kinds=plan.kinds, commands=plan.commands,
                              include_changed=plan.include_changed, base=plan.base)
    status = document["status"]  # authoritative
    if document.get("missing_kinds"):
        reason = f"no runnable command for: {', '.join(document['missing_kinds'])}"
    else:
        reason = {"passed": "gates passed", "failed": "gates failed", "no-checks": "no checks were executed"}[status]
    return GateRun(status, plan, reason, document)
