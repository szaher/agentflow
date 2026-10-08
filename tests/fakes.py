"""Test doubles for Agentic Dev (unit tests only; contract tests use the real installed CLI)."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

from agentflow.agentic import REQUIRED_FEATURES, AgenticUnavailable


class FakeAgentic:
    """Answers like the Agentic client would, recording every verify request.

    Like Agentic Dev, a requested kind it has no command for makes the run
    ``no-checks`` with ``missing_kinds`` and executes nothing.
    """

    def __init__(self, kinds=("lint", "test"), status="passed", missing=(), unavailable=None,
                 bundled_digest="a" * 64, installed=None, block_status="created", skills_status="ok",
                 tools=("claude", "codex"), readiness_passed=True, capability_state=None, worktree_root=None,
                 clean_error=None, metrics_error=None, session_status="ready", session_digest="d" * 64,
                 prepare_error=None):
        self.kinds = set(kinds)
        self.status = status
        self.missing = list(missing)
        self.unavailable = unavailable
        self.calls: list[dict] = []
        # Bootstrap state: the bundled provider digest, the global registry, and canned answers.
        self.bundled_digest = bundled_digest
        self.installed = list(installed or [])
        self.block_status = block_status
        self.skills_status = skills_status
        self.tools = set(tools)
        self.provider_adds: list[dict] = []
        self.blocks: list[dict] = []
        self.skill_calls: list[dict] = []
        # Pattern requirements: canned answers, and every call in order.
        self.readiness_passed = readiness_passed
        self.capability_state = dict(capability_state or {})
        self.worktree_root = worktree_root
        self.clean_error = clean_error
        self.metrics_error = metrics_error
        self.requirement_calls: list[tuple] = []
        self.worktrees: dict[str, dict] = {}
        self.metrics: list[dict] = []
        self.session_status = session_status
        self.session_digest = session_digest
        self.session_calls: list[tuple] = []
        self.session_plan_override: dict | None = None
        self.prepare_error = prepare_error

    def plan_session(self, root, request):
        self.session_calls.append(("plan", str(root), request))
        if self.session_plan_override is not None:
            return dict(self.session_plan_override)
        return {
            "schema_version": "1", "document_type": "agentic.session-plan",
            "status": self.session_status, "repository": str(root), "request": request,
            "plan_digest": self.session_digest, "request_digest": "r" * 64,
            "inputs_digest": "i" * 64,
            "invocations": [{"id": item["id"], "role": item["role"],
                             "harness": item["harness"], "version": "test-1.0",
                             "permissions": {dimension: {"effective": {"level": bounds["minimum"]},
                                                        "enforceable": "enforceable" if self.session_status == "ready" else "unknown"}
                                             for dimension, bounds in item["permissions"].items()}}
                            for item in request["invocations"]],
            "blockers": [] if self.session_status == "ready" else
                        [{"code": "permission-unenforceable", "detail": "test unknown enforcement"}],
        }

    def prepare_session(self, workspace, plan):
        self.session_calls.append(("prepare", str(workspace), plan["plan_digest"]))
        if self.prepare_error:
            from agentflow.agentic import AgenticError

            raise AgenticError(self.prepare_error)
        return {
            "schema_version": "1",
            "document_type": "agentic.session-record",
            "status": "prepared",
            "repository": plan["repository"],
            "workspace": str(workspace),
            "commit": subprocess.run(
                ["git", "-C", str(workspace), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip(),
            "plan_digest": plan["plan_digest"],
            "request_digest": plan["request_digest"],
            "inputs_digest": plan["inputs_digest"],
            "invocations": plan["invocations"],
        }

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
        missing = self.missing or [kind for kind in kinds if kind not in self.kinds]
        if missing:
            return verification_document("no-checks", kinds, commands, missing)
        return verification_document(self.status, kinds, commands, [])


def _bootstrap_methods():
    def inspect_provider(self, source):
        self.handshake()
        return {"name": "agentflow", "version": "0.1.0", "content_digest": self.bundled_digest, "source": str(source)}

    def providers(self):
        self.handshake()
        return list(self.installed)

    def add_provider(self, source, *, sha256):
        self.handshake()
        self.provider_adds.append({"source": str(source), "sha256": sha256})
        self.installed = [p for p in self.installed if p["name"] != "agentflow"] + [installed_provider(sha256)]
        return {"name": "agentflow", "content_digest": sha256}

    def put_block(self, root, *, file, owner, block, content, dry_run=False):
        self.handshake()
        self.blocks.append({"file": file, "owner": owner, "block": block, "dry_run": dry_run})
        ok = self.block_status in {"created", "appended", "replaced", "unchanged"}
        return {"document_type": "agentic.instruction-block", "file": file, "block_id": f"{owner}.{block}",
                "status": self.block_status, "exit_code": 0 if ok else 1, "dry_run": dry_run,
                "reason": None if ok else "managed block agentflow.workflow was edited by hand"}

    def activate_skills(self, root, names, *, target="all", shared=True, dry_run=False):
        self.handshake()
        self.skill_calls.append({"names": list(names), "target": target, "shared": shared, "dry_run": dry_run})
        status = "skipped-unmanaged" if self.skills_status == "conflict" else "written"
        return {"document_type": "agentic.skills-activation", "status": self.skills_status, "dry_run": dry_run,
                "exit_code": 0 if self.skills_status == "ok" else 1,
                "outcomes": [{"skill": n, "harness": "claude", "path": f".claude/skills/{n}/SKILL.md", "status": status}
                             for n in names]}

    def doctor(self):
        self.handshake()
        return {"document_type": "agentic.doctor",
                "tools": {name: {"available": name in self.tools, "path": None} for name in ("claude", "codex", "pi", "opencode")}}

    return locals()


def _requirement_methods():
    import subprocess
    from datetime import datetime, timezone

    from agentflow.agentic import AgenticError

    def readiness(self, workspace, target):
        self.handshake()
        self.requirement_calls.append(("readiness", str(workspace), target))
        passed = self.readiness_passed
        return {"document_type": "agentic.readiness-verification", "target": target, "scope": "local",
                "passed": passed, "exit_code": 0 if passed else 1,
                "maturity": {"current": target if passed else "unaware", "target": target, "target_met": passed},
                "blockers": [] if passed else [{"id": "context.readme.setup", "title": "README explains setup"}]}

    def capabilities(self):
        self.handshake()
        self.requirement_calls.append(("capabilities",))
        return {name: {"enabled": enabled, "provider": "x"} for name, enabled in self.capability_state.items()}

    def create_worktree(self, root, *, name, branch, base, agent=None, task=None):
        self.handshake()
        self.requirement_calls.append(("worktree-create", name, branch, base))
        path = Path(self.worktree_root or Path(root).parent / "worktrees") / name
        done = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "worktree",
                "add",
                "-q",
                "-b",
                branch,
                str(path),
                base,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode:  # like agentic: exit 2, nothing created
            raise AgenticError(
                f"`agentic worktree create` exited 2: {done.stderr.strip()}"
            )
        session = {
            "schema_version": "1",
            "name": name,
            "branch": branch,
            "base": base,
            "agent": agent,
            "task": task,
            "repository": str(root),
            "worktree": str(path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.worktrees[name] = {
            "document_type": "agentic.worktree-status",
            "repository": str(root),
            "worktree": str(path),
            "branch": branch,
            "session": session,
        }
        return {
            "document_type": "agentic.worktree",
            "repository": str(root),
            "worktree": str(path),
            "branch": branch,
            "session": session,
        }

    def worktree_status(self, root, name):
        self.handshake()
        self.requirement_calls.append(("worktree-status", name))
        if name not in self.worktrees:
            raise AgenticError(
                f"`agentic worktree status` exited 2: unknown worktree: {name}"
            )
        document = dict(self.worktrees[name])
        actual_path = Path(self.worktree_root or Path(root).parent / "worktrees") / name
        if "head" not in document:
            document["head"] = subprocess.run(
                ["git", "-C", str(actual_path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        return document

    def clean_worktree(self, root, name):
        self.handshake()
        self.requirement_calls.append(("worktree-clean", name))
        if self.clean_error:
            raise AgenticError(self.clean_error)
        return {"document_type": "agentic.worktree-clean", "worktree": name}

    def record_metric(self, event, fields, *, repository, session_id=None):
        self.handshake()
        if self.metrics_error:
            raise AgenticError(self.metrics_error)
        self.metrics.append({"event": event, "session_id": session_id, **fields})
        return {"document_type": "agentic.metric-record", "recorded": True}

    return locals()


for _name, _method in {**_bootstrap_methods(), **_requirement_methods()}.items():
    if not _name.startswith("_") and callable(_method) and _name not in {"subprocess", "AgenticError"}:
        setattr(FakeAgentic, _name, _method)


def installed_provider(digest, verified=True):
    return {"name": "agentflow", "version": "0.1.0", "content_digest": digest, "installed": True,
            "verified": verified, "compatible": True, "source": "/somewhere"}


def verification_document(status, kinds=(), commands=(), missing=()):
    ok = status == "passed"
    results = [] if status == "no-checks" else [
        {"kind": kind, "command": f"run-{kind}", "executed": True, "success": ok, "returncode": 0 if ok else 1,
         "stdout": "", "stderr": "", "duration_ms": 5.0, "reason": "r"} for kind in kinds
    ] + [
        {"kind": "custom", "command": command, "executed": True, "success": ok, "returncode": 0 if ok else 1,
         "stdout": "", "stderr": "", "duration_ms": 5.0, "reason": "r"} for command in commands
    ]
    return {"schema_version": "1", "document_type": "agentic.verification-run", "status": status,
            "success": ok, "mode": "full", "requested_kinds": list(kinds), "missing_kinds": list(missing),
            "checks_executed": len(results), "results": results}


GOOD_CONTRACTS = {
    "schema_version": "1", "document_type": "agentic.contracts",
    "contracts": {"contracts": ["1"], "repo-inspection": ["1"], "verification-run": ["1"]},
    "features": [*REQUIRED_FEATURES, "verification.change-aware"],
}

# Minimal stand-ins for the schemas a real `agentic contracts schema NAME` returns.
SCHEMAS = {
    "contracts": {"type": "object", "required": ["document_type", "contracts", "features"]},
    "repo-inspection": {"type": "object", "required": ["document_type", "discovered_commands"],
                        "properties": {"document_type": {"const": "agentic.repo-inspection"}}},
    "verification-run": {"type": "object", "required": ["document_type", "status", "success", "results"],
                         "properties": {"document_type": {"const": "agentic.verification-run"},
                                        "status": {"enum": ["passed", "failed", "no-checks"]}}},
}


def fake_cli(directory: Path, *, contracts=GOOD_CONTRACTS, inspection=None, verify=None, verify_exit=0) -> str:
    """A stand-in `agentic` executable with canned JSON; every argv is logged to `calls.jsonl`."""

    script = directory / "agentic"
    log = directory / "calls.jsonl"
    payload = json.dumps({"contracts": contracts, "schemas": SCHEMAS,
                          "inspection": inspection or {"document_type": "agentic.repo-inspection",
                                                       "discovered_commands": [{"kind": "test", "command": "t",
                                                                                "source": "Makefile"}]},
                          "verify": verify or verification_document("passed", ["test"])})
    script.write_text(f"""#!{sys.executable}
import json, sys
data = json.loads({payload!r})
args = sys.argv[1:]
with open({str(log)!r}, "a") as handle:
    handle.write(json.dumps(args) + "\\n")
if args[:2] == ["contracts", "schema"]:
    print(json.dumps(data["schemas"][args[2]])); sys.exit(0)
if args[:1] == ["contracts"]:
    print(json.dumps(data["contracts"])); sys.exit(0)
if args[:2] == ["repo", "inspect"]:
    print(json.dumps(data["inspection"])); sys.exit(0)
if args[:2] == ["verify", "run"]:
    print(json.dumps(data["verify"])); sys.exit({verify_exit})
sys.exit(2)
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def logged_calls(directory: Path) -> list[list[str]]:
    path = directory / "calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
