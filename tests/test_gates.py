import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fakes import GOOD_CONTRACTS, FakeAgentic, fake_cli, logged_calls, verification_document  # noqa: E402

import agentflow  # noqa: E402
from agentflow import gates  # noqa: E402
from agentflow.agentic import Agentic, AgenticError, AgenticUnavailable  # noqa: E402
from agentflow.gates import PROFILE_KINDS, plan_gate, run_gates  # noqa: E402
from agentflow.models import ProjectConfig  # noqa: E402

SRC = Path(agentflow.__file__).resolve().parent


class GateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_profiles_are_kinds_not_commands(self):
        self.assertEqual(PROFILE_KINDS, {"fast": ("lint", "test"), "standard": ("lint", "typecheck", "test"),
                                         "strict": ("build", "lint", "typecheck", "test")})

    def test_profile_kinds_are_intersected_with_discovered_kinds(self):
        fake = FakeAgentic(kinds={"test", "build", "install"})
        run_gates(self.root, ProjectConfig(), "standard", agentic=fake)
        run_gates(self.root, ProjectConfig(), "strict", agentic=fake)
        self.assertEqual([c["kinds"] for c in fake.calls], [["test"], ["build", "test"]])

    def test_custom_gates_travel_through_agentic_as_commands(self):
        fake = FakeAgentic(kinds=set())
        gate = run_gates(self.root, ProjectConfig(gates={"fast": ["make e2e", "make smoke"]}), "fast", agentic=fake)
        self.assertEqual(fake.calls, [{"kinds": [], "commands": ["make e2e", "make smoke"],
                                       "include_changed": False, "base": None}])
        self.assertEqual([r["command"] for r in gate.results], ["make e2e", "make smoke"])

    def test_nothing_to_run_fails_closed_without_calling_verify(self):
        fake = FakeAgentic(kinds={"format", "install"})
        gate = run_gates(self.root, ProjectConfig(), "fast", agentic=fake)
        self.assertEqual((gate.status, gate.passed, gate.verification, fake.calls), ("no-checks", False, None, []))

    def test_status_is_authoritative(self):
        for status, missing in (("no-checks", ["test"]), ("failed", [])):
            with self.subTest(status):
                gate = run_gates(self.root, ProjectConfig(), "fast", agentic=FakeAgentic(status=status, missing=missing))
                self.assertEqual((gate.status, gate.passed), (status, False))
        # A document claiming success without status=passed does not pass.
        fake = FakeAgentic()
        fake.verify = lambda *a, **k: {**verification_document("failed", ["test"]), "success": True}
        self.assertFalse(run_gates(self.root, ProjectConfig(), "fast", agentic=fake).passed)

    def test_the_verification_document_is_kept_whole(self):
        gate = run_gates(self.root, ProjectConfig(), "fast", agentic=FakeAgentic())
        self.assertEqual(gate.verification, verification_document("passed", ["lint", "test"]))

    def test_change_aware_augmentation_passes_the_base(self):
        fake = FakeAgentic()
        run_gates(self.root, ProjectConfig(), "fast", agentic=fake, include_changed=True, base="abc123")
        self.assertEqual((fake.calls[0]["include_changed"], fake.calls[0]["base"]), (True, "abc123"))

    def test_unknown_profile(self):
        with self.assertRaises(ValueError):
            plan_gate(self.root, ProjectConfig(), "paranoid", agentic=FakeAgentic())


class BoundaryTests(unittest.TestCase):
    """AgentFlow must not grow its own repository command detector or gate shell again."""

    def test_no_command_detector_or_shell_execution_in_agentflow(self):
        self.assertFalse(hasattr(gates, "detected_commands"))
        self.assertFalse(hasattr(gates, "commands_for"))
        markers = ("package.json", "pyproject.toml", "go.mod", "Cargo.toml", "Makefile", "pnpm-lock.yaml")
        for path in SRC.rglob("*.py"):
            text = path.read_text()
            for marker in markers:
                self.assertNotIn(f'"{marker}"', text, f"{path.name} inspects {marker}")
        tree = ast.parse((SRC / "gates.py").read_text())
        imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
                    for alias in node.names}
        self.assertNotIn("run_command", imported)
        self.assertNotIn("subprocess", (SRC / "gates.py").read_text())

    def test_no_cross_project_imports(self):
        for path in SRC.rglob("*.py"):
            self.assertNotIn("agentic_dev", path.read_text(), path.name)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_missing_binary_fails_clearly(self):
        with self.assertRaisesRegex(AgenticUnavailable, "install Agentic Dev"):
            Agentic(executable=str(self.dir / "nope")).handshake()

    def test_incompatible_handshake_fails_before_any_verification(self):
        lacking = {**GOOD_CONTRACTS, "features": ["commands.canonical-discovery"], "agentic_version": "99.0.0"}
        cli = fake_cli(self.dir, contracts=lacking)
        with self.assertRaisesRegex(AgenticUnavailable, "verification.no-checks-status"):
            Agentic(cli).verify(self.dir, kinds=["test"], commands=[])
        self.assertFalse(any(call[:2] == ["verify", "run"] for call in logged_calls(self.dir)))
        old = {**GOOD_CONTRACTS, "contracts": {"contracts": ["1"], "repo-inspection": ["1"]}}
        with self.assertRaisesRegex(AgenticUnavailable, "verification-run@1"):
            Agentic(fake_cli(Path(tempfile.mkdtemp()), contracts=old)).handshake()

    def test_never_reads_the_version(self):
        Agentic(fake_cli(self.dir)).handshake()
        self.assertFalse(any("--version" in call for call in logged_calls(self.dir)))

    def test_schema_invalid_documents_fail_closed(self):
        bad_verify = {"document_type": "agentic.verification-run", "status": "maybe", "success": True, "results": []}
        with self.assertRaisesRegex(AgenticError, "invalid verification-run document"):
            Agentic(fake_cli(self.dir, verify=bad_verify)).verify(self.dir, kinds=["test"], commands=[])
        bad_inspection = {"document_type": "agentic.repo-inspection"}
        with self.assertRaisesRegex(AgenticError, "invalid repo-inspection document"):
            Agentic(fake_cli(Path(tempfile.mkdtemp()), inspection=bad_inspection)).discovered_kinds(self.dir)

    def test_exit_code_must_agree_with_status(self):
        failed = verification_document("failed", ["test"])
        self.assertEqual(Agentic(fake_cli(self.dir, verify=failed, verify_exit=1)).verify(
            self.dir, kinds=["test"], commands=[])["status"], "failed")
        with self.assertRaisesRegex(AgenticError, "disagrees"):
            Agentic(fake_cli(Path(tempfile.mkdtemp()), verify=failed, verify_exit=0)).verify(
                self.dir, kinds=["test"], commands=[])

    def test_argv_not_shell(self):
        Agentic(fake_cli(self.dir)).verify(self.dir, kinds=["test"], commands=["echo a; rm -rf /"],
                                           include_changed=True, base="abc")
        call = next(c for c in logged_calls(self.dir) if c[:2] == ["verify", "run"])
        self.assertEqual(call[call.index("--command") + 1], "echo a; rm -rf /")
        self.assertEqual(call[-3:], ["--include-changed", "--base", "abc"])

    def test_environment_override(self):
        os.environ["AGENTFLOW_AGENTIC"] = "/custom/agentic"
        try:
            self.assertEqual(Agentic().executable, "/custom/agentic")
        finally:
            del os.environ["AGENTFLOW_AGENTIC"]


if __name__ == "__main__":
    unittest.main()
