import subprocess
import tempfile
import unittest
from pathlib import Path
from agentflow.git import implementation_fingerprint

class GitTests(unittest.TestCase):
    def test_evidence_bookkeeping_does_not_change_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            subprocess.run(["git","init"],cwd=root,check=True,capture_output=True)
            subprocess.run(["git","config","user.email","test@example.com"],cwd=root,check=True)
            subprocess.run(["git","config","user.name","Test"],cwd=root,check=True)
            (root/"a.txt").write_text("a")
            subprocess.run(["git","add","."],cwd=root,check=True)
            subprocess.run(["git","commit","-m","init"],cwd=root,check=True,capture_output=True)
            one=implementation_fingerprint(root)
            (root/".agentflow/evidence").mkdir(parents=True)
            (root/".agentflow/evidence/x.json").write_text("{}")
            two=implementation_fingerprint(root)
            self.assertEqual(one,two)
            (root/"a.txt").write_text("b")
            self.assertNotEqual(two, implementation_fingerprint(root))
