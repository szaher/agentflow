from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from .bootstrap import BootstrapError, init_project
from .config import find_root, load_project, save_config
from .engine import Engine, EngineError
from . import provider
from .agentic import Agentic, AgenticError, AgenticUnavailable
from .gates import plan_gate, run_gates
from .git import head_commit, implementation_fingerprint
from .harnesses import detected as detect_harnesses, names as harness_names
from .models import ProjectConfig
from .patterns import list_patterns, load_pattern
from .requirements import requirements
from .session import build_session_request
from .state import load_state, new_state, record, save_state, workspace


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if args.init_git and not (root / ".git").exists():
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    cfg = ProjectConfig(pattern=args.pattern, executor=args.agent, reviewers=args.reviewers.split(",") if args.reviewers else ["codex"])
    try:
        result = init_project(root, cfg, force=args.force, install_provider=not args.no_provider_install,
                              replace_provider=args.update_provider)
    except AgenticUnavailable as exc:
        print(f"agentflow: {exc}", file=sys.stderr); return 2
    except (BootstrapError, AgenticError) as exc:
        print(f"agentflow: {exc}", file=sys.stderr); return 1
    print(f"Initialized Agentflow in {root}")
    print(f"Pattern: {cfg.pattern} | executor: {cfg.executor} | reviewers: {', '.join(cfg.reviewers)}")
    print(f"Provider {provider.PROVIDER_NAME}: {result.provider_action} (was {result.provider_state})")
    for block in result.blocks:
        print(f"Block {block['block_id']} in {block['file']}: {block['status']}")
    placed = sorted({o["harness"] for o in (result.skills or {}).get("outcomes", [])})
    print(f"Skill {provider.SKILL_NAME} via agentic-dev: {', '.join(placed)}")
    return 0


def cmd_provider_status(args: argparse.Namespace) -> int:
    try:
        current = provider.status(Agentic())
    except AgenticError as exc:
        print(f"agentflow: {exc}", file=sys.stderr); return 2
    if args.json:
        print(json.dumps(current.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"{provider.PROVIDER_NAME}: {current.state} — {provider.explain(current)}")
    return 0 if current.state == provider.CURRENT else 1


def cmd_provider_install(args: argparse.Namespace) -> int:
    try:
        action, before = provider.ensure(Agentic(), install=True, replace=args.replace)
    except AgenticError as exc:
        print(f"agentflow: {exc}", file=sys.stderr); return 2
    except provider.ProviderError as exc:
        print(f"agentflow: {exc}", file=sys.stderr); return 1
    print(f"{provider.PROVIDER_NAME}: {action} (was {before.state})")
    return 0


def cmd_patterns(args: argparse.Namespace) -> int:
    root = find_root()
    for p in list_patterns(root):
        tags = ", ".join(p.tags)
        print(f"{p.name:22} {p.description}" + (f" [{tags}]" if tags else ""))
    return 0


def _harness_facts() -> dict[str, bool]:
    return detect_harnesses(Agentic().doctor().get("tools") or {})


def cmd_detect(args: argparse.Namespace) -> int:
    try:
        statuses = _harness_facts()
    except AgenticError as exc:
        print(f"agentflow: {exc}", file=sys.stderr); return 2
    for name, ok in statuses.items():
        print(f"{'✓' if ok else '○'} {name}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    project = load_project()
    print(f"Project: {project.root}")
    print(f"Pattern: {project.config.pattern}")
    pattern = load_pattern(project.config.pattern, project.root)
    print(f"✓ pattern valid: {pattern.name} ({len(pattern.stages)} stages)")
    try:
        agentic = Agentic()
        statuses = detect_harnesses(agentic.doctor().get("tools") or {})
        gp = plan_gate(project.root, project.config, project.config.gate_profile, agentic=agentic)
        discovered = agentic.discovered_kinds(project.root) if gp.kinds else set()
        current = provider.status(agentic)
    except AgenticError as exc:
        print(f"✗ agentic-dev: {exc}"); return 2
    for name, ok in statuses.items(): print(f"{'✓' if ok else '○'} harness {name}")
    print(f"{'✓' if current.state == provider.CURRENT else '✗'} provider {provider.PROVIDER_NAME}: {current.state}"
          + ("" if current.state == provider.CURRENT else f" — {provider.explain(current)}"))
    if gp.commands:
        print(f"✓ gates ({gp.profile}) via agentic-dev, explicit: " + "; ".join(gp.commands))
    for kind in gp.kinds:
        # Informational only: the requirement stands, and the gate fails if a kind has no command.
        mark = "✓" if kind in discovered else "✗"
        note = "" if kind in discovered else " — no command discovered; this gate will fail (no-checks)"
        print(f"{mark} gate ({gp.profile}) requires {kind}{note}")
    return 0 if statuses.get(project.config.executor, False) else 2


def cmd_configure(args: argparse.Namespace) -> int:
    project = load_project()
    cfg = project.config
    if args.pattern: cfg.pattern = args.pattern; load_pattern(args.pattern, project.root)
    if args.agent: cfg.executor = args.agent
    if args.reviewers is not None: cfg.reviewers = [x for x in args.reviewers.split(",") if x]
    if args.profile: cfg.gate_profile = args.profile
    save_config(project.root, cfg)
    print(json.dumps(cfg.to_dict(), indent=2))
    return 0


def _make_state(task: str, pattern_name: str | None, agent: str | None, reviewers: str | None, *, save: bool = True):
    """A new run. With ``save=False`` (``--dry-run``) it exists only in memory."""
    project = load_project()
    pattern_name = pattern_name or project.config.pattern
    pattern = load_pattern(pattern_name, project.root)
    executor = agent or project.config.executor
    revs = [x for x in reviewers.split(",") if x] if reviewers is not None else project.config.reviewers
    state = new_state(task, pattern.name, pattern.entry, executor, revs, run_start_commit=head_commit(project.root))
    if save:
        save_state(project.root, state)
    return project, state


def cmd_run(args: argparse.Namespace) -> int:
    # Resolve and display the environment before writing run state or creating a worktree.
    project, state = _make_state(args.task, args.pattern, args.agent, args.reviewers, save=False)
    engine = Engine(project, state, agentic=Agentic())
    try:
        request = build_session_request(project, engine.pattern, state.task, state.executor, state.reviewers)
        plan = engine.agentic.plan_session(project.root, request)
    except (AgenticError, ValueError) as exc:
        print(f"agentflow: session planning failed: {exc}", file=sys.stderr)
        return 2
    print(f"Run {state.run_id}: pattern={state.pattern}, executor={state.executor}, reviewers={','.join(state.reviewers) or '(executor)'}")
    _print_session_plan(plan)
    if args.dry_run:
        print(f"Entry stage: {state.stage}")
        for line in engine.requirements.describe(): print(f"Requires {line}")
        print("Dry run: nothing was saved or created.")
        return 0 if plan["status"] == "ready" else 2
    if plan["status"] != "ready":
        print("Session blocked; no run state, worktree, or stage was created.")
        return 2
    method = _session_approval(plan["plan_digest"], yes=args.yes)
    if method is None:
        print("Session not approved; no run state or worktree was created.")
        return 2
    try:
        current = engine.agentic.plan_session(project.root, request)
    except AgenticError as exc:
        print(f"agentflow: session revalidation failed: {exc}", file=sys.stderr)
        return 2
    if current["status"] != "ready" or current["plan_digest"] != plan["plan_digest"]:
        print("Session plan changed before approval was recorded; review the new plan and run again.")
        _print_session_plan(current)
        return 2
    state.session_request = request
    state.session_plan = current
    state.approved_plan_digest = current["plan_digest"]
    record(state, "session_approved", plan_digest=state.approved_plan_digest, method=method)
    save_state(project.root, state)
    print(f"Approved session plan {state.approved_plan_digest} for run {state.run_id}.")
    return 0


def _session_approval(digest: str, *, yes: bool) -> str | None:
    if yes:
        return "--yes"
    if not sys.stdin.isatty():
        print("Interactive approval requires a terminal; use --yes to approve this run explicitly.")
        return None
    try:
        answer = input(f"Approve plan_digest {digest} for this run? [y/N] ")
    except EOFError:
        return None
    return "interactive" if answer.strip().lower() in {"y", "yes"} else None


def _print_session_plan(plan: dict) -> None:
    print(f"Session plan: {plan['status']} | plan_digest={plan['plan_digest']}")
    for invocation in plan["invocations"]:
        permissions = ", ".join(
            f"{dimension}={detail['effective']['level']} ({detail['enforceable']})"
            for dimension, detail in invocation["permissions"].items()
        )
        print(f"  {invocation['id']}: {invocation['harness']} {invocation['version'] or 'unavailable'}; {permissions}")
    for blocker in plan["blockers"]:
        print(f"  BLOCKED {blocker['code']}: {blocker['detail']}")


def _run_after_session_approval(engine: Engine, args: argparse.Namespace) -> int:
    try:
        status = engine.start()
        if status == "running":
            status = engine.run(max_steps=args.max_steps)
    except (EngineError, FileNotFoundError, KeyError) as exc:
        print(f"agentflow: {exc}", file=sys.stderr); return 2
    _print_worktree(engine.state)
    print(f"Status: {status}")
    if status == "blocked": print(f"Reason: {engine.state.awaiting_reason}")
    if status == "awaiting_approval": print(f"Reason: {engine.state.awaiting_reason}\nApprove with: agentflow approve")
    return 0 if status in {"complete", "awaiting_approval"} else 2


def _print_worktree(state) -> None:
    tree = state.worktree
    if tree:
        where = "removed (clean, on success)" if tree.get("cleaned") else tree["path"]
        print(f"Worktree: {where} | branch {tree['branch']} from {tree['base'][:12]}")


def cmd_step(args: argparse.Namespace) -> int:
    project = load_project(); state = load_state(project.root)
    try: status = Engine(project, state).step()
    except Exception as exc: print(f"agentflow: {exc}", file=sys.stderr); return 2
    print(status); return 0


def cmd_status(args: argparse.Namespace) -> int:
    project = load_project(); state = load_state(project.root)
    work = workspace(project.root, state)
    current = implementation_fingerprint(work) if work.is_dir() else None
    print(f"run:       {state.run_id}\nstatus:    {state.status}\npattern:   {state.pattern}\nstage:     {state.stage}\nexecutor:  {state.executor}\nreviewers: {', '.join(state.reviewers)}")
    print(f"evidence:  {len(state.evidence)} records")
    if state.worktree:
        tree = state.worktree
        print(f"worktree:  {'removed' if tree.get('cleaned') else tree['path']} (branch {tree['branch']})")
    if state.fingerprint: print(f"fresh:     {'yes' if state.fingerprint == current else 'NO — repository changed since verification'}")
    if state.awaiting_reason: print(f"reason:    {state.awaiting_reason}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    project = load_project(); state = load_state(project.root)
    profile = args.profile or project.config.gate_profile
    minimum = requirements(load_pattern(state.pattern, project.root)).minimum
    try:
        gate = run_gates(workspace(project.root, state), project.config, profile, minimum=minimum,
                         include_changed=args.include_changed,
                         base=state.run_start_commit if args.include_changed else None)
    except (AgenticError, ValueError) as exc:
        print(f"agentflow: {exc}", file=sys.stderr); return 2
    for r in gate.results:
        label = r.get("command") or r.get("test_file") or r.get("capability") or "-"
        mark = "PASS" if r.get("success") else ("SKIP" if r.get("success") is None else "FAIL")
        print(f"{mark} {r.get('kind')}: {label} ({float(r.get('duration_ms', 0)) / 1000:.2f}s)")
        if r.get("success") is False:
            if r.get("stdout"): print(r["stdout"][-4000:])
            if r.get("stderr"): print(r["stderr"][-4000:], file=sys.stderr)
    print(f"verification: {gate.status} ({gate.reason})")
    return 0 if gate.passed else 1


def cmd_approve(args: argparse.Namespace) -> int:
    project = load_project(); state = load_state(project.root)
    engine = Engine(project, state)
    try: engine.approve()
    except EngineError as exc: print(f"agentflow: {exc}", file=sys.stderr); return 2
    print(f"Approved. New status={engine.state.status}, stage={engine.state.stage}")
    if args.continue_run and engine.state.status == "running":
        status = engine.run(); print(f"Status: {status}")
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    project = load_project(); name = args.pattern or project.config.pattern
    p = load_pattern(name, project.root)
    print(f"{p.name}: {p.description}\n")
    for line in requirements(p).describe(): print(f"requires  {line}")
    for s in p.stages:
        print(f"- {s.id:20} {s.kind:7} -> pass:{s.on_success or 'done'} fail:{s.on_failure or '-'} | {s.title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentflow", description="Agentic SDLC meta-harness")
    p.add_argument("--version", action="version", version=f"agentflow {__version__}")
    sp = p.add_subparsers(dest="cmd", required=True)
    q=sp.add_parser("init"); q.add_argument("path", nargs="?", default="."); q.add_argument("--pattern", default="standard"); q.add_argument("--agent", default="claude"); q.add_argument("--reviewers", default="codex"); q.add_argument("--init-git", action="store_true"); q.add_argument("--force", action="store_true", help="refresh AgentFlow's own files and blocks (never rewrites shared files)")
    q.add_argument("--update-provider", "--replace-provider", dest="update_provider", action="store_true", help="replace an installed agentflow provider that differs from this AgentFlow's")
    q.add_argument("--no-provider-install", action="store_true", help="never install or replace the global agentflow provider; fail unless it is already current")
    q.set_defaults(func=cmd_init)
    q=sp.add_parser("provider", help="The agentflow provider (agentflow-sdlc skill) installed through Agentic Dev"); psub=q.add_subparsers(dest="provider_command", required=True)
    r=psub.add_parser("status"); r.add_argument("--json", action="store_true"); r.set_defaults(func=cmd_provider_status)
    r=psub.add_parser("install"); r.add_argument("--replace", action="store_true", help="replace an installed agentflow provider that differs"); r.set_defaults(func=cmd_provider_install)
    q=sp.add_parser("patterns"); q.set_defaults(func=cmd_patterns)
    q=sp.add_parser("detect"); q.set_defaults(func=cmd_detect)
    q=sp.add_parser("doctor"); q.set_defaults(func=cmd_doctor)
    q=sp.add_parser("configure"); q.add_argument("--pattern"); q.add_argument("--agent"); q.add_argument("--reviewers"); q.add_argument("--profile", choices=["fast","standard","strict"]); q.set_defaults(func=cmd_configure)
    q=sp.add_parser("run"); q.add_argument("task"); q.add_argument("--pattern"); q.add_argument("--agent"); q.add_argument("--reviewers"); q.add_argument("--dry-run", action="store_true"); q.add_argument("--yes", action="store_true", help="approve this run's exact session plan without a prompt"); q.add_argument("--max-steps", type=int, default=100); q.set_defaults(func=cmd_run)
    q=sp.add_parser("step"); q.set_defaults(func=cmd_step)
    q=sp.add_parser("status"); q.set_defaults(func=cmd_status)
    q=sp.add_parser("verify"); q.add_argument("--profile", choices=["fast","standard","strict"]); q.add_argument("--include-changed", action="store_true", help="add change-aware checks since the run's start commit (never removes any)"); q.set_defaults(func=cmd_verify)
    q=sp.add_parser("approve"); q.add_argument("--continue-run", action="store_true"); q.set_defaults(func=cmd_approve)
    q=sp.add_parser("explain"); q.add_argument("pattern", nargs="?"); q.set_defaults(func=cmd_explain)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"agentflow: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__": raise SystemExit(main())
