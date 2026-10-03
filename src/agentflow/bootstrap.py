"""``agentflow init``: AgentFlow's project integration, placed through Agentic Dev.

Ownership (v0.16 decisions 4 and 5):

- AgentFlow owns its instruction *content* and the ``agentflow-sdlc`` skill
  content. Agentic Dev owns the mutation of shared files: the workflow text goes
  into one managed block (``agentflow.workflow``) in ``AGENTS.md`` and
  ``CLAUDE.md`` through ``agentic instructions block put``. Shared instruction
  files are never rewritten wholesale, ``--force`` included; a hand-edited block
  is a conflict, not something to overwrite.
- The skill reaches every harness through Agentic Dev's provider + skill
  mechanism (see :mod:`agentflow.provider`); AgentFlow no longer writes copies.
- Files AgentFlow owns outright (``.agentflow/config.json``, ``.agentflow/.gitignore``,
  the OpenCode reviewer agent) are written atomically by AgentFlow.

Everything that can fail is checked before the repository is touched: the
Agentic Dev handshake, the provider policy, a dry run of both blocks, and a dry
run of skill activation for every harness (an unmanaged ``SKILL.md`` in the way
is a conflict found here, not after other files were written).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import provider
from .agentic import Agentic
from .config import save_config
from .models import ProjectConfig

OWNER = "agentflow"
BLOCK = "workflow"

AGENTS_BLOCK = """## AgentFlow workflow

This repository uses AgentFlow, an Agentic SDLC meta-harness.

- Read `.agentflow/config.json` and follow the selected AgentFlow pattern.
- Work only on the current bounded stage/checkpoint.
- Do not claim the overall task is complete merely because implementation finished.
- Run `agentflow status` to inspect workflow state, and `agentflow verify` when verification is required.
- Independent review must be read-only; reviewers must not edit files.
- Preserve unrelated user changes. Never use destructive Git commands to erase unknown work.
- AgentFlow evidence is tied to the current repository fingerprint; code changes can stale previous evidence.

Useful AgentFlow commands: `agentflow patterns`, `agentflow status`, `agentflow verify`, `agentflow step`, `agentflow approve`.
"""

CLAUDE_BLOCK = """## AgentFlow

@AGENTS.md

Use the `agentflow-sdlc` skill for AgentFlow-managed work.
"""

BLOCKS = (("AGENTS.md", AGENTS_BLOCK), ("CLAUDE.md", CLAUDE_BLOCK))

OPENCODE_REVIEWER = """---
description: Independent read-only Agentflow reviewer
mode: primary
permissions:
  - action: edit
    resource: "*"
    effect: deny
  - action: external_directory
    resource: "*"
    effect: deny
  - action: read
    resource: "*"
    effect: allow
  - action: glob
    resource: "*"
    effect: allow
  - action: grep
    resource: "*"
    effect: allow
  - action: shell
    resource: "*"
    effect: allow
  - action: skill
    resource: "*"
    effect: allow
---
Review only. Do not modify files. Follow AGENTS.md and the agentflow-sdlc skill.
"""


class BootstrapError(RuntimeError):
    """Initialization stopped; nothing in the repository was changed unless stated."""


@dataclass
class BootstrapResult:
    provider_action: str
    provider_state: str
    written: list[Path] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    skills: dict[str, Any] | None = None


def _write_owned(path: Path, text: str) -> Path:
    """Atomically replace a file AgentFlow owns outright."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return path


def init_project(root: Path, config: ProjectConfig | None = None, force: bool = False, *,
                 agentic: Agentic | None = None, install_provider: bool = True,
                 replace_provider: bool = False) -> BootstrapResult:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    config = config or ProjectConfig()
    agentic = agentic or Agentic()
    af = root / ".agentflow"
    if af.exists() and not force:
        raise FileExistsError(".agentflow already exists; use --force to refresh AgentFlow's own files and blocks")

    # 1. Preflight, before any repository write: provider policy (may install/replace globally only when allowed).
    try:
        action, before = provider.ensure(agentic, install=install_provider, replace=replace_provider)
    except provider.ProviderError as exc:
        raise BootstrapError(f"{exc}. Nothing in the repository was changed.") from exc
    # 2. Dry-run both shared-file blocks: a hand-edited block or an unwritable file stops init here.
    for file, content in BLOCKS:
        preview = agentic.put_block(root, file=file, owner=OWNER, block=BLOCK, content=content, dry_run=True)
        if preview["exit_code"] != 0:
            raise BootstrapError(f"{file}: {preview['status']}: {preview['reason']}. "
                                 "Nothing in the repository was changed.")
    # 3. Dry-run skill activation: an unmanaged skill in any harness stops init here.
    preview = _activate(agentic, root, dry_run=True)
    if preview["status"] != "ok":
        raise BootstrapError(f"{_unmanaged(preview)}. Nothing in the repository was changed.")

    result = BootstrapResult(provider_action=action, provider_state=before.state)
    # 4. Files AgentFlow owns outright.
    for name in ("patterns", "evidence", "logs"):
        (af / name).mkdir(parents=True, exist_ok=True)
    result.written.append(save_config(root, config))
    result.written.append(_write_owned(af / ".gitignore", "state.json\nevidence/\nlogs/\n"))
    result.written.append(_write_owned(root / ".opencode" / "agents" / "agentflow-reviewer.md", OPENCODE_REVIEWER))
    # 5. Shared instruction files: one managed block each, through Agentic Dev.
    for file, content in BLOCKS:
        document = agentic.put_block(root, file=file, owner=OWNER, block=BLOCK, content=content)
        result.blocks.append(document)
        if document["exit_code"] != 0:
            raise BootstrapError(f"{file}: {document['status']}: {document['reason']}")
    # 6. The skill, placed and activated by Agentic Dev for every harness.
    result.skills = _activate(agentic, root)
    if result.skills["status"] != "ok":  # appeared since the preflight
        raise BootstrapError(_unmanaged(result.skills))
    return result


def _activate(agentic: Agentic, root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    return agentic.activate_skills(root, [provider.SKILL_NAME], target="all", shared=True, dry_run=dry_run)


def _unmanaged(document: dict[str, Any]) -> str:
    skipped = [o["path"] for o in document["outcomes"] if o["status"] == "skipped-unmanaged"]
    return (f"an unmanaged skill is in the way, left untouched: {', '.join(skipped)}; "
            "move it aside or remove it, then rerun init")
