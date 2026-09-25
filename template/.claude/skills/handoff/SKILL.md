---
name: handoff
description: Create a concise filesystem-grounded handoff for a fresh agent context or different harness. Use when switching Claude Code, Codex, Pi, or starting a fresh session.
---

Produce a handoff grounded in repository state. Include: active checkpoint ID and goal; completed work; current `git status`; latest gate status and whether its fingerprint is current; latest review status; blockers; exact next action; commands needed to resume.

Do not rely on chat-only details if the filesystem contradicts them. Keep durable facts in the checkpoint/docs so a fresh harness can recover state without inheriting a long conversation.
