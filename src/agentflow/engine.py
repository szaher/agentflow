from __future__ import annotations

import time
from pathlib import Path

from .config import ROOT_ENV, RUN_ENV, WORKSPACE_ENV, Project
from .evidence import (write_agent_evidence, write_gate_evidence, write_precondition_evidence,
                       write_review_evidence, write_session_evidence)
from .agentic import Agentic, AgenticError
from .gates import run_gates
from .git import implementation_fingerprint, uncommitted_changes
from .harnesses import get as get_harness
from .models import Pattern, RunState, Stage
from .patterns import load_pattern
from .prompts import review_prompt, stage_prompt
from .requirements import capability_blockers, readiness_blockers, requirements
from .risk import classify
from .state import record, save_state, workspace
from .util import now_iso, sha256_text

class EngineError(RuntimeError):
    pass


def _enforceable_session(document: dict | None) -> bool:
    if not document or not document.get("invocations"):
        return False
    return all(
        set(item.get("permissions", {})) == {"filesystem", "network"}
        and all(detail.get("enforceable") == "enforceable"
                for detail in item["permissions"].values())
        for item in document["invocations"]
    )


class Engine:
    """Runs a pattern's stages.

    State and evidence live in ``root/.agentflow``. The work itself (agents,
    reviews, gates, risk, fingerprints) happens in :attr:`workspace`: the run's
    worktree when its pattern asks for isolation, otherwise ``root``.
    """

    def __init__(self, project: Project, state: RunState, agentic: Agentic | None = None):
        self.project = project
        self.agentic = agentic or Agentic()
        self.root = project.root
        self.state = state
        self.pattern: Pattern = load_pattern(state.pattern, self.root)
        self.requirements = requirements(self.pattern)
        self._outcome = "unknown"
        # Durable across `agentflow step` invocations: one metrics_unavailable record per run.
        self._metrics_off = any(h.get("event") == "metrics_unavailable" for h in state.history)

    @property
    def workspace(self) -> Path:
        return workspace(self.root, self.state)

    @property
    def harness_env(self) -> dict[str, str]:
        """Bridges a harness running in the workspace back to this run's control root."""

        return {ROOT_ENV: str(self.root), WORKSPACE_ENV: str(self.workspace), RUN_ENV: self.state.run_id}

    def _evidence_root(self) -> Path | None:
        """Evidence paths are relative to the control root; qualify them when the agent works elsewhere."""

        return self.root if self.workspace.resolve() != self.root.resolve() else None

    # -- run start: worktree, then preconditions in that workspace, then the first stage ------

    def start(self) -> str:
        """Prepare a new run. Order: create the worktree (if isolated), then readiness and
        capability preconditions in that workspace. A failed precondition blocks the run;
        nothing is remediated or enabled on the user's behalf.

        Restart-safe: ``state.started`` is persisted only once preparation completed, and
        :meth:`step` never runs a stage before that. A worktree recorded (or created) by an
        interrupted start is validated and reused, never created twice."""

        if self.state.started or self.state.status != "running":
            return self.state.status
        if self.state.session_plan is None and isinstance(self.agentic, Agentic):
            self._transition("blocked", "approved session plan is required before any stage")
            return self.state.status
        if self.state.session_plan is not None:
            return self._start_session()
        reqs = self.requirements
        if reqs.worktree and not self._ensure_worktree():
            return self.state.status
        blockers: list[str] = []
        try:
            if reqs.readiness:
                document = self.agentic.readiness(self.workspace, reqs.readiness)
                self._precondition_evidence("readiness", document, document["passed"])
                if not document["passed"]:
                    blockers.append(readiness_blockers(document))
            if reqs.capabilities:
                status = self.agentic.capabilities()
                problems = capability_blockers(reqs.capabilities, status)
                self._precondition_evidence("capabilities", {name: status.get(name) for name in reqs.capabilities},
                                            not problems)
                blockers += problems
        except AgenticError as exc:
            self._transition("blocked", f"preconditions could not be checked: {exc}")
            return self.state.status
        if blockers:
            self._transition("blocked", "preconditions not met: " + " | ".join(blockers))
            return self.state.status
        if reqs.readiness or reqs.capabilities:
            record(self.state, "preconditions_passed", workspace=str(self.workspace))
        self.state.started = True
        record(self.state, "run_started", workspace=str(self.workspace))
        save_state(self.root, self.state)
        return self.state.status

    def _start_session(self) -> str:
        if not self._revalidate_approved_session():
            return self.state.status
        plan = self.state.session_plan
        digest = self.state.approved_plan_digest
        assert plan is not None and digest is not None
        if not self._ensure_worktree():
            return self.state.status
        try:
            prepared = self.agentic.prepare_session(self.workspace, plan)
        except AgenticError as exc:
            self._transition("blocked", f"session preparation failed: {exc}")
            return self.state.status
        if prepared.get("plan_digest") != digest:
            self._transition("blocked", "session record does not match the approved plan digest")
            return self.state.status
        if not _enforceable_session(prepared):
            self._transition("blocked", "session permission enforcement is unknown or unsupported")
            return self.state.status
        path = write_session_evidence(self.root, self.state, prepared)
        self.state.session_record = prepared
        self.state.evidence.append({"kind": "session", "path": str(path.relative_to(self.root)),
                                    "plan_digest": digest})
        record(self.state, "session_prepared", workspace=str(self.workspace), plan_digest=digest)
        self.state.started = True
        record(self.state, "run_started", workspace=str(self.workspace))
        save_state(self.root, self.state)
        return self.state.status

    def _revalidate_approved_session(self) -> bool:
        plan = self.state.session_plan
        request = self.state.session_request
        digest = self.state.approved_plan_digest
        if not (plan and request and digest and plan.get("plan_digest") == digest and plan.get("status") == "ready"):
            self._transition("blocked", "session approval is missing or does not match the stored plan")
            return False
        try:
            current = self.agentic.plan_session(self.root, request)
        except AgenticError as exc:
            self._transition("blocked", f"session plan could not be revalidated: {exc}")
            return False
        if current.get("status") != "ready" or current.get("plan_digest") != digest:
            self._transition("blocked", "session plan changed after approval; replan and approve a new run")
            return False
        return True

    def _ensure_worktree(self) -> bool:
        tree = self.state.worktree
        if tree:  # recorded by an interrupted start: reuse it, never create a second one
            if not Path(tree["path"]).is_dir():
                self._transition("blocked", f"the run's worktree is missing: {tree['path']}")
                return False
            if self.state.session_plan is not None:
                try:
                    current = self.agentic.worktree_status(self.root, tree["name"])
                except AgenticError as exc:
                    self._transition("blocked", f"the run's worktree cannot be verified: {exc}")
                    return False
                if Path(current["worktree"]).resolve() != Path(tree["path"]).resolve() or current["branch"] != tree["branch"]:
                    self._transition("blocked", "the run's recorded worktree path or branch changed")
                    return False
            return True
        base = self.state.run_start_commit
        if not base:
            self._transition("blocked", "worktree isolation needs a commit to start from; commit first")
            return False
        dirty = uncommitted_changes(self.root)
        if dirty:
            shown = ", ".join(dirty[:8]) + (f" (+{len(dirty) - 8} more)" if len(dirty) > 8 else "")
            self._transition("blocked", "worktree isolation starts from the committed run-start snapshot; "
                                        f"commit or stash the current changes first: {shown}")
            return False
        name, branch = f"agentflow-{self.state.run_id}", f"agentflow/{self.state.run_id}"
        try:
            document = self.agentic.create_worktree(self.root, name=name, branch=branch, base=base,
                                                    agent=self.state.executor, task=self.state.task)
            event = "worktree_created"
        except AgenticError as exc:
            # Created before an interruption but never recorded? Adopt it only if it is exactly ours.
            try:
                document = self.agentic.worktree_status(self.root, name)
            except AgenticError:
                document = None
            if not document or document["branch"] != branch:
                self._transition("blocked", f"worktree could not be created: {exc}")
                return False
            event = "worktree_adopted"
        assert document is not None
        self.state.worktree = {"name": name, "path": document["worktree"], "branch": branch,
                               "base": base, "cleaned": False}
        record(self.state, event, **{k: v for k, v in self.state.worktree.items() if k != "cleaned"})
        save_state(self.root, self.state)
        return True

    def _precondition_evidence(self, name: str, document: dict, passed: bool) -> None:
        path = write_precondition_evidence(self.root, self.state, name, document)
        self.state.evidence.append({"kind": "precondition", "name": name, "path": str(path.relative_to(self.root)),
                                    "passed": passed})
        record(self.state, "precondition", name=name, passed=passed)

    # -- transitions, worktree cleanup, metrics ---------------------------------------------------

    def _transition(self, target: str | None, reason: str) -> None:
        if target in (None, "done"):
            self.state.status = "complete"
            self.state.awaiting_reason = None
            record(self.state, "complete", reason=reason)
            self._cleanup_on_success()
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

    def _cleanup_on_success(self) -> None:
        """Optional pattern policy. Never forced: a worktree with uncommitted work is kept."""

        tree = self.state.worktree
        if not (tree and self.requirements.cleanup_on_success and not tree.get("cleaned")):
            return
        try:
            self.agentic.clean_worktree(self.root, tree["name"])
        except AgenticError as exc:
            record(self.state, "worktree_kept", path=tree["path"], branch=tree["branch"], reason=str(exc))
            return
        tree["cleaned"] = True
        record(self.state, "worktree_cleaned", path=tree["path"], branch=tree["branch"])

    def _metric(self, stage: Stage, outcome: str, started: float) -> None:
        """One ``agentflow.stage`` event per executed stage. Agentic Dev stores it only when the
        user enabled metrics; a metrics problem never changes the run's outcome."""

        if self._metrics_off:
            return
        fields = {"stage": stage.id, "kind": stage.kind, "outcome": outcome, "pattern": self.pattern.name,
                  "attempt": self.state.attempts_by_stage.get(stage.id, 0),
                  "duration_ms": int((time.monotonic() - started) * 1000)}
        try:
            self.agentic.record_metric("agentflow.stage", fields, repository=self.root, session_id=self.state.run_id)
        except AgenticError as exc:
            self._metrics_off = True
            record(self.state, "metrics_unavailable", error=str(exc))
            save_state(self.root, self.state)

    # -- stages ---------------------------------------------------------------------------------

    def _session_permissions(self, role: str, harness: str) -> dict | None:
        """Return approved bounds or refuse launch; legacy engine fixtures have no session."""

        if self.state.session_plan is None:
            return None
        doc = self.state.session_record
        if not doc or doc.get("plan_digest") != self.state.approved_plan_digest:
            raise EngineError("session record is missing or differs from the approved plan")
        invocations = doc.get("invocations") or []
        if any(detail.get("enforceable") != "enforceable"
               for item in invocations for detail in item.get("permissions", {}).values()):
            raise EngineError("session permission enforcement is unknown or unsupported")
        matches = [item for item in invocations if item.get("role") == role and item.get("harness") == harness]
        if not matches:
            raise EngineError(f"no approved {role} invocation for {harness}")
        return matches[0]["permissions"]

    def step(self) -> str:
        if self.state.status in {"complete", "blocked", "awaiting_approval"}:
            return self.state.status
        if self.state.session_plan is None and isinstance(self.agentic, Agentic):
            self._transition("blocked", "approved session plan is required before any stage")
            return self.state.status
        if self.state.session_plan is not None and self.state.started and not self._revalidate_approved_session():
            return self.state.status
        if not self.state.started and self.start() != "running":
            return self.state.status
        if self.state.session_plan is not None and (
            self.state.session_record is None
            or self.state.session_record.get("plan_digest") != self.state.approved_plan_digest
            or not _enforceable_session(self.state.session_record)
        ):
            self._transition("blocked", "session record or permission enforcement is not valid for launch")
            return self.state.status
        if self.state.session_plan is not None:
            if self.state.worktree is None:
                self._transition("blocked", "prepared session worktree is missing")
                return self.state.status
            if not self._ensure_worktree():
                return self.state.status
        if not self.workspace.is_dir():
            self._transition("blocked", f"the run's worktree is missing: {self.workspace}")
            return self.state.status
        stage = self.pattern.stage(self.state.stage)
        started = time.monotonic()
        if stage.kind == "agent":
            status = self._agent(stage)
        elif stage.kind == "gate":
            status = self._gate(stage)
        elif stage.kind == "review":
            status = self._review(stage)
        elif stage.kind == "human":
            status = self._human(stage)
        else:
            self._outcome = "skipped"
            self._transition(stage.on_success, f"noop stage {stage.id}")
            status = self.state.status
        self._metric(stage, self._outcome, started)
        return status

    def _agent(self, stage: Stage) -> str:
        try:
            permissions = self._session_permissions("implementer", self.state.executor)
        except EngineError as exc:
            self._transition("blocked", str(exc))
            return self.state.status
        cfg = self.project.config.harness.get(self.state.executor, {})
        harness = get_harness(self.state.executor, cfg)
        if permissions is not None and not getattr(harness, "session_launch_verified", False):
            self._transition("blocked", f"verified session launch recipe is unavailable for {self.state.executor}")
            return self.state.status
        used = self.state.attempts_by_stage.get(stage.id, 0)
        if used >= stage.max_attempts:
            self._outcome = "attempt-limit"
            self._transition("blocked", f"attempt limit reached at {stage.id}")
            return self.state.status
        used += 1
        self.state.attempts_by_stage[stage.id] = used
        self.state.attempt = used
        save_state(self.root, self.state)
        prompt = stage_prompt(self.pattern, stage, self.state, control_root=self._evidence_root())
        try:
            result = (harness.execute_session(self.workspace, prompt, permissions=permissions,
                                              extra=cfg, env=self.harness_env)
                      if permissions is not None else
                      harness.execute(self.workspace, prompt, extra=cfg, env=self.harness_env))
        except NotImplementedError as exc:
            self._transition("blocked", f"verified session launch recipe is unavailable: {exc}")
            return self.state.status
        fp = implementation_fingerprint(self.workspace)
        ep = write_agent_evidence(self.root, self.state, harness.name, result.stdout, result.stderr, fp, result.returncode)
        self.state.evidence.append({"kind": "agent", "path": str(ep.relative_to(self.root)), "fingerprint": fp, "stage": stage.id, "harness": harness.name})
        if stage.role in {"planner", "specifier", "migration-planner"} and result.returncode == 0:
            self.state.plan_hash = sha256_text([result.stdout])
        record(self.state, "agent_result", stage=stage.id, harness=harness.name, returncode=result.returncode, changed=result.changed)
        save_state(self.root, self.state)
        self._outcome = "succeeded" if result.returncode == 0 else "failed"
        if result.returncode == 0:
            self._transition(stage.on_success, f"{harness.name} completed {stage.id}")
        elif self.state.attempt >= stage.max_attempts:
            self._transition(stage.on_failure or "blocked", f"{harness.name} failed {stage.id}")
        return self.state.status

    def _gate(self, stage: Stage) -> str:
        profile = stage.gate_profile or self.project.config.gate_profile
        fp = implementation_fingerprint(self.workspace)
        try:
            # Workflow gates are full-project only; change-aware augmentation is not a stage option yet.
            gate = run_gates(self.workspace, self.project.config, profile, agentic=self.agentic,
                             minimum=self.requirements.minimum)
        except (AgenticError, ValueError) as exc:
            # A missing or incompatible verifier is not a code failure: block, do not retry implementation.
            self._outcome = "unavailable"
            record(self.state, "gates_unavailable", stage=stage.id, profile=profile, error=str(exc))
            self._transition("blocked", f"verification unavailable: {exc}")
            return self.state.status
        path = write_gate_evidence(self.root, self.state, gate, fp)
        # Zero checks is never verification: only an explicit `passed` passes.
        passed = gate.passed
        self._outcome = gate.status
        self.state.evidence.append({"kind": "gates", "path": str(path.relative_to(self.root)), "fingerprint": fp,
                                    "passed": passed, "status": gate.status})
        record(self.state, "gates", stage=stage.id, profile=profile, passed=passed, status=gate.status,
               checks_executed=(gate.verification or {}).get("checks_executed", 0))
        self.state.fingerprint = fp
        save_state(self.root, self.state)
        self._transition(stage.on_success if passed else stage.on_failure, f"gates {gate.status}: {gate.reason}")
        return self.state.status

    def _review(self, stage: Stage) -> str:
        work = self.workspace
        fp = implementation_fingerprint(work)
        reviewers = self.state.reviewers or self.project.config.reviewers
        count = stage.reviewers or len(reviewers) or 1
        selected = [reviewers[i % len(reviewers)] for i in range(count)] if reviewers else [self.state.executor] * count
        approved = []
        try:
            for name in selected:
                permissions = self._session_permissions("reviewer", name)
                cfg = self.project.config.harness.get(name, {})
                harness = get_harness(name, cfg)
                if permissions is not None and not getattr(harness, "session_launch_verified", False):
                    raise EngineError(f"verified session launch recipe is unavailable for {name}")
                approved.append((name, cfg, harness, permissions))
        except EngineError as exc:
            self._transition("blocked", str(exc))
            return self.state.status
        passes = []
        for idx, (name, cfg, harness, permissions) in enumerate(approved, 1):
            before = implementation_fingerprint(work)
            try:
                result = (harness.execute_session(work, review_prompt(self.pattern, stage, self.state),
                                                  permissions=permissions, read_only=True, extra=cfg,
                                                  env=self.harness_env)
                          if permissions is not None else
                          harness.execute(work, review_prompt(self.pattern, stage, self.state), read_only=True,
                                          extra=cfg, env=self.harness_env))
            except NotImplementedError as exc:
                self._transition("blocked", f"verified session launch recipe is unavailable: {exc}")
                return self.state.status
            after = implementation_fingerprint(work)
            clean = before == after
            passed = result.returncode == 0 and clean and "AGENTFLOW_REVIEW_PASS" in result.stdout and "AGENTFLOW_REVIEW_FAIL" not in result.stdout
            path = write_review_evidence(self.root, self.state, name, idx, result.stdout, result.stderr, fp, passed)
            self.state.evidence.append({"kind": "review", "path": str(path.relative_to(self.root)), "fingerprint": fp, "passed": passed, "harness": name})
            record(self.state, "review", reviewer=name, passed=passed, read_only_clean=clean)
            passes.append(passed)
        save_state(self.root, self.state)
        self._outcome = "passed" if all(passes) else "failed"
        self._transition(stage.on_success if all(passes) else stage.on_failure, f"reviews {'passed' if all(passes) else 'failed'}")
        return self.state.status

    def _human(self, stage: Stage) -> str:
        risk, reasons = classify(self.workspace)
        required = risk in self.project.config.human_approval_for or stage.metadata.get("always", False)
        if not required and self.project.config.auto_approve_low_risk:
            self._outcome = "auto-approved"
            record(self.state, "auto_approved", risk=risk, reasons=reasons)
            self._transition(stage.on_success, f"auto-approved {risk} risk")
            return self.state.status
        self._outcome = "awaiting-approval"
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
