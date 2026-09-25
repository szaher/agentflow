---
name: checkpoint-implement
description: Implement exactly one active Agentflow checkpoint without scope creep. Use for feature work, fixes, or refactors after a checkpoint exists.
---

Read `AGENTS.md`, the active checkpoint, relevant source, and tests. Implement only the active checkpoint. Preserve unrelated user changes. Prefer the simplest general solution that satisfies the acceptance criteria.

Do not game tests, hard-code test fixtures into production logic, or weaken assertions. Add/update tests only when they express intended behavior. Run `agentflow gates . --profile fast` during iteration and `agentflow gates . --profile standard` before declaring the implementation ready for review.
