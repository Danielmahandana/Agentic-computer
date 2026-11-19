# Initial threat model

This is a starting checklist, not a completed security review. Revisit it as the system gains capabilities.

## Assets

- Browser credentials, cookies, and session state
- The host and network reachable by the browser or tools
- Local files and acquired artifacts
- Task history, screenshots, observations, and operator controls

## Threats and design constraints

- A page, redirect, download, or extracted value may be malicious or misleading.
- A browser action may reach an unauthorized destination or trigger a sensitive change.
- A compromised browser or tool may expose local files, credentials, or internal network services.
- A planner or future model may propose an unsafe or incorrect action.
- Logs, screenshots, and saved observations may expose sensitive information.

## Initial controls

- Use a local test site first; explicitly authorize sources before external browsing.
- Restrict browser actions and validate them in a supervisor with destination, step, time, and resource limits.
- Enforce network isolation outside Python as well as through application policy.
- Require approval for sensitive actions; provide pause and stop controls as the control plane arrives.
- Treat artifacts and model suggestions as untrusted. Never execute downloads.
- Keep credentials and debugging ports private; redact sensitive data from logs and screenshots.
- Design any future code-execution environment separately and test its isolation before use.
