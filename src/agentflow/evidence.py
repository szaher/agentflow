from __future__ import annotations

from pathlib import Path
from .gates import GateRun
from .models import RunState
from .util import atomic_json, now_iso


def write_gate_evidence(root: Path, state: RunState, gate: GateRun, fingerprint: str) -> Path:
    """AgentFlow's envelope around Agentic Dev's unmodified verification-run document."""

    data = {
        "run_id": state.run_id,
        "stage": state.stage,
        "at": now_iso(),
        "fingerprint": fingerprint,
        "profile": gate.plan.profile,
        "passed": gate.passed,
        "status": gate.status,
        "reason": gate.reason,
        "plan": gate.plan.to_dict(),
        "verification": gate.verification,
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
