"""Deterministic verification gates, executed by Agentic Dev.

AgentFlow decides *which verification kinds are required*; Agentic Dev decides
whether each requirement can be satisfied, which concrete commands implement it,
and runs them (``agentic verify run``). AgentFlow holds no repository or tool
knowledge of its own:

- a profile names required kinds, and every one is requested unchanged. Agentic
  Dev runs **every** command of each kind, or, if any required kind has no
  command, reports ``no-checks`` with ``missing_kinds`` and runs nothing;
- explicit ``gates`` in ``.agentflow/config.json`` replace the profile's kinds
  and still execute through Agentic Dev: each is passed intact as one
  ``--command`` argument (AgentFlow never invokes a shell itself; Agentic Dev's
  execution backend runs it);
- a pattern's ``verification.minimum`` kinds are required by every gate of that
  pattern: added to the profile's kinds, and required alongside custom commands;
- a gate with nothing to run fails closed; only an explicit ``passed`` passes;
- change-aware checks (``include_changed``) can only add to the full baseline,
  using the run-start commit as the base. Workflow gate stages are full-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

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
    # The validated agentic.verification-run document, unmodified.
    verification: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def results(self) -> list[dict[str, Any]]:
        return list((self.verification or {}).get("results") or [])


def plan_gate(root: Path, config: ProjectConfig, profile: str, *, agentic: Agentic | None = None,
              include_changed: bool = False, base: str | None = None, minimum: Sequence[str] = ()) -> GatePlan:
    if profile not in PROFILE_KINDS:
        raise ValueError(f"unknown gate profile {profile!r}; choose one of: {', '.join(PROFILE_KINDS)}")
    custom = config.gates.get(profile)
    if custom:
        # Custom commands replace the profile's kinds, never the pattern's minimum.
        return GatePlan(profile, list(dict.fromkeys(minimum)), list(custom), include_changed, base)
    # The requirement is AgentFlow's; whether it can be met is Agentic Dev's answer.
    kinds = list(dict.fromkeys([*PROFILE_KINDS[profile], *minimum]))
    return GatePlan(profile, kinds, [], include_changed, base)


def run_gates(root: Path, config: ProjectConfig, profile: str, *, agentic: Agentic | None = None,
              include_changed: bool = False, base: str | None = None, minimum: Sequence[str] = ()) -> GateRun:
    agentic = agentic or Agentic()
    plan = plan_gate(root, config, profile, agentic=agentic, include_changed=include_changed, base=base,
                     minimum=minimum)
    document = agentic.verify(root, kinds=plan.kinds, commands=plan.commands,
                              include_changed=plan.include_changed, base=plan.base)
    status = document["status"]  # authoritative
    if document.get("missing_kinds"):
        reason = (f"no runnable command for required kind(s): {', '.join(document['missing_kinds'])}; "
                  f"add one to the project or configure .agentflow/config.json -> gates.{profile}")
    else:
        reason = {"passed": "gates passed", "failed": "gates failed", "no-checks": "no checks were executed"}[status]
    return GateRun(status, plan, reason, document)
