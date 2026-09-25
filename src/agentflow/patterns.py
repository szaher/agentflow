from __future__ import annotations

import importlib.resources
import json
from pathlib import Path

from .models import Pattern


def validate_pattern(pattern: Pattern) -> None:
    if not pattern.name or not pattern.stages:
        raise ValueError("Pattern requires a name and at least one stage")
    ids = [s.id for s in pattern.stages]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate stage ids in {pattern.name}")
    if pattern.entry not in ids:
        raise ValueError(f"Entry stage {pattern.entry!r} not found in {pattern.name}")
    known = set(ids) | {"done", "blocked", None}
    for s in pattern.stages:
        if s.on_success not in known:
            raise ValueError(f"Unknown on_success {s.on_success!r} from {s.id}")
        if s.on_failure not in known:
            raise ValueError(f"Unknown on_failure {s.on_failure!r} from {s.id}")


def _load(path: Path) -> Pattern:
    p = Pattern.from_dict(json.loads(path.read_text(encoding="utf-8")))
    validate_pattern(p)
    return p


def builtin_pattern_paths() -> list[Path]:
    root = importlib.resources.files("agentflow").joinpath("builtin_patterns")
    return sorted(Path(str(x)) for x in root.iterdir() if x.name.endswith(".json"))


def list_patterns(project_root: Path | None = None) -> list[Pattern]:
    patterns: dict[str, Pattern] = {}
    for path in builtin_pattern_paths():
        p = _load(path)
        patterns[p.name] = p
    if project_root:
        custom = project_root / ".agentflow" / "patterns"
        if custom.exists():
            for path in sorted(custom.glob("*.json")):
                p = _load(path)
                patterns[p.name] = p
    return sorted(patterns.values(), key=lambda x: x.name)


def load_pattern(name: str, project_root: Path | None = None) -> Pattern:
    for p in list_patterns(project_root):
        if p.name == name:
            return p
    raise KeyError(f"Unknown pattern {name!r}")
