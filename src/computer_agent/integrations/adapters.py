from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Protocol

from computer_agent.memory.artifacts import ArtifactManager
from computer_agent.memory.store import ArtifactEntry, SQLiteMemory


SCHEMA_VERSION = "1.0"
DEFAULT_DESTINATION = "quarantine-gateway"
_DESTINATION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class QuarantineExportResult:
    run_id: str
    destination: str
    quarantine_status: str
    exported_at: str
    record_count: int
    payload_artifact: ArtifactEntry
    manifest_artifact: ArtifactEntry
    manifest: dict[str, object]


class DownstreamAdapter(Protocol):
    def export_run(
        self,
        run_id: str,
        destination: str = DEFAULT_DESTINATION,
    ) -> QuarantineExportResult: ...


class QuarantineExporter:
    """Packages completed runs into hash-verified quarantine bundles for downstream ETL."""

    def __init__(
        self,
        memory: SQLiteMemory,
        artifacts: ArtifactManager,
    ) -> None:
        self._memory = memory
        self._artifacts = artifacts

    def export_run(
        self,
        run_id: str,
        destination: str = DEFAULT_DESTINATION,
    ) -> QuarantineExportResult:
        clean_destination = destination.strip().lower()
        if not _DESTINATION_PATTERN.match(clean_destination):
            raise ValueError(
                "Destination must be 1-64 lowercase letters, digits, hyphens, or underscores."
            )

        summary = self._memory.get_run(run_id)
        if summary.status != "completed" or summary.result is None:
            raise ValueError(
                f"Only completed task runs can be exported to quarantine (got {summary.status!r})."
            )

        exported_at = datetime.now(timezone.utc).isoformat()
        result_data = summary.result
        records = result_data.get("records", [])
        pages_visited = result_data.get("pages_visited", [])
        steps = result_data.get("steps", [])

        payload_document: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "quarantine_status": "pending_validation",
            "destination": clean_destination,
            "run_id": run_id,
            "query": summary.request.query,
            "start_page": summary.request.start_page,
            "exported_at": exported_at,
            "record_count": len(records) if isinstance(records, list) else 0,
            "records": records,
            "provenance": {
                "source_pages": pages_visited,
                "step_count": len(steps) if isinstance(steps, list) else 0,
                "completion_reason": summary.reason,
                "run_created_at": summary.created_at,
                "run_updated_at": summary.updated_at,
            },
        }
        payload_bytes = json.dumps(payload_document, indent=2, sort_keys=True).encode("utf-8")
        payload_digest = hashlib.sha256(payload_bytes).hexdigest()[:12]
        payload_artifact = self._artifacts.save_bytes(
            run_id=run_id,
            relative_path=f"quarantine/{run_id}/records-{payload_digest}.json",
            content=payload_bytes,
            media_type="application/json",
        )
        self._artifacts.read_verified(payload_artifact)

        manifest_document: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "quarantine_status": "pending_validation",
            "destination": clean_destination,
            "run_id": run_id,
            "query": summary.request.query,
            "start_page": summary.request.start_page,
            "exported_at": exported_at,
            "record_count": payload_document["record_count"],
            "payload": {
                "artifact_id": payload_artifact.artifact_id,
                "relative_path": payload_artifact.relative_path,
                "media_type": payload_artifact.media_type,
                "size_bytes": payload_artifact.size_bytes,
                "sha256": payload_artifact.sha256,
            },
            "provenance": payload_document["provenance"],
        }
        manifest_bytes = json.dumps(manifest_document, indent=2, sort_keys=True).encode("utf-8")
        manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()[:12]
        manifest_artifact = self._artifacts.save_bytes(
            run_id=run_id,
            relative_path=f"quarantine/{run_id}/manifest-{manifest_digest}.json",
            content=manifest_bytes,
            media_type="application/json",
        )
        self._artifacts.read_verified(manifest_artifact)

        return QuarantineExportResult(
            run_id=run_id,
            destination=clean_destination,
            quarantine_status="pending_validation",
            exported_at=exported_at,
            record_count=int(payload_document["record_count"]),
            payload_artifact=payload_artifact,
            manifest_artifact=manifest_artifact,
            manifest=manifest_document,
        )
