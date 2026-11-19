# Computer Agent

A learn-by-building project for a general-purpose computer-use system. We will first build a safe, observable browser computer; task planning and optional model-assisted reasoning come later. merSETA and other data platforms will be integrations, not assumptions in the core.

## Build approach

This project is being implemented in substantial, coherent tranches. The user explicitly asked the assistant to implement the project; walkthroughs and learning notes can be added as requested. A milestone is marked implemented only after its code has been tested, and verified behavior is recorded separately from learning checkpoints.

## Getting started (Windows PowerShell)

This workspace has an existing `.venv` using Python 3.14.8. Install the project and its development dependencies from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run unit tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Install the Chromium browser when beginning the browser-computer tranche:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

The local browser computer, observation engine, bounded task loop, optional local reasoning provider, and M5 persistence foundations are implemented. The control interface and integrations remain future tranches.

## Run the local agent loop

The M3 site-specific agent searches the local fixture pages and writes a task trace and matching records to `artifacts/agent-task.json`:

```powershell
.\.venv\Scripts\python.exe -m computer_agent.agent.main electrician
```

All planners accept a search query rather than arbitrary natural-language instructions. They are restricted to the bundled local demo site, 20 actions maximum, and a 60-second timeout. The default M3 workflow needs no inference.

Compare structural heuristics and the optional local Ollama model on the unfamiliar library fixture:

```powershell
.\.venv\Scripts\python.exe -m computer_agent.agent.main electrician --start-page library/portal.html --planner heuristic --output artifacts\heuristic-comparison.json
.\.venv\Scripts\python.exe -m computer_agent.agent.main electrician --start-page library/portal.html --planner ollama --model qwen2.5-coder:3b --timeout 60 --output artifacts\ollama-comparison.json
```

The Ollama command requires the local Ollama service and selected model to be installed. It sends prompts only to `127.0.0.1`; there is no cloud fallback. Model proposals are checked against observed controls, task limits, and local navigation rules before execution.

Groq is also available as an explicitly selected hosted planner. Its key is read from the ignored `.env` file (or `GROQ_API_KEY` in the process environment); `.env.example` shows the standard variable names. The loader also accepts the existing whitespace-based `groq key` entry. You can run it on the local library fixture with:

```powershell
.\.venv\Scripts\python.exe -m computer_agent.agent.main electrician --start-page library/portal.html --planner groq --model llama-3.3-70b-versatile
```

When Groq is selected, the task query and current fixture-page observation are sent to Groq over HTTPS for each planning step. Site-rules, heuristic, and Ollama runs do not use the Groq key or send data to Groq. Never commit `.env` or use the hosted planner with sensitive page content.

## M5: resume, replay, and artifacts

Runs are stored in SQLite by default at `artifacts\memory.sqlite3`. To create a run that stops at its action limit, note its `run_id` in `artifacts\agent-task.json`, then resume it:

```powershell
.\.venv\Scripts\python.exe -m computer_agent.agent.main electrician --max-steps 1
$runId = "paste-the-run_id-from-artifacts\agent-task.json"
.\.venv\Scripts\python.exe -m computer_agent.agent.main --resume $runId
```

Save a completed run as a verified procedure, then replay it against the same local fixture page:

```powershell
.\.venv\Scripts\python.exe -m computer_agent.agent.main electrician --save-procedure "local electrician search"
.\.venv\Scripts\python.exe -m computer_agent.agent.main electrician --replay-procedure "local electrician search"
```

Use `--memory-db` to select another SQLite file. Result artifacts are saved under `artifacts\workspace` with content-addressed paths and integrity metadata. Approval requests are currently audited and single-use in storage; approval enforcement is not yet connected to browser actions. These are persistence and application-level navigation foundations, not an operating-system or network-isolation sandbox.

## M6: local control API

Start the API from the repository root. It binds to localhost only:

```powershell
.\.venv\Scripts\python.exe -m computer_agent.api.main
```

Open `http://127.0.0.1:8000/docs` for the interactive API reference. Submit a local-fixture task with `POST /tasks`, inspect it with `GET /tasks/{task_id}`, and control it with `POST /tasks/{task_id}/pause`, `/resume`, or `/terminate`. `GET /tasks/{task_id}/events` streams status, browser observations, action steps, and the final result over server-sent events. Set `"planner": "groq"` in the submission body to opt into Groq.

Pause and termination take effect at safe action boundaries: a current browser action is allowed to finish before the agent pauses or stops. The API is an unauthenticated, single-process development interface, so it intentionally listens only on `127.0.0.1`; do not expose it to a network.

## Current learning checkpoints

The foundation test and M1–M6 tests pass. The foundation type-annotation explanation and M1–M6 architecture walkthroughs are still pending in `docs/learning-log.md`.

Learning notes and verified evidence are tracked in `docs/progress/README.md`.

## Architecture

Keep these components independently testable and keep the planner separate from the computer runtime:

- **Computer runtime:** isolated Playwright browser sessions and a small, restricted action interface.
- **Observation engine:** structured observations of accessible controls, DOM/page text, URLs, screenshots, and action results.
- **Planning engine:** interchangeable site rules, structural heuristics, or an optional local model propose actions based on observations.
- **Execution supervisor:** permissions, allowed destinations, approvals, timeouts, resource and step limits, and audit records.
- **Memory and artifacts:** task history, observations, checkpoints, screenshots, downloads, and approved reusable procedures.
- **Agent control plane:** task submission, status, monitoring, interruption, and integration APIs.

The intended execution cycle is: understand the task and completion criteria, observe, choose one permitted action, execute, verify the result, then continue, recover, request approval, or stop. An action completing is not sufficient evidence that the task succeeded.

## Tranches

| Tranche | Focus | Acceptance check |
| --- | --- | --- |
| M1 | Browser computer | Control a local test website through a restricted action API; close the browser reliably |
| M2 | Observation engine | Identify actionable elements structurally, without hard-coded coordinates |
| M3 | Agent loop | Complete a simple multi-page local task with verification and stopping conditions |
| M4 | Reasoning | Compare deterministic heuristics with optional, replaceable local or hosted models |
| M5 | Memory and sandbox foundations | Persist runs and artifacts; resume and replay verified procedures within local fixture constraints |
| M6 | Control interface | Submit, inspect, pause, and terminate a task through the local API |
| M7 | Integrations | Produce traceable artifacts for approved downstream systems |

Build and test each tranche before moving on. Desktop control, remote browser control, unrestricted code execution, and production deployment are out of scope unless we explicitly agree to expand the project.

## Safety boundaries

- Use only authorized sources; never bypass CAPTCHAs, paywalls, or access restrictions.
- Treat pages, downloads, extracted data, and model suggestions as untrusted input.
- Validate every action through the supervisor. Enforce destination and network restrictions outside the application as well as in it.
- Require explicit approval for sensitive actions. Apply step, time, and resource limits.
- Never execute downloaded content. Keep any future code execution restricted to a separately designed sandbox.
- The current browser is limited to bundled local fixtures by application checks; no OS-level or network-level sandbox is implemented.
- Keep credentials, cookies, browser debugging ports, and sensitive page contents out of source control and logs.
- Start with deterministic operations. Model-assisted reasoning is optional and deferred; repeated successful procedures should be replayable without inference.
- Data-acquisition integrations must send artifacts through approved quarantine and governance processes, never directly into authoritative datasets.

## Progress

The tranche-by-tranche status and evidence belong in [docs/progress/README.md](docs/progress/README.md). Learning notes belong in [docs/learning-log.md](docs/learning-log.md); design rationale goes in [docs/decisions.md](docs/decisions.md).
