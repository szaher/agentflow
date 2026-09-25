---
name: checkpoint-verify
description: Verify an implemented Agentflow checkpoint using deterministic gates and observable behavior. Use after implementation and before independent review.
---

Verification is independent from implementation. First run the configured deterministic gates and record actual output. Then compare the active checkpoint's acceptance criteria with observable behavior.

If a criterion cannot be verified, mark it unknown rather than assuming success. For UI behavior, use the `ui-evidence` skill. Do not silently fix implementation while acting as verifier; return failures to the worker unless explicitly reassigned.
