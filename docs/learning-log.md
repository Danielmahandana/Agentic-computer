# Learning log

Record concepts you can explain and evidence you personally ran. Do not mark a tranche complete because code exists.

| Tranche | Status | What I can explain / evidence |
| --- | --- | --- |
| Foundation exercise | In progress (explanation deferred) | Learner-reported: `.\.venv\Scripts\python.exe -m pytest -vv tests/unit/test_labels.py` — 1 passed. |
| M1 — Browser computer | Implemented; explanation pending | Learner's local fixture/action module integrated; 2 tests passed and demo artifacts generated. Explain the component boundaries and cleanup lifecycle. |
| M2 — Observation engine | Implemented; explanation pending | 3 tests pass; local demo still runs. Explain how interactive roles/names are derived and the limits of the heuristic. |
| M3 — Agent loop | Implemented; explanation pending | Browser loop tests, max-step tests, navigation policy tests, and selector loop detection pass. Explain observe/select/execute/verify and why the agent is fixture-scoped. |
| M4 — Reasoning | Implemented and exercised; explanation pending | Heuristic and local Ollama planners completed the unfamiliar library fixture. An opt-in Groq planner now reads its credential from `.env`; mocked provider tests pass without making a network request. Explain the replaceable planner boundary, privacy implications, and why model proposals are validated. |
| M5 — Memory and sandbox foundations | Implemented and verified; explanation pending | 27 tests pass, including rollback of a failed final transaction. CLI resume, verified procedure save/replay, and artifact size/hash checks succeeded using a temporary SQLite database. Explain transaction boundaries, checkpoint recovery, artifact integrity, and why this is not yet an OS/network sandbox. |
| M6 — Control interface | Implemented; explanation pending | API tests cover task submission/inspection, live SSE observations and results, pause/resume at safe boundaries, termination, and database migration. Explain the task manager, cooperative controls, and SSE event flow. |
| M7 — Integrations | Not started | |

## Notes
