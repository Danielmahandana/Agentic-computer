import asyncio
import json
from pathlib import Path

from computer_agent.main import run_demo


def test_local_browser_computer(tmp_path: Path) -> None:
    asyncio.run(run_demo(tmp_path))

    observations = json.loads(
        (tmp_path / "observations.json").read_text(encoding="utf-8")
    )
    before = observations["before"]
    after = observations["after"]

    assert before["url"].startswith("file:")
    assert before["title"] == "Computer Agent Practice Page"
    assert before["textbox_count"] == 2
    assert before["button_count"] == 3
    assert after["status_text"] == "Search complete: Python engineer"

    screenshot = (tmp_path / "screenshot.png").read_bytes()
    assert screenshot.startswith(b"\x89PNG\r\n\x1a\n")

    trace = json.loads((tmp_path / "trace.json").read_text(encoding="utf-8"))
    assert [record["action"] for record in trace] == [
        "navigate",
        "observe",
        "fill",
        "click",
        "observe",
        "screenshot",
    ]
    assert all(record["duration_ms"] >= 0 for record in trace)
