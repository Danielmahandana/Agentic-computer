# Tranche progress

This file is the durable status record for the build. Update it at the end of each tranche with what was learned, what was demonstrated, test commands and results, and the next small step. Keep unverified behavior clearly labeled.

## T0 — Project structure

- **Status:** Complete
- **Built:** Project metadata, package and test directories, course README, learning/design/security logs, and tranche tracker.
- **Behavior implemented:** None. This tranche only prepared the workspace.
- **Setup verification:** Editable install succeeded; `computer_agent` imports; Playwright 1.65.2, Pydantic 2.14.4, and pytest 9.2.0 import; `pip check` reports no broken requirements. Chromium was installed for M1.
- **Tests:** No tests were part of T0; the first learner-written test is tracked below.
- **Evidence of learning:** Not assessed yet.
- **Next:** The learner chose to proceed to M1 and revisit the explanation checkpoint later.

## Foundation exercise — typed function and pytest

- **Status:** In progress
- **Built by learner:** `format_task_label` and its unit test.
- **Verification:** Learner-reported command `.\.venv\Scripts\python.exe -m pytest -vv tests/unit/test_labels.py` — 1 passed in 0.23s.
- **Still to demonstrate:** Explain `task_name: str`, `-> str`, and the test's import path. Deferred while M1 proceeds.

## M1 — Browser computer

- **Status:** Implemented and verified; learner walkthrough pending
- **Acceptance check:** Control a local test website through a restricted action API and close the browser reliably.
- **Scope:** Local fixture page, isolated Playwright session, a small semantic action API, initial page observation, screenshot bytes, and an action trace.
- **Implementation:** Reused the learner's `fixtures/fixture_site/index.html` and `computer/actions.py`; added the session manager, demo runner, browser test, package marker, and artifact ignore rule at the learner's request.
- **Verification:** `.\.venv\Scripts\python.exe -m pytest -vv` — 2 passed. `.\.venv\Scripts\python.exe -m computer_agent.main` printed `Search complete: Python engineer` and created observation, screenshot, and trace artifacts.
- **Learning checkpoint:** Explain how `actions.py`, `session.py`, and `main.py` divide responsibilities, and why the async context manager is used for cleanup.

## M2 — Observation engine

- **Status:** Implemented and verified; learner walkthrough pending
- **Implementation:** Added `computer/observations.py` with structured page and interactive-element records. It reports roles, best-effort accessible names, tag/input type, disabled state, and page status; hidden and `aria-hidden` controls are excluded.
- **Fixture and tests:** Expanded the local fixture with a link, disabled and hidden buttons, and an unlabeled textbox. Browser tests cover role/name recognition, disabled state, unnamed controls, and hidden controls.
- **Verification:** `.\.venv\Scripts\python.exe -m pytest -vv` — 3 passed. The M1 demo still runs and produces observation, screenshot, and trace artifacts.
- **Limitations:** Name and role extraction is a deterministic DOM heuristic, not a complete browser accessibility-tree implementation. Unknown custom widgets may not be classified yet.
- **Learning checkpoint:** Explain how the DOM observations are gathered and why the result is best-effort rather than a full accessibility tree.

## M3 — Agent loop

- **Status:** Implemented and verified; learner walkthrough pending
- **Implementation:** Added a structured, bounded task request; deterministic action selector; task state and trace; action verifier; and async runtime loop.
- **Local workflow:** The agent searches the local demo, follows its two result pages, extracts records, and filters matches against the requested query. It does not accept arbitrary natural-language tasks, run models, or visit external websites.
- **Safety bounds:** Maximum 20 actions, maximum 60 seconds, fixture-path destination checks, step-limit reporting, pagination loop detection, and action postcondition checks.
- **Verification:** `.\.venv\Scripts\python.exe -m pytest -vv` — 15 passed. Running `.\.venv\Scripts\python.exe -m computer_agent.agent.main electrician --output artifacts\agent-task.json` completed with 2 matching records from 3 visited pages. The original M1 demo still works; `pip check` reports no broken requirements.
- **Learning checkpoint:** Explain how observe/select/execute/verify repeats, how the loop knows it is done, and what prevents it from browsing beyond the local fixture.

## M4 — Reasoning

- **Status:** Implemented and exercised with a real local model; walkthrough pending
- **Implementation:** Added a planner protocol, a structural heuristic planner, and an Ollama chat provider. Observations now include bounded page text and a count of result records; each proposed action records a short rationale.
- **Unfamiliar-site fixture:** Added a local reports-catalog task with different labels and page paths from the original job-search fixture. Both the heuristic and `qwen2.5-coder:3b` completed it.
- **Model safety:** Ollama endpoints are restricted to loopback. Proposed controls must uniquely match visible, enabled observations; fill content is supplied by the task, and link destinations are constrained to the local fixture. No cloud fallback is configured.
- **Verification:** `.\.venv\Scripts\python.exe -m pytest -vv` — 23 passed. The heuristic and `qwen2.5-coder:3b` runs each completed the unfamiliar fixture with the same 1 matching record; the model trace includes explanations for fill, click, extraction, and finish. The M3 site-rules run still returns 2 records; `pip check` is clean.
- **Learning checkpoint:** Explain how the planner interface separates reasoning from browser actions, what the heuristic/model comparison showed, and how the supervisor constrains model proposals.
- **Later extension:** Added an explicitly selected Groq planner. It loads a key from the ignored `.env` file or `GROQ_API_KEY`, supports the existing whitespace-based `groq key` entry without logging its value, and sends bounded task observations to Groq only when selected. The actual local credential was detected without displaying or transmitting it; the API request path was tested with a mock, not a live Groq call.

## M5 — Memory and sandbox foundations

- **Status:** Implemented and verified; walkthrough pending
- **Implementation:** Added SQLite storage for task runs, action history, acquired records, checkpoints, verified procedures, artifacts, and approval requests. The runtime can resume an interrupted task from a validated local fixture URL and replay a stored procedure only from its verified start page, validating proposed actions against current observations.
- **Artifacts and approvals:** Artifact paths are confined to the workspace, content-addressed result paths avoid overwriting earlier run results, and reads verify saved size and SHA-256 metadata. Approval requests are auditable and single-use in storage; approval enforcement is not yet integrated with browser action execution.
- **Atomicity:** Final progress, checkpoint, and run status/result are committed in one SQLite transaction. Conflicting writes to an existing artifact path fail rather than invalidating earlier metadata.
- **Verification:** `.\.venv\Scripts\python.exe -m pytest -vv` — 27 passed, including a transaction rollback test for a simulated final-write failure. `.\.venv\Scripts\python.exe -m pip check` — no broken requirements. CLI workflows with a temporary database successfully stopped at the step limit, resumed to completion, saved and replayed a verified procedure, and verified all four generated artifact records against their file sizes and hashes.
- **Limitations:** This tranche provides persistence and application-level fixture navigation controls, not an OS/network sandbox. Sensitive-action approval enforcement and external integrations are not implemented.
- **Next:** M6 — control interface for submitting, inspecting, pausing, and terminating a task.

## M6 — Control interface

- **Status:** Implemented and verified; walkthrough pending
- **Implementation:** Added a FastAPI service for task submission and inspection, pause/resume/termination controls, and an SSE stream for status, page observations, action steps, and results. The service defaults to `127.0.0.1:8000`.
- **Control behavior:** Pause and termination are cooperative and take effect at the next safe action boundary; an in-progress browser action may finish first. Termination is persisted as a terminal run status. Existing M5 databases are migrated to accept `terminated` and `failed` outcomes.
- **Safety boundary:** API submissions use the same validated `TaskRequest` and local fixture constraints as the CLI. This is an unauthenticated, single-process development API and must not be exposed on a network.
- **Verification:** `.\.venv\Scripts\python.exe -m pytest -vv` — 33 passed, covering invalid task rejection, observation/result SSE, pause/resume, termination persistence, legacy database migration, and mocked Groq configuration/request behavior. `.\.venv\Scripts\python.exe -m pip check` — no broken requirements.
- **Next:** M7 — integrations that produce traceable artifacts for approved downstream systems.

## M7 — Integrations & connected frontend

- **Status:** Implemented and verified; walkthrough pending
- **Implementation:**
  - Added `integrations/adapters.py` with `DownstreamAdapter` and `QuarantineExporter`, packaging completed runs into hash-verified, content-addressed JSON payload and manifest bundles (`quarantine_status: "pending_validation"`) through `ArtifactManager` without platform-specific assumptions in the core.
  - Extended `SQLiteMemory` (`get_run`, `list_runs`, `list_procedures`, `get_artifact`) and `replay_procedure` (live SSE observations, steps, and safe-boundary pause/resume/terminate).
  - Expanded the FastAPI control plane (`api/main.py`) with `/api/*` routing alongside root endpoints, CORS for local Vite dev, `GET /tasks`, `POST /tasks/{id}/save-procedure`, `GET /procedures`, `POST /procedures/{name}/replay`, `GET /tasks/{id}/artifacts`, `POST /tasks/{id}/export`, `GET /artifacts/{id}`, and static serving of the built `web/dist` frontend at `/`.
  - Connected the React + Vite frontend (`web/`) to the full Control API (Vite `/api` proxy, live SSE observation & step stream, pause/resume/terminate controls, recent SQLite runs, verified procedure save & replay, M7 quarantine export & SHA-256 artifact inspector, plus Tavily web research mode).
- **Verification:** `.\.venv\Scripts\python.exe -m pytest -vv`, `npm.cmd run lint`, `npm.cmd run build`, and `.\.venv\Scripts\python.exe -m pip check` all pass.
