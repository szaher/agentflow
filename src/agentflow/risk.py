from __future__ import annotations

from pathlib import Path
from .git import IGNORE_PREFIXES, git_text

HIGH = ("auth", "security", "permission", "migration", "schema", "deploy", "infra", "terraform", "secret", "payment", "billing", "credential")
MEDIUM = ("api", "database", "config", "workflow", "ci", "docker", "kubernetes")


def changed_paths(root: Path) -> list[str]:
    """Every path the working tree changes: modified, staged, deleted, renamed, and untracked.

    Untracked files must count: a brand-new module is a change too. ``git status``
    also works before the first commit, when ``git diff HEAD`` fails.
    """
    fields = git_text(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]).split("\0")
    paths: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in code or "C" in code:
            paths.append(fields[i])  # -z puts the rename/copy source in the next field
            i += 1
    return sorted({p for p in paths if p and not p.startswith(IGNORE_PREFIXES)})


def classify(root: Path) -> tuple[str, list[str]]:
    files = [p.lower() for p in changed_paths(root)]
    joined = "\n".join(files)
    reasons: list[str] = []
    for token in HIGH:
        if token in joined:
            reasons.append(f"changed path matched high-risk token: {token}")
    if reasons:
        return "high", reasons
    for token in MEDIUM:
        if token in joined:
            reasons.append(f"changed path matched medium-risk token: {token}")
    if reasons:
        return "medium", reasons
    if files and all(x.endswith((".md", ".txt", ".rst")) for x in files):
        return "low", ["documentation-only tracked changes"]
    return "medium" if files else "low", ["default classification"]
