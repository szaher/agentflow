import unittest
from agentflow.patterns import list_patterns, validate_pattern

class PatternTests(unittest.TestCase):
    def test_all_builtin_patterns_validate(self):
        patterns = list_patterns()
        self.assertGreaterEqual(len(patterns), 20)
        for p in patterns:
            validate_pattern(p)

    def test_core_patterns_exist(self):
        names = {p.name for p in list_patterns()}
        for expected in {"helix","checkpoint","tdd","reproduce-first","security-critical","ui-parity","standard"}:
            self.assertIn(expected, names)
