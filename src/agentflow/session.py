"""Map a resolved AgentFlow workflow to Agentic Dev's portable session request."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .gates import plan_gate
from .models import Pattern, Project
from .requirements import requirements

DEFAULT_PERMISSIONS: dict[str, dict[str, dict[str, str]]] = {
    "implementer": {
        "filesystem": {"minimum": "workspace-write", "maximum": "workspace-write"},
        "network": {"minimum": "off", "maximum": "off"},
    },
    "reviewer": {
        "filesystem": {"minimum": "read-only", "maximum": "read-only"},
        "network": {"minimum": "off", "maximum": "off"},
    },
}


def build_session_request(
    project: Project, pattern: Pattern, task: str, executor: str, reviewers: list[str]
) -> dict[str, Any]:
    """Describe required environment authority without passing workflow stages or policy."""

    reqs = requirements(pattern)
    bounds = reqs.permissions or {}

    def invocation(name: str, role: str, harness: str) -> dict[str, Any]:
        return {
            "id": name,
            "role": role,
            "harness": harness,
            "permissions": deepcopy(bounds.get(role, DEFAULT_PERMISSIONS[role])),
        }

    invocations = [invocation("implement", "implementer", executor)]
    review_stages = [stage for stage in pattern.stages if stage.kind == "review"]
    if review_stages:
        candidates = reviewers or project.config.reviewers or [executor]
        count = max(stage.reviewers or len(candidates) or 1 for stage in review_stages)
        invocations += [
            invocation(f"review-{index}", "reviewer", candidates[(index - 1) % len(candidates)])
            for index in range(1, count + 1)
        ]

    verification = set(reqs.minimum)
    for stage in pattern.stages:
        if stage.kind == "gate":
            profile = stage.gate_profile or project.config.gate_profile
            verification.update(
                plan_gate(project.root, project.config, profile, minimum=reqs.minimum).kinds
            )

    request: dict[str, Any] = {
        "schema_version": "1",
        "document_type": "agentic.session-request",
        "task": task,
        "invocations": invocations,
        "verification_kinds": sorted(verification),
    }
    if reqs.readiness:
        request["readiness_minimum"] = reqs.readiness
    if reqs.capabilities:
        request["required_capabilities"] = list(reqs.capabilities)
    if reqs.skills:
        request["required_skills"] = list(reqs.skills)
    if reqs.allowed_skills is not None:
        request["allowed_skills"] = list(reqs.allowed_skills)
    if reqs.trust_profile:
        request["trust_profile"] = reqs.trust_profile
    if reqs.trust_ceiling:
        request["trust_ceiling"] = reqs.trust_ceiling
    return request
