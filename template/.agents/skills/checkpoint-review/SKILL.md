---
name: checkpoint-review
description: Perform an independent, read-only review of an Agentflow checkpoint after deterministic gates pass. Use to find semantic bugs and requirement gaps.
---

Do not modify the worktree. Read the checkpoint, current diff, tests, and relevant surrounding code. Prioritize correctness, requirement coverage, security/reliability, backward compatibility, and hidden scope expansion over formatting preferences.

Distinguish blocking findings from non-blocking suggestions. Reproduce or point to concrete evidence when possible. A passing deterministic suite does not automatically imply a passing review.
