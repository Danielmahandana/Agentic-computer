# Decision log

Keep entries short: record the decision, context, and trade-off. Revisit when evidence changes.

## Initial decisions

- **Build a standalone computer-use system:** the core is not tied to merSETA or a particular data platform; integrations come later.
- **Start with a browser, not desktop control:** Playwright and Chromium provide a testable first runtime. Desktop control would need a separate isolated environment.
- **Separate planning from execution:** the planner proposes actions; the runtime exposes only a limited action API; the supervisor checks permissions and bounds.
- **Build in tranches:** directories can anticipate later components, but features are implemented and demonstrated one lesson at a time by the learner.
- **Teach substantial slices:** provide coherent assignments across related files rather than splitting a tranche into tiny code snippets; the learner authors the code.
- **Keep model reasoning optional and local:** deterministic behavior and structural inspection remain available without inference. M4 adds a replaceable planner boundary and a loopback-only Ollama adapter.
- **Keep M3 on a local workflow:** the first agent loop uses a structured search request and observed controls on the bundled fixture. It does not interpret arbitrary natural language or browse external sites.
- **Validate model proposals as untrusted input:** an action must match one unique, visible, enabled control; fill values come from the task, and link destinations must stay in the local fixture.
- **Make bounds explicit:** cap actions, wall-clock time, supported fixture pages, and link destinations; return explicit statuses when a step limit, timeout, or pagination loop prevents completion.
- **Defer Docker configuration:** a sandbox image without a tested network and permission policy could suggest false security. Design it with the sandbox tranche.
- **Use the existing Python 3.14 environment:** project metadata supports Python 3.12 and newer.
