from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import __version__
from .bootstrap import init_project
from .config import load_project, save_config
from .engine import Engine, EngineError
from .gates import commands_for, run_gates
from .git import implementation_fingerprint
from .harnesses import detected as detect_harnesses, names as harness_names
from .models import ProjectConfig
from .patterns import list_patterns, load_pattern
from .state import load_state, new_state, record, save_state


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if args.init_git and not (root / ".git").exists():
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    cfg = ProjectConfig(pattern=args.pattern, executor=args.agent, reviewers=args.reviewers.split(",") if args.reviewers else ["codex"])
    paths = init_project(root, cfg, force=args.force)
    print(f"Initialized Agentflow in {root}")
    print(f"Pattern: {cfg.pattern} | executor: {cfg.executor} | reviewers: {', '.join(cfg.reviewers)}")
    print(f"Generated {len(paths)} integration files")
    return 0


def cmd_patterns(args: argparse.Namespace) -> int:
    root = Path.cwd()
    for p in list_patterns(root):
        tags = ", ".join(p.tags)
        print(f"{p.name:22} {p.description}" + (f" [{tags}]" if tags else ""))
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    for name, ok in detect_harnesses().items():
        print(f"{'✓' if ok else '○'} {name}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    project = load_project()
    print(f"Project: {project.root}")
    print(f"Pattern: {project.config.pattern}")
    statuses = detect_harnesses()
    for name, ok in statuses.items(): print(f"{'✓' if ok else '○'} harness {name}")
    pattern = load_pattern(project.config.pattern, project.root)
    print(f"✓ pattern valid: {pattern.name} ({len(pattern.stages)} stages)")
    cmds = commands_for(project.root, project.config, project.config.gate_profile)
    if cmds:
        for name, cmd in cmds: print(f"✓ gate {name}: {cmd}")
    else:
        print("! no deterministic gates detected; configure .agentflow/config.json -> gates")
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


def _make_state(task: str, pattern_name: str | None, agent: str | None, reviewers: str | None):
    project = load_project()
    pattern_name = pattern_name or project.config.pattern
    pattern = load_pattern(pattern_name, project.root)
    executor = agent or project.config.executor
    revs = [x for x in reviewers.split(",") if x] if reviewers is not None else project.config.reviewers
    state = new_state(task, pattern.name, pattern.entry, executor, revs)
    save_state(project.root, state)
    return project, state


def cmd_run(args: argparse.Namespace) -> int:
    project, state = _make_state(args.task, args.pattern, args.agent, args.reviewers)
    engine = Engine(project, state)
    print(f"Run {state.run_id}: pattern={state.pattern}, executor={state.executor}, reviewers={','.join(state.reviewers) or '(executor)'}")
    if args.dry_run:
        print(f"Entry stage: {state.stage}")
        return 0
    try:
        status = engine.run(max_steps=args.max_steps)
    except (EngineError, FileNotFoundError, KeyError) as exc:
        print(f"agentflow: {exc}", file=sys.stderr); return 2
    print(f"Status: {status}")
    if status == "awaiting_approval": print(f"Reason: {engine.state.awaiting_reason}\nApprove with: agentflow approve")
    return 0 if status in {"complete", "awaiting_approval"} else 2


def cmd_step(args: argparse.Namespace) -> int:
    project = load_project(); state = load_state(project.root)
    try: status = Engine(project, state).step()
    except Exception as exc: print(f"agentflow: {exc}", file=sys.stderr); return 2
    print(status); return 0


def cmd_status(args: argparse.Namespace) -> int:
    project = load_project(); state = load_state(project.root)
    current = implementation_fingerprint(project.root)
    print(f"run:       {state.run_id}\nstatus:    {state.status}\npattern:   {state.pattern}\nstage:     {state.stage}\nexecutor:  {state.executor}\nreviewers: {', '.join(state.reviewers)}")
    print(f"evidence:  {len(state.evidence)} records")
    if state.fingerprint: print(f"fresh:     {'yes' if state.fingerprint == current else 'NO — repository changed since verification'}")
    if state.awaiting_reason: print(f"reason:    {state.awaiting_reason}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    project = load_project(); state = load_state(project.root)
    profile = args.profile or project.config.gate_profile
    results = run_gates(project.root, project.config, profile)
    if not results:
        print("No gates detected/configured.", file=sys.stderr); return 2
    for r in results:
        print(f"{'PASS' if r.passed else 'FAIL'} {r.name}: {r.command} ({r.duration_s:.2f}s)")
        if not r.passed:
            if r.stdout: print(r.stdout[-4000:])
            if r.stderr: print(r.stderr[-4000:], file=sys.stderr)
    return 0 if all(r.passed for r in results) else 1


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
    for s in p.stages:
        print(f"- {s.id:20} {s.kind:7} -> pass:{s.on_success or 'done'} fail:{s.on_failure or '-'} | {s.title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentflow", description="Agentic SDLC meta-harness")
    p.add_argument("--version", action="version", version=f"agentflow {__version__}")
    sp = p.add_subparsers(dest="cmd", required=True)
    q=sp.add_parser("init"); q.add_argument("path", nargs="?", default="."); q.add_argument("--pattern", default="standard"); q.add_argument("--agent", default="claude"); q.add_argument("--reviewers", default="codex"); q.add_argument("--init-git", action="store_true"); q.add_argument("--force", action="store_true"); q.set_defaults(func=cmd_init)
    q=sp.add_parser("patterns"); q.set_defaults(func=cmd_patterns)
    q=sp.add_parser("detect"); q.set_defaults(func=cmd_detect)
    q=sp.add_parser("doctor"); q.set_defaults(func=cmd_doctor)
    q=sp.add_parser("configure"); q.add_argument("--pattern"); q.add_argument("--agent"); q.add_argument("--reviewers"); q.add_argument("--profile", choices=["fast","standard","strict"]); q.set_defaults(func=cmd_configure)
    q=sp.add_parser("run"); q.add_argument("task"); q.add_argument("--pattern"); q.add_argument("--agent"); q.add_argument("--reviewers"); q.add_argument("--dry-run", action="store_true"); q.add_argument("--max-steps", type=int, default=100); q.set_defaults(func=cmd_run)
    q=sp.add_parser("step"); q.set_defaults(func=cmd_step)
    q=sp.add_parser("status"); q.set_defaults(func=cmd_status)
    q=sp.add_parser("verify"); q.add_argument("--profile", choices=["fast","standard","strict"]); q.set_defaults(func=cmd_verify)
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
