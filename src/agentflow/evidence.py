from __future__ import annotations

from pathlib import Path
from .models import GateResult, RunState
from .util import atomic_json, now_iso


def write_gate_evidence(root: Path, state: RunState, results: list[GateResult], fingerprint: str) -> Path:
    data = {
        "run_id": state.run_id,
        "stage": state.stage,
        "at": now_iso(),
        "fingerprint": fingerprint,
        "passed": all(r.passed for r in results),
        "results": [
            {"name": r.name, "command": r.command, "returncode": r.returncode,
             "stdout": r.stdout[-20000:], "stderr": r.stderr[-20000:], "duration_s": r.duration_s}
            for r in results
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
