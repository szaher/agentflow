---
name: agentflow-sdlc
description: Execute software development work under the repository's Agentflow SDLC pattern, including stages, verification, reviews, evidence, and approval gates.
---

# Agentflow SDLC

Before substantive coding, read `AGENTS.md`, `.agentflow/config.json`, and run `agentflow status`.
Treat Agentflow as the authority for workflow progression. The coding harness owns reasoning and implementation; Agentflow owns the current stage, evidence requirements, review rules, and transition decisions.

Do not bypass failed gates or fabricate evidence. Keep reviewer work read-only. After changing implementation, expect prior evidence to become stale.
