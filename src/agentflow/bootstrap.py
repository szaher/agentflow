from __future__ import annotations

import json
from pathlib import Path

from .config import save_config
from .models import ProjectConfig

AGENTS = """# Agentflow project instructions

This repository uses Agentflow, an Agentic SDLC meta-harness.

## Mandatory workflow
- Read `.agentflow/config.json` and follow the selected Agentflow pattern.
- Work only on the current bounded stage/checkpoint.
- Do not claim the overall task is complete merely because implementation finished.
- Run `agentflow status` to inspect workflow state.
- Run `agentflow verify` when verification is required.
- Independent review must be read-only; reviewers must not edit files.
- Preserve unrelated user changes. Never use destructive Git commands to erase unknown work.
- Agentflow evidence is tied to the current repository fingerprint; code changes can stale previous evidence.

## Useful commands
- `agentflow patterns`
- `agentflow status`
- `agentflow verify`
- `agentflow step`
- `agentflow approve`
"""

SKILL = """---
name: agentflow-sdlc
description: Execute software development work under the repository's Agentflow SDLC pattern, including stages, verification, reviews, evidence, and approval gates.
---

# Agentflow SDLC

Before substantive coding, read `AGENTS.md`, `.agentflow/config.json`, and run `agentflow status`.
Treat Agentflow as the authority for workflow progression. The coding harness owns reasoning and implementation; Agentflow owns the current stage, evidence requirements, review rules, and transition decisions.

Do not bypass failed gates or fabricate evidence. Keep reviewer work read-only. After changing implementation, expect prior evidence to become stale.
"""

CLAUDE = """# Claude Code + Agentflow\n\n@AGENTS.md\n\nUse the `agentflow-sdlc` skill for Agentflow-managed work.\n"""


def init_project(root: Path, config: ProjectConfig | None = None, force: bool = False) -> list[Path]:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    config = config or ProjectConfig()
    af = root / ".agentflow"
    if af.exists() and not force:
        raise FileExistsError(".agentflow already exists; use --force to refresh generated integration files")
    (af / "patterns").mkdir(parents=True, exist_ok=True)
    (af / "evidence").mkdir(parents=True, exist_ok=True)
    (af / "logs").mkdir(parents=True, exist_ok=True)
    created = [save_config(root, config)]
    (af / ".gitignore").write_text("state.json\nevidence/\nlogs/\n", encoding="utf-8")
    created.append(af / ".gitignore")

    agents = root / "AGENTS.md"
    if not agents.exists() or force:
        agents.write_text(AGENTS, encoding="utf-8")
        created.append(agents)
    claude = root / "CLAUDE.md"
    if not claude.exists() or force:
        claude.write_text(CLAUDE, encoding="utf-8")
        created.append(claude)

    # Generate compatibility skills rather than assuming every harness searches the same path.
    for base in [root / ".agents" / "skills", root / ".claude" / "skills", root / ".codex" / "skills", root / ".pi" / "skills", root / ".opencode" / "skills"]:
        skill_dir = base / "agentflow-sdlc"
        skill_dir.mkdir(parents=True, exist_ok=True)
        p = skill_dir / "SKILL.md"
        p.write_text(SKILL, encoding="utf-8")
        created.append(p)

    # OpenCode gets an explicit read-only reviewer agent. Agentflow still checks worktree immutability.
    oc_agent = root / ".opencode" / "agents" / "agentflow-reviewer.md"
    oc_agent.parent.mkdir(parents=True, exist_ok=True)
    oc_agent.write_text("""---
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
""", encoding="utf-8")
    created.append(oc_agent)

    return created
