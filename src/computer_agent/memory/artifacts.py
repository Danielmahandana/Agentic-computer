import hashlib
from pathlib import Path, PurePosixPath
from uuid import uuid4

from computer_agent.memory.store import ArtifactEntry, SQLiteMemory


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "workspace"


class ArtifactManager:
    def __init__(
        self,
        memory: SQLiteMemory,
        root: Path = DEFAULT_ARTIFACT_ROOT,
    ) -> None:
        self._memory = memory
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save_bytes(
        self,
        run_id: str,
        relative_path: str,
        content: bytes,
        media_type: str,
    ) -> ArtifactEntry:
        destination = self._resolve_path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination = self._resolve_path(relative_path)

        if destination.exists():
            if destination.read_bytes() != content:
                raise FileExistsError(
                    f"Artifact path {relative_path!r} already contains different data."
                )
        else:
            temporary_path = destination.with_name(
                f".{destination.name}.{uuid4().hex}.tmp"
            )
            try:
                temporary_path.write_bytes(content)
                temporary_path.replace(destination)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()

        entry = ArtifactEntry(
            artifact_id=str(uuid4()),
            run_id=run_id,
            relative_path=PurePosixPath(relative_path).as_posix(),
            media_type=media_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        self._memory.record_artifact(entry)
        return entry

    def read_verified(self, entry: ArtifactEntry) -> bytes:
        content = self._resolve_path(entry.relative_path).read_bytes()
        if len(content) != entry.size_bytes:
            raise ValueError("Artifact size no longer matches its saved metadata.")
        if hashlib.sha256(content).hexdigest() != entry.sha256:
            raise ValueError("Artifact hash no longer matches its saved metadata.")
        return content

    def _resolve_path(self, relative_path: str) -> Path:
        if "\\" in relative_path:
            raise ValueError("Artifact paths must use relative POSIX-style paths.")
        path = PurePosixPath(relative_path)
        if (
            path.is_absolute()
            or not path.parts
            or ".." in path.parts
            or any(part in {"", "."} for part in path.parts)
        ):
            raise ValueError("Artifact path must stay inside the artifact workspace.")

        destination = (self._root / Path(*path.parts)).resolve()
        if not destination.is_relative_to(self._root):
            raise ValueError("Artifact path resolves outside the artifact workspace.")
        return destination
