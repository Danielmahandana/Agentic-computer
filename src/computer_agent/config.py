import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_project_env(allowed_names: set[str]) -> dict[str, str]:
    env_file = PROJECT_ROOT / ".env"
    values: dict[str, str] = {}
    if not env_file.is_file():
        return values

    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        normalized_name = re.sub(r"\s+", "_", name.strip()).upper()
        if not separator or normalized_name not in allowed_names:
            continue

        candidate = value.strip()
        if len(candidate) >= 2 and candidate[0] == candidate[-1] in {"'", '"'}:
            candidate = candidate[1:-1]
        else:
            candidate = candidate.split("#", 1)[0].strip()
        if candidate:
            values[normalized_name] = candidate
    return values
