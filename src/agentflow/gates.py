from __future__ import annotations

import time
from pathlib import Path

from .models import GateResult, ProjectConfig
from .util import run_command

DEFAULTS = {
    "fast": [],
    "standard": [],
    "strict": [],
}


def detected_commands(root: Path, profile: str = "standard") -> list[tuple[str, str]]:
    cmds: list[tuple[str, str]] = []
    # Python
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        if (root / "pyproject.toml").exists():
            text = (root / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
        else:
            text = ""
        if "pytest" in text or (root / "tests").exists():
            cmds.append(("pytest", "python -m pytest -q"))
        if "ruff" in text:
            cmds.insert(0, ("ruff", "python -m ruff check ."))
        if "mypy" in text and profile != "fast":
            cmds.append(("mypy", "python -m mypy ."))
    # Node
    if (root / "package.json").exists():
        import json
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            runner = "npm"
            if (root / "pnpm-lock.yaml").exists(): runner = "pnpm"
            elif (root / "yarn.lock").exists(): runner = "yarn"
            for name in ["lint", "typecheck", "test", "build"]:
                if name in scripts and (profile != "fast" or name in {"lint", "test"}):
                    cmds.append((name, f"{runner} run {name}"))
        except Exception:
            pass
    if (root / "go.mod").exists():
        cmds.append(("go-test", "go test ./..."))
        if profile == "strict": cmds.append(("go-vet", "go vet ./..."))
    if (root / "Cargo.toml").exists():
        cmds.append(("cargo-test", "cargo test --quiet"))
        if profile != "fast": cmds.insert(0, ("cargo-check", "cargo check --quiet"))
    if (root / "Makefile").exists() and profile == "strict":
        cmds.append(("make-check", "make check"))
    return cmds


def commands_for(root: Path, config: ProjectConfig, profile: str) -> list[tuple[str, str]]:
    custom = config.gates.get(profile)
    if custom:
        return [(f"custom-{i+1}", cmd) for i, cmd in enumerate(custom)]
    return detected_commands(root, profile)


def run_gates(root: Path, config: ProjectConfig, profile: str) -> list[GateResult]:
    results: list[GateResult] = []
    for name, command in commands_for(root, config, profile):
        start = time.monotonic()
        cp = run_command(command, root)
        results.append(GateResult(name, command, cp.returncode, cp.stdout, cp.stderr, time.monotonic() - start))
        if cp.returncode != 0:
            break
    return results
