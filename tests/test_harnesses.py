import unittest
from agentflow.harnesses.claude import ClaudeHarness
from agentflow.harnesses.codex import CodexHarness
from agentflow.harnesses.pi import PiHarness
from agentflow.harnesses.opencode import OpenCodeHarness

class HarnessCommandTests(unittest.TestCase):
    def test_claude_read_only(self):
        c=ClaudeHarness().command_preview("review", read_only=True)
        self.assertEqual(c[0], "claude")
        self.assertIn("--disallowedTools", c)
    def test_codex_exec(self):
        c=CodexHarness().command_preview("do it", read_only=False)
        self.assertEqual(c[:2], ["codex","exec"])
    def test_codex_review_sandbox(self):
        c=CodexHarness().command_preview("review", read_only=True)
        self.assertIn("read-only", c)
    def test_pi_review_tools(self):
        c=PiHarness().command_preview("review", read_only=True)
        self.assertIn("read,grep,find,ls", c)
    def test_opencode_run(self):
        c=OpenCodeHarness().command_preview("do it", read_only=False)
        self.assertEqual(c[:2],["opencode","run"])
