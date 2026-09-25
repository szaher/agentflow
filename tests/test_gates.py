import json
import tempfile
import unittest
from pathlib import Path
from agentflow.gates import detected_commands

class GateTests(unittest.TestCase):
    def test_detect_node_scripts(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"package.json").write_text(json.dumps({"scripts":{"lint":"x","test":"y","build":"z"}}))
            cmds=dict(detected_commands(root,"strict"))
            self.assertIn("lint",cmds); self.assertIn("test",cmds); self.assertIn("build",cmds)
