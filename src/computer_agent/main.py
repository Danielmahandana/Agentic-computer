import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from computer_agent.computer.session import open_demo_computer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts"


async def run_demo(output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    async with open_demo_computer() as computer:
        before = await computer.observe()
        await computer.fill_textbox("Search query", "Python engineer")
        await computer.click_button("Search")
        after = await computer.observe()
        screenshot = await computer.screenshot()
        trace = computer.trace

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "observations.json").write_text(
        json.dumps(
            {"before": asdict(before), "after": asdict(after)},
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "screenshot.png").write_bytes(screenshot)
    (output_dir / "trace.json").write_text(
        json.dumps([asdict(record) for record in trace], indent=2),
        encoding="utf-8",
    )

    print(after.status_text)


if __name__ == "__main__":
    asyncio.run(run_demo())
