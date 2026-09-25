---
name: ui-evidence
description: Collect and judge UI/runtime evidence for a visual or interactive checkpoint. Use when screenshots, browser behavior, layout, or interaction matters.
---

Read `docs/agentflow/ui-verification.md`. Start the app using the repository's recorded run recipe. Exercise the exact route/screen involved in the checkpoint using available browser/computer tooling.

Compare actual behavior with the reference spec or image. Record screenshots/evidence and concrete differences. Check interactions, loading/empty/error states, responsive behavior when relevant, and basic accessibility. If browser evidence cannot be produced, report the gate as unverified rather than passing it from source inspection alone.
