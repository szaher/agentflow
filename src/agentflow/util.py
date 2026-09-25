from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Iterable


def run_command(command: list[str] | str, cwd: Path, timeout: int | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    shell = isinstance(command, str)
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        command,
        cwd=str(cwd),
        shell=shell,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=merged,
    )


def which(name: str) -> str | None:
    from shutil import which as _which
    return _which(name)


def sha256_text(parts: Iterable[str]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8", errors="replace"))
        h.update(b"\0")
    return h.hexdigest()


def atomic_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def quote_cmd(parts: list[str]) -> str:
    return " ".join(shlex.quote(p) for p in parts)
