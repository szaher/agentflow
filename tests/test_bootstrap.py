import tempfile
import unittest
from pathlib import Path
from agentflow.bootstrap import init_project
from agentflow.models import ProjectConfig

class BootstrapTests(unittest.TestCase):
    def test_generates_cross_harness_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            init_project(root, ProjectConfig())
            expected=[
                "AGENTS.md","CLAUDE.md",".agentflow/config.json",
                ".agents/skills/agentflow-sdlc/SKILL.md",
                ".claude/skills/agentflow-sdlc/SKILL.md",
                ".codex/skills/agentflow-sdlc/SKILL.md",
                ".pi/skills/agentflow-sdlc/SKILL.md",
                ".opencode/skills/agentflow-sdlc/SKILL.md",
                ".opencode/agents/agentflow-reviewer.md",
            ]
            for rel in expected:
                self.assertTrue((root/rel).exists(), rel)
