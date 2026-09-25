---
name: checkpoint-plan
description: Decompose a large software task into bounded Agentflow checkpoints with explicit acceptance criteria. Use before implementation of multi-step or risky work.
---

Read `AGENTS.md` and the relevant product/design docs. Decompose the requested outcome into the smallest useful ordered checkpoints that can each be implemented and verified independently.

For each checkpoint specify: goal, in-scope files/components, observable acceptance criteria, explicit out-of-scope items, dependencies, and expected evidence. Prefer vertical slices over layers when a slice can be exercised end to end.

Do not create a huge plan whose steps cannot be independently judged. Do not treat "agent says done" as acceptance. Create or update files under `docs/exec-plans/active/` and keep machine state aligned with `.agentflow/checkpoints/` when Agentflow is already initialized.
