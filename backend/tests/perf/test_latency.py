"""Gate G5 — the perf guard (Agent C owns it, spec §5-C / §6).

Two budgets, both from the phone's point of view:

* mock p95 < 300 ms — the mock path is the demo path, and it is also the floor
  the torch path is measured against later;
* 4 concurrent predicts each finish < 25 s — the client's timeout budget is
  30 s, and `INFERENCE_CONCURRENCY` (default 2) deliberately queues requests
  rather than thrashing a single-worker container. The guard is that queueing
  stays inside the budget.

Excluded from the default suite by the `perf` marker: it is a timing test, and
timing tests do not belong in a correctness gate.

Every request uses a distinct patient code on purpose — identical bytes with
the same patient and eye would be replayed by C14 dedup, and the measurement
would silently become a measurement of the dedup lookup.
"""

from __future__ import annotations

import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from tests.contract import _shim

_shim.install()

pytestmark = pytest.mark.perf

P95_BUDGET_MS = 300.0
CONCURRENT_BUDGET_S = 25.0
SAMPLES = 20
WARMUP = 3


def _predict(client: Any, raw: bytes, patient_id: str) -> Any:
    return client.post(
        "/api/v1/predict",
        files={"file": ("eye.jpg", raw, "image/jpeg")},
        data={"patient_id": patient_id, "eye": "right"},
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


def test_mock_predict_p95_under_300ms(client: Any, refer_jpeg_bytes: bytes) -> None:
    for i in range(WARMUP):
        assert _predict(client, refer_jpeg_bytes, f"W-{i:04d}").status_code == 200

    timings: list[float] = []
    for i in range(SAMPLES):
        started = time.perf_counter()
        response = _predict(client, refer_jpeg_bytes, f"P-{i:04d}")
        timings.append((time.perf_counter() - started) * 1000.0)
        assert response.status_code == 200, response.text

    p95 = _percentile(timings, 0.95)
    assert p95 < P95_BUDGET_MS, (
        f"p95={p95:.1f}ms median={statistics.median(timings):.1f}ms "
        f"max={max(timings):.1f}ms budget={P95_BUDGET_MS}ms"
    )


def test_four_concurrent_predicts_each_finish_under_25s(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    assert _predict(client, refer_jpeg_bytes, "W-0000").status_code == 200

    def one(index: int) -> tuple[int, float]:
        started = time.perf_counter()
        response = _predict(client, refer_jpeg_bytes, f"C-{index:04d}")
        return response.status_code, time.perf_counter() - started

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, range(4)))

    for status, elapsed in results:
        assert status == 200
        assert elapsed < CONCURRENT_BUDGET_S, f"{elapsed:.2f}s over budget"


def test_the_semaphore_is_released_under_concurrency(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    """A leaked permit shows up as a hang, not an error, so it is checked by
    running more requests than the semaphore has permits and requiring the
    last one to still be fast."""
    from app.config import get_settings

    permits = get_settings().inference_concurrency

    def one(index: int) -> int:
        return _predict(client, refer_jpeg_bytes, f"S-{index:04d}").status_code

    with ThreadPoolExecutor(max_workers=permits * 2) as pool:
        assert list(pool.map(one, range(permits * 3))) == [200] * (permits * 3)

    started = time.perf_counter()
    assert _predict(client, refer_jpeg_bytes, "S-9999").status_code == 200
    assert (time.perf_counter() - started) < 5.0, "a permit was never returned"


def test_ungradable_path_is_not_slower_than_the_graded_one(
    client: Any, blurry_jpeg_bytes: bytes
) -> None:
    """It skips inference and the heatmap, so it must be cheaper, not dearer."""
    for i in range(WARMUP):
        assert _predict(client, blurry_jpeg_bytes, f"WU-{i:04d}").status_code == 200

    timings = []
    for i in range(SAMPLES):
        started = time.perf_counter()
        assert _predict(client, blurry_jpeg_bytes, f"U-{i:04d}").status_code == 200
        timings.append((time.perf_counter() - started) * 1000.0)

    assert _percentile(timings, 0.95) < P95_BUDGET_MS
