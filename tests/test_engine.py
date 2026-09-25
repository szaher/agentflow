import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentflow.bootstrap import init_project
from agentflow.config import load_project
from agentflow.engine import Engine
from agentflow.models import HarnessResult, ProjectConfig
from agentflow.patterns import load_pattern
from agentflow.state import new_state, save_state

class FakeHarness:
    name="fake"
    def __init__(self, mutate=True, review_pass=True): self.mutate=mutate; self.review_pass=review_pass
    def execute(self, root, prompt, read_only=False, extra=None):
        if self.mutate and not read_only:
            p=root/"work.txt"; p.write_text(p.read_text() + "x" if p.exists() else "x")
        out="AGENTFLOW_REVIEW_PASS" if read_only and self.review_pass else "ok"
        return HarnessResult("fake",0,out,"",["fake"],changed=self.mutate and not read_only)

class MutatingReviewer(FakeHarness):
    def execute(self, root, prompt, read_only=False, extra=None):
        if read_only:
            p=root/"bad-review.txt"; p.write_text((p.read_text() if p.exists() else "") + "mutation\n")
            return HarnessResult("fake",0,"AGENTFLOW_REVIEW_PASS","",["fake"],changed=True)
        return super().execute(root,prompt,read_only,extra)

class EngineTests(unittest.TestCase):
    def repo(self):
        td=tempfile.TemporaryDirectory(); root=Path(td.name)
        subprocess.run(["git","init"],cwd=root,check=True,capture_output=True)
        subprocess.run(["git","config","user.email","test@example.com"],cwd=root,check=True)
        subprocess.run(["git","config","user.name","Test"],cwd=root,check=True)
        (root/"seed.txt").write_text("seed")
        subprocess.run(["git","add","."],cwd=root,check=True)
        subprocess.run(["git","commit","-m","seed"],cwd=root,check=True,capture_output=True)
        return td,root

    def test_fast_pattern_end_to_end_with_mock_harness(self):
        td,root=self.repo()
        try:
            cfg=ProjectConfig(pattern="fast",executor="claude",reviewers=["codex"],gates={"fast":["python -c 'print(1)'"]})
            init_project(root,cfg)
            p=load_pattern("fast",root)
            st=new_state("change",p.name,p.entry,"claude",["codex"]); save_state(root,st)
            with patch("agentflow.engine.get_harness", return_value=FakeHarness()):
                status=Engine(load_project(root),st).run()
            self.assertEqual(status,"complete")
            self.assertTrue((root/"work.txt").exists())
        finally: td.cleanup()

    def test_mutating_reviewer_is_rejected(self):
        td,root=self.repo()
        try:
            cfg=ProjectConfig(pattern="pair-review",executor="claude",reviewers=["codex"],gates={"standard":["python -c 'print(1)'"]})
            init_project(root,cfg)
            p=load_pattern("pair-review",root)
            st=new_state("change",p.name,p.entry,"claude",["codex"]); save_state(root,st)
            fake=MutatingReviewer()
            with patch("agentflow.engine.get_harness", return_value=fake):
                status=Engine(load_project(root),st).run(max_steps=20)
            self.assertEqual(status,"blocked")
        finally: td.cleanup()
