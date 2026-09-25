# Agentflow Meta-Harness

Agentflow is an **Agentic SDLC meta-harness** for general-purpose coding agents.

It does not replace Claude Code, Codex, Pi, OpenCode, or another coding agent. Those harnesses keep their native reasoning, repository exploration, editing, tool use, and debugging loops. Agentflow supplies the development methodology around them: stages, evidence, reviews, retry limits, approvals, and durable workflow state.

> Bring your coding agent. Choose your SDLC. Agentflow enforces it.

## What is included

- Installable Python 3.11+ CLI with no runtime Python dependencies.
- First-class adapters for **Claude Code**, **Codex**, **Pi**, and **OpenCode**.
- Generic command adapter for any other non-interactive coding-agent CLI.
- 21 built-in Agentic SDLC patterns.
- Repository-local durable run state and evidence.
- Git-diff fingerprints so verification evidence is tied to the code it verified.
- Automatic deterministic gate detection for Python, Node/TypeScript, Go, Rust, and Make projects.
- Configurable custom gates for any stack.
- Independent read-only review with post-run worktree mutation detection.
- Risk-sensitive human approval support.
- Cross-harness review: e.g. Claude implements, Codex and Pi review.
- Generated `AGENTS.md`, `CLAUDE.md`, and Agent Skills for compatible harnesses.
- OpenCode read-only reviewer configuration.
- Unit/integration tests using only the Python standard library.

## Install

```bash
unzip agentflow-meta-harness.zip
cd agentflow-meta-harness
./install.sh
agentflow --version
```

The default installer is intentionally zero-dependency: it copies the source under `~/.local/share/agentflow-meta` and installs a launcher under `~/.local/bin`. It does not need PyPI access.

You can also run directly from the extracted directory without installing:

```bash
./bin/agentflow --version
./bin/agentflow patterns
```

For development, either use `PYTHONPATH=src` or install with your preferred Python packaging tool:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m agentflow patterns
```

## Start a new project

```bash
mkdir my-app && cd my-app
agentflow init --init-git --pattern standard --agent claude --reviewers codex,pi
agentflow doctor
```

Commit the generated project integration files before beginning real work:

```bash
git add AGENTS.md CLAUDE.md .agentflow .agents .claude .codex .pi .opencode
git commit -m "chore: enable Agentflow"
```

Then run a task:

```bash
agentflow run "Implement password reset with expiring single-use tokens"
```

Use another pattern or harness for a specific run:

```bash
agentflow run "Fix issue #142" --pattern reproduce-first --agent codex --reviewers claude,pi
```

If a pattern reaches a human gate:

```bash
agentflow status
agentflow approve --continue-run
```

## Mental model

```text
Developer / CI
     │
     ▼
 Agentflow
(meta-harness)
     │
     ├── selects/enforces SDLC pattern
     ├── persists stage + evidence + attempts
     ├── invokes deterministic gates
     ├── invokes independent reviewers
     └── controls workflow transitions
     │
     ├─────────────┬─────────────┬─────────────┐
     ▼             ▼             ▼             ▼
Claude Code      Codex           Pi         OpenCode
     │             │             │             │
     └─────────────┴─────────────┴─────────────┘
                     │
            reason / edit / debug
                     │
                     ▼
                  Git repo
```

**Harnesses decide how to accomplish the delegated stage. Agentflow decides what counts as accomplished.**

## Built-in patterns

Run `agentflow patterns` to see the live catalog.

| Pattern | Intended use |
|---|---|
| `fast` | Small, low-risk changes |
| `standard` | Balanced default |
| `checkpoint` | Bounded checkpoint + strict gates + 2 reviewers + approval |
| `helix` | High-confidence Helix-inspired convergence loop |
| `tdd` | Red → green → refactor |
| `reproduce-first` | Bug fixes that require a regression reproducer |
| `spec-driven` | Explicit acceptance criteria before implementation |
| `security-critical` | Threat analysis + strict verification + 2 reviews + mandatory approval |
| `ui-parity` | Reference-driven UI + visual/accessibility review |
| `refactor` | Behavior-preserving refactor |
| `dependency-upgrade` | Compatibility-aware dependency upgrade |
| `database-migration` | Migration safety, rollback thinking, mandatory approval |
| `api-change` | API contract and compatibility workflow |
| `legacy-migration` | Incremental legacy migration with parity review |
| `performance` | Baseline → measured optimization |
| `release` | Release readiness + approval |
| `hotfix` | Minimal production repair + strict verification |
| `docs` | Lightweight documentation workflow |
| `test-hardening` | Improve tests and invariants |
| `spike` | Bounded exploratory technical research |
| `pair-review` | Implementation + two independent reviewers |

## Harness support

### Claude Code

Programmatic execution uses `claude -p`. Read-only review disables edit/write tools and Agentflow independently fingerprints the repo before and after review.

### Codex

Programmatic execution uses `codex exec`. Review requests a read-only sandbox and Agentflow independently checks for repository mutation.

### Pi

Programmatic execution uses `pi -p`. Read-only review restricts tools to read/grep/find/ls.

### OpenCode

Programmatic execution uses `opencode run --standalone`. `agentflow init` generates `.opencode/agents/agentflow-reviewer.md`; Agentflow still verifies that review did not mutate the worktree.

### Any other coding agent

Configure a command adapter in `.agentflow/config.json`:

```json
{
  "executor": "my-agent",
  "reviewers": ["my-agent-review"],
  "harness": {
    "my-agent": {
      "command": ["my-agent", "run", "{prompt}"]
    },
    "my-agent-review": {
      "command": ["my-agent", "run", "{prompt}"],
      "review_command": ["my-agent", "review", "{prompt}"]
    }
  }
}
```

Agentflow intentionally uses a coarse adapter boundary. It does not reimplement a harness's internal agent loop.

## Deterministic verification

`agentflow verify` auto-detects common project checks. You can override each profile in `.agentflow/config.json`:

```json
{
  "gates": {
    "fast": ["ruff check .", "pytest -q tests/unit"],
    "standard": ["ruff check .", "mypy src", "pytest -q"],
    "strict": ["ruff check .", "mypy src", "pytest -q", "python -m build"]
  }
}
```

A gate stage with zero detected/configured checks **fails closed**; Agentflow never treats “nothing ran” as verification.

## Evidence freshness

Verification/review evidence stores a fingerprint of the implementation state. Agentflow ignores its own runtime bookkeeping (`.agentflow/state.json`, evidence, logs) when computing the implementation fingerprint.

If the implementation changes after verification, `agentflow status` reports stale evidence.

## Independent reviews

Review stages are context-isolated new harness invocations. Reviewers are instructed to be read-only and must end with one of:

```text
AGENTFLOW_REVIEW_PASS
AGENTFLOW_REVIEW_FAIL
```

The text alone is insufficient: Agentflow also compares the repository fingerprint before and after each review. A reviewer that edits files is rejected even if it prints `PASS`.

## Risk and approval

The included v0.1 classifier is deliberately conservative and transparent. Paths related to auth, security, credentials, migrations, deployment, infrastructure, payments, and similar areas are elevated. Patterns such as `security-critical`, `database-migration`, `hotfix`, `release`, `checkpoint`, and `helix` can force human approval regardless of classification.

Treat the built-in classifier as a baseline. Real organizations should replace/augment it with policy checks appropriate to their repositories.

## Custom patterns

Project patterns live in:

```text
.agentflow/patterns/*.json
```

A project pattern with the same name overrides the built-in pattern.

Example:

```json
{
  "name": "acme-service-change",
  "description": "Acme service change policy",
  "version": "1.0",
  "entry": "implement",
  "tags": ["acme", "service"],
  "defaults": {},
  "stages": [
    {
      "id": "implement",
      "kind": "agent",
      "title": "Implement bounded service change",
      "role": "implementer",
      "instruction": "Implement one bounded service change.",
      "max_attempts": 3,
      "on_success": "verify",
      "on_failure": "blocked"
    },
    {
      "id": "verify",
      "kind": "gate",
      "title": "Service verification",
      "gate_profile": "strict",
      "on_success": "review",
      "on_failure": "implement"
    },
    {
      "id": "review",
      "kind": "review",
      "title": "Independent review",
      "reviewers": 2,
      "on_success": "approve",
      "on_failure": "implement"
    },
    {
      "id": "approve",
      "kind": "human",
      "title": "Production owner approval",
      "metadata": {"always": true},
      "on_success": "done",
      "on_failure": "blocked"
    }
  ]
}
```

Supported stage kinds are `agent`, `gate`, `review`, `human`, and `noop`.

## Commands

```text
agentflow init [PATH]             initialize a repository
agentflow patterns               list built-in + project patterns
agentflow detect                 detect installed first-class harnesses
agentflow doctor                 validate project integration
agentflow configure              update common project settings
agentflow run TASK               create and execute a run
agentflow step                   execute only the current stage
agentflow status                 inspect durable workflow state
agentflow verify                 run deterministic project gates
agentflow approve                satisfy a pending human gate
agentflow explain [PATTERN]      print a pattern's state machine
```

## Running inside a coding harness

Agentflow can be the top-level entry point (`agentflow run`) or a coding harness can be opened interactively and use the generated repository instructions/skills.

For example, inside Claude Code, Codex, Pi, or OpenCode:

```text
Continue the current Agentflow task. Inspect `agentflow status` and execute only the current stage.
```

This gives one architecture with two UX entry points; the durable `.agentflow` state remains authoritative.

## Safety properties implemented

- Bounded per-stage agent attempts.
- Fail-closed deterministic gate stages.
- Reviewer worktree-mutation detection.
- Evidence fingerprints tied to repository state.
- Human approval stages.
- No destructive Git reset behavior in Agentflow itself.
- Agentflow runtime artifacts are isolated from implementation fingerprints.
- Pattern validation catches invalid transitions and duplicate stages before execution.

## Current limitations

This is a usable v0.1 meta-harness, not a remote execution platform. It invokes locally installed coding-agent CLIs and inherits their authentication/runtime environment. It does not yet provide distributed workers, a web UI, remote secrets brokering, PR-provider integrations, or native browser automation. UI patterns rely on the selected coding harness's available browser/screenshot tooling.

## Development

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
agentflow patterns
```

See `ARCHITECTURE.md` for design boundaries and `examples/` for project configuration examples.
