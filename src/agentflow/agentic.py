"""Agentic Dev client: AgentFlow's only route to repository facts and verification.

Agentic Dev (https://github.com/szaher/agentic-dev) owns command discovery and
verification mechanics; AgentFlow owns which gates are mandatory and what their
results mean. The boundary is process + JSON only: AgentFlow runs the ``agentic``
CLI and reads its documented contracts. It never imports Agentic Dev and never
infers compatibility from ``agentic --version``. Instead it checks the
``agentic contracts`` handshake for the contract versions and features it needs.

Every document AgentFlow consumes is validated against the schema the
installed ``agentic`` ships (``agentic contracts schema NAME``); a document that
does not match fails closed.

There is deliberately no fallback: if ``agentic`` is missing or incompatible,
gates cannot run and AgentFlow says so.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

INSTALL_HINT = "install Agentic Dev (https://github.com/szaher/agentic-dev) so `agentic` is on PATH, or set AGENTFLOW_AGENTIC"

# What AgentFlow consumes, per operation. Checked against `agentic contracts --json`.
REQUIRED_CONTRACTS = {"contracts": "1", "repo-inspection": "1", "verification-run": "1"}
REQUIRED_FEATURES = (
    "commands.canonical-discovery",
    "repo-inspection.discovered-commands",
    "verification.explicit-commands",
    "verification.full-kind-filter",
    "verification.no-checks-status",
)
CHANGE_AWARE_FEATURE = "verification.change-aware"
BOOTSTRAP_CONTRACTS = {"contracts": "1", "provider-source": "1", "providers": "1", "provider-install": "1",
                       "skills-activation": "1", "instruction-block": "1"}
BOOTSTRAP_FEATURES = ("instructions.managed-block", "providers.inspect", "providers.install-pinned",
                      "skills.activation-dry-run", "skills.activation-report")
DOCTOR_CONTRACTS = {"contracts": "1", "doctor": "1"}
# Pattern requirements (v0.16 slice 4): each operation checks only what it uses.
READINESS_CONTRACTS = {"contracts": "1", "readiness-verification": "1"}
READINESS_FEATURES = ("readiness.scope-ci",)  # introduced `--scope local|ci`
CAPABILITY_CONTRACTS = {"contracts": "1", "capability-status": "1"}
WORKTREE_CONTRACTS = {"contracts": "1", "worktree": "1", "worktree-status": "1", "worktree-clean": "1"}
WORKTREE_FEATURES = ("worktree.lifecycle",)
METRICS_CONTRACTS = {"contracts": "1", "metric-record": "1"}
METRICS_FEATURES = ("metrics.record-report",)
SESSION_PLAN_CONTRACTS = {"contracts": "1", "session-request": "1", "session-plan": "1"}
SESSION_PLAN_FEATURES = ("session.permission-dimensions", "session.plan-read-only")
SESSION_PREPARE_CONTRACTS = {"contracts": "1", "session-plan": "1", "session-record": "1"}
SESSION_PREPARE_FEATURES = ("session.prepare-revalidated",)
VERIFY_STATUSES = ("passed", "failed", "no-checks")


class AgenticError(RuntimeError):
    """Agentic Dev could not answer (missing, incompatible, or an unexpected response)."""


class AgenticUnavailable(AgenticError):
    """``agentic`` is not installed or does not offer the contracts AgentFlow needs."""


class Agentic:
    def __init__(self, executable: str | None = None, timeout: int | None = None):
        self.executable = executable or os.environ.get("AGENTFLOW_AGENTIC") or shutil.which("agentic")
        self.timeout = timeout
        self._contracts: dict[str, Any] | None = None
        self._schemas: dict[str, dict[str, Any]] = {}

    def _call(self, args: list[str], cwd: Path | None = None, ok: tuple[int, ...] = (0,),
              stdin: str | None = None) -> tuple[int, dict[str, Any]]:
        if not self.executable:
            raise AgenticUnavailable(f"`agentic` was not found; {INSTALL_HINT}")
        try:
            cp = subprocess.run([self.executable, *args], cwd=str(cwd) if cwd else None, text=True,
                                input=stdin, capture_output=True, timeout=self.timeout)
        except OSError as exc:
            raise AgenticUnavailable(f"cannot run {self.executable}: {exc}; {INSTALL_HINT}") from exc
        if cp.returncode not in ok:
            detail = (cp.stderr or cp.stdout).strip().splitlines()[-1:] or ["no output"]
            raise AgenticError(f"`agentic {' '.join(args[:3])}` exited {cp.returncode}: {detail[0]}")
        try:
            document = json.loads(cp.stdout)
        except json.JSONDecodeError as exc:
            raise AgenticError(f"`agentic {' '.join(args[:3])}` did not return JSON") from exc
        if not isinstance(document, dict):
            raise AgenticError(f"`agentic {' '.join(args[:3])}` returned an unexpected document")
        return cp.returncode, document

    def _validated(self, contract: str, document: dict[str, Any]) -> dict[str, Any]:
        """Fail closed unless ``document`` matches the installed agentic's own schema for ``contract``."""

        try:
            import jsonschema
        except ImportError as exc:  # runtime dependency; see pyproject.toml
            raise AgenticUnavailable("jsonschema is required to validate Agentic Dev documents; reinstall agentflow") from exc
        if contract not in self._schemas:
            _, self._schemas[contract] = self._call(["contracts", "schema", contract])
        try:
            jsonschema.validate(document, self._schemas[contract])
        except jsonschema.ValidationError as exc:
            where = "/".join(str(part) for part in exc.absolute_path) or "document"
            raise AgenticError(f"`agentic` returned an invalid {contract} document ({where}: {exc.message})") from exc
        return document

    def _contracts_document(self) -> dict[str, Any]:
        if self._contracts is not None:
            return self._contracts
        try:
            _, document = self._call(["contracts", "--json"])
        except AgenticUnavailable:
            raise
        except AgenticError as exc:
            raise AgenticUnavailable(f"`agentic` has no compatibility handshake ({exc}); {INSTALL_HINT}") from exc
        if document.get("document_type") != "agentic.contracts" or document.get("schema_version") != "1":
            raise AgenticUnavailable(f"unsupported `agentic contracts` document; {INSTALL_HINT}")
        try:
            self._validated("contracts", document)
        except AgenticUnavailable:
            raise  # already explains itself (for example jsonschema missing)
        except AgenticError as exc:
            raise AgenticUnavailable(f"{exc}; {INSTALL_HINT}") from exc
        self._contracts = document
        return document

    def handshake(self, contracts: dict[str, str] = REQUIRED_CONTRACTS,
                  features: tuple[str, ...] = REQUIRED_FEATURES) -> dict[str, Any]:
        """The contracts document, after checking it offers ``contracts`` and ``features``."""

        document = self._contracts_document()
        offered = document.get("contracts") or {}
        missing = [f"{name}@{version}" for name, version in contracts.items()
                   if version not in (offered.get(name) or [])]
        missing += [f"feature {feature}" for feature in features if feature not in (document.get("features") or [])]
        if missing:
            raise AgenticUnavailable(f"installed `agentic` lacks {', '.join(missing)}; {INSTALL_HINT}")
        return document

    def supports(self, feature: str) -> bool:
        return feature in (self._contracts_document().get("features") or [])

    def discovered_kinds(self, root: Path) -> set[str]:
        """Command kinds Agentic Dev discovers for the repository (repo-inspection v1)."""

        self.handshake()
        _, document = self._call(["repo", "inspect", str(root), "--json"], cwd=root)
        self._validated("repo-inspection", document)
        return {item["kind"] for item in document.get("discovered_commands") or []}

    def verify(self, root: Path, *, kinds: list[str], commands: list[str], include_changed: bool = False,
               base: str | None = None) -> dict[str, Any]:
        """Run full-project verification (verification-run v1). Exit 1 is a result, not an error."""

        self.handshake()
        if include_changed and not self.supports(CHANGE_AWARE_FEATURE):
            raise AgenticUnavailable(f"installed `agentic` lacks feature {CHANGE_AWARE_FEATURE}; {INSTALL_HINT}")
        args = ["verify", "run", str(root), "--json"]
        for kind in kinds:
            args += ["--kind", kind]
        for command in commands:
            args += ["--command", command]
        if include_changed:
            args.append("--include-changed")
            if base:
                args += ["--base", base]
        code, document = self._call(args, cwd=root, ok=(0, 1))
        self._validated("verification-run", document)
        if document.get("status") not in VERIFY_STATUSES:
            raise AgenticError(f"unexpected verification status {document.get('status')!r}")
        expected_exit = 0 if document["status"] == "passed" else 1
        if code != expected_exit:
            raise AgenticError(f"`agentic verify run` status {document['status']} disagrees with exit {code}")
        return document

    # -- bootstrap: provider installation, skill activation, instruction blocks --------------

    def _bootstrap(self) -> None:
        self.handshake(BOOTSTRAP_CONTRACTS, BOOTSTRAP_FEATURES)

    def inspect_provider(self, source: Path) -> dict[str, Any]:
        """Describe a provider source as installation would record it (provider-source v1)."""

        self._bootstrap()
        _, document = self._call(["providers", "inspect", str(source), "--json"])
        return self._validated("provider-source", document)

    def providers(self) -> list[dict[str, Any]]:
        self._bootstrap()
        _, document = self._call(["providers", "list", "--json"])
        return self._validated("providers", document)["providers"]

    def add_provider(self, source: Path, *, sha256: str) -> dict[str, Any]:
        """Install a provider pinned to ``sha256``. Replaces a provider of the same name: callers decide."""

        self._bootstrap()
        _, document = self._call(["providers", "add", str(source), "--sha256", sha256, "--json"])
        return self._validated("provider-install", document)

    def activate_skills(self, root: Path, names: list[str], *, target: str = "all",
                        shared: bool = True, dry_run: bool = False) -> dict[str, Any]:
        """Place skills in the repository (skills-activation v1). Exit 1 (conflict) is a result.

        ``dry_run`` writes nothing and reports what a real run would do, conflicts included.
        """

        self._bootstrap()
        args = ["skills", "add", *names, "--path", str(root), "--target", target, "--json"]
        if shared:
            args.append("--shared")
        if dry_run:
            args.append("--dry-run")
        code, document = self._call(args, cwd=root, ok=(0, 1))
        self._validated("skills-activation", document)
        if document["dry_run"] is not dry_run:
            raise AgenticError(f"`agentic skills add` answered dry_run={document['dry_run']}, asked {dry_run}")
        if code != document["exit_code"]:
            raise AgenticError(f"`agentic skills add` status {document['status']} disagrees with exit {code}")
        return document

    def put_block(self, root: Path, *, file: str, owner: str, block: str, content: str,
                  dry_run: bool = False) -> dict[str, Any]:
        """Place or update a managed block (instruction-block v1). Conflict/refusal (exit 1) is a result."""

        self._bootstrap()
        args = ["instructions", "block", "put", "--path", str(root), "--file", file, "--owner", owner,
                "--id", block, "--content-file", "-", "--json"]
        if dry_run:
            args.append("--dry-run")
        code, document = self._call(args, cwd=root, ok=(0, 1, 3), stdin=content)
        self._validated("instruction-block", document)
        if code != document["exit_code"]:
            raise AgenticError(f"`agentic instructions block put` status {document['status']} disagrees with exit {code}")
        return document

    # -- environment facts --------------------------------------------------------------------

    def doctor(self) -> dict[str, Any]:
        """Workstation tool and integration facts (doctor v1)."""

        self.handshake(DOCTOR_CONTRACTS, ())
        _, document = self._call(["doctor", "--json"])
        return self._validated("doctor", document)

    # -- session planning and preparation --------------------------------------------------------

    def plan_session(self, root: Path, request: dict[str, Any]) -> dict[str, Any]:
        """Resolve one Agentic Dev session plan without mutating repository or AgentFlow state."""

        self.handshake(SESSION_PLAN_CONTRACTS, SESSION_PLAN_FEATURES)
        self._validated("session-request", request)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as handle:
            json.dump(request, handle, sort_keys=True)
            handle.flush()
            code, document = self._call(
                ["session", "plan", "--request", handle.name, "--path", str(root), "--json"],
                cwd=root,
                ok=(0, 1),
            )
        self._validated("session-plan", document)
        expected = 0 if document.get("status") == "ready" else 1
        if code != expected:
            raise AgenticError(
                f"`agentic session plan` status {document.get('status')!r} disagrees with exit {code}"
            )
        return document

    def prepare_session(self, workspace: Path, plan: dict[str, Any]) -> dict[str, Any]:
        """Prepare an approved plan in an existing worktree and return session-record@1.

        Only successful preparation returns JSON today; all fail-closed exits are surfaced as
        AgenticError and therefore stop AgentFlow before any stage.
        """

        self.handshake(SESSION_PREPARE_CONTRACTS, SESSION_PREPARE_FEATURES)
        self._validated("session-plan", plan)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as handle:
            json.dump(plan, handle, sort_keys=True)
            handle.flush()
            _, document = self._call(
                ["session", "prepare", "--plan", handle.name, "--path", str(workspace), "--json"],
                cwd=workspace,
            )
        return self._validated("session-record", document)

    # -- pattern requirements: readiness, capabilities, worktrees, metrics ---------------------

    def readiness(self, workspace: Path, target: str) -> dict[str, Any]:
        """Verify ``target`` with local scope in ``workspace`` (readiness-verification v1). Never remediates.

        Exit 1 (target not met) is a result; exit 2 (unknown level, spec error) raises.
        """

        self.handshake(READINESS_CONTRACTS, READINESS_FEATURES)
        code, document = self._call(["ready", "verify", str(workspace), "--target", target, "--scope", "local",
                                     "--json"], cwd=workspace, ok=(0, 1))
        self._validated("readiness-verification", document)
        if code != document["exit_code"] or document["passed"] is not (code == 0):
            raise AgenticError(f"`agentic ready verify` passed={document['passed']} disagrees with exit {code}")
        if document["scope"] != "local":
            raise AgenticError(f"`agentic ready verify` answered scope {document['scope']!r}, asked local")
        return document

    def capabilities(self) -> dict[str, Any]:
        """Optional capability state by name (capability-status v1)."""

        self.handshake(CAPABILITY_CONTRACTS, ())
        _, document = self._call(["capabilities", "status", "--json"])
        return self._validated("capability-status", document)

    def create_worktree(self, root: Path, *, name: str, branch: str, base: str, agent: str | None = None,
                        task: str | None = None) -> dict[str, Any]:
        """Create one isolated worktree (worktree v1). Exit 2 means nothing was created."""

        self.handshake(WORKTREE_CONTRACTS, WORKTREE_FEATURES)
        args = ["worktree", "create", name, "--path", str(root), "--branch", branch, "--base", base, "--json"]
        if agent:
            args += ["--agent", agent]
        if task:
            args += ["--task", task]
        _, document = self._call(args, cwd=root)
        return self._validated("worktree", document)

    def worktree_status(self, root: Path, name: str) -> dict[str, Any]:
        """One worktree's state (worktree-status v1). An unknown name exits 2 and raises AgenticError."""

        self.handshake(WORKTREE_CONTRACTS, WORKTREE_FEATURES)
        _, document = self._call(["worktree", "status", name, "--path", str(root), "--json"], cwd=root)
        self._validated("worktree-status", document)
        if not (isinstance(document.get("worktree"), str) and isinstance(document.get("branch"), str)):
            raise AgenticError(f"`agentic worktree status {name}` did not report a worktree path and branch")
        return document

    def clean_worktree(self, root: Path, name: str) -> dict[str, Any]:
        """Remove a worktree the normal way (worktree-clean v1): never ``--force``, never deletes the branch.

        A worktree with uncommitted changes is refused (exit 2, raised as AgenticError) and kept.
        """

        self.handshake(WORKTREE_CONTRACTS, WORKTREE_FEATURES)
        _, document = self._call(["worktree", "clean", name, "--path", str(root), "--json"], cwd=root)
        return self._validated("worktree-clean", document)

    def record_metric(self, event: str, fields: dict[str, Any], *, repository: Path,
                      session_id: str | None = None) -> dict[str, Any]:
        """Submit a local metric event (metric-record v1). Agentic Dev drops it unless metrics are enabled."""

        self.handshake(METRICS_CONTRACTS, METRICS_FEATURES)
        args = ["metrics", "record", event, "--path", str(repository), "--json"]
        for key, value in fields.items():
            args += ["--field", f"{key}={value}"]
        if session_id:
            args += ["--session-id", session_id]
        _, document = self._call(args, cwd=repository)
        return self._validated("metric-record", document)

