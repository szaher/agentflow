from __future__ import annotations

from pathlib import Path
from .git import git_text

HIGH = ("auth", "security", "permission", "migration", "schema", "deploy", "infra", "terraform", "secret", "payment", "billing", "credential")
MEDIUM = ("api", "database", "config", "workflow", "ci", "docker", "kubernetes")


def classify(root: Path) -> tuple[str, list[str]]:
    files = git_text(root, ["diff", "--name-only", "HEAD", "--", "."]).lower().splitlines()
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
