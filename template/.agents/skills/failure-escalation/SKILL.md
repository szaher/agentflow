---
name: failure-escalation
description: Diagnose an Agentflow checkpoint that repeatedly fails gates or review. Use after repeated attempts instead of looping indefinitely.
---

Stop feature implementation temporarily. Gather the latest deterministic failure output, review findings, git diff, and checkpoint criteria. Identify the earliest incorrect assumption or architectural mismatch, not just the last symptom.

Choose one outcome: narrow the checkpoint, change implementation strategy, fix an invalid acceptance criterion/test, split the checkpoint, or request human input. Document the reason before another implementation attempt. Never respond to repeated failure by weakening gates.
