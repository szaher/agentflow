@AGENTS.md

## Claude Code adapter

Use project subagents under `.claude/agents/` when independent context improves the result. Prefer direct work for small sequential edits; use subagents for isolated implementation, verification, security review, or independent review.

The project Stop hook is intentionally narrow: while an Agentflow checkpoint is active, it asks for current deterministic gate evidence before the main agent stops. It blocks at most one continuation because the hook honors Claude Code's `stop_hook_active` loop guard.
