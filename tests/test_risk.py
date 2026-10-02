import subprocess, tempfile, unittest
from pathlib import Path
from agentflow.risk import changed_paths, classify


def repo(td: str, commit: bool = True) -> Path:
    root = Path(td)
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=root, check=True)
    if commit:
        (root / "README.md").write_text("x\n")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    return root


class RiskTests(unittest.TestCase):
    def test_auth_path_is_high_risk(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); subprocess.run(["git","init"],cwd=root,check=True,capture_output=True)
            subprocess.run(["git","config","user.email","t@e.com"],cwd=root,check=True); subprocess.run(["git","config","user.name","T"],cwd=root,check=True)
            (root/"auth.py").write_text("old"); subprocess.run(["git","add","."],cwd=root,check=True); subprocess.run(["git","commit","-m","x"],cwd=root,check=True,capture_output=True)
            (root/"auth.py").write_text("new")
            self.assertEqual(classify(root)[0],"high")

    def test_untracked_auth_module_is_high_risk(self):
        # Regression: a brand-new (untracked) auth module was classified low and auto-approved.
        with tempfile.TemporaryDirectory() as td:
            root = repo(td)
            (root / "auth").mkdir()
            (root / "auth" / "tokens.py").write_text("def issue(): ...\n")
            risk, reasons = classify(root)
            self.assertEqual(risk, "high")
            self.assertIn("changed path matched high-risk token: auth", reasons)

    def test_staged_deleted_and_renamed_paths_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = repo(td)
            (root / "billing.py").write_text("x\n")
            (root / "notes.md").write_text("x\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "more"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "mv", "billing.py", "ledger.py"], cwd=root, check=True)
            (root / "notes.md").unlink()
            self.assertEqual(changed_paths(root), ["billing.py", "ledger.py", "notes.md"])
            self.assertEqual(classify(root)[0], "high")

    def test_before_first_commit(self):
        with tempfile.TemporaryDirectory() as td:
            root = repo(td, commit=False)
            (root / "deploy.sh").write_text("x\n")
            self.assertEqual(classify(root)[0], "high")

    def test_agentflow_runtime_state_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            root = repo(td)
            (root / ".agentflow" / "logs").mkdir(parents=True)
            (root / ".agentflow" / "logs" / "secret-run.log").write_text("x\n")
            self.assertEqual(changed_paths(root), [])
            self.assertEqual(classify(root), ("low", ["default classification"]))

    def test_untracked_docs_only_stays_low(self):
        with tempfile.TemporaryDirectory() as td:
            root = repo(td)
            (root / "GUIDE.md").write_text("x\n")
            self.assertEqual(classify(root), ("low", ["documentation-only tracked changes"]))
