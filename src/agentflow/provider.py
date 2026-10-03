"""The ``agentflow`` provider: AgentFlow-owned skill content, installed by Agentic Dev.

AgentFlow ships its ``agentflow-sdlc`` skill as an Agentic Dev provider bundled
in this package. Agentic Dev owns installation and activation; AgentFlow only
decides *whether* to ask for an install, and never silently replaces global
state:

- **missing**: install the bundled provider (pinned to its digest);
- **current** (same ``content_digest``, verified, compatible): nothing to do;
- **different** (another AgentFlow build's provider, older or newer) or
  **unverified** (tampered or incompatible): fail closed. Replacing it requires
  explicit intent (``replace=True``: ``agentflow provider install --replace`` or
  ``agentflow init --update-provider``).

Digests always come from Agentic Dev (``agentic providers inspect``); AgentFlow
never computes them itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from .agentic import Agentic

PROVIDER_NAME = "agentflow"
SKILL_NAME = "agentflow-sdlc"
MISSING, CURRENT, DIFFERENT, UNVERIFIED = "missing", "current", "different", "unverified"


class ProviderError(RuntimeError):
    """The installed provider is not the one this AgentFlow build ships, or may not be installed."""


@dataclass
class ProviderStatus:
    state: str
    bundled: dict[str, Any]
    installed: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        installed = self.installed or {}
        return {
            "state": self.state,
            "name": PROVIDER_NAME,
            "bundled": {"version": self.bundled["version"], "content_digest": self.bundled["content_digest"],
                        "source": self.bundled["source"]},
            "installed": {key: installed.get(key) for key in
                          ("version", "content_digest", "verified", "compatible", "source")} if self.installed else None,
        }


def bundled_source() -> Path:
    """The provider directory this AgentFlow build ships (overridable for tests)."""

    override = os.environ.get("AGENTFLOW_PROVIDER_SOURCE")
    return Path(override) if override else Path(str(resources.files("agentflow").joinpath("provider")))


def status(agentic: Agentic, source: Path | None = None) -> ProviderStatus:
    bundled = agentic.inspect_provider(source or bundled_source())
    if bundled["name"] != PROVIDER_NAME:
        raise ProviderError(f"bundled provider is named {bundled['name']!r}, expected {PROVIDER_NAME!r}")
    installed = next((p for p in agentic.providers() if p["name"] == PROVIDER_NAME), None)
    if installed is None:
        state = MISSING
    elif not (installed.get("installed") and installed.get("verified") and installed.get("compatible")):
        state = UNVERIFIED
    elif installed["content_digest"] == bundled["content_digest"]:
        state = CURRENT
    else:
        state = DIFFERENT
    return ProviderStatus(state, bundled, installed)


def explain(current: ProviderStatus) -> str:
    installed = current.installed or {}
    if current.state == DIFFERENT:
        return (f"the installed `{PROVIDER_NAME}` provider (version {installed.get('version')}, "
                f"sha256 {str(installed.get('content_digest'))[:12]}) differs from this AgentFlow's "
                f"(version {current.bundled['version']}, sha256 {current.bundled['content_digest'][:12]}); "
                "it may belong to another AgentFlow installation, so it is not replaced automatically. "
                "Run `agentflow provider install --replace` or rerun init with `--update-provider`")
    if current.state == UNVERIFIED:
        return (f"the installed `{PROVIDER_NAME}` provider failed verification (tampered, missing, or incompatible); "
                "run `agentflow provider install --replace` or rerun init with `--update-provider`")
    if current.state == MISSING:
        return f"the `{PROVIDER_NAME}` provider is not installed; run `agentflow provider install`"
    return f"the `{PROVIDER_NAME}` provider is current"


def ensure(agentic: Agentic, *, install: bool = True, replace: bool = False,
           source: Path | None = None) -> tuple[str, ProviderStatus]:
    """Make the installed provider match this build. Returns (action, status before any change).

    ``action`` is ``unchanged``, ``installed``, or ``replaced``. ``install=False``
    never mutates global state: it only verifies.
    """

    current = status(agentic, source)
    if current.state == CURRENT:
        return "unchanged", current
    if not install:
        raise ProviderError(explain(current) + " (provider installation is disabled)")
    if current.state == MISSING:
        agentic.add_provider(source or bundled_source(), sha256=current.bundled["content_digest"])
        return "installed", current
    if not replace:
        raise ProviderError(explain(current))
    agentic.add_provider(source or bundled_source(), sha256=current.bundled["content_digest"])
    return "replaced", current
