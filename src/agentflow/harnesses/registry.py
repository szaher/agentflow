from __future__ import annotations

from .base import Harness
from .claude import ClaudeHarness
from .codex import CodexHarness
from .pi import PiHarness
from .opencode import OpenCodeHarness
from .custom import CommandHarness

_REGISTRY: dict[str, type[Harness]] = {
    "claude": ClaudeHarness,
    "codex": CodexHarness,
    "pi": PiHarness,
    "opencode": OpenCodeHarness,
}


def names() -> list[str]:
    return sorted(_REGISTRY)


def get(name: str, config: dict | None = None) -> Harness:
    if name in _REGISTRY:
        return _REGISTRY[name]()
    if config and config.get("command"):
        return CommandHarness(name, config)
    raise KeyError(f"Unknown harness {name!r}; configure a custom command under .agentflow/config.json -> harness.{name}.command")


def detected(tools: dict[str, dict]) -> dict[str, bool]:
    """Harness availability from Agentic Dev's doctor ``tools`` facts (AgentFlow does not probe PATH)."""
    return {name: bool((tools.get(cls.executable) or {}).get("available")) for name, cls in _REGISTRY.items()}
