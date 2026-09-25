---
name: security-review
description: Review security-sensitive changes independently and read-only. Use for high-risk checkpoints involving trust boundaries, auth, secrets, infrastructure, or supply chain.
---

Operate read-only. Identify trust boundaries and assets first. Review authentication and authorization decisions, secret exposure, injection surfaces, path/shell handling, unsafe parsing/deserialization, privilege changes, network egress, dependency/supply-chain changes, destructive operations, and insecure defaults.

For each blocking finding provide the affected code path, plausible failure/attack mechanism, and a concrete verification or remediation direction. Avoid speculative severity inflation; separate confirmed defects, credible risks, and optional hardening.
