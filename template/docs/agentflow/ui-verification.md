# UI verification protocol

UI verification is evidence, not a vague "looks good" step.

For UI checkpoints, record:

1. the run/start command and environment assumptions;
2. target URL, route, or app screen;
3. viewport/device assumptions when relevant;
4. reference image/design/spec identifier;
5. screenshots or browser evidence from the implemented state;
6. differences found and whether each is intended;
7. accessibility/interaction checks that cannot be seen from a screenshot.

Prefer an actual browser/computer tool available to the active harness. If the project needs a special boot sequence (database, env vars, fixture data, services), capture that recipe in a project-specific skill rather than rediscovering it every session.
