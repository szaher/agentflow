# Agentflow architecture

Agentflow is a small control plane around coding-agent harnesses. It does not replace Claude Code, Codex, or Pi; it supplies the shared project state, evidence gates, bounded retry policy, and cross-harness contract.

## State

- `AGENTS.md`: concise map and project-wide rules.
- `docs/exec-plans/active/`: human-readable active checkpoint plans.
- `.agentflow/checkpoints/*.json`: machine-readable checkpoint state.
- `.agentflow/config.json`: gate commands and policy.
- `.agentflow/runtime/`: ephemeral logs/evidence; ignored by Git.

## Trust boundary

The worker may mutate the repository. The reviewer must not. Deterministic gates are executed by Agentflow rather than inferred from an agent's prose. A gate or review result is bound to a SHA-256 fingerprint of the current diff, so later changes invalidate earlier evidence.

## Bounded retries

A cycle stops after the configured maximum attempts. Exhaustion marks the checkpoint blocked. The correct next action is to investigate, re-scope, change implementation strategy, or ask for human input.

## Harness boundary

Agentflow invokes harnesses as subprocesses. Default one-shot entry points are `claude -p`, `codex exec`, and `pi -p`; environment variables can override them. This keeps the orchestration policy stable even when a harness changes its internal agent/subagent implementation.
