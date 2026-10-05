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
BRIDGE = ("AGENTFLOW_ROOT", "AGENTFLOW_WORKSPACE", "AGENTFLOW_RUN_ID")


def clean_env() -> dict:
    import os
    return {k: v for k, v in os.environ.items() if k not in BRIDGE}
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


class ControlRootTests(unittest.TestCase):
    def setUp(self):
        from agentflow.config import save_config
        self.tmp = Path(tempfile.mkdtemp(prefix="agentflow-root-")).resolve()
        self.primary, self.work, self.other = self.tmp / "primary", self.tmp / "work", self.tmp / "other"
        for d in (self.primary, self.work / "sub", self.other):
            d.mkdir(parents=True)
        save_config(self.primary, ProjectConfig())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def env(self, root):
        return patch.dict("os.environ", {"AGENTFLOW_ROOT": str(root), "AGENTFLOW_WORKSPACE": str(self.work)})

    def test_honoured_from_the_workspace_and_the_root(self):
        from agentflow.config import find_root
        with self.env(self.primary):
            self.assertEqual(find_root(self.work / "sub"), self.primary)
            self.assertEqual(find_root(self.primary), self.primary)

    def test_ignored_outside_the_run(self):
        from agentflow.config import find_root
        with self.env(self.primary):
            self.assertEqual(find_root(self.other), self.other)

    def test_an_uninitialized_root_is_an_error(self):
        from agentflow.config import find_root
        with self.env(self.other), self.assertRaisesRegex(FileNotFoundError, "not an initialized AgentFlow project"):
            find_root(self.work)


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

    def commit(self) -> None:
        git = ["git", "-C", str(self.root)]
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-qm", "agentflow"], check=True, capture_output=True)

    def use(self, **extra) -> None:
        """Install and commit a custom pattern (isolated runs start from the committed snapshot)."""
        (self.root / ".agentflow" / "patterns" / "custom.json").write_text(json.dumps({**FAST, "name": "custom", **extra}))
        self.commit()

    def new_run(self, executor: str = "claude"):
        p = load_pattern("custom", self.root)
        state = new_state("change", p.name, p.entry, executor, ["codex"], run_start_commit=head_commit(self.root))
        save_state(self.root, state)
        return state

    def run_pattern(self, fake: FakeAgentic, harness=None, start_commit: str | None = "head"):
        p = load_pattern("custom", self.root)
        commit = head_commit(self.root) if start_commit == "head" else start_commit
        state = new_state("change", p.name, p.entry, "claude", ["codex"], run_start_commit=commit)
        save_state(self.root, state)
        engine = Engine(load_project(self.root), state, agentic=fake)
        with patch("agentflow.engine.get_harness", return_value=harness if harness is not None else FakeHarness()):
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

    # -- run-start lifecycle --------------------------------------------------------------------

    def test_step_never_runs_a_stage_before_start_completed(self):
        # `agentflow step` on a fresh run (never started) must prepare it first: worktree, then readiness.
        self.use(requires={"readiness": "foundational"}, isolation={"mode": "worktree"})
        fake, harness = FakeAgentic(worktree_root=self.tmp / "trees"), FakeHarness()
        state = self.new_run()
        self.assertFalse(state.started)
        with patch("agentflow.engine.get_harness", return_value=harness):
            Engine(load_project(self.root), load_state(self.root), agentic=fake).step()
        state = load_state(self.root)
        self.assertTrue(state.started)
        self.assertEqual([c[0] for c in fake.requirement_calls], ["worktree-create", "readiness"])
        self.assertEqual(harness.seen[0]["root"], Path(state.worktree["path"]))
        self.assertFalse((self.root / "work.txt").exists())

    def test_step_on_an_unready_fresh_run_blocks_without_running_a_stage(self):
        self.use(requires={"readiness": "structured"})
        harness = FakeHarness()
        self.new_run()
        with patch("agentflow.engine.get_harness", return_value=harness):
            status = Engine(load_project(self.root), load_state(self.root),
                            agentic=FakeAgentic(readiness_passed=False)).step()
        self.assertEqual((status, harness.seen), ("blocked", []))

    def test_interrupted_start_reuses_its_recorded_worktree(self):
        self.use(isolation={"mode": "worktree"})
        fake = FakeAgentic(worktree_root=self.tmp / "trees")
        state = self.new_run()
        Engine(load_project(self.root), state, agentic=fake)._ensure_worktree()  # crash before `started`
        self.assertFalse(load_state(self.root).started)
        resumed = Engine(load_project(self.root), load_state(self.root), agentic=fake)
        self.assertEqual(resumed.start(), "running")
        self.assertEqual([c[0] for c in fake.requirement_calls], ["worktree-create"])
        self.assertTrue(load_state(self.root).started)

    def test_interrupted_start_adopts_an_unrecorded_worktree_of_its_own(self):
        self.use(isolation={"mode": "worktree"})
        fake = FakeAgentic(worktree_root=self.tmp / "trees")
        state = self.new_run()
        # Created by Agentic Dev, but AgentFlow was interrupted before recording it.
        fake.create_worktree(self.root, name=f"agentflow-{state.run_id}", branch=f"agentflow/{state.run_id}",
                             base=state.run_start_commit)
        engine = Engine(load_project(self.root), load_state(self.root), agentic=fake)
        self.assertEqual(engine.start(), "running")
        state = load_state(self.root)
        self.assertEqual(state.worktree["path"], fake.worktrees[f"agentflow-{state.run_id}"]["worktree"])
        self.assertTrue(any(h["event"] == "worktree_adopted" for h in state.history))
        out = subprocess.run(["git", "-C", str(self.root), "worktree", "list"], capture_output=True, text=True,
                             check=True).stdout
        self.assertEqual(len(out.splitlines()), 2)  # primary + exactly one run worktree

    def test_dirty_primary_checkout_blocks_isolation_and_changes_nothing(self):
        self.use(isolation={"mode": "worktree"})
        (self.root / "seed.txt").write_text("edited, not committed")
        (self.root / "new_module.py").write_text("x = 1\n")
        before = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain"], capture_output=True,
                                text=True, check=True).stdout
        fake = FakeAgentic(worktree_root=self.tmp / "trees")
        status, state = self.run_pattern(fake)
        self.assertEqual(status, "blocked")
        self.assertIn("starts from the committed run-start snapshot; commit or stash", state.awaiting_reason)
        self.assertIn("seed.txt", state.awaiting_reason)
        self.assertIn("new_module.py", state.awaiting_reason)
        self.assertEqual((fake.requirement_calls, state.worktree), ([], None))
        after = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain"], capture_output=True,
                               text=True, check=True).stdout
        self.assertEqual(after, before)  # nothing copied, stashed, or committed

    def test_a_dirty_checkout_is_fine_without_isolation(self):
        self.use()
        (self.root / "seed.txt").write_text("edited, not committed")
        self.assertEqual(self.run_pattern(FakeAgentic())[0], "complete")

    def test_dry_run_saves_nothing(self):
        import contextlib
        import io
        import os
        from agentflow import cli
        self.use(requires={"readiness": "foundational"}, isolation={"mode": "worktree"})
        state_file = self.root / ".agentflow" / "state.json"
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            fake = FakeAgentic()
            with patch("agentflow.cli.Agentic", return_value=fake), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cli.main(["run", "first", "--pattern", "custom", "--dry-run"]), 0)
            self.assertFalse(state_file.exists())
            self.assertIn("nothing was saved", out.getvalue())
            self.assertIn(f"plan_digest={fake.session_digest}", out.getvalue())
            self.new_run()
            existing = state_file.read_bytes()
            with patch("agentflow.cli.Agentic", return_value=fake), contextlib.redirect_stdout(io.StringIO()):
                cli.main(["run", "second", "--pattern", "custom", "--dry-run"])
            self.assertEqual(state_file.read_bytes(), existing)
        finally:
            os.chdir(cwd)
        self.assertEqual(len(subprocess.run(["git", "-C", str(self.root), "worktree", "list"], capture_output=True,
                                            text=True, check=True).stdout.splitlines()), 1)

    def test_blocked_session_plan_creates_no_run_or_worktree(self):
        import contextlib
        import io
        import os
        from agentflow import cli

        self.use(isolation={"mode": "worktree"})
        fake = FakeAgentic(session_status="blocked")
        old = os.getcwd()
        os.chdir(self.root)
        try:
            with patch("agentflow.cli.Agentic", return_value=fake), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cli.main(["run", "blocked", "--pattern", "custom"]), 2)
            self.assertIn("permission-unenforceable", out.getvalue())
            self.assertFalse((self.root / ".agentflow" / "state.json").exists())
            self.assertEqual(len(subprocess.run(["git", "-C", str(self.root), "worktree", "list"],
                                                capture_output=True, text=True, check=True).stdout.splitlines()), 1)
            self.assertEqual([call[0] for call in fake.session_calls], ["plan"])
        finally:
            os.chdir(old)

    # -- control-root bridge -------------------------------------------------------------------

    def test_isolated_harnesses_get_the_control_root_and_absolute_evidence_paths(self):
        self.use(isolation={"mode": "worktree"})
        harness = FakeHarness()
        _, state = self.run_pattern(FakeAgentic(status="failed", worktree_root=self.tmp / "trees"), harness)
        tree = Path(state.worktree["path"])
        self.assertEqual(harness.seen[0]["env"], {"AGENTFLOW_ROOT": str(self.root.resolve()),
                                                  "AGENTFLOW_WORKSPACE": str(tree), "AGENTFLOW_RUN_ID": state.run_id})
        second = harness.seen[1]["prompt"]  # the retry after a failed gate lists prior evidence
        paths = [line.split(": ", 1)[1] for line in second.splitlines() if line.startswith(("- agent: ", "- gates: "))]
        self.assertTrue(paths)
        for path in paths:
            self.assertTrue(Path(path).is_absolute() and Path(path).exists(), path)
        self.assertIn(f"AgentFlow state and evidence live in {self.root.resolve()}", second)

    def test_status_from_inside_the_worktree_reaches_the_primary_run(self):
        # A real child process, launched by AgentFlow's own harness adapter in the worktree.
        from agentflow.config import save_config
        probe = (f"PYTHONPATH={SRC.parent} {sys.executable} -m agentflow.cli status; echo cwd=$(pwd -P)")
        config = load_project(self.root).config
        config.harness = {"probe": {"command": ["sh", "-c", probe, "{prompt}"]}}
        save_config(self.root, config)
        self.use(isolation={"mode": "worktree"})
        fake = FakeAgentic(worktree_root=self.tmp / "trees")
        state = self.new_run(executor="probe")
        engine = Engine(load_project(self.root), state, agentic=fake)
        with patch.dict("os.environ", clean_env(), clear=True):
            engine.step()
        state = load_state(self.root)
        evidence = json.loads((self.root / next(e["path"] for e in state.evidence if e["kind"] == "agent")).read_text())
        self.assertIn(f"run:       {state.run_id}", evidence["stdout"])
        self.assertIn(f"worktree:  {state.worktree['path']}", evidence["stdout"])
        self.assertIn(f"cwd={Path(state.worktree['path']).resolve()}", evidence["stdout"])
        # Without the bridge, the same command in the worktree finds no run (control check).
        lost = subprocess.run([sys.executable, "-m", "agentflow.cli", "status"], cwd=state.worktree["path"],
                              env={**clean_env(), "PYTHONPATH": str(SRC.parent)}, capture_output=True, text=True,
                              check=False)
        self.assertNotEqual(lost.returncode, 0)
        self.assertIn("No active Agentflow run", lost.stderr)

    def test_metrics_unavailable_is_recorded_once_per_run_across_invocations(self):
        self.use()
        fake = FakeAgentic(metrics_error="installed `agentic` lacks metric-record@1")
        self.new_run()
        with patch("agentflow.engine.get_harness", return_value=FakeHarness()):
            for _ in range(2):  # two separate `agentflow step` invocations
                Engine(load_project(self.root), load_state(self.root), agentic=fake).step()
        state = load_state(self.root)
        self.assertEqual(state.status, "complete")
        self.assertEqual(len(self.events(state, "metrics_unavailable")), 1)

    def test_metrics_problems_never_change_the_outcome(self):
        self.use()
        status, state = self.run_pattern(FakeAgentic(metrics_error="installed `agentic` lacks metric-record@1"))
        self.assertEqual(status, "complete")
        self.assertEqual(len(self.events(state, "metrics_unavailable")), 1)


if __name__ == "__main__":
    unittest.main()
