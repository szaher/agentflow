# Upstream compatibility notes

This kit intentionally relies on stable, documented entry points and keeps harness-specific behavior thin.

As of 2026-09-25:

- Claude Code: project `AGENTS.md` support, `.claude/skills/`, `.claude/agents/`, and lifecycle hooks including `Stop` are documented by Anthropic. The Stop hook receives `stop_hook_active` and Claude Code itself caps repeated continuation, which is why Agentflow's hook blocks only the first stop attempt.
- OpenAI Codex: `AGENTS.md` is layered project guidance; Agent Skills use `SKILL.md`; `codex exec` is the supported non-interactive CLI entry point. The shared `.agents/skills/` location is used here as the cross-harness project skill store.
- Pi: Pi is intentionally minimal and extensible; it supports `AGENTS.md`/context discovery, Agent Skills including `.agents/skills/`, and one-shot `pi -p`, JSON, RPC, and SDK modes. Agentflow does not require a third-party Pi subagent package because isolation can be achieved by spawning separate Pi processes.

Run `agentflow doctor .` after harness upgrades. If a vendor changes a one-shot command, override it with `AGENTFLOW_CLAUDE_CMD`, `AGENTFLOW_CODEX_CMD`, or `AGENTFLOW_PI_CMD` until the kit is updated.

## References

- Claude Code hooks: https://code.claude.com/docs/en/hooks
- Claude Code subagents: https://code.claude.com/docs/en/sub-agents
- Claude Code skills: https://code.claude.com/docs/en/skills
- Claude Code project memory / AGENTS.md: https://code.claude.com/docs/en/memory
- Codex repository: https://github.com/openai/codex
- OpenAI Agent Skills: https://developers.openai.com/api/docs/guides/tools-skills
- OpenAI harness engineering: https://openai.com/index/harness-engineering/
- Pi repository: https://github.com/earendil-works/pi
- Pi skill docs: https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md
