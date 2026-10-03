import json
import os
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
from agentflow.git import head_commit
from agentflow.state import load_state, new_state, save_state

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fakes import FakeAgentic, fake_cli, logged_calls, verification_document  # noqa: E402

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
                fake_agentic=FakeAgentic()
                status=Engine(load_project(root),st,agentic=fake_agentic).run()
            self.assertEqual(status,"complete")
            self.assertEqual(fake_agentic.calls[0]["commands"],["python -c 'print(1)'"])
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
                status=Engine(load_project(root),st,agentic=FakeAgentic()).run(max_steps=20)
            self.assertEqual(status,"blocked")
        finally: td.cleanup()

    def run_fast(self, agentic):
        td,root=self.repo()
        self.addCleanup(td.cleanup)
        init_project(root,ProjectConfig(pattern="fast",executor="claude",reviewers=["codex"]))
        p=load_pattern("fast",root)
        st=new_state("change",p.name,p.entry,"claude",["codex"],run_start_commit=head_commit(root)); save_state(root,st)
        with patch("agentflow.engine.get_harness", return_value=FakeHarness()):
            status=Engine(load_project(root),st,agentic=agentic).run(max_steps=20)
        return root,status,load_state(root)

    def test_unavailable_verifier_blocks_instead_of_retrying(self):
        root,status,state=self.run_fast(FakeAgentic(unavailable="`agentic` was not found"))
        self.assertEqual(status,"blocked")
        self.assertIn("verification unavailable",state.awaiting_reason)
        self.assertEqual(state.attempts_by_stage.get("implement"),1)
        self.assertFalse(any(e["kind"]=="gates" for e in state.evidence))

    def test_no_checks_gate_fails_closed(self):
        root,status,state=self.run_fast(FakeAgentic(kinds={"test"}))
        gates=[e for e in state.evidence if e["kind"]=="gates"]
        self.assertTrue(gates)
        self.assertTrue(all(not e["passed"] and e["status"]=="no-checks" for e in gates))
        self.assertNotEqual(status,"complete")

    def test_run_records_its_start_commit(self):
        root,status,state=self.run_fast(FakeAgentic())
        self.assertEqual(status,"complete")
        head=subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],capture_output=True,text=True).stdout.strip()
        self.assertEqual(state.run_start_commit,head)
        self.assertEqual(state.history[0]["run_start_commit"],head)

    def test_gate_evidence_wraps_the_whole_verification_document(self):
        root,status,state=self.run_fast(FakeAgentic())
        gate=next(e for e in state.evidence if e["kind"]=="gates")
        evidence=json.loads((root/gate["path"]).read_text())
        self.assertEqual(evidence["verification"],verification_document("passed",["lint","test"]))
        self.assertEqual((evidence["profile"],evidence["passed"],evidence["status"]),("fast",True,"passed"))

    def test_workflow_gates_are_full_only(self):
        fake=FakeAgentic()
        self.run_fast(fake)
        self.assertTrue(fake.calls)
        self.assertTrue(all(not c["include_changed"] and c["base"] is None for c in fake.calls))


class RunStateTests(unittest.TestCase):
    def test_run_start_commit_survives_serialization(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            save_state(root,new_state("t","fast","implement","claude",[],run_start_commit="a"*40))
            self.assertEqual(load_state(root).run_start_commit,"a"*40)

    def test_old_state_files_still_load(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            state=new_state("t","fast","implement","claude",[]).to_dict()
            del state["run_start_commit"]
            (root/".agentflow").mkdir()
            (root/".agentflow"/"state.json").write_text(json.dumps(state))
            self.assertIsNone(load_state(root).run_start_commit)

    def test_unborn_repository_has_no_start_commit(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["git","init","-q",td],check=True)
            self.assertIsNone(head_commit(Path(td)))


class VerifyCliTests(unittest.TestCase):
    def test_include_changed_passes_the_stored_start_commit(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as tool:
            root=Path(td)
            subprocess.run(["git","init","-q",str(root)],check=True)
            init_project(root,ProjectConfig())
            save_state(root,new_state("t","fast","implement","claude",[],run_start_commit="b"*40))
            env={**os.environ,"PYTHONPATH":str(Path(__file__).resolve().parents[1]/"src"),
                 "AGENTFLOW_AGENTIC":fake_cli(Path(tool))}
            def verify(*extra):
                return subprocess.run([sys.executable,"-m","agentflow.cli","verify",*extra],cwd=root,env=env,
                                      capture_output=True,text=True)
            full=verify(); augmented=verify("--include-changed")
            self.assertEqual((full.returncode,augmented.returncode),(0,0),full.stderr+augmented.stderr)
            runs=[c for c in logged_calls(Path(tool)) if c[:2]==["verify","run"]]
            self.assertNotIn("--include-changed",runs[0])
            self.assertEqual(runs[1][-3:],["--include-changed","--base","b"*40])
