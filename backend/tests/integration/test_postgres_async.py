"""Async -> status round trip on a real Postgres (run manually).

    docker run --rm -p 5432:5432 -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=eye postgres:16
    TEST_POSTGRES_URL=postgresql://postgres:pw@localhost:5432/eye \
        EYE_MODE=demo venv/bin/python -m pytest -m postgres tests/integration/test_postgres_async.py
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.contract._appkit import build_client

TEST_POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not TEST_POSTGRES_URL, reason="TEST_POSTGRES_URL is not set"),
]


@pytest.fixture
def pg_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Any]:
    yield from build_client(
        monkeypatch, tmp_path, DATABASE_URL=str(TEST_POSTGRES_URL)
    )


def test_async_then_status_round_trip(pg_client: Any, refer_jpeg_bytes: bytes) -> None:
    queued = pg_client.post(
        "/api/v1/predict/async",
        files={"file": ("eye.jpg", refer_jpeg_bytes, "image/jpeg")},
        data={"patient_id": "P-PG", "eye": "right"},
    )
    assert queued.status_code == 200, queued.text
    task = queued.json()
    assert task["status"] == "PROCESSING"
    assert task["task_id"].startswith("replay:")

    status = pg_client.get(f"/api/v1/predict/status/{task['task_id']}")
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["status"] == "SUCCESS"
    result = body["result"]
    assert task["task_id"] == f"replay:{result['exam_id']}"

    stored = pg_client.get(f"/api/v1/exams/{result['exam_id']}").json()
    for key in ("exam_id", "decision", "probability", "icdr_grade", "quality"):
        assert result[key] == stored[key]
    assert result["decision"] == "REFER"
