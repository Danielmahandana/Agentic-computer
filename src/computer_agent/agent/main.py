import argparse
import asyncio
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from computer_agent.agent.runtime import run_task
from computer_agent.agent.planner import HeuristicPlanner
from computer_agent.agent.runtime import replay_procedure, resume_task
from computer_agent.agent.task_state import TaskRequest
from computer_agent.intelligence.model_provider import GroqProvider, OllamaProvider
from computer_agent.memory.artifacts import ArtifactManager
from computer_agent.memory.store import SQLiteMemory


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "agent-task.json"
DEFAULT_MEMORY_DB = PROJECT_ROOT / "artifacts" / "memory.sqlite3"


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the bounded local demo-site computer agent."
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Text to search for in local demo records.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Maximum number of browser actions (1-20).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for the JSON task result.",
    )
    parser.add_argument(
        "--planner",
        choices=("site-rules", "heuristic", "ollama", "groq"),
        default="site-rules",
        help="Choose site rules, structural heuristics, local Ollama, or Groq.",
    )
    parser.add_argument(
        "--start-page",
        default=None,
        help="Relative page path inside fixtures/fixture_site.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name for --planner ollama or --planner groq.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Overall task time limit in seconds (maximum 60).",
    )
    parser.add_argument(
        "--memory-db",
        type=Path,
        default=DEFAULT_MEMORY_DB,
        help="SQLite database for runs, checkpoints, and procedures.",
    )
    resume_group = parser.add_mutually_exclusive_group()
    resume_group.add_argument(
        "--resume",
        metavar="RUN_ID",
        help="Resume a saved run from its last checkpoint.",
    )
    resume_group.add_argument(
        "--replay-procedure",
        metavar="NAME",
        help="Replay a previously verified procedure.",
    )
    parser.add_argument(
        "--save-procedure",
        metavar="NAME",
        help="Save a completed run as a verified procedure.",
    )
    arguments = parser.parse_args()
    memory = SQLiteMemory(arguments.memory_db)

    planner = None
    if arguments.planner == "heuristic":
        planner = HeuristicPlanner()
    elif arguments.planner == "ollama":
        planner = OllamaProvider(
            arguments.model or "qwen2.5-coder:3b",
            timeout_seconds=arguments.timeout,
        )
    elif arguments.planner == "groq":
        planner = GroqProvider(
            arguments.model,
            timeout_seconds=arguments.timeout,
        )

    if arguments.resume:
        result = await resume_task(
            arguments.resume,
            memory,
            planner=planner,
            max_steps=arguments.max_steps,
            timeout_seconds=arguments.timeout,
        )
    else:
        if not arguments.query:
            parser.error("A query is required unless --resume is specified.")
        if arguments.replay_procedure:
            procedure = memory.load_procedure(arguments.replay_procedure)
            start_page = arguments.start_page or procedure.start_page
            result = await replay_procedure(
                procedure,
                TaskRequest(
                    query=arguments.query,
                    max_steps=arguments.max_steps,
                    timeout_seconds=arguments.timeout,
                    start_page=start_page,
                ),
                memory=memory,
            )
        else:
            result = await run_task(
                TaskRequest(
                    query=arguments.query,
                    max_steps=arguments.max_steps,
                    timeout_seconds=arguments.timeout,
                    start_page=arguments.start_page or "index.html",
                ),
                planner=planner,
                memory=memory,
            )

    if arguments.save_procedure:
        if result.run_id is None:
            raise RuntimeError("The completed task was not saved to memory.")
        memory.save_verified_procedure(result.run_id, arguments.save_procedure)

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    result_json = json.dumps(asdict(result), indent=2)
    arguments.output.write_text(result_json, encoding="utf-8")
    if result.run_id is not None:
        result_hash = hashlib.sha256(result_json.encode("utf-8")).hexdigest()
        ArtifactManager(memory).save_bytes(
            result.run_id,
            f"runs/{result.run_id}/results/{result_hash}.json",
            result_json.encode("utf-8"),
            "application/json",
        )
    print(
        f"Task {result.status}: {len(result.records)} matching records "
        f"from {len(result.pages_visited)} visited pages."
    )
    print(f"Result saved to {arguments.output}")


if __name__ == "__main__":
    asyncio.run(main())
