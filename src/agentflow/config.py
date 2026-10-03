from __future__ import annotations

import json
import os
from pathlib import Path

from .models import Project, ProjectConfig

CONFIG_DIR = ".agentflow"
CONFIG_FILE = "config.json"


ROOT_ENV = "AGENTFLOW_ROOT"
WORKSPACE_ENV = "AGENTFLOW_WORKSPACE"
RUN_ENV = "AGENTFLOW_RUN_ID"


def _within(path: Path, base: str | None) -> bool:
    return bool(base) and Path(base).is_absolute() and path.is_relative_to(Path(base).resolve())


def control_root(here: Path) -> Path | None:
    """The AgentFlow control root exported to harnesses AgentFlow launches (AGENTFLOW_ROOT).

    An isolated run works in a worktree while its state and evidence stay in the
    primary checkout; a harness started in the worktree (and any `agentflow`
    command it runs) reaches that state through this variable. It is honoured
    only from inside that root or the run's workspace (AGENTFLOW_WORKSPACE), so a
    variable leaked into an unrelated directory changes nothing, and it must
    name an initialized AgentFlow project.
    """

    root = os.environ.get(ROOT_ENV)
    if not root:
        return None
    if not (_within(here, root) or _within(here, os.environ.get(WORKSPACE_ENV))):
        return None
    resolved = Path(root).resolve()
    if not (resolved / CONFIG_DIR / CONFIG_FILE).is_file():
        raise FileNotFoundError(f"{ROOT_ENV}={root} is not an initialized AgentFlow project")
    return resolved


def find_root(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    bridged = control_root(here)
    if bridged:
        return bridged
    for p in [here, *here.parents]:
        if (p / CONFIG_DIR / CONFIG_FILE).exists():
            return p
        if (p / ".git").exists():
            return p
    return here


def load_project(start: Path | None = None) -> Project:
    root = find_root(start)
    path = root / CONFIG_DIR / CONFIG_FILE
    if not path.exists():
        raise FileNotFoundError(f"Agentflow is not initialized in {root}. Run: agentflow init")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Project(root=root, config=ProjectConfig.from_dict(data))


def save_config(root: Path, config: ProjectConfig) -> Path:
    path = root / CONFIG_DIR / CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
