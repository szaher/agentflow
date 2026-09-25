import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / "bin" / "agentflow"
loader=importlib.machinery.SourceFileLoader("agentflow_cli", str(CLI))
spec=importlib.util.spec_from_loader(loader.name, loader)
mod=importlib.util.module_from_spec(spec)
loader.exec_module(mod)

class AgentflowTests(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(["git",*args],cwd=root,text=True,capture_output=True,check=True)

    def init_repo(self):
        td=tempfile.TemporaryDirectory(); root=Path(td.name)
        self.git(root,"init","-q")
        self.git(root,"config","user.email","test@example.com")
        self.git(root,"config","user.name","Test")
        (root/"README.md").write_text("hello\n")
        self.git(root,"add","README.md"); self.git(root,"commit","-qm","init")
        return td,root

    def test_slugify(self):
        self.assertEqual(mod.slugify("Add Passkey Login!"),"add-passkey-login")

    def test_detect_node_scripts(self):
        td,root=self.init_repo()
        try:
            (root/"package.json").write_text(json.dumps({"scripts":{"lint":"eslint .","test":"vitest","build":"vite build"}}))
            d=mod.detect_project(root)
            self.assertIn("node",d["detected"])
            self.assertTrue(any(x["name"]=="lint" for x in d["gates"]["standard"]))
            self.assertTrue(any(x["name"]=="build" for x in d["gates"]["strict"]))
        finally: td.cleanup()

    def test_risk_docs_low(self):
        td,root=self.init_repo()
        try:
            (root/"docs").mkdir(); (root/"docs"/"x.md").write_text("x")
            r=mod.risk_assessment(root)
            self.assertEqual(r["level"],"low")
        finally: td.cleanup()

    def test_risk_workflow_high(self):
        td,root=self.init_repo()
        try:
            (root/".github/workflows").mkdir(parents=True); (root/".github/workflows/x.yml").write_text("name: x")
            r=mod.risk_assessment(root)
            self.assertEqual(r["level"],"high")
        finally: td.cleanup()

    def test_fingerprint_changes_for_untracked_content(self):
        td,root=self.init_repo()
        try:
            (root/"new.txt").write_text("a")
            a=mod.git_diff_fingerprint(root)
            (root/"new.txt").write_text("b")
            b=mod.git_diff_fingerprint(root)
            self.assertNotEqual(a,b)
        finally: td.cleanup()

    def test_fingerprint_ignores_checkpoint_bookkeeping(self):
        td,root=self.init_repo()
        try:
            (root/".agentflow/checkpoints").mkdir(parents=True)
            p=root/".agentflow/checkpoints/x.json"
            p.write_text('{"status":"a"}')
            a=mod.git_diff_fingerprint(root)
            p.write_text('{"status":"b"}')
            b=mod.git_diff_fingerprint(root)
            self.assertEqual(a,b)
        finally: td.cleanup()

    def test_full_worktree_fingerprint_includes_checkpoint_bookkeeping(self):
        td,root=self.init_repo()
        try:
            (root/".agentflow/checkpoints").mkdir(parents=True)
            p=root/".agentflow/checkpoints/x.json"
            p.write_text('{"status":"a"}')
            a=mod.worktree_fingerprint(root)
            p.write_text('{"status":"b"}')
            b=mod.worktree_fingerprint(root)
            self.assertNotEqual(a,b)
        finally: td.cleanup()

if __name__ == '__main__':
    unittest.main()
