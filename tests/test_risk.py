import subprocess, tempfile, unittest
from pathlib import Path
from agentflow.risk import classify

class RiskTests(unittest.TestCase):
    def test_auth_path_is_high_risk(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); subprocess.run(["git","init"],cwd=root,check=True,capture_output=True)
            subprocess.run(["git","config","user.email","t@e.com"],cwd=root,check=True); subprocess.run(["git","config","user.name","T"],cwd=root,check=True)
            (root/"auth.py").write_text("old"); subprocess.run(["git","add","."],cwd=root,check=True); subprocess.run(["git","commit","-m","x"],cwd=root,check=True,capture_output=True)
            (root/"auth.py").write_text("new")
            self.assertEqual(classify(root)[0],"high")
