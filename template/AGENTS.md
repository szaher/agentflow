# Agent instructions

This repository uses **Agentflow** for bounded, evidence-driven agentic development.

## Start here

1. Read the active checkpoint under `docs/exec-plans/active/` and `.agentflow/checkpoints/` before changing code.
2. Work on one checkpoint at a time. Do not silently broaden scope.
3. Treat repository files and executable checks as the system of record; do not rely on chat memory for project facts.
4. Before claiming completion, run the configured deterministic gates with `agentflow gates . --profile standard`.
5. Do not weaken, delete, skip, or rewrite tests merely to make a change pass.
6. Do not claim a command, test, build, review, or external action succeeded unless you observed its result.

## Control loop

`plan -> implement -> deterministic evidence -> independent review -> risk policy -> approval -> accept`

A failed gate returns the checkpoint to implementation. A failed independent review also returns it to implementation. The loop is bounded; repeated failure is a reason to replan or escalate, not to retry forever.

## Evidence hierarchy

Prefer stronger evidence over model opinion:

1. compiler / schema / type system
2. lint / formatting / static analysis
3. unit and integration tests
4. runtime behavior and invariant checks
5. UI/visual evidence when relevant
6. independent semantic review
7. human judgment for high-risk or ambiguous changes

## Risk

Changes touching authentication, authorization, security, secrets, payments, migrations, infrastructure, deployment, CI workflows, containers, or dependency lockfiles are treated as high risk by default and require explicit human approval.

## Git and scope safety

- Never discard, reset, overwrite, or revert unrelated user changes.
- Review `git status` and the staged diff before committing.
- Do not use broad staging such as `git add -A` unless the user explicitly requests it and the staged file list has been reviewed.
- Keep temporary artifacts under `.agentflow/runtime/` or another ignored scratch directory.
- Independent reviewers are read-only. If a reviewer changes the worktree, its review is invalid.

## Project commands

The executable gate commands live in `.agentflow/config.json`. Update that file when the project's build/test workflow changes. Keep this `AGENTS.md` concise; put long procedures in Agent Skills or `docs/`.

## Skills

Reusable workflows are authored under `.agents/skills/`; Claude Code mirrors them under `.claude/skills/`. Use them when the task matches their description, especially checkpoint planning, implementation, verification, review, risk assessment, UI evidence, failure escalation, and handoff.
