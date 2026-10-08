# Agentflow Meta-Harness

Agentflow is an **Agentic SDLC meta-harness** for general-purpose coding agents.

It does not replace Claude Code, Codex, Pi, OpenCode, or another coding agent. Those harnesses keep their native reasoning, repository exploration, editing, tool use, and debugging loops. Agentflow supplies the development methodology around them: stages, evidence, reviews, retry limits, approvals, and durable workflow state.

> Bring your coding agent. Choose your SDLC. Agentflow enforces it.

## What is included

- Installable Python 3.11+ CLI. Runtime requirements: `jsonschema` (to validate Agentic Dev's documents) and the [Agentic Dev](https://github.com/szaher/agentic-dev) `agentic` CLI for repository facts and verification. AgentFlow never imports Agentic Dev's Python code.
- First-class adapters for **Claude Code**, **Codex**, **Pi**, and **OpenCode**.
- Generic command adapter for any other non-interactive coding-agent CLI.
- 21 built-in Agentic SDLC patterns.
- Repository-local durable run state and evidence.
- Git-diff fingerprints so verification evidence is tied to the code it verified.
- Deterministic gates discovered and executed by Agentic Dev (`agentic verify run`) for any stack Agentic Dev supports.
- Configurable custom gates for any stack, also executed by Agentic Dev.
- Independent read-only review with post-run worktree mutation detection.
- Risk-sensitive human approval support.
- Cross-harness review: e.g. Claude implements, Codex and Pi review.
- `AGENTS.md`/`CLAUDE.md` workflow blocks and the `agentflow-sdlc` skill, placed through Agentic Dev (managed blocks and its provider/skill mechanism).
- OpenCode read-only reviewer configuration.
- Unit tests using only the Python standard library, plus contract tests against the installed `agentic` CLI (jsonschema, test-only).

## Install

```bash
unzip agentflow-meta-harness.zip
cd agentflow-meta-harness
./install.sh
agentflow --version
```

The default installer copies the source under `~/.local/share/agentflow-meta`, creates a private virtual environment there for AgentFlow's one runtime dependency (`jsonschema`), and installs a launcher under `~/.local/bin`. Install Agentic Dev (`agentic`) separately.

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

`agentflow init` sets the project up through Agentic Dev and never rewrites shared files:

- **Instructions:** AgentFlow's workflow text goes into one managed block, `agentflow.workflow`, in `AGENTS.md` and `CLAUDE.md`, placed by `agentic instructions block put`. Existing content is preserved byte for byte, re-running is a no-op, and a block you edited by hand stops `init` instead of being overwritten (`--force` included).
- **Skill:** the `agentflow-sdlc` skill ships as an Agentic Dev *provider* bundled with AgentFlow. Agentic Dev installs it and places it for Claude Code, Codex, Pi, and OpenCode (`agentic skills add --shared`). A `SKILL.md` of your own already at one of those paths stops `init` before anything in the repository changes; move it aside and rerun.
- **Files AgentFlow owns:** `.agentflow/` and the OpenCode reviewer agent `.opencode/agents/agentflow-reviewer.md`.

The provider lives in your global Agentic Dev registry, so `init` is careful with it:

| Installed `agentflow` provider | `agentflow init` |
|---|---|
| missing | installs the one bundled with this AgentFlow |
| identical (same content digest, verified) | nothing to do |
| different (another AgentFlow version), or failing verification | **stops**; nothing is changed |

Replace a different provider only on purpose: `agentflow provider install --replace` or `agentflow init --update-provider`. With `--no-provider-install`, `init` never touches global state and fails unless the provider is already current. `agentflow provider status` shows where you stand.

Commit the generated project integration files before beginning real work. From `.agentic/`, commit only `skills.json`; other Agentic Dev state there is local:

```bash
git add AGENTS.md CLAUDE.md .agentflow .agentic/skills.json .claude .codex .pi .opencode
git commit -m "chore: enable Agentflow"
```

Then run a task:

```bash
agentflow run "Implement password reset with expiring single-use tokens" --dry-run
agentflow run "Implement password reset with expiring single-use tokens"
```

The dry run displays the resolved workflow, Agentic Dev session plan, blockers, and `plan_digest` without creating run state or a worktree. A ready plan needs explicit approval of that digest before preparation; use `--yes` to approve one new run in a non-interactive script. Real Codex/Claude/Pi/OpenCode plans remain blocked while their launch permissions are `unknown`, and AgentFlow will not launch them. Verified launch recipes are still required before real execution.

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

AgentFlow decides **what a gate requires**; [Agentic Dev](https://github.com/szaher/agentic-dev) **discovers and runs the commands**. The `agentic` CLI is a hard prerequisite: AgentFlow talks to it only through process + JSON contracts, checks `agentic contracts --json` for the contracts and features it needs (never the version), and has no fallback of its own. If `agentic` is missing or incompatible, `agentflow doctor` and `agentflow verify` say so and a gate stage **blocks** the run instead of retrying the implementation. Set `AGENTFLOW_AGENTIC` to use a specific binary.

A gate is full-project verification. Each profile names the command kinds it **requires**, and Agentic Dev runs **every** command it discovers for each:

| Profile | Kinds |
|---|---|
| `fast` | lint, test |
| `standard` | lint, typecheck, test |
| `strict` | build, lint, typecheck, test |

Profiles are defined in terms of *kinds*, not tools. AgentFlow decides which kinds are required and always requests all of them; Agentic Dev decides whether each can be satisfied and which concrete commands implement it (for example `make check`, `uv run pytest`, `pnpm test`). If **any** required kind has no command, Agentic Dev reports `no-checks` with the `missing_kinds` and runs nothing, and the gate fails: for example, `fast` fails on a repository with tests but no lint command. `agentflow doctor` lists the required kinds and which ones have no command yet.

You can override each profile in `.agentflow/config.json`; explicit commands replace the profile's kinds and still execute through Agentic Dev. AgentFlow passes each command intact as a single argument and never invokes a shell itself; Agentic Dev's execution backend runs it:

```json
{
  "gates": {
    "fast": ["ruff check .", "pytest -q tests/unit"],
    "standard": ["ruff check .", "mypy src", "pytest -q"],
    "strict": ["ruff check .", "mypy src", "pytest -q", "python -m build"]
  }
}
```

A gate stage with zero discovered/configured checks **fails closed** (`no-checks`); AgentFlow never treats “nothing ran” as verification.

Each run records the commit it started from (`run_start_commit`; none for a repository with no commits yet). Workflow gate stages are full-project only. `agentflow verify --include-changed` additionally asks Agentic Dev for change-aware checks since that commit; they can only add to the full baseline, never remove a check.

Every Agentic Dev document AgentFlow consumes is validated against the schema the installed `agentic` ships; an invalid response fails closed. Gate evidence is an AgentFlow envelope (run, stage, fingerprint, profile, status) around Agentic Dev's unmodified `agentic.verification-run` document.

### Migration from the built-in detector

Gate commands now come from Agentic Dev's canonical discovery, so some differ from earlier AgentFlow: Python tests run as `uv run pytest` rather than `python -m pytest -q`; package scripts use the lockfile's runner (`pnpm`, `yarn`, `bun run`); Rust `cargo check` and Go `go vet` are no longer added implicitly (use `strict` with a project `lint`/`build` command, or explicit `gates`); `make check` counts as a test command when there is no `make test`. Use `gates` in `.agentflow/config.json` to pin exact commands.

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

### Pattern requirements

A pattern can also declare what must hold before a run starts and how the run is isolated. Every field is optional and off by default; the built-in patterns declare none.

```json
{
  "requires": {"readiness": "foundational", "capabilities": ["sast"]},
  "verification": {"minimum": ["test"]},
  "isolation": {"mode": "worktree", "cleanup": "on-success"}
}
```

| Field | Meaning |
|---|---|
| `requires.readiness` | Passed as `readiness_minimum` to Agentic Dev's session planner. A missing level blocks the plan; preparation revalidates it. AgentFlow never remediates. |
| `requires.capabilities` | Passed as required capabilities to the session planner. They must already be enabled; AgentFlow never enables them. |
| `requires.skills`, `requires.allowed_skills` | Required skills and optional allowlist passed to the session planner. Only selected skills are prepared in the worktree. |
| `requires.trust_profile`, `requires.trust_ceiling` | Requested trust profile and ceiling, composed by Agentic Dev with the repository profile. |
| `requires.permissions` | Optional `implementer` and `reviewer` filesystem/network bounds. Reviewers remain read-only; Agentic Dev rejects invalid or unenforceable bounds. |
| `verification.minimum` | Kinds every gate of this pattern requires, added to the profile's kinds. They also apply when `.agentflow/config.json` replaces a profile with custom commands. |
| `isolation.mode: worktree` | Session runs always prepare a linked worktree (`agentflow-<run id>`, branch `agentflow/<run id>`) from the approved commit. This pattern field remains relevant to cleanup policy. The worktree must be clean; AgentFlow never copies or stashes uncommitted changes. |
| `isolation.cleanup: on-success` | When a run completes, ask Agentic Dev for a normal clean. A worktree with uncommitted work is refused and kept. Worktrees are never force-removed, and failed or blocked runs always keep theirs (`agentic worktree clean agentflow-<run id>` when you are done). |

The order is: resolve request and plan in the primary checkout, display the `plan_digest`, obtain explicit per-run approval, persist that approval, create or reuse the worktree, call `agentic session prepare`, and save `session-record@1` as evidence. A changed plan or failed preparation blocks the run before any stage. `agentflow step` resumes an approved, interrupted preparation using the same digest and worktree.

Harnesses AgentFlow launches get `AGENTFLOW_ROOT` (the primary checkout), `AGENTFLOW_WORKSPACE`, and `AGENTFLOW_RUN_ID`. Inside an isolated worktree, `agentflow status` and `agentflow verify` therefore reach the run's state in the primary checkout, and evidence paths in stage prompts are absolute. `AGENTFLOW_ROOT` is honoured only from inside that root or the run's workspace. Unknown keys in these sections are a validation error, not ignored. Level, capability and kind names belong to Agentic Dev, which rejects unknown ones.

When local metrics are enabled in Agentic Dev (`agentic metrics enable`; off by default), each executed stage records one `agentflow.stage` event (stage, kind, outcome, pattern, attempt, duration) through `agentic metrics record`. A metrics problem never changes a run's outcome.

## Commands

```text
agentflow init [PATH]             initialize a repository
agentflow patterns               list built-in + project patterns
agentflow detect                 detect installed first-class harnesses (via agentic doctor)
agentflow provider status        is the agentflow provider (agentflow-sdlc skill) current?
agentflow provider install       install it if missing (--replace to replace a different one)
agentflow doctor                 validate project integration
agentflow configure              update common project settings
agentflow run TASK --dry-run     show workflow + session plan without mutation
agentflow run TASK [--yes]      plan, approve, prepare, then run supported stages
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
- Pattern requirements block a run before its first stage (readiness and capabilities are never remediated); isolated runs work in their own worktree, which is never force-removed.

## Current limitations

This is a usable v0.1 meta-harness, not a remote execution platform. It invokes locally installed coding-agent CLIs and inherits their authentication/runtime environment. It does not yet provide distributed workers, a web UI, remote secrets brokering, PR-provider integrations, or native browser automation. UI patterns rely on the selected coding harness's available browser/screenshot tooling.

## Development

```bash
python -m unittest discover -s tests -v
python -m compileall -q src tests
agentflow patterns
```

See `ARCHITECTURE.md` for design boundaries and `examples/` for project configuration examples.
