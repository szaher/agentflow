# Architecture

## Product boundary

Agentflow is an **Agentic SDLC meta-harness**. Its scope is software development workflows. It is not a model-training system and it is not a replacement coding agent.

### Agentflow owns

- pattern definition and validation
- workflow stage and transition state
- attempt budgets
- deterministic verification gates
- evidence provenance
- independent review requirements
- risk/approval policy
- durable workflow history
- routing to coding-agent harnesses

### Coding harnesses own

- codebase exploration
- reasoning strategy
- context management
- tool invocation
- code editing
- debugging strategy
- native subagents/extensions

## Core data flow

```text
Task -> Pattern -> Stage -> Harness execution -> Repository state
                              |                    |
                              +---- evidence <-----+
                                       |
                              transition decision
```

## Adapter rule

Keep adapters coarse. Agentflow should not normalize every native tool or reconstruct each harness's inner loop. The stable surface is roughly:

- execute(prompt, workspace, constraints)
- review(prompt, workspace, read_only)
- capabilities/configuration

## Pattern rule

Patterns express policy semantically ("independent read-only review", "strict deterministic gates", "human approval") rather than naming harness-specific features such as a Claude Stop hook.

## Evidence rule

No state transition that claims verification should depend solely on an agent's prose assertion. Deterministic gates are executed directly by Agentflow. Review output is stored and bound to a repository fingerprint.

## Extensibility

- Add project-local JSON patterns under `.agentflow/patterns/`.
- Add arbitrary CLI harnesses via `harness.<name>.command` configuration.
- First-class adapters can add stronger native enforcement while preserving the pattern semantics.
