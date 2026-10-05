"""Pattern requirements: what must hold before a run starts, and how it is isolated.

A pattern may declare (all optional, all off by default)::

    "requires": {"readiness": "foundational", "capabilities": ["sast"]},
    "verification": {"minimum": ["test"]},
    "isolation": {"mode": "worktree", "cleanup": "on-success"}

- ``requires.readiness``: the repository must meet this Agent Ready level, checked
  by ``agentic ready verify --scope local`` in the run's workspace. It is a
  blocking precondition: AgentFlow never remediates (never ``ready make``).
- ``requires.capabilities``: each must be enabled (``agentic capabilities status``).
- ``verification.minimum``: kinds every gate of this pattern requires, on top of
  the profile's (and alongside explicit custom gate commands).
- ``isolation.mode: worktree``: one Agentic Dev worktree per run, created from the
  run-start commit before any precondition, so preconditions and every stage
  run there. It is never force-cleaned: failed or blocked runs keep it, and
  ``cleanup: on-success`` only asks Agentic Dev for a normal (non-forced) clean.

Level names, capability names, and kinds belong to Agentic Dev; AgentFlow passes
them through and Agentic Dev rejects unknown ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Pattern

SECTIONS = {"requires": {"readiness", "capabilities", "skills", "allowed_skills", "trust_profile",
                          "trust_ceiling", "permissions"},
            "verification": {"minimum"}, "isolation": {"mode", "cleanup"}}
ISOLATION_MODES = ("none", "worktree")
CLEANUP_POLICIES = ("never", "on-success")


@dataclass(frozen=True)
class Requirements:
    readiness: str | None = None
    capabilities: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    allowed_skills: tuple[str, ...] | None = None
    trust_profile: str | None = None
    trust_ceiling: str | None = None
    permissions: dict[str, Any] | None = None
    minimum: tuple[str, ...] = ()
    worktree: bool = False
    cleanup_on_success: bool = False

    def describe(self) -> list[str]:
        lines = []
        if self.readiness:
            lines.append(f"readiness: {self.readiness} (local scope, checked at run start)")
        if self.capabilities:
            lines.append(f"capabilities: {', '.join(self.capabilities)}")
        if self.skills:
            lines.append(f"skills: {', '.join(self.skills)}")
        if self.trust_profile:
            lines.append(f"trust profile: {self.trust_profile}")
        if self.trust_ceiling:
            lines.append(f"trust ceiling: {self.trust_ceiling}")
        if self.minimum:
            lines.append(f"verification minimum: {', '.join(self.minimum)}")
        if self.worktree:
            lines.append("isolation: one worktree per run" + (", cleaned on success" if self.cleanup_on_success else ""))
        return lines


def _names(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{where} must be a list of non-empty names")
    return tuple(dict.fromkeys(value))


def requirements(pattern: Pattern) -> Requirements:
    """Parse and validate a pattern's requirements; unknown keys are an error, not ignored."""

    for section, allowed in SECTIONS.items():
        value = getattr(pattern, section)
        if not isinstance(value, dict):
            raise ValueError(f"{pattern.name}: {section} must be an object")
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"{pattern.name}: unknown {section} key(s): {', '.join(unknown)}")
    readiness = pattern.requires.get("readiness")
    if readiness is not None and (not isinstance(readiness, str) or not readiness.strip()):
        raise ValueError(f"{pattern.name}: requires.readiness must be a level name")
    for key in ("trust_profile", "trust_ceiling"):
        value = pattern.requires.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{pattern.name}: requires.{key} must be a non-empty name")
    permissions = pattern.requires.get("permissions")
    if permissions is not None and (not isinstance(permissions, dict) or
                                    set(permissions) - {"implementer", "reviewer"} or
                                    any(not isinstance(value, dict) for value in permissions.values())):
        raise ValueError(f"{pattern.name}: requires.permissions must map implementer/reviewer to bounds")
    mode = pattern.isolation.get("mode", "none")
    cleanup = pattern.isolation.get("cleanup", "never")
    if mode not in ISOLATION_MODES:
        raise ValueError(f"{pattern.name}: isolation.mode must be one of {', '.join(ISOLATION_MODES)}")
    if cleanup not in CLEANUP_POLICIES:
        raise ValueError(f"{pattern.name}: isolation.cleanup must be one of {', '.join(CLEANUP_POLICIES)}")
    if cleanup != "never" and mode != "worktree":
        raise ValueError(f"{pattern.name}: isolation.cleanup needs isolation.mode worktree")
    return Requirements(
        readiness=readiness,
        capabilities=_names(pattern.requires.get("capabilities", []), f"{pattern.name}: requires.capabilities"),
        skills=_names(pattern.requires.get("skills", []), f"{pattern.name}: requires.skills"),
        allowed_skills=(_names(pattern.requires["allowed_skills"], f"{pattern.name}: requires.allowed_skills")
                        if "allowed_skills" in pattern.requires else None),
        trust_profile=pattern.requires.get("trust_profile"),
        trust_ceiling=pattern.requires.get("trust_ceiling"),
        permissions=permissions,
        minimum=_names(pattern.verification.get("minimum", []), f"{pattern.name}: verification.minimum"),
        worktree=mode == "worktree",
        cleanup_on_success=cleanup == "on-success",
    )


def readiness_blockers(document: dict[str, Any]) -> str:
    """A one-line account of why a readiness-verification document did not pass."""

    maturity = document.get("maturity") or {}
    blockers = "; ".join(f"{b['id']} ({b.get('title') or b.get('reason')})" for b in document.get("blockers") or [])
    return (f"readiness {document['target']} not met (current {maturity.get('current', 'unknown')})"
            + (f"; blockers: {blockers}" if blockers else ""))


def capability_blockers(required: tuple[str, ...], status: dict[str, Any]) -> list[str]:
    unknown = [name for name in required if name not in status]
    disabled = [name for name in required if name in status and not status[name].get("enabled")]
    problems = []
    if unknown:
        problems.append(f"unknown capability: {', '.join(unknown)}")
    if disabled:
        problems.append(f"capability not enabled: {', '.join(disabled)} "
                        f"(enable explicitly: agentic capabilities enable NAME)")
    return problems
