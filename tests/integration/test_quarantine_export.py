import json

import pytest
from fastapi.testclient import TestClient

from computer_agent.api.main import create_app


def test_quarantine_export_and_procedure_replay_api_flow(tmp_path) -> None:
    app = create_app(
        memory_path=tmp_path / "memory.sqlite3",
        artifact_root=tmp_path / "workspace",
    )
    with TestClient(app) as client:
        # Both /health and /api/health work so frontend & direct clients share one API.
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/health").json() == {"status": "ok"}

        # Submit a task via /api/tasks and wait for completion via SSE.
        submitted = client.post(
            "/api/tasks",
            json={"query": "electrician", "max_steps": 12},
        )
        assert submitted.status_code == 202
        task_id = submitted.json()["task_id"]

        with client.stream("GET", f"/api/tasks/{task_id}/events") as response:
            assert response.status_code == 200
            events = "".join(response.iter_text())
        assert "event: result" in events

        # Task appears in GET /api/tasks and is completed.
        listed = client.get("/api/tasks").json()["tasks"]
        assert any(item["task_id"] == task_id and item["status"] == "completed" for item in listed)

        # Save the completed run as a verified procedure and list it.
        saved_proc = client.post(
            f"/api/tasks/{task_id}/save-procedure",
            json={"name": "local-electrician-search"},
        )
        assert saved_proc.status_code == 201
        assert saved_proc.json()["name"] == "local-electrician-search"
        assert saved_proc.json()["action_count"] >= 3

        procedures = client.get("/api/procedures").json()["procedures"]
        assert any(proc["name"] == "local-electrician-search" for proc in procedures)

        # Duplicate procedure name returns 409 Conflict.
        duplicate = client.post(
            f"/api/tasks/{task_id}/save-procedure",
            json={"name": "local-electrician-search"},
        )
        assert duplicate.status_code == 409

        # Replay the saved procedure over the API and stream SSE to completion.
        replayed = client.post(
            "/api/procedures/local-electrician-search/replay",
            json={"query": "electrician"},
        )
        assert replayed.status_code == 202
        replay_id = replayed.json()["task_id"]
        with client.stream("GET", f"/api/tasks/{replay_id}/events") as response:
            assert response.status_code == 200
            replay_events = "".join(response.iter_text())
        assert "event: result" in replay_events
        assert client.get(f"/api/tasks/{replay_id}").json()["status"] == "completed"

        # M7 Quarantine export produces verified payload + manifest artifacts.
        exported = client.post(
            f"/api/tasks/{task_id}/export",
            json={"destination": "etl-quarantine"},
        )
        assert exported.status_code == 201
        export_body = exported.json()
        assert export_body["quarantine_status"] == "pending_validation"
        assert export_body["destination"] == "etl-quarantine"
        assert export_body["record_count"] == 2

        payload_id = export_body["payload_artifact"]["artifact_id"]
        manifest_id = export_body["manifest_artifact"]["artifact_id"]

        artifacts = client.get(f"/api/tasks/{task_id}/artifacts").json()["artifacts"]
        artifact_ids = {item["artifact_id"] for item in artifacts}
        assert {payload_id, manifest_id}.issubset(artifact_ids)

        # Read & verify both artifacts through the API.
        verified_manifest = client.get(f"/api/artifacts/{manifest_id}")
        assert verified_manifest.status_code == 200
        manifest_data = verified_manifest.json()
        assert manifest_data["verified"] is True
        assert manifest_data["json"]["payload"]["sha256"] == export_body["payload_artifact"]["sha256"]

        verified_payload = client.get(f"/api/artifacts/{payload_id}")
        assert verified_payload.status_code == 200
        payload_json = json.loads(verified_payload.json()["content"])
        assert payload_json["quarantine_status"] == "pending_validation"
        assert len(payload_json["records"]) == 2


def test_quarantine_export_rejects_incomplete_runs_and_bad_destinations(tmp_path) -> None:
    app = create_app(
        memory_path=tmp_path / "memory.sqlite3",
        artifact_root=tmp_path / "workspace",
    )
    with TestClient(app) as client:
        submitted = client.post(
            "/api/tasks",
            json={"query": "electrician", "max_steps": 1},
        )
        assert submitted.status_code == 202
        task_id = submitted.json()["task_id"]
        with client.stream("GET", f"/api/tasks/{task_id}/events") as response:
            "".join(response.iter_text())

        # Incomplete (step_limit_reached) run cannot be exported to quarantine.
        rejected = client.post(f"/api/tasks/{task_id}/export")
        assert rejected.status_code == 400
        assert "completed" in rejected.json()["detail"].lower()

        # Invalid destination slug is rejected.
        bad_dest = client.post(
            f"/api/tasks/{task_id}/export",
            json={"destination": "../outside"},
        )
        assert bad_dest.status_code == 400


def test_built_frontend_is_served_at_root(tmp_path) -> None:
    app = create_app(
        memory_path=tmp_path / "memory.sqlite3",
        artifact_root=tmp_path / "workspace",
        serve_frontend=True,
    )
    with TestClient(app) as client:
        index = client.get("/")
        assert index.status_code == 200
        assert "Understory" in index.text
