from __future__ import annotations

from pathlib import Path

from .util import run_command, sha256_text

IGNORE_PREFIXES = (".agentflow/state.json", ".agentflow/evidence/", ".agentflow/logs/")


def is_git_repo(root: Path) -> bool:
    return run_command(["git", "rev-parse", "--is-inside-work-tree"], root).returncode == 0


def git_text(root: Path, args: list[str]) -> str:
    cp = run_command(["git", *args], root)
    return cp.stdout if cp.returncode == 0 else ""


def tracked_diff(root: Path) -> str:
    return git_text(root, ["diff", "--binary", "HEAD", "--", "."])


def untracked_files(root: Path) -> list[Path]:
    out = git_text(root, ["ls-files", "--others", "--exclude-standard"])
    result = []
    for line in out.splitlines():
        if line and not line.startswith(IGNORE_PREFIXES):
            result.append(root / line)
    return result


def implementation_fingerprint(root: Path) -> str:
    parts = [tracked_diff(root)]
    for path in sorted(untracked_files(root)):
        rel = path.relative_to(root).as_posix()
        try:
            content = path.read_bytes()
            if len(content) <= 2_000_000:
                parts.append(rel)
                parts.append(content.decode("utf-8", errors="replace"))
            else:
                parts.append(rel + f":size={len(content)}")
        except OSError:
            parts.append(rel + ":unreadable")
    return sha256_text(parts)


def status_porcelain(root: Path) -> str:
    return git_text(root, ["status", "--porcelain=v1", "--untracked-files=all"])
