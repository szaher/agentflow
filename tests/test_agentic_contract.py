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

from agentflow.agentic import Agentic
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

    def test_gate_runs_the_discovered_command_through_agentic(self):
        root = self.repo({"README.md": "# x\n", "app.py": "print(1)\n",
                          "Makefile": "check:\n\ttouch ran-make-check\n"})
        self.assertEqual(self.agentic.discovered_kinds(root), {"test"})
        gate = run_gates(root, ProjectConfig(), "fast", agentic=self.agentic)
        jsonschema.validate(gate.verification, self.schema("verification-run"))
        self.assertEqual((gate.status, gate.plan.kinds), ("passed", ["test"]))
        self.assertEqual([(r["kind"], r["command"]) for r in gate.results], [("test", "make check")])
        self.assertTrue((root / "ran-make-check").exists())

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
    def test_every_command_of_a_required_kind_runs(self):
        root = self.repo({"README.md": "# x\n", "app.py": "x = 1\n",
                          "Makefile": "test:\n\ttouch ran-make\n",
                          "package.json": json.dumps({"scripts": {"test": "node -e \"require('fs').writeFileSync('ran-npm','')\""}})})
        gate = run_gates(root, ProjectConfig(), "fast", agentic=self.agentic)
        jsonschema.validate(gate.verification, self.schema("verification-run"))
        self.assertEqual(gate.status, "passed")
        self.assertEqual([r["command"] for r in gate.results], ["make test", "npm run test"])
        self.assertTrue((root / "ran-make").exists() and (root / "ran-npm").exists())

    def test_no_discovered_commands_never_passes(self):
        root = self.repo({"README.md": "# docs only\n"})
        gate = run_gates(root, ProjectConfig(), "standard", agentic=self.agentic)
        self.assertEqual((gate.status, gate.passed), ("no-checks", False))


if __name__ == "__main__":
    unittest.main()
