# Agentflow Starter Kit

A reusable, harness-neutral control loop for agentic software development.

The core rule is simple:

> Agents propose changes. Evidence and policy decide whether the checkpoint is accepted.

Agentflow turns a large task into bounded checkpoints and drives each checkpoint through deterministic gates, semantic review, risk assessment, and (when needed) human approval. It is designed to work with **Claude Code**, **OpenAI Codex**, and **Pi** without making your repository depend on any one harness.

## What is included

- `agentflow` CLI: bootstrap, detection, checkpoints, gates, risk, harness execution, review, approval, and bounded cycles.
- Shared `AGENTS.md` as the project-level map/system of record.
- Cross-harness Agent Skills under `.agents/skills/`.
- Claude Code native project subagents and a bounded Stop hook.
- Codex-compatible `AGENTS.md` + Agent Skills layout.
- Pi-compatible `AGENTS.md` + Agent Skills, with a project settings file and CLI/RPC-friendly orchestration.
- Automatic project detection for Python, Node/TypeScript, Go, Rust, Maven/Gradle, and Make-based repositories.
- Risk-aware approval policy and a change fingerprint so stale gate results cannot be reused after the diff changes.
- GitHub Actions example for deterministic CI gates (kept under docs/examples so bootstrap does not silently activate CI).
- Unit tests for the local control-plane logic.

## Install once

```bash
unzip agentflow-starter-kit.zip
cd agentflow-starter-kit
./install.sh
```

This installs the kit under `~/.local/share/agentflow` and creates `~/.local/bin/agentflow`.

Make sure `~/.local/bin` is on your `PATH`.

### Optional: install the three harnesses on macOS

```bash
./scripts/install-harnesses-macos.sh --dry-run
./scripts/install-harnesses-macos.sh
```

The script uses Homebrew for Claude Code and Codex, and npm for Pi. Authentication remains interactive and is never automated by this kit.

## Bootstrap a new or existing project

```bash
mkdir -p my-project
cd my-project
# If this is not already a Git repo:
agentflow bootstrap . --init-git
# For an existing Git repo, use: agentflow bootstrap .
agentflow doctor .

# Commit the control-plane scaffold before starting feature work.
git add AGENTS.md CLAUDE.md .agentflow .agents .claude .pi docs .gitignore
git commit -m "chore: add agentflow project harness"
```

Bootstrap creates:

```text
AGENTS.md
CLAUDE.md
.agentflow/
  config.json
  checkpoints/
  hooks/
  runtime/          # gitignored
.agents/skills/
.claude/
  agents/
  settings.json
.pi/settings.json
docs/exec-plans/{active,completed}/
```

For an existing repository, Agentflow does not overwrite conflicting files unless you pass `--force`. It records skipped files in `.agentflow/bootstrap-conflicts.txt`.

## Normal workflow

Create a checkpoint:

```bash
agentflow new "Add passkey login" .
```

Edit the generated file under `docs/exec-plans/active/` and replace the placeholder acceptance criteria with concrete checks.

Then either work interactively in your preferred harness and use Agentflow only for gates:

```bash
claude        # or codex / pi
agentflow gates . --profile standard
agentflow risk .
agentflow status .
```

Or let Agentflow drive a bounded worker/reviewer loop:

```bash
agentflow cycle . \
  --worker claude \
  --reviewer codex \
  --max-attempts 3
```

You can mix harnesses:

```bash
agentflow cycle . --worker codex --reviewer pi --max-attempts 3
agentflow cycle . --worker pi --reviewer claude --max-attempts 3
```

When a checkpoint is ready:

```bash
agentflow approve . --human
```

High-risk changes require `--human`. Lower-risk changes can be accepted without it if project policy allows.

## Harness commands

Agentflow defaults to these one-shot commands:

```text
Claude Code: claude -p <prompt>
Codex:       codex exec <prompt>
Pi:          pi -p <prompt>
```

Override them without editing the kit:

```bash
export AGENTFLOW_CLAUDE_CMD='claude -p'
export AGENTFLOW_CODEX_CMD='codex exec'
export AGENTFLOW_PI_CMD='pi -p'
```

For reviews, Agentflow fingerprints the Git diff before and after the reviewer. If a reviewer mutates the repository, the review is rejected; Agentflow never auto-reverts user work.

## Profiles

- `fast`: cheap checks intended for inner-loop iteration.
- `standard`: normal pre-review gate set.
- `strict`: full build/test gate set when detected.

The generated `.agentflow/config.json` is intentionally ordinary JSON. Change the gate commands to match your repository rather than teaching every agent bespoke commands in prompts.

## Design

```text
Goal / feature
    |
    v
Checkpoint plan
    |
    v
Worker agent
    |
    v
Deterministic gates ---- fail ----> worker retry
    |
   pass
    v
Independent reviewer ---- fail ----> worker retry
    |
   pass
    v
Risk policy
   / \
 low  high
  |     |
  |   human approval
   \   /
    v v
Accepted checkpoint
    |
    v
Next checkpoint
```

The loop is deliberately bounded. After `max_attempts`, Agentflow marks the checkpoint `blocked` and asks for replanning or human intervention instead of spending tokens indefinitely.

## Important limitations

Agentflow does not pretend an LLM review is deterministic. Compiler, lint, test, build, schema, and repository invariants should be represented as executable gates whenever possible. The semantic reviewer is a separate layer, not a substitute for tests.

UI/visual verification is provided as a skill and evidence protocol because browser/computer tooling differs across harnesses and projects. Configure the project-specific run/browser recipe rather than hiding it behind a fragile generic script.

## Run the kit's tests

```bash
python3 -m unittest discover -s tests -v
```
