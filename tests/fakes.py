"""Test double for the Agentic Dev client (unit tests only; contract tests use the real CLI)."""

from __future__ import annotations

from agentflow.agentic import AgenticUnavailable


class FakeAgentic:
    """Records calls and answers like `agentic` would, without running anything."""

    def __init__(self, kinds=("lint", "test"), status="passed", missing=(), unavailable=None):
        self.kinds = set(kinds)
        self.status = status
        self.missing = list(missing)
        self.unavailable = unavailable
        self.calls: list[dict] = []

    def handshake(self):
        if self.unavailable:
            raise AgenticUnavailable(self.unavailable)
        return {"document_type": "agentic.contracts", "features": []}

    def supports(self, feature):
        return True

    def discovered_kinds(self, root):
        self.handshake()
        return set(self.kinds)

    def verify(self, root, *, kinds, commands, include_changed=False, base=None):
        self.handshake()
        self.calls.append({"kinds": list(kinds), "commands": list(commands),
                           "include_changed": include_changed, "base": base})
        executed = [] if self.status == "no-checks" else [
            {"kind": kind, "command": f"run-{kind}", "executed": True, "success": self.status == "passed",
             "returncode": 0 if self.status == "passed" else 1, "stdout": "", "stderr": "", "duration_ms": 5.0}
            for kind in kinds
        ] + [
            {"kind": "custom", "command": command, "executed": True, "success": self.status == "passed",
             "returncode": 0 if self.status == "passed" else 1, "stdout": "", "stderr": "", "duration_ms": 5.0}
            for command in commands
        ]
        return {"schema_version": "1", "document_type": "agentic.verification-run", "status": self.status,
                "success": self.status == "passed", "mode": "full", "requested_kinds": list(kinds),
                "missing_kinds": self.missing, "checks_executed": len(executed), "results": executed}
