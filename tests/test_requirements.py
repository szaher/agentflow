"""Pattern requirements (v0.16 slice 4): preconditions, verification minimum, worktree isolation, metrics."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fakes import FakeAgentic  # noqa: E402
from test_engine import FakeHarness  # noqa: E402

import agentflow  # noqa: E402
from agentflow.bootstrap import init_project  # noqa: E402
from agentflow.config import load_project  # noqa: E402
from agentflow.engine import Engine  # noqa: E402
from agentflow.gates import plan_gate  # noqa: E402
from agentflow.git import head_commit  # noqa: E402
from agentflow.models import Pattern, ProjectConfig  # noqa: E402
from agentflow.patterns import list_patterns, load_pattern, validate_pattern  # noqa: E402
from agentflow.requirements import requirements  # noqa: E402
from agentflow.state import load_state, new_state, save_state  # noqa: E402

SRC = Path(agentflow.__file__).resolve().parent
FAST = json.loads((SRC / "builtin_patterns" / "fast.json").read_text())


def pattern(**extra) -> Pattern:
    return Pattern.from_dict({**FAST, "name": "custom", **extra})


class PatternRequirementTests(unittest.TestCase):
    def test_requirements_are_off_by_default_and_builtins_declare_none(self):
        self.assertEqual(requirements(pattern()).describe(), [])
        for builtin in list_patterns():
            reqs = requirements(builtin)
            self.assertFalse(reqs.worktree or reqs.readiness or reqs.capabilities or reqs.minimum, builtin.name)

    def test_full_declaration(self):
        reqs = requirements(pattern(requires={"readiness": "foundational", "capabilities": ["sast", "sast"]},
                                    verification={"minimum": ["test"]},
                                    isolation={"mode": "worktree", "cleanup": "on-success"}))
        self.assertEqual((reqs.readiness, reqs.capabilities, reqs.minimum, reqs.worktree, reqs.cleanup_on_success),
                         ("foundational", ("sast",), ("test",), True, True))

    def test_malformed_requirements_fail_validation(self):
        for label, extra in (
            ("typo", {"requires": {"readyness": "foundational"}}),
            ("bad mode", {"isolation": {"mode": "container"}}),
            ("cleanup without worktree", {"isolation": {"cleanup": "on-success"}}),
            ("capabilities not a list", {"requires": {"capabilities": "sast"}}),
            ("empty kind", {"verification": {"minimum": [""]}}),
            ("empty level", {"requires": {"readiness": ""}}),
        ):
            with self.subTest(label), self.assertRaises(ValueError):
                validate_pattern(pattern(**extra))


class VerificationMinimumTests(unittest.TestCase):
    def test_minimum_adds_to_the_profile_without_duplicates(self):
        plan = plan_gate(Path("."), ProjectConfig(), "fast", agentic=FakeAgentic(), minimum=("test", "build"))
        self.assertEqual((plan.kinds, plan.commands), (["lint", "test", "build"], []))

    def test_custom_commands_never_drop_the_minimum(self):
        config = ProjectConfig(gates={"fast": ["make e2e"]})
        plan = plan_gate(Path("."), config, "fast", agentic=FakeAgentic(), minimum=("test",))
        self.assertEqual((plan.kinds, plan.commands), (["test"], ["make e2e"]))


class RunRequirementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agentflow-req-"))
        self.root = self.tmp / "repo"
        self.root.mkdir()
        git = ["git", "-C", str(self.root)]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "config", "user.email", "t@example.com"], check=True)
        subprocess.run([*git, "config", "user.name", "T"], check=True)
        (self.root / "seed.txt").write_text("seed")
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-qm", "seed"], check=True)
        init_project(self.root, ProjectConfig(pattern="fast"), agentic=FakeAgentic())

    def tearDown(self):
        subprocess.run(["git", "-C", str(self.root), "worktree", "prune"], capture_output=True, check=False)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def use(self, **extra) -> None:
        (self.root / ".agentflow" / "patterns" / "custom.json").write_text(json.dumps({**FAST, "name": "custom", **extra}))

    def run_pattern(self, fake: FakeAgentic, harness=None, start_commit: str | None = "head"):
        p = load_pattern("custom", self.root)
        commit = head_commit(self.root) if start_commit == "head" else start_commit
        state = new_state("change", p.name, p.entry, "claude", ["codex"], run_start_commit=commit)
        save_state(self.root, state)
        engine = Engine(load_project(self.root), state, agentic=fake)
        with patch("agentflow.engine.get_harness", return_value=harness or FakeHarness()):
            status = engine.start()
            if status == "running":
                status = engine.run(max_steps=20)
        return status, load_state(self.root)

    def events(self, state, name):
        return [h for h in state.history if h["event"] == name]

    def test_worktree_comes_first_then_preconditions_in_it_then_stages_there(self):
        self.use(requires={"readiness": "foundational", "capabilities": ["sast"]},
                 isolation={"mode": "worktree"})
        fake = FakeAgentic(capability_state={"sast": True}, worktree_root=self.tmp / "trees")
        status, state = self.run_pattern(fake)
        self.assertEqual(status, "complete")
        tree = Path(state.worktree["path"])
        self.assertEqual([call[0] for call in fake.requirement_calls], ["worktree-create", "readiness", "capabilities"])
        self.assertEqual(fake.requirement_calls[0][1:], (f"agentflow-{state.run_id}", f"agentflow/{state.run_id}",
                                                         state.run_start_commit))
        self.assertEqual(fake.requirement_calls[1], ("readiness", str(tree), "foundational"))
        # The work happened in the worktree; the user's checkout is untouched and still holds state and evidence.
        self.assertTrue((tree / "work.txt").exists())
        self.assertFalse((self.root / "work.txt").exists())
        self.assertTrue((self.root / ".agentflow" / "state.json").exists())
        self.assertTrue(all((self.root / e["path"]).exists() for e in state.evidence))
        self.assertFalse(state.worktree["cleaned"])  # cleanup is opt-in
        self.assertEqual(fake.requirement_calls[-1][0], "capabilities")

    def test_failed_readiness_blocks_before_any_stage_and_never_remediates(self):
        self.use(requires={"readiness": "structured"}, isolation={"mode": "worktree"})
        fake = FakeAgentic(readiness_passed=False, worktree_root=self.tmp / "trees")
        status, state = self.run_pattern(fake)
        self.assertEqual(status, "blocked")
        self.assertIn("readiness structured not met (current unaware)", state.awaiting_reason)
        self.assertIn("context.readme.setup", state.awaiting_reason)
        self.assertEqual(state.attempts_by_stage, {})
        self.assertEqual(fake.calls, [])
        self.assertTrue(Path(state.worktree["path"]).is_dir())  # a blocked run keeps its worktree
        evidence = next(e for e in state.evidence if e["kind"] == "precondition")
        self.assertEqual((evidence["name"], evidence["passed"]), ("readiness", False))
        for path in SRC.rglob("*.py"):
            self.assertNotIn('"ready", "make"', path.read_text(), path.name)

    def test_capabilities_must_exist_and_be_enabled(self):
        self.use(requires={"capabilities": ["sast", "browser-agent", "nope"]})
        status, state = self.run_pattern(FakeAgentic(capability_state={"sast": True, "browser-agent": False}))
        self.assertEqual(status, "blocked")
        self.assertIn("unknown capability: nope", state.awaiting_reason)
        self.assertIn("capability not enabled: browser-agent", state.awaiting_reason)

    def test_unavailable_preconditions_block(self):
        self.use(requires={"readiness": "foundational"})
        status, state = self.run_pattern(FakeAgentic(unavailable="installed `agentic` lacks readiness-verification@1"))
        self.assertEqual(status, "blocked")
        self.assertIn("preconditions could not be checked", state.awaiting_reason)

    def test_failed_run_keeps_its_worktree_and_cleanup_is_never_forced(self):
        self.use(isolation={"mode": "worktree", "cleanup": "on-success"})
        fake = FakeAgentic(status="failed", worktree_root=self.tmp / "trees")
        status, state = self.run_pattern(fake)
        self.assertEqual(status, "blocked")
        self.assertTrue(Path(state.worktree["path"]).is_dir())
        self.assertNotIn("worktree-clean", [c[0] for c in fake.requirement_calls])

    def test_cleanup_on_success_asks_agentic_and_keeps_a_refused_worktree(self):
        self.use(isolation={"mode": "worktree", "cleanup": "on-success"})
        cleaned = FakeAgentic(worktree_root=self.tmp / "a")
        status, state = self.run_pattern(cleaned)
        self.assertEqual((status, state.worktree["cleaned"]), ("complete", True))
        self.assertEqual(cleaned.requirement_calls[-1], ("worktree-clean", state.worktree["name"]))
        refused = FakeAgentic(worktree_root=self.tmp / "b", clean_error="worktree has uncommitted changes")
        status, state = self.run_pattern(refused)
        self.assertEqual((status, state.worktree["cleaned"]), ("complete", False))
        self.assertIn("uncommitted", self.events(state, "worktree_kept")[0]["reason"])

    def test_worktree_isolation_needs_a_start_commit(self):
        self.use(isolation={"mode": "worktree"})
        status, state = self.run_pattern(FakeAgentic(), start_commit=None)
        self.assertEqual(status, "blocked")
        self.assertIn("needs a commit", state.awaiting_reason)

    def test_a_missing_worktree_blocks_instead_of_running_elsewhere(self):
        self.use(isolation={"mode": "worktree"})
        fake = FakeAgentic(worktree_root=self.tmp / "trees")
        p = load_pattern("custom", self.root)
        state = new_state("change", p.name, p.entry, "claude", [], run_start_commit=head_commit(self.root))
        engine = Engine(load_project(self.root), state, agentic=fake)
        engine.start()
        subprocess.run(["git", "-C", str(self.root), "worktree", "remove", "--force", state.worktree["path"]], check=True)
        with patch("agentflow.engine.get_harness", return_value=FakeHarness()):
            self.assertEqual(engine.run(), "blocked")
        self.assertIn("worktree is missing", engine.state.awaiting_reason)
        self.assertFalse((self.root / "work.txt").exists())

    def test_minimum_reaches_workflow_gates(self):
        self.use(verification={"minimum": ["typecheck"]})
        fake = FakeAgentic(kinds={"lint", "test", "typecheck"})
        self.run_pattern(fake)
        self.assertEqual(fake.calls[0]["kinds"], ["lint", "test", "typecheck"])

    def test_one_stage_metric_per_executed_stage(self):
        self.use()
        fake = FakeAgentic()
        _, state = self.run_pattern(fake)
        self.assertEqual([(m["event"], m["stage"], m["kind"], m["outcome"]) for m in fake.metrics],
                         [("agentflow.stage", "implement", "agent", "succeeded"),
                          ("agentflow.stage", "verify", "gate", "passed")])
        self.assertTrue(all(m["session_id"] == state.run_id and m["pattern"] == "custom" for m in fake.metrics))

    def test_metrics_problems_never_change_the_outcome(self):
        self.use()
        status, state = self.run_pattern(FakeAgentic(metrics_error="installed `agentic` lacks metric-record@1"))
        self.assertEqual(status, "complete")
        self.assertEqual(len(self.events(state, "metrics_unavailable")), 1)


if __name__ == "__main__":
    unittest.main()
