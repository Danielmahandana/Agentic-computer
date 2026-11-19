# **Building a General-Purpose Computer-Use Agent**

I would change the direction of the project quite significantly.

Instead of building a watcher specifically for the merSETA data platform, we should build a **standalone computer-use system** that can operate a browser, interact with websites, navigate applications, manage files, execute permitted tasks, and observe its own progress.

The merSETA platform would become one of its first integrations, rather than the reason the computer exists.

The goal is to build something inspired by the computer-use capabilities of Manus, but with our own architecture, execution model, security boundaries, and extensibility.

## **1. What we are actually building**

The system should accept a task expressed in natural language, such as:

> Open a public employment website, find electrician vacancies in Gauteng, navigate through the results, collect the job descriptions, and save the information as a structured dataset.

It should then be capable of planning the task, operating a real browser, observing the results of its actions, recovering from failures, and producing a verifiable output.

Unlike our previous watcher design, **the user does not need to provide a predefined navigation plan for every website**.

That is the central engineering challenge.

We need a system that can translate a high-level objective into a sequence of safe, observable computer actions.

## **2. Proposed capabilities**

| Capability           | Initial implementation                       | Later expansion                 |
| -------------------- | -------------------------------------------- | ------------------------------- |
| Browser control      | Playwright + Chromium                        | Multiple browser engines        |
| Computer observation | DOM, accessibility tree, screenshots         | Visual grounding                |
| Task planning        | Rules and structured action planning         | Local language models           |
| Action execution     | Click, type, scroll, navigate, download      | Desktop applications            |
| Memory               | Task history, page observations, checkpoints | Reusable learned procedures     |
| File operations      | Isolated workspace and artifact management   | Document processing             |
| Code execution       | Restricted Python tools                      | General-purpose compute sandbox |
| Human supervision    | Approve, pause, resume, stop                 | Interactive takeover            |
| Extensibility        | Python tool interfaces                       | External platform integrations  |

One important distinction: Playwright gives us browser control, not unrestricted control of an entire operating system. We should first build a reliable browser computer, then introduce desktop control in an isolated virtual machine.

## **3. The core architecture**

I would separate the system into six independently testable components.

**Computer Runtime:** Creates and manages isolated browser sessions. It exposes a limited set of computer actions rather than allowing the planning system to execute arbitrary browser code.

**Observation Engine:** Inspects the current browser state using accessible elements, DOM structure, URLs, screenshots, and action results. It produces a compact description of what the computer can currently see and do.

**Planning Engine:** Converts a user objective into smaller steps, chooses an appropriate action, and revises the plan when observations differ from expectations.

**Execution Supervisor:** Validates actions against permissions, destination restrictions, timeouts, resource limits, and approval requirements before execution.

**Memory and Artifacts:** Persists task history, observations, screenshots, downloads, checkpoints, and successful reusable procedures.

**Agent Control Plane:** Provides task submission, execution status, live monitoring, interruption, and integration APIs.

The key is to keep the planning engine separate from the computer runtime. That allows us to experiment with different intelligence approaches without rebuilding browser automation.

## **4. How we make it intelligent without expensive AI**

A genuinely general-purpose computer agent needs some way to interpret unfamiliar pages and decide what to do next. Purely hard-coded rules will not achieve Manus-like flexibility.

I propose a **hybrid intelligence architecture** with three levels.

| Level                       | Mechanism                                              | Responsibility                                        |
| --------------------------- | ------------------------------------------------------ | ----------------------------------------------------- |
| 1. Deterministic            | Python rules and state machines                        | Execute known workflows reliably                      |
| 2. Structural reasoning     | DOM inspection, accessibility roles, heuristics        | Discover controls and navigate familiar page patterns |
| 3. Model-assisted reasoning | Optional small local vision-language or language model | Interpret unfamiliar interfaces and propose actions   |

We should use model inference selectively, not for every click. Once the agent discovers a successful procedure, it can save that procedure and replay it deterministically.

That creates a useful distinction between **exploration mode**, where the system figures out how to complete a task, and **execution mode**, where it repeats an established procedure.

It won't eliminate the need for intelligence, but it can substantially reduce repeated inference.

## **5. Project structure**

I would create a standalone Python repository:

```

computer-agent/
├── README.md
├── pyproject.toml
├── .env.example
├── Dockerfile
│
├── src/computer_agent/
│   ├── main.py
│   ├── config.py
│   │
│   ├── computer/
│   │   ├── browser.py
│   │   ├── session.py
│   │   ├── actions.py
│   │   ├── observations.py
│   │   └── screenshots.py
│   │
│   ├── agent/
│   │   ├── runtime.py
│   │   ├── planner.py
│   │   ├── action_selector.py
│   │   ├── verifier.py
│   │   └── task_state.py
│   │
│   ├── intelligence/
│   │   ├── dom_analyzer.py
│   │   ├── page_classifier.py
│   │   ├── element_grounding.py
│   │   └── model_provider.py
│   │
│   ├── memory/
│   │   ├── task_store.py
│   │   ├── procedure_store.py
│   │   └── checkpoints.py
│   │
│   ├── sandbox/
│   │   ├── workspace.py
│   │   ├── permissions.py
│   │   ├── network_policy.py
│   │   └── artifact_manager.py
│   │
│   ├── tools/
│   │   ├── registry.py
│   │   ├── browser_tools.py
│   │   ├── filesystem_tools.py
│   │   └── extraction_tools.py
│   │
│   ├── api/
│   │   ├── app.py
│   │   ├── tasks.py
│   │   └── events.py
│   │
│   └── integrations/
│       └── adapters.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── browser/
│
└── examples/
    └── tasks/

```

The important design decision is that `integrations/` contains no merSETA-specific assumptions. Labour intelligence becomes an adapter or separate application that submits tasks and receives artifacts.

## **6. The agent execution loop**

The heart of the project is the agent runtime.

AGENT EXECUTION CYCLE

1

**Understand**

Interpret the objective, constraints and completion criteria

2

**Observe**

Read the current browser state and available actions

3

**Decide**

Select one permitted action based on the objective and observations

4

**Execute**

Perform the action through the computer runtime

5

**Verify**

Check whether the action succeeded and changed the state as expected

6

**Continue or stop**

Repeat, recover, request approval or produce the final artifact

Every action should produce an execution record containing the action, observation, result, timing, and relevant artifact references.

The supervisor must enforce a maximum number of steps, task timeout, allowed destinations, and explicit approval for sensitive actions.

A task should not be marked successful simply because the final browser action completed. Its output must satisfy defined completion criteria.

## **7. How it integrates with merSETA**

Once the computer-use runtime works independently, we can introduce specialized tools.

For the labour intelligence platform, these could include:

- **Source discovery:** Find relevant public data repositories and documents.
- **Web acquisition:** Navigate approved job portals and collect vacancies.
- **Document collection:** Retrieve occupational reports, qualification frameworks, and industry publications.
- **Research assistance:** Compare published information across permitted sources.
- **ETL integration:** Submit downloaded artifacts to the quarantine gateway, then trigger the established data processing pipeline after clearance.
- **Monitoring:** Revisit sources periodically and report changes.

The computer agent should never directly write unverified data into authoritative datasets. Its output enters the same security, validation, provenance, and governance processes as every other source.

## **8. Development milestones**

M1

**Build the Computer**

Create a Chromium session, expose click/type/scroll/navigation tools, capture screenshots, and close sessions safely.

**Completion test:** A Python program can control a local test website through a restricted action API.

M2

**Build the Observation Engine**

Extract interactive elements, accessible labels, page text, URLs and screenshots into a structured observation.

**Completion test:** The runtime can identify actionable elements without hard-coded coordinates.

M3

**Build the Agent Loop**

Introduce task state, action selection, execution verification, retries and stopping conditions.

**Completion test:** The agent can complete a simple multi-page task without a manually written sequence.

M4

**Introduce Reasoning**

Add a replaceable model provider and compare heuristic planning against a small local model.

**Completion test:** The agent can navigate an unfamiliar test website and explain its actions.

M5

**Add Memory and Sandbox**

Persist checkpoints, reusable procedures, artifacts, approval requests and execution history.

**Completion test:** The agent can recover from interruption and replay a verified procedure.

M6

**Build the Control Interface**

Expose FastAPI task endpoints and live browser observation through WebSocket or server-sent events.

**Completion test:** A user can submit, inspect, pause and terminate a task.

M7

**Integrate with Data Platforms**

Create connectors for quarantine ingestion, Kafka events, Airflow workflows and external applications.

**Completion test:** The computer can produce a traceable artifact that enters the secure ETL pipeline.

## **9. Where we should begin**

Our first milestone should be a **working browser computer**, not an AI agent.

For the first implementation, I would use Python 3.12+, Playwright, Chromium, Pydantic, and pytest.

The first program should:

1. Launch Chromium in a dedicated browser context.
2. Open a local test website.
3. Inspect its interactive elements.
4. Execute a click or form interaction.
5. Capture the resulting observation and screenshot.
6. Save an execution trace.
7. Close the session cleanly.

We should build this ourselves, understanding each component rather than generating the entire repository at once.

After that, we can tackle the genuinely difficult problem: **how a computer decides what to do when it has never seen a website before**.

That is the engineering challenge that will distinguish this project from an ordinary Playwright automation framework.