---
name: risk-assess
description: Assess change risk and required approval for an Agentflow checkpoint. Use before accepting changes or when sensitive areas are touched.
---

Run `agentflow risk .` and inspect the actual changed files. Treat the tool's path-based risk as a floor, not a ceiling. Raise risk when semantics justify it (for example authorization behavior changed in a generic-looking file).

High risk normally includes auth/authz, secrets, security boundaries, payments/billing, database migrations, destructive data changes, infrastructure/deployment, CI/CD, container/build supply chain, dependency locks, or public compatibility surfaces. Explain why human review is required rather than hiding the decision in a score.
