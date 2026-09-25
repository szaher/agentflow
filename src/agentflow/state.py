from __future__ import annotations

import json
import uuid
from pathlib import Path

from .models import RunState
from .util import atomic_json, now_iso

STATE_FILE = ".agentflow/state.json"


def new_state(task: str, pattern: str, entry: str, executor: str, reviewers: list[str]) -> RunState:
    return RunState(
        run_id=uuid.uuid4().hex[:12],
        task=task,
        pattern=pattern,
        stage=entry,
        executor=executor,
        reviewers=reviewers,
        history=[{"at": now_iso(), "event": "run_created", "stage": entry}],
    )


def load_state(root: Path) -> RunState:
    path = root / STATE_FILE
    if not path.exists():
        raise FileNotFoundError("No active Agentflow run. Use: agentflow run <task>")
    return RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_state(root: Path, state: RunState) -> None:
    atomic_json(root / STATE_FILE, state.to_dict())


def record(state: RunState, event: str, **fields: object) -> None:
    state.history.append({"at": now_iso(), "event": event, **fields})
