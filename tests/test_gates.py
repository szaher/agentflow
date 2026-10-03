import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fakes import FakeAgentic  # noqa: E402

from agentflow.agentic import Agentic, AgenticError, AgenticUnavailable, REQUIRED_FEATURES  # noqa: E402
from agentflow.gates import PROFILE_KINDS, plan_gate, run_gates  # noqa: E402
from agentflow.models import ProjectConfig  # noqa: E402


class GateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_profiles_request_only_discovered_kinds(self):
        fake = FakeAgentic(kinds={"test", "build", "install"})
        gate = run_gates(self.root, ProjectConfig(), "standard", agentic=fake)
        self.assertEqual(fake.calls[0]["kinds"], ["test", "build"])
        self.assertEqual((gate.status, gate.passed), ("passed", True))
        self.assertEqual([r.name for r in gate.results], ["test", "build"])
        self.assertEqual(PROFILE_KINDS["fast"], ("lint", "test"))

    def test_explicit_gates_replace_discovery_but_still_run_through_agentic(self):
        fake = FakeAgentic(kinds=set())
        gate = run_gates(self.root, ProjectConfig(gates={"fast": ["make e2e"]}), "fast", agentic=fake)
        self.assertEqual(fake.calls, [{"kinds": [], "commands": ["make e2e"], "include_changed": False, "base": None}])
        self.assertEqual(gate.results[0].command, "make e2e")

    def test_nothing_to_run_fails_without_calling_verify(self):
        fake = FakeAgentic(kinds={"format", "install"})
        gate = run_gates(self.root, ProjectConfig(), "fast", agentic=fake)
        self.assertEqual((gate.status, gate.passed, fake.calls), ("no-checks", False, []))
        self.assertIn("gates.fast", gate.reason)

    def test_no_checks_and_failures_never_pass(self):
        for status, missing in (("no-checks", ["test"]), ("failed", [])):
            with self.subTest(status):
                gate = run_gates(self.root, ProjectConfig(), "fast",
                                 agentic=FakeAgentic(status=status, missing=missing))
                self.assertFalse(gate.passed)
                self.assertEqual(gate.status, status)
        missing = run_gates(self.root, ProjectConfig(), "fast", agentic=FakeAgentic(status="no-checks", missing=["test"]))
        self.assertEqual((missing.reason, missing.results), ("no runnable command for: test", []))

    def test_change_aware_augmentation_passes_the_run_base(self):
        fake = FakeAgentic()
        run_gates(self.root, ProjectConfig(), "fast", agentic=fake, include_changed=True, base="abc123")
        self.assertEqual((fake.calls[0]["include_changed"], fake.calls[0]["base"]), (True, "abc123"))

    def test_unknown_profile(self):
        with self.assertRaises(ValueError):
            plan_gate(self.root, ProjectConfig(), "paranoid", agentic=FakeAgentic())


def fake_cli(directory: Path, contracts: dict, verify: dict | None = None, verify_exit: int = 0) -> str:
    """A stand-in `agentic` executable answering with canned JSON."""

    script = directory / "agentic"
    script.write_text(f"""#!{sys.executable}
import json, sys
args = sys.argv[1:]
if args[:1] == ["contracts"]:
    print(json.dumps({json.dumps(contracts)!s})); sys.exit(0)
if args[:2] == ["verify", "run"]:
    print(json.dumps({json.dumps(verify or {})!s})); sys.exit({verify_exit})
sys.exit(2)
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


GOOD_CONTRACTS = {
    "schema_version": "1", "document_type": "agentic.contracts",
    "contracts": {"contracts": ["1"], "repo-inspection": ["1"], "verification-run": ["1"]},
    "features": [*REQUIRED_FEATURES, "verification.change-aware"],
}


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_missing_binary_is_unavailable_with_an_install_hint(self):
        with self.assertRaisesRegex(AgenticUnavailable, "install Agentic Dev"):
            Agentic(executable=str(self.dir / "nope")).handshake()

    def test_handshake_requires_contracts_and_features_not_versions(self):
        self.assertEqual(Agentic(fake_cli(self.dir, GOOD_CONTRACTS)).handshake()["document_type"], "agentic.contracts")
        lacking = {**GOOD_CONTRACTS, "features": ["commands.canonical-discovery"], "agentic_version": "99.0.0"}
        with self.assertRaisesRegex(AgenticUnavailable, "verification.no-checks-status"):
            Agentic(fake_cli(self.dir, lacking)).handshake()
        old = {**GOOD_CONTRACTS, "contracts": {"contracts": ["1"], "repo-inspection": ["1"]}}
        with self.assertRaisesRegex(AgenticUnavailable, "verification-run@1"):
            Agentic(fake_cli(self.dir, old)).handshake()

    def test_verify_accepts_exit_one_and_checks_it_matches_the_status(self):
        failed = {"document_type": "agentic.verification-run", "status": "failed", "results": []}
        self.assertEqual(Agentic(fake_cli(self.dir, GOOD_CONTRACTS, failed, 1)).verify(
            self.dir, kinds=["test"], commands=[])["status"], "failed")
        with self.assertRaisesRegex(AgenticError, "disagrees"):
            Agentic(fake_cli(self.dir, GOOD_CONTRACTS, failed, 0)).verify(self.dir, kinds=["test"], commands=[])
        with self.assertRaises(AgenticError):
            Agentic(fake_cli(self.dir, GOOD_CONTRACTS, {"document_type": "x"}, 0)).verify(
                self.dir, kinds=["test"], commands=[])

    def test_environment_override(self):
        os.environ["AGENTFLOW_AGENTIC"] = "/custom/agentic"
        try:
            self.assertEqual(Agentic().executable, "/custom/agentic")
        finally:
            del os.environ["AGENTFLOW_AGENTIC"]


if __name__ == "__main__":
    unittest.main()
