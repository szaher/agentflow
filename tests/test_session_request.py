from __future__ import annotations

import unittest
from pathlib import Path

from agentflow.models import Pattern, Project, ProjectConfig
from agentflow.session import build_session_request


class SessionRequestTests(unittest.TestCase):
    def test_resolved_workflow_maps_without_agentflow_semantics(self):
        pattern = Pattern.from_dict({
            "name": "custom-review", "description": "workflow", "version": "1", "entry": "write",
            "requires": {
                "readiness": "foundational", "capabilities": ["sast"],
                "skills": ["python-engineering"], "allowed_skills": ["python-engineering", "code-review"],
                "trust_profile": "development", "trust_ceiling": "development",
                "permissions": {
                    "implementer": {"filesystem": {"minimum": "workspace-write", "maximum": "workspace-write"},
                                    "network": {"minimum": "off", "maximum": "off"}},
                    "reviewer": {"filesystem": {"minimum": "read-only", "maximum": "read-only"},
                                 "network": {"minimum": "off", "maximum": "off"}},
                },
            },
            "verification": {"minimum": ["build"]},
            "stages": [
                {"id": "write", "kind": "agent", "title": "write", "max_attempts": 3},
                {"id": "check", "kind": "gate", "title": "check", "gate_profile": "fast"},
                {"id": "review", "kind": "review", "title": "review", "reviewers": 2},
            ],
        })
        project = Project(Path("/repo"), ProjectConfig(gate_profile="strict"))
        request = build_session_request(project, pattern, "Fix the parser", "codex", ["claude", "pi"])
        self.assertEqual(request["document_type"], "agentic.session-request")
        self.assertEqual(request["task"], "Fix the parser")
        self.assertEqual(request["readiness_minimum"], "foundational")
        self.assertEqual(request["required_capabilities"], ["sast"])
        self.assertEqual(request["required_skills"], ["python-engineering"])
        self.assertEqual(request["allowed_skills"], ["python-engineering", "code-review"])
        self.assertEqual(request["trust_profile"], "development")
        self.assertEqual(request["trust_ceiling"], "development")
        self.assertEqual(request["verification_kinds"], ["build", "lint", "test"])
        self.assertEqual(
            [(item["id"], item["role"], item["harness"]) for item in request["invocations"]],
            [("implement", "implementer", "codex"),
             ("review-1", "reviewer", "claude"), ("review-2", "reviewer", "pi")],
        )
        self.assertEqual(request["invocations"][1]["permissions"]["filesystem"]["maximum"], "read-only")
        self.assertEqual(set(request), {
            "schema_version", "document_type", "task", "invocations", "verification_kinds",
            "readiness_minimum", "required_capabilities", "required_skills", "allowed_skills",
            "trust_profile", "trust_ceiling",
        })

    def test_default_permissions_and_review_count_follow_actual_stage(self):
        pattern = Pattern.from_dict({
            "name": "review", "description": "", "version": "1", "entry": "review",
            "stages": [{"id": "review", "kind": "review", "title": "review", "reviewers": 1}],
        })
        project = Project(Path("/repo"), ProjectConfig(reviewers=["pi", "claude"]))
        request = build_session_request(project, pattern, "Check patch", "codex", ["pi", "claude"])
        self.assertEqual([item["harness"] for item in request["invocations"]], ["codex", "pi"])
        self.assertEqual(request["invocations"][0]["permissions"]["network"]["maximum"], "off")
        self.assertEqual(request["invocations"][1]["permissions"]["filesystem"]["maximum"], "read-only")
        self.assertEqual(request["verification_kinds"], [])
