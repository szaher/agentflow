# Package manifest

Agentflow Starter Kit contains **43 files**.

Key components:

- Harness-neutral `agentflow` CLI and installer.
- Claude Code adapter: project instructions, 4 subagents, mirrored skills, bounded Stop hook.
- Codex adapter: shared `AGENTS.md` + `.agents/skills` conventions and `codex exec` runner.
- Pi adapter: shared instructions/skills + `.pi/settings.json` and `pi -p` runner.
- 9 reusable Agent Skills.
- Auto-detected gates for Python, Node/TypeScript, Go, Rust, Maven, Gradle, Make, and generic Git repos.
- Risk-aware approval, stale-evidence protection, reviewer mutation detection, bounded retries, UI verification protocol, and CI example.
- Self-tests and upstream compatibility references.

## Files

- `README.md`
- `agentflow-local.sh`
- `bin/agentflow`
- `docs/SOURCES.md`
- `install.sh`
- `scripts/install-harnesses-macos.sh`
- `scripts/self-test.sh`
- `template/.agentflow/checkpoints/.gitkeep`
- `template/.agentflow/config.json`
- `template/.agentflow/hooks/claude-stop.py`
- `template/.agentflow/runtime/.gitkeep`
- `template/.agents/skills/checkpoint-implement/SKILL.md`
- `template/.agents/skills/checkpoint-plan/SKILL.md`
- `template/.agents/skills/checkpoint-review/SKILL.md`
- `template/.agents/skills/checkpoint-verify/SKILL.md`
- `template/.agents/skills/failure-escalation/SKILL.md`
- `template/.agents/skills/handoff/SKILL.md`
- `template/.agents/skills/risk-assess/SKILL.md`
- `template/.agents/skills/security-review/SKILL.md`
- `template/.agents/skills/ui-evidence/SKILL.md`
- `template/.claude/agents/implementer.md`
- `template/.claude/agents/reviewer.md`
- `template/.claude/agents/security-reviewer.md`
- `template/.claude/agents/verifier.md`
- `template/.claude/settings.json`
- `template/.claude/skills/checkpoint-implement/SKILL.md`
- `template/.claude/skills/checkpoint-plan/SKILL.md`
- `template/.claude/skills/checkpoint-review/SKILL.md`
- `template/.claude/skills/checkpoint-verify/SKILL.md`
- `template/.claude/skills/failure-escalation/SKILL.md`
- `template/.claude/skills/handoff/SKILL.md`
- `template/.claude/skills/risk-assess/SKILL.md`
- `template/.claude/skills/security-review/SKILL.md`
- `template/.claude/skills/ui-evidence/SKILL.md`
- `template/.pi/settings.json`
- `template/AGENTS.md`
- `template/CLAUDE.md`
- `template/docs/agentflow/architecture.md`
- `template/docs/agentflow/examples/github-actions-agentflow-gates.yml`
- `template/docs/agentflow/ui-verification.md`
- `template/docs/exec-plans/active/.gitkeep`
- `template/docs/exec-plans/completed/.gitkeep`
- `tests/test_agentflow.py`
