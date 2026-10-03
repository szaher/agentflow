"""agentflow init through Agentic Dev (v0.16 slice 3): decision logic, with a fake Agentic Dev."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fakes import FakeAgentic, installed_provider  # noqa: E402

import agentflow  # noqa: E402
from agentflow import provider  # noqa: E402
from agentflow.bootstrap import BootstrapError, init_project  # noqa: E402
from agentflow.harnesses import detected  # noqa: E402
from agentflow.models import ProjectConfig  # noqa: E402

SRC = Path(agentflow.__file__).resolve().parent
BUNDLED = "a" * 64
OTHER = "b" * 64


class ProviderPolicyTests(unittest.TestCase):
    def test_missing_provider_is_installed_pinned_to_the_bundled_digest(self):
        fake = FakeAgentic(bundled_digest=BUNDLED)
        action, before = provider.ensure(fake)
        self.assertEqual((action, before.state), ("installed", provider.MISSING))
        self.assertEqual(fake.provider_adds[0]["sha256"], BUNDLED)

    def test_identical_provider_is_a_no_op(self):
        fake = FakeAgentic(bundled_digest=BUNDLED, installed=[installed_provider(BUNDLED)])
        self.assertEqual(provider.ensure(fake)[0], "unchanged")
        self.assertEqual(fake.provider_adds, [])

    def test_a_different_provider_is_never_replaced_silently(self):
        for state, installed in ((provider.DIFFERENT, installed_provider(OTHER)),
                                 (provider.UNVERIFIED, installed_provider(BUNDLED, verified=False))):
            with self.subTest(state):
                fake = FakeAgentic(bundled_digest=BUNDLED, installed=[installed])
                with self.assertRaisesRegex(provider.ProviderError, "--update-provider"):
                    provider.ensure(fake)
                self.assertEqual(fake.provider_adds, [])
                self.assertEqual(provider.ensure(fake, replace=True)[0], "replaced")
                self.assertEqual(fake.provider_adds[-1]["sha256"], BUNDLED)

    def test_no_install_mode_only_verifies(self):
        with self.assertRaisesRegex(provider.ProviderError, "disabled"):
            provider.ensure(FakeAgentic(), install=False)
        current = FakeAgentic(bundled_digest=BUNDLED, installed=[installed_provider(BUNDLED)])
        self.assertEqual(provider.ensure(current, install=False)[0], "unchanged")
        with self.assertRaises(provider.ProviderError):
            provider.ensure(FakeAgentic(installed=[installed_provider(OTHER)]), install=False, replace=True)


class InitTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def files(self):
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())

    def test_init_writes_only_agentflow_owned_files_and_delegates_the_rest(self):
        fake = FakeAgentic()
        result = init_project(self.root, ProjectConfig(), agentic=fake)
        self.assertEqual(self.files(), [".agentflow/.gitignore", ".agentflow/config.json",
                                        ".opencode/agents/agentflow-reviewer.md"])
        writes = [b for b in fake.blocks if not b["dry_run"]]
        self.assertEqual([(b["file"], b["owner"], b["block"]) for b in writes],
                         [("AGENTS.md", "agentflow", "workflow"), ("CLAUDE.md", "agentflow", "workflow")])
        self.assertEqual(result.skills["status"], "ok")
        self.assertEqual(result.provider_action, "installed")

    def test_preflight_failures_change_nothing_in_the_repository(self):
        for label, fake, message in (
            ("different provider", FakeAgentic(installed=[installed_provider(OTHER)]), "--update-provider"),
            ("hand-edited block", FakeAgentic(block_status="conflict"), "edited by hand"),
            ("unmanaged skill", FakeAgentic(skills_status="conflict"), "unmanaged skill"),
        ):
            with self.subTest(label):
                root = Path(tempfile.mkdtemp())
                with self.assertRaisesRegex(BootstrapError, message):
                    init_project(root, ProjectConfig(), agentic=fake)
                self.assertEqual(list(root.iterdir()), [])
                self.assertFalse(any(not b["dry_run"] for b in fake.blocks))
                self.assertFalse(any(not c["dry_run"] for c in fake.skill_calls))

    def test_skill_activation_is_previewed_before_any_write(self):
        fake = FakeAgentic()
        init_project(self.root, ProjectConfig(), agentic=fake)
        self.assertEqual([c["dry_run"] for c in fake.skill_calls], [True, False])
        self.assertEqual({(c["target"], c["shared"]) for c in fake.skill_calls}, {("all", True)})

    def test_no_wholesale_writes_to_shared_files(self):
        for path in SRC.rglob("*.py"):
            text = path.read_text()
            for shared in ('"AGENTS.md").write_text', '"CLAUDE.md").write_text', "SKILL.md\").write_text"):
                self.assertNotIn(shared, text, path.name)

    def test_existing_project_needs_force(self):
        init_project(self.root, ProjectConfig(), agentic=FakeAgentic())
        with self.assertRaises(FileExistsError):
            init_project(self.root, ProjectConfig(), agentic=FakeAgentic())
        init_project(self.root, ProjectConfig(), force=True, agentic=FakeAgentic())


class HarnessFactsTests(unittest.TestCase):
    def test_harness_availability_comes_from_agentic_doctor(self):
        tools = FakeAgentic(tools=("codex", "opencode")).doctor()["tools"]
        self.assertEqual(detected(tools), {"claude": False, "codex": True, "pi": False, "opencode": True})
        self.assertNotIn("which", (SRC / "harnesses" / "registry.py").read_text())


if __name__ == "__main__":
    unittest.main()
