from __future__ import annotations

import json
from pathlib import Path

from .models import Project, ProjectConfig

CONFIG_DIR = ".agentflow"
CONFIG_FILE = "config.json"


def find_root(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
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
