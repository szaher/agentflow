from __future__ import annotations

from pathlib import Path

from .models import Pattern, Stage, RunState

CORE = """You are executing one stage of an Agentflow Agentic SDLC pattern.
Agentflow owns workflow state and acceptance. You own reasoning and execution for this delegated stage.
Do not declare the overall feature complete. Complete only the delegated stage.
Preserve unrelated user changes. Do not use destructive git reset/checkout to erase work.
Read AGENTS.md and repository-local instructions before making changes.
"""


def stage_prompt(pattern: Pattern, stage: Stage, state: RunState, control_root: Path | None = None) -> str:
    """``control_root`` is set when the agent works in an isolated worktree: evidence lives in the
    primary checkout, so its paths are given absolute, and the agent is told where state lives."""

    def where(path: str | None) -> str | None:
        return str(control_root / path) if control_root and path else path

    prior = "\n".join(f"- {e.get('kind')}: {where(e.get('path'))}" for e in state.evidence[-6:]) or "- none yet"
    isolation = (f"\nIsolation: you are working in this run's own worktree. AgentFlow state and evidence live in "
                 f"{control_root}; `agentflow status` reaches them through AGENTFLOW_ROOT.\n") if control_root else ""
    return f"""{CORE}{isolation}
Pattern: {pattern.name} — {pattern.description}
Run: {state.run_id}
Task: {state.task}
Current stage: {stage.id} — {stage.title}
Role: {stage.role}
Attempt: {state.attempt}/{stage.max_attempts}

Prior Agentflow evidence/artifacts (inspect relevant files before acting):
{prior}

Stage instructions:
{stage.instruction}

When finished, summarize concrete changes, commands run, failures remaining, and evidence. Do not advance Agentflow state yourself.
"""


def review_prompt(pattern: Pattern, stage: Stage, state: RunState) -> str:
    return f"""{CORE}
You are an INDEPENDENT READ-ONLY reviewer. Do not modify any file.
Pattern: {pattern.name}
Task: {state.task}
Stage under review: {stage.id} — {stage.title}

Review the current repository changes against the task and repository instructions.
Look for correctness bugs, missing requirements, regressions, unsafe assumptions, security issues, test gaps, and maintainability risks.
Prioritize findings by severity. If there are no blocking findings, end with exactly: AGENTFLOW_REVIEW_PASS
If there are blocking findings, end with exactly: AGENTFLOW_REVIEW_FAIL
"""
