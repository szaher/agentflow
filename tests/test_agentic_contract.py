"""Contract tests against the real, installed Agentic Dev CLI (no imports across projects).

Every document AgentFlow consumes is validated against the schema the installed
`agentic` ships (`agentic contracts schema NAME`). Locally the tests skip when
`agentic` or jsonschema is missing; CI sets AGENTFLOW_REQUIRE_AGENTIC=1 so a
missing prerequisite fails instead of skipping.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from agentflow.agentic import Agentic, AgenticError
from agentflow.gates import run_gates
from agentflow.models import ProjectConfig

AGENTIC = os.environ.get("AGENTFLOW_AGENTIC") or shutil.which("agentic")
REQUIRED = os.environ.get("AGENTFLOW_REQUIRE_AGENTIC") == "1"
try:
    import jsonschema
except ImportError:  # test-only dependency
    jsonschema = None

if REQUIRED and (not AGENTIC or jsonschema is None):
    raise RuntimeError("AGENTFLOW_REQUIRE_AGENTIC=1 but `agentic` or jsonschema is not installed")


@unittest.skipUnless(AGENTIC and jsonschema, "needs an installed `agentic` and jsonschema")
class AgenticContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agentflow-contract-"))
        self.env_backup = os.environ.get("AGENTIC_DEV_CONFIG_DIR")
        os.environ["AGENTIC_DEV_CONFIG_DIR"] = str(self.tmp / "config")
        self.agentic = Agentic(AGENTIC)

    def tearDown(self):
        if self.env_backup is None:
            os.environ.pop("AGENTIC_DEV_CONFIG_DIR", None)
        else:
            os.environ["AGENTIC_DEV_CONFIG_DIR"] = self.env_backup
        shutil.rmtree(self.tmp, ignore_errors=True)

    def repo(self, files: dict[str, str]) -> Path:
        root = self.tmp / "repo"
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        for name, text in files.items():
            (root / name).write_text(text)
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "init"], check=True)
        return root

    def schema(self, name: str) -> dict:
        out = subprocess.run([AGENTIC, "contracts", "schema", name], check=True, capture_output=True, text=True)
        return json.loads(out.stdout)

    def test_handshake(self):
        document = self.agentic.handshake()
        jsonschema.validate(document, self.schema("contracts"))

    def test_session_plan_contract_is_consumed_fail_closed(self):
        root = self.repo({"README.md": "# session\n", "app.py": "print(1)\n"})
        request = {
            "schema_version": "1",
            "document_type": "agentic.session-request",
            "task": "Fix the app",
            "invocations": [
                {"id": "implement", "role": "implementer", "harness": "codex"}
            ],
        }
        before = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        plan = self.agentic.plan_session(root, request)
        jsonschema.validate(request, self.schema("session-request"))
        jsonschema.validate(plan, self.schema("session-plan"))
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["request"]["task"], "Fix the app")
        self.assertTrue(plan["plan_digest"])
        self.assertTrue(
            any(item["code"] == "permission-unenforceable" for item in plan["blockers"])
        )
        self.assertEqual(
            subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout,
            before,
        )
        with self.assertRaises(AgenticError):
            self.agentic.prepare_session(root, plan)

    def test_a_missing_required_kind_fails_and_executes_nothing(self):
        # `fast` requires lint + test; the repo only has `make check` (test). Discovery must not weaken that.
        root = self.repo({"README.md": "# x\n", "app.py": "print(1)\n",
                          "Makefile": "check:\n\ttouch ran-make-check\n"})
        gate = run_gates(root, ProjectConfig(), "fast", agentic=self.agentic)
        jsonschema.validate(gate.verification, self.schema("verification-run"))
        self.assertEqual(gate.plan.kinds, ["lint", "test"])
        self.assertEqual((gate.status, gate.passed), ("no-checks", False))
        self.assertEqual((gate.verification["missing_kinds"], gate.verification["checks_executed"], gate.results),
                         (["lint"], 0, []))
        self.assertFalse((root / "ran-make-check").exists())

    def test_explicit_gate_failure_and_change_aware_augmentation(self):
        root = self.repo({"README.md": "# x\n", "Makefile": "test:\n\ttrue\nlint:\n\ttrue\n", "app.py": "x = 1\n"})
        base = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        failed = run_gates(root, ProjectConfig(gates={"fast": ["exit 3"]}), "fast", agentic=self.agentic)
        jsonschema.validate(failed.verification, self.schema("verification-run"))
        self.assertEqual((failed.status, failed.results[0]["returncode"], failed.results[0]["kind"]),
                         ("failed", 3, "custom"))

        (root / "app.py").write_text("x = 2\n")
        augmented = run_gates(root, ProjectConfig(), "fast", agentic=self.agentic, include_changed=True, base=base)
        jsonschema.validate(augmented.verification, self.schema("verification-run"))
        self.assertEqual(augmented.status, "passed")
        self.assertEqual(augmented.verification["requested_kinds"], ["test", "lint"])

    @unittest.skipUnless(shutil.which("npm") or REQUIRED, "needs npm")
    def test_every_command_of_each_required_kind_runs_once_all_kinds_exist(self):
        root = self.repo({"README.md": "# x\n", "app.py": "x = 1\n",
                          "Makefile": "test:\n\ttouch ran-make-test\nlint:\n\ttouch ran-make-lint\n",
                          "package.json": json.dumps({"scripts": {"test": "node -e \"require('fs').writeFileSync('ran-npm','')\""}})})
        gate = run_gates(root, ProjectConfig(), "fast", agentic=self.agentic)
        jsonschema.validate(gate.verification, self.schema("verification-run"))
        self.assertEqual((gate.status, gate.verification["missing_kinds"]), ("passed", []))
        self.assertEqual([(r["kind"], r["command"]) for r in gate.results],
                         [("test", "make test"), ("test", "npm run test"), ("lint", "make lint")])
        for marker in ("ran-make-test", "ran-npm", "ran-make-lint"):
            self.assertTrue((root / marker).exists(), marker)

    def test_no_discovered_commands_never_passes(self):
        root = self.repo({"README.md": "# docs only\n"})
        gate = run_gates(root, ProjectConfig(), "standard", agentic=self.agentic)
        jsonschema.validate(gate.verification, self.schema("verification-run"))
        self.assertEqual((gate.status, gate.passed), ("no-checks", False))
        self.assertEqual(gate.verification["missing_kinds"], ["test", "lint", "typecheck"])


@unittest.skipUnless(AGENTIC and jsonschema, "needs an installed `agentic` and jsonschema")
class BootstrapContractTests(unittest.TestCase):
    """agentflow init against the real agentic, with an isolated global provider registry."""

    def setUp(self):
        from agentflow import provider
        self.provider = provider
        self.tmp = Path(tempfile.mkdtemp(prefix="agentflow-bootstrap-"))
        self.saved = {k: os.environ.get(k) for k in ("AGENTIC_DEV_CONFIG_DIR", "AGENTFLOW_PROVIDER_SOURCE")}
        os.environ["AGENTIC_DEV_CONFIG_DIR"] = str(self.tmp / "config")
        bundled = provider.bundled_source()
        self.version_a = self.tmp / "provider-a"
        shutil.copytree(bundled, self.version_a)
        self.version_b = self.tmp / "provider-b"
        shutil.copytree(bundled, self.version_b)
        skill = self.version_b / "skills" / "agentflow-sdlc" / "SKILL.md"
        skill.write_text(skill.read_text() + "\nA different AgentFlow build.\n")
        self.agentic = Agentic(AGENTIC)

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp, ignore_errors=True)

    def use(self, source: Path) -> None:
        os.environ["AGENTFLOW_PROVIDER_SOURCE"] = str(source)

    def repo(self, name: str = "repo") -> Path:
        root = self.tmp / name
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        return root

    def installed_digest(self) -> str | None:
        entry = next((p for p in Agentic(AGENTIC).providers() if p["name"] == "agentflow"), None)
        return entry["content_digest"] if entry else None

    def digest(self, source: Path) -> str:
        return Agentic(AGENTIC).inspect_provider(source)["content_digest"]

    def test_init_places_blocks_and_skills_through_agentic(self):
        from agentflow.bootstrap import init_project
        self.use(self.version_a)
        root = self.repo()
        (root / "AGENTS.md").write_text("# Team notes\n\nKeep this exactly.\n")
        result = init_project(root, ProjectConfig(), agentic=self.agentic)
        self.assertEqual((result.provider_action, self.installed_digest()), ("installed", self.digest(self.version_a)))
        self.assertTrue((root / "AGENTS.md").read_text().startswith("# Team notes\n\nKeep this exactly.\n\n"))
        for harness in (".claude", ".codex", ".pi", ".opencode"):
            self.assertTrue((root / harness / "skills" / "agentflow-sdlc" / "SKILL.md").exists(), harness)
        listed = json.loads(subprocess.run([AGENTIC, "instructions", "block", "list", "--path", str(root), "--json"],
                                           capture_output=True, text=True, check=True).stdout)
        jsonschema.validate(listed, self.schema("instruction-block-list"))
        self.assertEqual({(b["file"], b["block_id"], b["intact"]) for b in listed["blocks"]},
                         {("AGENTS.md", "agentflow.workflow", True), ("CLAUDE.md", "agentflow.workflow", True)})
        before = (root / "AGENTS.md").read_bytes()
        again = init_project(root, ProjectConfig(), force=True, agentic=Agentic(AGENTIC))
        self.assertEqual(([b["status"] for b in again.blocks], again.provider_action), (["unchanged", "unchanged"], "unchanged"))
        self.assertEqual((root / "AGENTS.md").read_bytes(), before)

    def schema(self, name: str) -> dict:
        return json.loads(subprocess.run([AGENTIC, "contracts", "schema", name], capture_output=True, text=True,
                                         check=True).stdout)

    def assert_no_silent_replacement(self, installed: Path, incoming: Path) -> None:
        from agentflow.bootstrap import BootstrapError, init_project
        self.use(installed)
        init_project(self.repo("first"), ProjectConfig(), agentic=Agentic(AGENTIC))
        self.assertEqual(self.installed_digest(), self.digest(installed))
        self.use(incoming)
        second = self.repo("second")
        with self.assertRaisesRegex(BootstrapError, "--update-provider"):
            init_project(second, ProjectConfig(), agentic=Agentic(AGENTIC))
        self.assertEqual(self.installed_digest(), self.digest(installed))  # global provider untouched
        self.assertEqual(list(second.iterdir()), [second / ".git"])          # repository untouched
        result = init_project(second, ProjectConfig(), agentic=Agentic(AGENTIC), replace_provider=True)
        self.assertEqual((result.provider_action, self.installed_digest()), ("replaced", self.digest(incoming)))

    def test_older_agentflow_cannot_silently_downgrade_a_newer_provider(self):
        self.assert_no_silent_replacement(installed=self.version_b, incoming=self.version_a)

    def test_newer_agentflow_needs_explicit_intent_to_replace(self):
        self.assert_no_silent_replacement(installed=self.version_a, incoming=self.version_b)

    def test_no_provider_install_never_mutates_global_state(self):
        from agentflow.bootstrap import BootstrapError, init_project
        self.use(self.version_a)
        root = self.repo()
        with self.assertRaisesRegex(BootstrapError, "disabled"):
            init_project(root, ProjectConfig(), agentic=Agentic(AGENTIC), install_provider=False)
        self.assertIsNone(self.installed_digest())
        self.assertEqual(list(root.iterdir()), [root / ".git"])

    def test_hand_edited_block_stops_init_before_any_write(self):
        from agentflow.bootstrap import BootstrapError, init_project
        self.use(self.version_a)
        root = self.repo()
        init_project(root, ProjectConfig(), agentic=Agentic(AGENTIC))
        agents = root / "AGENTS.md"
        agents.write_text(agents.read_text().replace("Work only on", "Mostly work on"))
        config = (root / ".agentflow" / "config.json").read_bytes()
        snapshot = agents.read_bytes()
        with self.assertRaisesRegex(BootstrapError, "edited by hand"):
            init_project(root, ProjectConfig(pattern="tdd"), force=True, agentic=Agentic(AGENTIC))
        self.assertEqual((agents.read_bytes(), (root / ".agentflow" / "config.json").read_bytes()), (snapshot, config))

    def test_unmanaged_skill_in_any_harness_stops_init_with_zero_repository_changes(self):
        from agentflow.bootstrap import BootstrapError, init_project
        self.use(self.version_a)
        for harness in (".claude", ".codex", ".pi", ".opencode"):
            with self.subTest(harness):
                root = self.repo(f"repo-{harness[1:]}")
                (root / "AGENTS.md").write_text("# Team notes\n")
                mine = root / harness / "skills" / "agentflow-sdlc" / "SKILL.md"
                mine.parent.mkdir(parents=True)
                mine.write_text("my own skill\n")
                before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
                with self.assertRaisesRegex(BootstrapError, f"{harness}/skills/agentflow-sdlc/SKILL.md"):
                    init_project(root, ProjectConfig(), agentic=Agentic(AGENTIC))
                self.assertEqual({p: p.read_bytes() for p in root.rglob("*") if p.is_file()}, before)

    def test_doctor_facts(self):
        from agentflow.harnesses import detected
        document = Agentic(AGENTIC).doctor()
        jsonschema.validate(document, self.schema("doctor"))
        self.assertEqual(set(detected(document["tools"])), {"claude", "codex", "pi", "opencode"})


@unittest.skipUnless(AGENTIC and jsonschema, "needs an installed `agentic` and jsonschema")
class RequirementContractTests(unittest.TestCase):
    """Pattern requirements against the real agentic: worktree, local readiness, capabilities, metrics."""

    def setUp(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from fakes import FakeAgentic
        from agentflow.bootstrap import init_project
        self.tmp = Path(tempfile.mkdtemp(prefix="agentflow-requirements-"))
        keys = ("AGENTIC_DEV_CONFIG_DIR", "AGENTIC_WORKTREE_ROOT")
        self.saved = {k: os.environ.get(k) for k in keys}
        os.environ.update({"AGENTIC_DEV_CONFIG_DIR": str(self.tmp / "config"),
                           "AGENTIC_WORKTREE_ROOT": str(self.tmp / "worktrees")})
        self.root = self.tmp / "repo"
        git = ["git", "-C", str(self.root), "-c", "user.email=t@example.com", "-c", "user.name=T"]
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "app.py").write_text("print(1)\n")
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-qm", "seed"], check=True)
        # AgentFlow's own files only; the run below talks to the real agentic.
        init_project(self.root, ProjectConfig(pattern="fast", gates={"fast": ["true"]}), agentic=FakeAgentic())

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        subprocess.run(["git", "-C", str(self.root), "worktree", "prune"], capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_pattern(self, **requirements):
        from test_engine import FakeHarness
        from unittest.mock import patch
        from agentflow.config import load_project
        from agentflow.engine import Engine
        from agentflow.git import head_commit
        from agentflow.patterns import load_pattern
        from agentflow.state import load_state, new_state, save_state
        fast = json.loads((Path(__file__).resolve().parents[1] / "src" / "agentflow" / "builtin_patterns"
                           / "fast.json").read_text())
        (self.root / ".agentflow" / "patterns" / "custom.json").write_text(
            json.dumps({**fast, "name": "custom", **requirements}))
        git = ["git", "-C", str(self.root), "-c", "user.email=t@example.com", "-c", "user.name=T"]
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-qm", "agentflow"], check=True, capture_output=True)
        p = load_pattern("custom", self.root)
        state = new_state("change", p.name, p.entry, "claude", [], run_start_commit=head_commit(self.root))
        save_state(self.root, state)
        engine = Engine(load_project(self.root), state, agentic=Agentic(AGENTIC))
        with patch("agentflow.engine.get_harness", return_value=FakeHarness()):
            status = engine.start()
            if status == "running":
                status = engine.run(max_steps=20)
        return status, load_state(self.root)

    def schema(self, name: str) -> dict:
        return json.loads(subprocess.run([AGENTIC, "contracts", "schema", name], capture_output=True, text=True,
                                         check=True).stdout)

    def test_readiness_is_checked_in_the_worktree_and_blocks_without_remediation(self):
        status, state = self.run_pattern(requires={"readiness": "foundational"}, isolation={"mode": "worktree"})
        self.assertEqual(status, "blocked")
        self.assertIn("readiness foundational not met", state.awaiting_reason)
        tree = Path(state.worktree["path"])
        self.assertTrue(tree.is_dir())
        self.assertTrue(tree.is_relative_to((self.tmp / "worktrees").resolve()))
        evidence = json.loads((self.root / next(e["path"] for e in state.evidence
                                                if e["kind"] == "precondition")).read_text())
        jsonschema.validate(evidence["document"], self.schema("readiness-verification"))
        self.assertEqual((evidence["document"]["scope"], evidence["document"]["passed"]), ("local", False))
        self.assertEqual(subprocess.run(["git", "-C", str(self.root), "status", "--porcelain"], capture_output=True,
                                        text=True, check=True).stdout, "")  # primary checkout untouched

    def test_interrupted_start_adopts_the_real_worktree_instead_of_creating_another(self):
        from agentflow.config import load_project
        from agentflow.engine import Engine
        from agentflow.state import load_state
        self.run_pattern(isolation={"mode": "worktree"})  # installs and commits the pattern
        state = load_state(self.root)
        # A second run whose worktree Agentic Dev created but AgentFlow never recorded.
        from agentflow.git import head_commit
        from agentflow.state import new_state, save_state
        fresh = new_state("again", "custom", state.stage, "claude", [], run_start_commit=head_commit(self.root))
        save_state(self.root, fresh)
        Agentic(AGENTIC).create_worktree(self.root, name=f"agentflow-{fresh.run_id}",
                                         branch=f"agentflow/{fresh.run_id}", base=fresh.run_start_commit)
        self.assertEqual(Engine(load_project(self.root), load_state(self.root), agentic=Agentic(AGENTIC)).start(),
                         "running")
        adopted = load_state(self.root)
        self.assertTrue(adopted.started)
        self.assertTrue(any(h["event"] == "worktree_adopted" for h in adopted.history))
        self.assertTrue(Path(adopted.worktree["path"]).is_dir())

    def test_unknown_capability_blocks(self):
        status, state = self.run_pattern(requires={"capabilities": ["no-such-capability"]})
        self.assertEqual(status, "blocked")
        self.assertIn("unknown capability: no-such-capability", state.awaiting_reason)

    def test_isolated_run_with_metrics_and_a_refused_cleanup(self):
        subprocess.run([AGENTIC, "metrics", "enable"], check=True, capture_output=True)
        status, state = self.run_pattern(verification={"minimum": []},
                                         isolation={"mode": "worktree", "cleanup": "on-success"})
        self.assertEqual(status, "complete")
        tree = Path(state.worktree["path"])
        # The agent's uncommitted work makes the worktree dirty: Agentic Dev refuses, AgentFlow never forces.
        self.assertTrue((tree / "work.txt").exists())
        self.assertFalse(state.worktree["cleaned"])
        self.assertTrue(any(h["event"] == "worktree_kept" for h in state.history))
        self.assertFalse((self.root / "work.txt").exists())
        summary = json.loads(subprocess.run([AGENTIC, "metrics", "summary", "--json"], capture_output=True,
                                            text=True, check=True).stdout)
        self.assertIn("implement", json.dumps(summary))
        self.assertIn("verify", json.dumps(summary))


if __name__ == "__main__":
    unittest.main()
