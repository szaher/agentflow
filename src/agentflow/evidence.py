from __future__ import annotations

from pathlib import Path
from .gates import GateRun
from .models import RunState
from .util import atomic_json, now_iso


def write_gate_evidence(root: Path, state: RunState, gate: GateRun, fingerprint: str) -> Path:
    verification = gate.verification or {}
    data = {
        "run_id": state.run_id,
        "stage": state.stage,
        "at": now_iso(),
        "fingerprint": fingerprint,
        "passed": gate.passed,
        "status": gate.status,
        "reason": gate.reason,
        "executor": "agentic-dev",
        "plan": {"profile": gate.plan.profile, "kinds": gate.plan.kinds, "commands": gate.plan.commands,
                 "include_changed": gate.plan.include_changed, "base": gate.plan.base},
        "verification": {key: verification.get(key) for key in
                         ("document_type", "schema_version", "mode", "status", "requested_kinds", "missing_kinds",
                          "checks_executed")} if verification else None,
        "results": [
            {"name": r.name, "command": r.command, "returncode": r.returncode,
             "stdout": r.stdout[-20000:], "stderr": r.stderr[-20000:], "duration_s": r.duration_s}
            for r in gate.results
        ],
    }
    path = root / ".agentflow" / "evidence" / state.run_id / f"{state.stage}-gates.json"
    atomic_json(path, data)
    return path


def write_review_evidence(root: Path, state: RunState, harness: str, index: int, stdout: str, stderr: str, fingerprint: str, passed: bool) -> Path:
    data = {"run_id": state.run_id, "stage": state.stage, "at": now_iso(), "harness": harness,
            "fingerprint": fingerprint, "passed": passed, "stdout": stdout, "stderr": stderr}
    path = root / ".agentflow" / "evidence" / state.run_id / f"{state.stage}-review-{index}-{harness}.json"
    atomic_json(path, data)
    return path


def write_agent_evidence(root: Path, state: RunState, harness: str, stdout: str, stderr: str, fingerprint: str, returncode: int) -> Path:
    data = {"run_id": state.run_id, "stage": state.stage, "at": now_iso(), "harness": harness,
            "fingerprint": fingerprint, "returncode": returncode, "stdout": stdout, "stderr": stderr}
    path = root / ".agentflow" / "evidence" / state.run_id / f"{state.stage}-agent.json"
    atomic_json(path, data)
    return path
