from __future__ import annotations

from pathlib import Path

from .config import Project
from .evidence import write_agent_evidence, write_gate_evidence, write_review_evidence
from .gates import run_gates
from .git import implementation_fingerprint
from .harnesses import get as get_harness
from .models import Pattern, RunState, Stage
from .patterns import load_pattern
from .prompts import review_prompt, stage_prompt
from .risk import classify
from .state import record, save_state
from .util import now_iso, sha256_text

class EngineError(RuntimeError):
    pass

class Engine:
    def __init__(self, project: Project, state: RunState):
        self.project = project
        self.root = project.root
        self.state = state
        self.pattern: Pattern = load_pattern(state.pattern, self.root)

    def _transition(self, target: str | None, reason: str) -> None:
        if target in (None, "done"):
            self.state.status = "complete"
            self.state.awaiting_reason = None
            record(self.state, "complete", reason=reason)
        elif target == "blocked":
            self.state.status = "blocked"
            self.state.awaiting_reason = reason
            record(self.state, "blocked", reason=reason)
        else:
            old = self.state.stage
            self.state.stage = target
            self.state.attempt = self.state.attempts_by_stage.get(target, 0)
            self.state.status = "running"
            self.state.awaiting_reason = None
            record(self.state, "transition", old=old, new=target, reason=reason)
        save_state(self.root, self.state)

    def step(self) -> str:
        if self.state.status in {"complete", "blocked", "awaiting_approval"}:
            return self.state.status
        stage = self.pattern.stage(self.state.stage)
        if stage.kind == "agent":
            return self._agent(stage)
        if stage.kind == "gate":
            return self._gate(stage)
        if stage.kind == "review":
            return self._review(stage)
        if stage.kind == "human":
            return self._human(stage)
        self._transition(stage.on_success, f"noop stage {stage.id}")
        return self.state.status

    def _agent(self, stage: Stage) -> str:
        used = self.state.attempts_by_stage.get(stage.id, 0)
        if used >= stage.max_attempts:
            self._transition("blocked", f"attempt limit reached at {stage.id}")
            return self.state.status
        used += 1
        self.state.attempts_by_stage[stage.id] = used
        self.state.attempt = used
        save_state(self.root, self.state)
        cfg = self.project.config.harness.get(self.state.executor, {})
        harness = get_harness(self.state.executor, cfg)
        result = harness.execute(self.root, stage_prompt(self.pattern, stage, self.state), extra=cfg)
        fp = implementation_fingerprint(self.root)
        ep = write_agent_evidence(self.root, self.state, harness.name, result.stdout, result.stderr, fp, result.returncode)
        self.state.evidence.append({"kind": "agent", "path": str(ep.relative_to(self.root)), "fingerprint": fp, "stage": stage.id, "harness": harness.name})
        if stage.role in {"planner", "specifier", "migration-planner"} and result.returncode == 0:
            self.state.plan_hash = sha256_text([result.stdout])
        record(self.state, "agent_result", stage=stage.id, harness=harness.name, returncode=result.returncode, changed=result.changed)
        save_state(self.root, self.state)
        if result.returncode == 0:
            self._transition(stage.on_success, f"{harness.name} completed {stage.id}")
        elif self.state.attempt >= stage.max_attempts:
            self._transition(stage.on_failure or "blocked", f"{harness.name} failed {stage.id}")
        return self.state.status

    def _gate(self, stage: Stage) -> str:
        profile = stage.gate_profile or self.project.config.gate_profile
        fp = implementation_fingerprint(self.root)
        results = run_gates(self.root, self.project.config, profile)
        path = write_gate_evidence(self.root, self.state, results, fp)
        passed = bool(results) and all(r.passed for r in results)
        # Projects with no detected gates are not silently considered verified.
        if not results:
            passed = False
        self.state.evidence.append({"kind": "gates", "path": str(path.relative_to(self.root)), "fingerprint": fp, "passed": passed})
        record(self.state, "gates", stage=stage.id, profile=profile, passed=passed, count=len(results))
        self.state.fingerprint = fp
        save_state(self.root, self.state)
        self._transition(stage.on_success if passed else stage.on_failure, f"gates {'passed' if passed else 'failed'}")
        return self.state.status

    def _review(self, stage: Stage) -> str:
        fp = implementation_fingerprint(self.root)
        reviewers = self.state.reviewers or self.project.config.reviewers
        count = stage.reviewers or len(reviewers) or 1
        selected = [reviewers[i % len(reviewers)] for i in range(count)] if reviewers else [self.state.executor] * count
        passes = []
        for idx, name in enumerate(selected, 1):
            cfg = self.project.config.harness.get(name, {})
            harness = get_harness(name, cfg)
            before = implementation_fingerprint(self.root)
            result = harness.execute(self.root, review_prompt(self.pattern, stage, self.state), read_only=True, extra=cfg)
            after = implementation_fingerprint(self.root)
            clean = before == after
            passed = result.returncode == 0 and clean and "AGENTFLOW_REVIEW_PASS" in result.stdout and "AGENTFLOW_REVIEW_FAIL" not in result.stdout
            path = write_review_evidence(self.root, self.state, name, idx, result.stdout, result.stderr, fp, passed)
            self.state.evidence.append({"kind": "review", "path": str(path.relative_to(self.root)), "fingerprint": fp, "passed": passed, "harness": name})
            record(self.state, "review", reviewer=name, passed=passed, read_only_clean=clean)
            passes.append(passed)
        save_state(self.root, self.state)
        self._transition(stage.on_success if all(passes) else stage.on_failure, f"reviews {'passed' if all(passes) else 'failed'}")
        return self.state.status

    def _human(self, stage: Stage) -> str:
        risk, reasons = classify(self.root)
        required = risk in self.project.config.human_approval_for or stage.metadata.get("always", False)
        if not required and self.project.config.auto_approve_low_risk:
            record(self.state, "auto_approved", risk=risk, reasons=reasons)
            self._transition(stage.on_success, f"auto-approved {risk} risk")
            return self.state.status
        self.state.status = "awaiting_approval"
        self.state.awaiting_reason = f"{stage.title}; risk={risk}; {'; '.join(reasons)}"
        record(self.state, "awaiting_approval", risk=risk, reasons=reasons)
        save_state(self.root, self.state)
        return self.state.status

    def run(self, max_steps: int = 100) -> str:
        for _ in range(max_steps):
            status = self.step()
            if status in {"complete", "blocked", "awaiting_approval"}:
                return status
        raise EngineError("workflow exceeded maximum stage transitions")

    def approve(self) -> None:
        if self.state.status != "awaiting_approval":
            raise EngineError("run is not awaiting human approval")
        stage = self.pattern.stage(self.state.stage)
        record(self.state, "human_approved", at=now_iso(), plan_hash=self.state.plan_hash)
        self._transition(stage.on_success, "human approval")
