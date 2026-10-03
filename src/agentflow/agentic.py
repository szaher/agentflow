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
from pathlib import Path
from typing import Any

INSTALL_HINT = "install Agentic Dev (https://github.com/szaher/agentic-dev) so `agentic` is on PATH, or set AGENTFLOW_AGENTIC"

# What AgentFlow consumes. Checked against `agentic contracts --json`.
REQUIRED_CONTRACTS = {"contracts": "1", "repo-inspection": "1", "verification-run": "1"}
REQUIRED_FEATURES = (
    "commands.canonical-discovery",
    "repo-inspection.discovered-commands",
    "verification.explicit-commands",
    "verification.full-kind-filter",
    "verification.no-checks-status",
)
CHANGE_AWARE_FEATURE = "verification.change-aware"
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

    def _call(self, args: list[str], cwd: Path | None = None, ok: tuple[int, ...] = (0,)) -> tuple[int, dict[str, Any]]:
        if not self.executable:
            raise AgenticUnavailable(f"`agentic` was not found; {INSTALL_HINT}")
        try:
            cp = subprocess.run([self.executable, *args], cwd=str(cwd) if cwd else None, text=True,
                                capture_output=True, timeout=self.timeout)
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

    def handshake(self) -> dict[str, Any]:
        """The contracts document, after checking everything AgentFlow requires is offered."""

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
        offered = document.get("contracts") or {}
        missing = [f"{name}@{version}" for name, version in REQUIRED_CONTRACTS.items()
                   if version not in (offered.get(name) or [])]
        missing += [f"feature {feature}" for feature in REQUIRED_FEATURES if feature not in (document.get("features") or [])]
        if missing:
            raise AgenticUnavailable(f"installed `agentic` lacks {', '.join(missing)}; {INSTALL_HINT}")
        self._contracts = document
        return document

    def supports(self, feature: str) -> bool:
        return feature in (self.handshake().get("features") or [])

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
