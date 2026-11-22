"""Phase 4: ``eval/run_claude_eval.py`` (MIGRATION_PLAN.md section 6, section 8). No network.

The script is loaded by path, fresh per test, after the ``app.*`` purge the other
unit tests rely on. The Claude client is always a fake.
"""

from __future__ import annotations

import asyncio
import datetime
import importlib.util
import io
import json
import math
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest
from PIL import Image

from tests.fakes import FakeAnthropic, make_assessment

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND / "eval" / "run_claude_eval.py"
MODNAME = "run_claude_eval"
JPEG_MAGIC = b"\xff\xd8\xff"


def _purge_app() -> None:
    for name in [n for n in sys.modules if n == "app" or n.startswith("app.")]:
        del sys.modules[name]


@pytest.fixture
def ev(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    for name in (
        "ANTHROPIC_API_KEY",
        "CLAUDE_MODEL",
        "CLAUDE_MAX_TOKENS",
        "PROMPT_VERSION",
        "UNCERTAIN_REFERS",
        "MAX_UPLOAD_MB",
        "QUALITY_BLUR_MIN_VAR",
    ):
        monkeypatch.delenv(name, raising=False)
    _purge_app()
    spec = importlib.util.spec_from_file_location(MODNAME, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODNAME] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(MODNAME, None)
        _purge_app()


def make_settings(**env: Any) -> Any:
    from app.config import Settings

    values: dict[str, Any] = {"EYE_MODE": "demo", "EYE_MODEL_SOURCE": "claude"}
    values.update(env)
    return Settings(**values)


class FakeEngine:
    """Duck-typed engine: ``await assess(raw)`` -> a ClaudePrediction-shaped dict."""

    def __init__(
        self,
        assessment: Any = None,
        *,
        delay: float = 0.0,
        fail_on: set[int] | None = None,
        error: type[Exception] = RuntimeError,
    ) -> None:
        self.assessment = assessment
        self.delay = delay
        self.fail_on = fail_on or set()
        self.error = error
        self.calls: list[bytes] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def assess(self, raw: bytes) -> dict[str, Any]:
        index = len(self.calls)
        self.calls.append(raw)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if index in self.fail_on:
                raise self.error("boom")
            return {
                "assessment": self.assessment or make_assessment(),
                "model_version": "fake/prompt-v1",
                "latency_ms": 12.5,
                "input_tokens": 1000,
                "output_tokens": 200,
            }
        finally:
            self.in_flight -= 1


def write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def run_eval(ev: ModuleType, items: list[Any], engine: Any, settings: Any, **kw: Any) -> list[Any]:
    return asyncio.run(ev.evaluate(items, engine, settings, **kw))


def fundus_item(ev: ModuleType, path: Path, grade: int = 0) -> Any:
    return ev.Item(path, "fundus", grade)


# --------------------------------------------------------------------------
# wilson_ci
# --------------------------------------------------------------------------
def test_wilson_known_example(ev: ModuleType) -> None:
    low, high = ev.wilson_ci(90, 100)
    assert low == pytest.approx(0.8256, abs=1e-3)
    assert high == pytest.approx(0.9448, abs=1e-3)


def test_wilson_zero_n_is_none(ev: ModuleType) -> None:
    assert ev.wilson_ci(0, 0) is None


def test_wilson_clipped_to_unit_interval(ev: ModuleType) -> None:
    assert ev.wilson_ci(0, 10)[0] == 0.0
    assert ev.wilson_ci(10, 10)[1] == 1.0


@pytest.mark.parametrize("k,n", [(1, 10), (5, 10), (9, 10), (37, 120)])
def test_wilson_brackets_the_proportion(ev: ModuleType, k: int, n: int) -> None:
    low, high = ev.wilson_ci(k, n)
    assert 0.0 <= low < k / n < high <= 1.0


# --------------------------------------------------------------------------
# read_labels
# --------------------------------------------------------------------------
def test_read_labels_happy_path(ev: ModuleType, tmp_path: Path) -> None:
    csv = tmp_path / "labels.csv"
    absolute = tmp_path / "elsewhere" / "b.png"
    csv.write_text(
        "split,note,patient_id,icdr_grade,image_path\n"
        f" test , x , p1 , 2 , imgs/a.jpg \n"
        f"train,y,p2,0,{absolute}\n",
        encoding="utf-8",
    )
    rows = ev.read_labels(csv)
    assert len(rows) == 2
    first, second = rows
    assert first.image_path == tmp_path / "imgs" / "a.jpg"
    assert (first.icdr_grade, first.patient_id, first.split) == (2, "p1", "test")
    assert second.image_path == absolute
    assert (second.icdr_grade, second.patient_id, second.split) == (0, "p2", "train")


@pytest.mark.parametrize("missing", ["image_path", "icdr_grade", "patient_id", "split"])
def test_read_labels_missing_column(ev: ModuleType, tmp_path: Path, missing: str) -> None:
    cols = [c for c in ("image_path", "icdr_grade", "patient_id", "split") if c != missing]
    csv = tmp_path / "labels.csv"
    csv.write_text(",".join(cols) + "\n" + ",".join("a" for _ in cols) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=missing):
        ev.read_labels(csv)


HEADER = "image_path,icdr_grade,patient_id,split\n"
GOOD = "a.jpg,0,pa,test\n"


@pytest.mark.parametrize(
    "bad_row",
    [
        "bad.jpg,5,pb,test",
        "bad.jpg,-1,pb,test",
        "bad.jpg,x,pb,test",
        "bad.jpg,2,,test",
        "bad.jpg,2,   ,test",
        "bad.jpg,2,pb,",
        "bad.jpg,2,pb,  ",
    ],
)
def test_read_labels_bad_row_names_line(ev: ModuleType, tmp_path: Path, bad_row: str) -> None:
    csv = tmp_path / "labels.csv"
    # header = line 1, the bad row is the 6th data row -> line 7
    csv.write_text(HEADER + GOOD * 5 + bad_row + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="7"):
        ev.read_labels(csv)


def test_read_labels_does_not_check_files_exist(ev: ModuleType, tmp_path: Path) -> None:
    csv = tmp_path / "labels.csv"
    csv.write_text(HEADER + "nope.jpg,1,p,test\n", encoding="utf-8")
    assert len(ev.read_labels(csv)) == 1


# --------------------------------------------------------------------------
# patients_across_splits, list_images
# --------------------------------------------------------------------------
def test_patients_across_splits(ev: ModuleType) -> None:
    def row(pid: str, split: str) -> Any:
        return ev.LabelRow(Path("x.jpg"), 0, pid, split)

    rows = [
        row("zed", "train"),
        row("zed", "test"),
        row("amy", "train"),
        row("amy", "val"),
        row("amy", "test"),
        row("bob", "test"),
        row("bob", "test"),
        row("cat", "train"),
    ]
    assert ev.patients_across_splits(rows) == ["amy", "zed"]
    assert ev.patients_across_splits([]) == []


def test_list_images(ev: ModuleType, tmp_path: Path) -> None:
    for name in ("b.JPG", "a.jpeg", "c.PNG", "d.png", "notes.txt", "e.gif", "noext"):
        (tmp_path / name).write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.jpg").write_bytes(b"x")
    (tmp_path / "dir.jpg").mkdir()
    found = ev.list_images(tmp_path)
    assert [p.name for p in found] == ["a.jpeg", "b.JPG", "c.PNG", "d.png"]


# --------------------------------------------------------------------------
# cost and token estimates
# --------------------------------------------------------------------------
def test_upper_bound_cost(ev: ModuleType) -> None:
    cost = ev.upper_bound_cost(2_000_000, 10, 4000, 2.0, 10.0)
    assert cost == pytest.approx(2_000_000 * 2.0 / 1e6 + 10 * 4000 * 10.0 / 1e6)
    assert ev.upper_bound_cost(0, 0, 4000, 2.0, 10.0) == 0.0


def _jpeg(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height))
    px = img.load()
    for x in range(0, width, 5):
        for y in range(0, height, 5):
            px[x, y] = ((x * 3) % 256, (y * 5) % 256, 90)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_estimate_input_tokens_covers_image_tokens(ev: ModuleType, refer_jpeg_bytes: bytes) -> None:
    from app.inference.claude_engine import prepare_jpeg

    w, h = Image.open(io.BytesIO(prepare_jpeg(refer_jpeg_bytes))).size
    est = ev.estimate_input_tokens(refer_jpeg_bytes, "x" * 300)
    assert est >= math.ceil(w * h / 750)
    assert est > math.ceil(w * h / 750)  # prompt, instruction and schema add more


def test_estimate_grows_with_system_prompt(ev: ModuleType, refer_jpeg_bytes: bytes) -> None:
    short = ev.estimate_input_tokens(refer_jpeg_bytes, "x" * 30)
    long = ev.estimate_input_tokens(refer_jpeg_bytes, "x" * 3000)
    assert long > short


def test_estimate_oversized_image_not_above_1568_version(ev: ModuleType) -> None:
    big = Image.open(io.BytesIO(_jpeg(3136, 2090))).convert("RGB")
    small = big.copy()
    small.thumbnail((1568, 1568), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format="JPEG", quality=90)
    est_big = ev.estimate_input_tokens(_jpeg(3136, 2090), "x" * 300)
    est_small = ev.estimate_input_tokens(buf.getvalue(), "x" * 300)
    assert est_big <= est_small + 2  # same prepared size, up to a rounding pixel


# --------------------------------------------------------------------------
# evaluate
# --------------------------------------------------------------------------
def test_evaluate_preserves_order_and_engine_gets_file_bytes(
    ev: ModuleType, tmp_path: Path, refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes
) -> None:
    a = write(tmp_path, "a.jpg", refer_jpeg_bytes)
    b = write(tmp_path, "b.jpg", norefer_jpeg_bytes)
    c = write(tmp_path, "c.jpg", refer_jpeg_bytes)
    engine = FakeEngine()
    items = [fundus_item(ev, p, g) for p, g in ((a, 4), (b, 0), (c, 2))]
    results = run_eval(ev, items, engine, make_settings())
    assert [r.image for r in results] == ["a.jpg", "b.jpg", "c.jpg"]
    assert [r.true_grade for r in results] == [4, 0, 2]
    assert sorted(engine.calls) == sorted([refer_jpeg_bytes, norefer_jpeg_bytes, refer_jpeg_bytes])
    assert all(r.called_claude and r.error is None and r.quality_ok for r in results)
    assert all(r.latency_ms == 12.5 and r.input_tokens == 1000 and r.output_tokens == 200 for r in results)
    assert all(r.image_type == "fundus" for r in results)


def test_evaluate_exact_bytes_single(ev: ModuleType, tmp_path: Path, refer_jpeg_bytes: bytes) -> None:
    engine = FakeEngine()
    run_eval(ev, [fundus_item(ev, write(tmp_path, "a.jpg", refer_jpeg_bytes))], engine, make_settings())
    assert engine.calls == [refer_jpeg_bytes]


@pytest.mark.parametrize("which", ["blurry", "dark"])
def test_evaluate_quality_gate_failure(
    ev: ModuleType, tmp_path: Path, blurry_jpeg_bytes: bytes, dark_jpeg_bytes: bytes, which: str
) -> None:
    data = blurry_jpeg_bytes if which == "blurry" else dark_jpeg_bytes
    engine = FakeEngine()
    (r,) = run_eval(ev, [fundus_item(ev, write(tmp_path, "q.jpg", data), 3)], engine, make_settings())
    assert r.decision == "UNGRADABLE"
    assert r.quality_ok is False
    assert r.called_claude is False
    assert r.error is None
    assert r.pred_grade is None
    assert r.input_tokens == 0 and r.output_tokens == 0
    assert engine.calls == []


def test_evaluate_invalid_image(ev: ModuleType, tmp_path: Path, text_file_bytes: bytes) -> None:
    engine = FakeEngine()
    (r,) = run_eval(ev, [fundus_item(ev, write(tmp_path, "t.jpg", text_file_bytes))], engine, make_settings())
    assert r.error == "invalid_image"
    assert r.called_claude is False
    assert r.decision is None
    assert engine.calls == []


def test_evaluate_too_large(ev: ModuleType, tmp_path: Path, refer_jpeg_bytes: bytes) -> None:
    big = JPEG_MAGIC + b"\x00" * (1024 * 1024 + 10)
    engine = FakeEngine()
    settings = make_settings(MAX_UPLOAD_MB=1)
    (r,) = run_eval(ev, [fundus_item(ev, write(tmp_path, "big.jpg", big))], engine, settings)
    assert r.error == "too_large"
    assert r.called_claude is False
    assert r.decision is None
    assert engine.calls == []


def test_evaluate_engine_exception_is_isolated(
    ev: ModuleType, tmp_path: Path, refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes
) -> None:
    paths = [
        write(tmp_path, "a.jpg", refer_jpeg_bytes),
        write(tmp_path, "b.jpg", norefer_jpeg_bytes),
        write(tmp_path, "c.jpg", refer_jpeg_bytes),
    ]
    engine = FakeEngine(fail_on={0}, error=TimeoutError)
    results = run_eval(ev, [fundus_item(ev, p) for p in paths], engine, make_settings(), concurrency=1)
    failed = [r for r in results if r.error]
    assert len(failed) == 1
    assert failed[0].error == "TimeoutError"
    assert failed[0].called_claude is True
    assert failed[0].decision is None
    assert failed[0].pred_grade is None
    assert failed[0].input_tokens == 0 and failed[0].output_tokens == 0
    ok = [r for r in results if not r.error]
    assert len(ok) == 2
    assert all(r.decision == "NO_REFER" for r in ok)
    assert len(engine.calls) == 3


def test_evaluate_non_fundus_assessment_is_ungradable(
    ev: ModuleType, tmp_path: Path, refer_jpeg_bytes: bytes
) -> None:
    engine = FakeEngine(make_assessment(image_type="other", gradable=False))
    item = ev.Item(write(tmp_path, "cat.jpg", refer_jpeg_bytes), "non_fundus", None)
    (r,) = run_eval(ev, [item], engine, make_settings())
    assert r.decision == "UNGRADABLE"
    assert r.image_type == "other"
    assert r.called_claude is True
    assert r.error is None
    assert r.pred_grade is None
    assert r.quality_ok is True
    assert r.kind == "non_fundus" and r.true_grade is None


def test_evaluate_referable_assessment(ev: ModuleType, tmp_path: Path, refer_jpeg_bytes: bytes) -> None:
    engine = FakeEngine(
        make_assessment(icdr_grade=3, referable_probability=0.95, lesions={"irma": "present"})
    )
    (r,) = run_eval(ev, [fundus_item(ev, write(tmp_path, "r.jpg", refer_jpeg_bytes), 3)], engine, make_settings())
    assert r.decision == "REFER"
    assert r.pred_grade == 3
    assert r.image_type == "fundus"


def test_evaluate_concurrency_cap(ev: ModuleType, tmp_path: Path, refer_jpeg_bytes: bytes) -> None:
    items = [fundus_item(ev, write(tmp_path, f"i{n}.jpg", refer_jpeg_bytes)) for n in range(6)]
    engine = FakeEngine(delay=0.004)
    results = run_eval(ev, items, engine, make_settings(), concurrency=2)
    assert len(results) == 6
    assert engine.max_in_flight == 2


def test_evaluate_deleted_file_is_an_error_not_a_crash(
    ev: ModuleType, tmp_path: Path, refer_jpeg_bytes: bytes
) -> None:
    gone = write(tmp_path, "gone.jpg", refer_jpeg_bytes)
    ok = write(tmp_path, "ok.jpg", refer_jpeg_bytes)
    items = [fundus_item(ev, gone), fundus_item(ev, ok)]
    gone.unlink()
    engine = FakeEngine()
    results = run_eval(ev, items, engine, make_settings())
    assert results[0].error == "FileNotFoundError"
    assert results[0].decision is None
    assert results[0].called_claude is False
    assert results[1].error is None and results[1].decision == "NO_REFER"
    assert len(engine.calls) == 1


def test_evaluate_decision_exception_is_isolated(
    ev: ModuleType, tmp_path: Path, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.inference.decision as decision_mod

    real = decision_mod.decide_from_assessment
    seen = {"n": 0}

    def flaky(*args: Any, **kwargs: Any) -> Any:
        seen["n"] += 1
        if seen["n"] == 1:
            raise ZeroDivisionError("bad")
        return real(*args, **kwargs)

    monkeypatch.setattr("app.inference.decision.decide_from_assessment", flaky)
    items = [fundus_item(ev, write(tmp_path, f"i{n}.jpg", refer_jpeg_bytes)) for n in range(3)]
    engine = FakeEngine()
    results = run_eval(ev, items, engine, make_settings(), concurrency=1)
    assert results[0].error == "ZeroDivisionError"
    assert results[0].called_claude is True
    assert results[0].decision is None
    assert [r.error for r in results[1:]] == [None, None]
    assert [r.decision for r in results[1:]] == ["NO_REFER", "NO_REFER"]


def test_evaluate_on_result_called_once_per_item(
    ev: ModuleType, tmp_path: Path, refer_jpeg_bytes: bytes, blurry_jpeg_bytes: bytes, text_file_bytes: bytes
) -> None:
    items = [
        fundus_item(ev, write(tmp_path, "a.jpg", refer_jpeg_bytes)),
        fundus_item(ev, write(tmp_path, "b.jpg", blurry_jpeg_bytes)),
        fundus_item(ev, write(tmp_path, "c.jpg", text_file_bytes)),
        fundus_item(ev, write(tmp_path, "d.jpg", refer_jpeg_bytes)),
    ]
    got: list[Any] = []
    results = run_eval(ev, items, FakeEngine(), make_settings(), on_result=got.append)
    assert len(got) == len(items)
    assert sorted(id(r) for r in got) == sorted(id(r) for r in results)
    assert sorted(r.image for r in got) == ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]


# --------------------------------------------------------------------------
# summarize
# --------------------------------------------------------------------------
PRICE_IN, PRICE_OUT = 2.0, 10.0


def res(ev: ModuleType, image: str, **kw: Any) -> Any:
    fields: dict[str, Any] = {
        "image": image,
        "kind": "fundus",
        "true_grade": 0,
        "decision": "NO_REFER",
        "pred_grade": 0,
        "image_type": "fundus",
        "quality_ok": True,
        "called_claude": True,
        "latency_ms": 100.0,
        "input_tokens": 1000,
        "output_tokens": 200,
        "error": None,
    }
    fields.update(kw)
    return ev.ImageResult(**fields)


def unanswered(**kw: Any) -> dict[str, Any]:
    base = {
        "called_claude": False,
        "latency_ms": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "image_type": None,
    }
    base.update(kw)
    return base


@pytest.fixture
def mixed(ev: ModuleType) -> list[Any]:
    return [
        res(ev, "f1.jpg", true_grade=0, decision="NO_REFER", pred_grade=0, latency_ms=100.0, input_tokens=1000, output_tokens=100),
        res(ev, "f2.jpg", true_grade=1, decision="REFER", pred_grade=2, latency_ms=200.0, input_tokens=1100, output_tokens=150),
        res(ev, "f3.jpg", true_grade=2, decision="REFER", pred_grade=2, latency_ms=300.0, input_tokens=1200, output_tokens=200),
        res(ev, "f4.jpg", true_grade=3, decision="REFER", pred_grade=3, latency_ms=400.0, input_tokens=1300, output_tokens=250),
        res(ev, "f5.jpg", true_grade=4, decision="NO_REFER", pred_grade=1, latency_ms=500.0, input_tokens=1400, output_tokens=300),
        res(ev, "f6.jpg", true_grade=2, decision="UNGRADABLE", pred_grade=None, latency_ms=600.0, input_tokens=1500, output_tokens=350),
        res(ev, "f7.jpg", true_grade=0, decision="UNGRADABLE", pred_grade=None, quality_ok=False, **unanswered()),
        res(ev, "f8.jpg", true_grade=3, decision=None, pred_grade=None, error="TimeoutError", called_claude=True, latency_ms=None, input_tokens=0, output_tokens=0, image_type=None),
        res(ev, "n1.jpg", kind="non_fundus", true_grade=None, decision="UNGRADABLE", pred_grade=None, image_type="other", latency_ms=700.0, input_tokens=1600, output_tokens=400),
        res(ev, "n2.jpg", kind="non_fundus", true_grade=None, decision="REFER", pred_grade=2, latency_ms=800.0, input_tokens=1700, output_tokens=450),
        res(ev, "n3.jpg", kind="non_fundus", true_grade=None, decision=None, pred_grade=None, error="invalid_image", quality_ok=None, **unanswered()),
    ]


def test_summarize_confusion_and_rates(ev: ModuleType, mixed: list[Any]) -> None:
    s = ev.summarize(mixed, PRICE_IN, PRICE_OUT)
    assert s["n_images"] == 11
    assert s["n_errors"] == 2
    assert s["errors"] == {"TimeoutError": 1, "invalid_image": 1}
    assert s["n_referable"] == 4  # f3, f4, f5, f6; the errored f8 is excluded
    assert s["n_non_referable"] == 3  # f1, f2, f7
    assert (s["tp"], s["fn"], s["fp"], s["tn"]) == (2, 1, 1, 1)
    assert s["sensitivity"] == pytest.approx(2 / 3)
    assert s["specificity"] == pytest.approx(1 / 2)
    assert s["sensitivity_ci"] == pytest.approx(list(ev.wilson_ci(2, 3)))
    assert s["specificity_ci"] == pytest.approx(list(ev.wilson_ci(1, 2)))
    assert isinstance(s["sensitivity_ci"], list)
    assert s["ungradable"] == 2
    assert s["ungradable_rate"] == pytest.approx(2 / 7)
    assert s["ungradable_rate_referable"] == pytest.approx(1 / 4)
    assert s["ungradable_rate_non_referable"] == pytest.approx(1 / 3)


def test_summarize_incl_ungradable(ev: ModuleType, mixed: list[Any]) -> None:
    s = ev.summarize(mixed, PRICE_IN, PRICE_OUT)
    # tp=2 of n_referable=4 (f6 is UNGRADABLE); tn=1 of n_non_referable=3 (f7 UNGRADABLE)
    assert s["sensitivity_incl_ungradable"] == pytest.approx(2 / 4)
    assert s["specificity_incl_ungradable"] == pytest.approx(1 / 3)
    assert s["sensitivity_incl_ungradable_ci"] == pytest.approx(list(ev.wilson_ci(2, 4)))
    assert s["specificity_incl_ungradable_ci"] == pytest.approx(list(ev.wilson_ci(1, 3)))
    assert isinstance(s["sensitivity_incl_ungradable_ci"], list)
    # the plain numbers are unchanged
    assert s["sensitivity"] == pytest.approx(2 / 3)
    assert s["specificity"] == pytest.approx(1 / 2)


def test_summarize_grade_confusion(ev: ModuleType, mixed: list[Any]) -> None:
    s = ev.summarize(mixed, PRICE_IN, PRICE_OUT)
    expected = [[0] * 5 for _ in range(5)]
    expected[0][0] = 1
    expected[1][2] = 1
    expected[2][2] = 1
    expected[3][3] = 1
    expected[4][1] = 1
    assert s["grade_confusion"] == expected


def test_summarize_decision_by_true_grade(ev: ModuleType, mixed: list[Any]) -> None:
    s = ev.summarize(mixed, PRICE_IN, PRICE_OUT)
    table = s["decision_by_true_grade"]
    assert set(table) == {"0", "1", "2", "3", "4"}
    assert all(set(v) == {"REFER", "NO_REFER", "UNGRADABLE"} for v in table.values())
    assert table["0"] == {"REFER": 0, "NO_REFER": 1, "UNGRADABLE": 1}
    assert table["1"] == {"REFER": 1, "NO_REFER": 0, "UNGRADABLE": 0}
    assert table["2"] == {"REFER": 1, "NO_REFER": 0, "UNGRADABLE": 1}
    assert table["3"] == {"REFER": 1, "NO_REFER": 0, "UNGRADABLE": 0}
    assert table["4"] == {"REFER": 0, "NO_REFER": 1, "UNGRADABLE": 0}


def test_summarize_non_fundus(ev: ModuleType, mixed: list[Any]) -> None:
    s = ev.summarize(mixed, PRICE_IN, PRICE_OUT)
    assert s["non_fundus_n"] == 2
    assert s["non_fundus_rejected"] == 1
    assert s["non_fundus_rejection_rate"] == pytest.approx(0.5)
    assert s["non_fundus_not_rejected"] == ["n2.jpg"]


def test_summarize_latency_tokens_cost(ev: ModuleType, mixed: list[Any]) -> None:
    s = ev.summarize(mixed, PRICE_IN, PRICE_OUT)
    lat = [r.latency_ms for r in mixed if r.latency_ms is not None]
    assert s["latency_p50_ms"] == pytest.approx(float(np.percentile(lat, 50)))
    assert s["latency_p95_ms"] == pytest.approx(float(np.percentile(lat, 95)))
    answered = [r for r in mixed if r.called_claude and r.error is None]
    assert len(answered) == 8
    assert s["claude_calls"] == 9  # the errored call counts
    assert s["mean_input_tokens"] == pytest.approx(sum(r.input_tokens for r in answered) / 8)
    assert s["mean_output_tokens"] == pytest.approx(sum(r.output_tokens for r in answered) / 8)
    total = (
        sum(r.input_tokens for r in mixed) * PRICE_IN / 1e6
        + sum(r.output_tokens for r in mixed) * PRICE_OUT / 1e6
    )
    assert s["cost_total_usd"] == pytest.approx(total)
    assert s["cost_per_scan_usd"] == pytest.approx(total / 8)


def test_summarize_is_json_serialisable(ev: ModuleType, mixed: list[Any]) -> None:
    s = ev.summarize(mixed, PRICE_IN, PRICE_OUT)
    assert json.loads(json.dumps(s))["tp"] == 2


def test_summarize_empty_has_none_for_zero_denominators(ev: ModuleType) -> None:
    s = ev.summarize([], PRICE_IN, PRICE_OUT)
    for key in (
        "sensitivity",
        "sensitivity_ci",
        "specificity",
        "specificity_ci",
        "ungradable_rate",
        "ungradable_rate_referable",
        "ungradable_rate_non_referable",
        "non_fundus_rejection_rate",
        "latency_p50_ms",
        "latency_p95_ms",
        "mean_input_tokens",
        "mean_output_tokens",
        "cost_per_scan_usd",
        "sensitivity_incl_ungradable",
        "sensitivity_incl_ungradable_ci",
        "specificity_incl_ungradable",
        "specificity_incl_ungradable_ci",
    ):
        assert key in s and s[key] is None, key
    assert s["n_images"] == 0 and s["claude_calls"] == 0
    assert s["cost_total_usd"] == 0
    assert s["grade_confusion"] == [[0] * 5 for _ in range(5)]
    json.dumps(s)


def test_summarize_all_ungradable_has_no_sensitivity(ev: ModuleType) -> None:
    rs = [res(ev, "a.jpg", true_grade=3, decision="UNGRADABLE", pred_grade=None)]
    s = ev.summarize(rs, PRICE_IN, PRICE_OUT)
    assert (s["tp"], s["fn"], s["fp"], s["tn"]) == (0, 0, 0, 0)
    assert s["sensitivity"] is None and s["specificity"] is None
    assert s["ungradable_rate_referable"] == 1.0
    assert s["ungradable_rate_non_referable"] is None
    assert s["sensitivity_incl_ungradable"] == 0.0
    assert s["sensitivity_incl_ungradable_ci"] == pytest.approx(list(ev.wilson_ci(0, 1)))
    assert s["specificity_incl_ungradable"] is None
    assert s["specificity_incl_ungradable_ci"] is None


# --------------------------------------------------------------------------
# pass_bar
# --------------------------------------------------------------------------
def good_summary() -> dict[str, Any]:
    return {
        "tp": 90,
        "fn": 10,
        "tn": 80,
        "fp": 20,
        "n_referable": 100,
        "n_non_referable": 100,
        "sensitivity": 0.90,
        "specificity": 0.80,
        "non_fundus_n": 10,
        "non_fundus_rejection_rate": 1.0,
        "n_errors": 0,
    }


CRITERIA = (
    "referable_scored>=100",
    "non_referable_scored>=100",
    "sensitivity>=0.90",
    "specificity>=0.80",
    "non_fundus_all_ungradable",
    "no_errors",
    "held_out_split",
)


def test_pass_bar_all_pass_at_boundaries(ev: ModuleType) -> None:
    bar = ev.pass_bar(good_summary(), "test")
    assert set(bar["criteria"]) == set(CRITERIA)
    assert all(v is True for v in bar["criteria"].values())
    assert bar["passed"] is True


@pytest.mark.parametrize(
    "change,criterion",
    [
        ({"tp": 59}, "referable_scored>=100"),
        ({"fn": 9}, "referable_scored>=100"),
        ({"tn": 79}, "non_referable_scored>=100"),
        ({"fp": 19}, "non_referable_scored>=100"),
        ({"sensitivity": 0.8999}, "sensitivity>=0.90"),
        ({"specificity": 0.7999}, "specificity>=0.80"),
        ({"non_fundus_rejection_rate": 0.99}, "non_fundus_all_ungradable"),
        ({"non_fundus_n": 0, "non_fundus_rejection_rate": None}, "non_fundus_all_ungradable"),
        ({"n_errors": 1}, "no_errors"),
        ({"sensitivity": None}, "sensitivity>=0.90"),
        ({"specificity": None}, "specificity>=0.80"),
    ],
)
def test_pass_bar_single_failure(ev: ModuleType, change: dict[str, Any], criterion: str) -> None:
    summary = good_summary()
    summary.update(change)
    bar = ev.pass_bar(summary, "test")
    assert bar["criteria"][criterion] is False
    assert [k for k, v in bar["criteria"].items() if not v] == [criterion]
    assert bar["passed"] is False


def test_pass_bar_counts_scored_not_labelled(ev: ModuleType) -> None:
    summary = good_summary()
    summary.update(n_referable=100, tp=50, fn=10)  # 40 of the 100 were UNGRADABLE
    bar = ev.pass_bar(summary, "test")
    assert bar["criteria"]["referable_scored>=100"] is False
    summary.update(n_referable=10, tp=90, fn=10)
    assert ev.pass_bar(summary, "test")["criteria"]["referable_scored>=100"] is True


def test_pass_bar_non_referable_scored_not_labelled(ev: ModuleType) -> None:
    summary = good_summary()
    summary.update(n_non_referable=100, tn=40, fp=20)
    assert ev.pass_bar(summary, "test")["criteria"]["non_referable_scored>=100"] is False


@pytest.mark.parametrize("split", [None, "all", "ALL", " train ", "training", "Train", ""])
def test_pass_bar_split_not_held_out(ev: ModuleType, split: Any) -> None:
    bar = ev.pass_bar(good_summary(), split)
    assert bar["criteria"]["held_out_split"] is False
    assert bar["passed"] is False


@pytest.mark.parametrize("split", ["test", "holdout", "val", " Test "])
def test_pass_bar_split_held_out(ev: ModuleType, split: str) -> None:
    bar = ev.pass_bar(good_summary(), split)
    assert bar["criteria"]["held_out_split"] is True
    assert bar["passed"] is True


def test_pass_bar_split_defaults_to_unknown(ev: ModuleType) -> None:
    bar = ev.pass_bar(good_summary())
    assert bar["criteria"]["held_out_split"] is False


def test_pass_bar_ignores_incl_ungradable_keys(ev: ModuleType) -> None:
    base = ev.pass_bar(good_summary(), "test")
    summary = good_summary()
    summary.update(
        sensitivity_incl_ungradable=0.1,
        sensitivity_incl_ungradable_ci=[0.0, 0.2],
        specificity_incl_ungradable=0.1,
        specificity_incl_ungradable_ci=[0.0, 0.2],
    )
    assert ev.pass_bar(summary, "test") == base


# --------------------------------------------------------------------------
# write_report
# --------------------------------------------------------------------------
META = {"model": "claude-sonnet-5-5", "prompt_version": "v1", "labels": "labels.csv"}
TODAY = datetime.date(2026, 11, 22)


def test_write_report_names_and_contents(ev: ModuleType, mixed: list[Any], tmp_path: Path) -> None:
    out = tmp_path / "nested" / "results"
    summary = ev.summarize(mixed, PRICE_IN, PRICE_OUT)
    json_path, md_path = ev.write_report(summary, META, mixed, out, TODAY)
    assert json_path == out / "2026-11-22-claude-sonnet-5-5-v1.json"
    assert md_path == out / "2026-11-22-claude-sonnet-5-5-v1.md"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert {"meta", "summary", "pass_bar", "images"} <= set(data)
    assert data["meta"] == META
    assert data["summary"]["tp"] == 2
    assert data["pass_bar"]["passed"] is False
    assert len(data["images"]) == len(mixed)
    assert data["images"][0]["image"] == "f1.jpg"
    assert "patient" not in json.dumps(data["images"]).lower()
    md = md_path.read_text(encoding="utf-8")
    assert "Sensitivity" in md and "Specificity" in md
    assert "PASS" in md or "FAIL" in md


def test_write_report_never_overwrites(ev: ModuleType, mixed: list[Any], tmp_path: Path) -> None:
    summary = ev.summarize(mixed, PRICE_IN, PRICE_OUT)
    first = ev.write_report(summary, META, mixed, tmp_path, TODAY)
    before = first[0].read_text(encoding="utf-8")
    second = ev.write_report(summary, META, mixed, tmp_path, TODAY)
    third = ev.write_report(summary, META, mixed, tmp_path, TODAY)
    assert second[0].name == "2026-11-22-claude-sonnet-5-5-v1-2.json"
    assert second[1].name == "2026-11-22-claude-sonnet-5-5-v1-2.md"
    assert third[0].name == "2026-11-22-claude-sonnet-5-5-v1-3.json"
    assert first[0].read_text(encoding="utf-8") == before
    assert len({first[0], second[0], third[0]}) == 3


def test_write_report_split_all_never_passes(ev: ModuleType, mixed: list[Any], tmp_path: Path) -> None:
    summary = ev.summarize(mixed, PRICE_IN, PRICE_OUT)
    summary.update(good_summary())
    summary["errors"] = {}
    ok_json, _ = ev.write_report(summary, {**META, "split": "test"}, mixed, tmp_path / "a", TODAY)
    assert json.loads(ok_json.read_text(encoding="utf-8"))["pass_bar"]["passed"] is True
    json_path, md_path = ev.write_report(summary, {**META, "split": "all"}, mixed, tmp_path / "b", TODAY)
    bar = json.loads(json_path.read_text(encoding="utf-8"))["pass_bar"]
    assert bar["passed"] is False
    assert bar["criteria"]["held_out_split"] is False
    md = md_path.read_text(encoding="utf-8")
    assert "held_out_split" in md
    assert "excluding UNGRADABLE" in md
    assert "counting UNGRADABLE as a miss" in md


def test_write_report_missing_split_never_passes(ev: ModuleType, mixed: list[Any], tmp_path: Path) -> None:
    summary = ev.summarize(mixed, PRICE_IN, PRICE_OUT)
    summary.update(good_summary())
    summary["errors"] = {}
    json_path, _ = ev.write_report(summary, META, mixed, tmp_path, TODAY)
    assert json.loads(json_path.read_text(encoding="utf-8"))["pass_bar"]["passed"] is False


def test_write_report_pass_and_fail_wording(ev: ModuleType, tmp_path: Path) -> None:
    summary = ev.summarize([], PRICE_IN, PRICE_OUT)
    _, md_path = ev.write_report(summary, META, [], tmp_path, TODAY)
    assert "FAIL" in md_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
SECRET_IDS = ("PAT-SECRET-001", "PAT-SECRET-002", "PAT-SECRET-003", "PAT-SECRET-004")


def make_dataset(
    tmp_path: Path,
    refer: bytes,
    norefer: bytes,
    blurry: bytes,
    *,
    rows: list[tuple[str, bytes | None, int, str, str]] | None = None,
) -> Path:
    default = [
        ("a.jpg", refer, 4, SECRET_IDS[0], "test"),
        ("b.jpg", norefer, 0, SECRET_IDS[1], "test"),
        ("c.jpg", blurry, 2, SECRET_IDS[2], "test"),
        ("d.jpg", refer, 1, SECRET_IDS[3], "train"),
    ]
    lines = ["image_path,icdr_grade,patient_id,split"]
    for name, data, grade, pid, split in rows or default:
        if data is not None:
            (tmp_path / name).write_bytes(data)
        lines.append(f"{name},{grade},{pid},{split}")
    csv = tmp_path / "labels.csv"
    csv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv


@pytest.fixture
def fake() -> FakeAnthropic:
    return FakeAnthropic.returning(make_assessment())


def run_main(ev: ModuleType, csv: Path, out: Path, fake: Any, *extra: str) -> int:
    return ev.main(["--labels", str(csv), "--out", str(out), *extra], client=fake)


def test_main_happy_path(
    ev: ModuleType,
    tmp_path: Path,
    fake: FakeAnthropic,
    capsys: pytest.CaptureFixture[str],
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    out = tmp_path / "out"
    assert run_main(ev, csv, out, fake) == 0
    # split "test": a and b pass the gate, c (blurry) does not, d is in train
    assert len(fake.calls) == 2
    reports = sorted(p.name for p in out.iterdir())
    assert len(reports) == 2
    assert {Path(n).suffix for n in reports} == {".json", ".md"}
    data = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
    assert data["summary"]["n_images"] == 3
    assert data["meta"]["labels"] == "labels.csv"
    assert str(tmp_path) not in json.dumps(data["meta"])
    blob = repr(fake.calls)
    for pid in SECRET_IDS:
        assert pid not in blob
        assert pid not in json.dumps(data)
    assert "estimate" in capsys.readouterr().out.lower()


def test_main_prints_estimate_before_first_call(
    ev: ModuleType,
    tmp_path: Path,
    fake: FakeAnthropic,
    capsys: pytest.CaptureFixture[str],
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    seen: list[str] = []
    original = fake.messages.parse

    async def spying(**kwargs: Any) -> Any:
        seen.append(capsys.readouterr().out)
        return await original(**kwargs)

    fake.messages.parse = spying  # type: ignore[method-assign]
    assert run_main(ev, csv, tmp_path / "out", fake) == 0
    assert seen and "estimate" in seen[0].lower()


def test_main_patient_in_two_splits(
    ev: ModuleType,
    tmp_path: Path,
    fake: FakeAnthropic,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    rows = [
        ("a.jpg", refer_jpeg_bytes, 4, "SAMEPAT", "test"),
        ("b.jpg", norefer_jpeg_bytes, 0, "SAMEPAT", "train"),
    ]
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes, rows=rows)
    assert run_main(ev, csv, tmp_path / "out", fake) == 2
    assert fake.calls == []


def test_main_missing_image_file(
    ev: ModuleType,
    tmp_path: Path,
    fake: FakeAnthropic,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    rows = [
        ("a.jpg", refer_jpeg_bytes, 4, "P1", "test"),
        ("gone.jpg", None, 0, "P2", "test"),
    ]
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes, rows=rows)
    assert run_main(ev, csv, tmp_path / "out", fake) == 2
    assert fake.calls == []


def test_main_bad_labels_file(ev: ModuleType, tmp_path: Path, fake: FakeAnthropic) -> None:
    csv = tmp_path / "labels.csv"
    csv.write_text("image_path,icdr_grade\na.jpg,1\n", encoding="utf-8")
    assert run_main(ev, csv, tmp_path / "out", fake) == 2
    assert fake.calls == []


def test_main_no_rows_for_split(
    ev: ModuleType,
    tmp_path: Path,
    fake: FakeAnthropic,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    assert run_main(ev, csv, tmp_path / "out", fake, "--split", "nosuchsplit") == 2
    assert fake.calls == []


def test_main_estimate_above_max_cost_needs_yes(
    ev: ModuleType,
    tmp_path: Path,
    fake: FakeAnthropic,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    out = tmp_path / "out"
    assert run_main(ev, csv, out, fake, "--max-cost", "0.0001") == 3
    assert fake.calls == []
    assert not list(out.glob("*.json")) if out.exists() else True
    assert run_main(ev, csv, out, fake, "--max-cost", "0.0001", "--yes") == 0
    assert len(fake.calls) == 2


def test_main_limit(
    ev: ModuleType,
    tmp_path: Path,
    fake: FakeAnthropic,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    rows = [(f"i{n}.jpg", refer_jpeg_bytes, 4, f"P{n}", "test") for n in range(4)]
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes, rows=rows)
    assert run_main(ev, csv, tmp_path / "out", fake, "--limit", "2") == 0
    assert len(fake.calls) == 2
    data = json.loads(next((tmp_path / "out").glob("*.json")).read_text(encoding="utf-8"))
    assert data["summary"]["n_images"] == 2


def test_main_split_filter_and_all(
    ev: ModuleType,
    tmp_path: Path,
    fake: FakeAnthropic,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    assert run_main(ev, csv, tmp_path / "o1", fake, "--split", "train") == 0
    assert len(fake.calls) == 1  # only d.jpg
    assert run_main(ev, csv, tmp_path / "o2", fake, "--split", "all") == 0
    assert len(fake.calls) == 1 + 3  # a, b, d pass the gate; c is blurry


def test_main_non_fundus_folder(
    ev: ModuleType,
    tmp_path: Path,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    nf = tmp_path / "nonfundus"
    nf.mkdir()
    (nf / "x.jpg").write_bytes(refer_jpeg_bytes)
    (nf / "y.png").write_bytes(norefer_jpeg_bytes)
    fake = FakeAnthropic.returning(make_assessment(image_type="other", gradable=False))
    out = tmp_path / "out"
    assert run_main(ev, csv, out, fake, "--non-fundus", str(nf)) == 0
    assert len(fake.calls) == 4  # a, b, x, y
    data = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
    assert data["summary"]["non_fundus_n"] == 2
    assert data["summary"]["non_fundus_rejection_rate"] == 1.0
    assert str(nf) not in json.dumps(data["images"])


def partial_files(out: Path) -> list[Path]:
    return sorted(out.glob("*.partial.jsonl"))


def test_main_success_leaves_no_partial_file(
    ev: ModuleType,
    tmp_path: Path,
    fake: FakeAnthropic,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    out = tmp_path / "out"
    assert run_main(ev, csv, out, fake) == 0
    assert partial_files(out) == []


def test_main_report_failure_keeps_partial_results(
    ev: ModuleType,
    tmp_path: Path,
    fake: FakeAnthropic,
    monkeypatch: pytest.MonkeyPatch,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    out = tmp_path / "out"

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("disk full")

    monkeypatch.setattr(ev, "write_report", boom)
    with pytest.raises(RuntimeError, match="disk full"):
        run_main(ev, csv, out, fake)
    (partial,) = partial_files(out)
    lines = [json.loads(line) for line in partial.read_text(encoding="utf-8").splitlines() if line]
    assert sorted(line["image"] for line in lines) == ["a.jpg", "b.jpg", "c.jpg"]
    blob = partial.read_text(encoding="utf-8")
    for pid in SECRET_IDS:
        assert pid not in blob


class _ClosableFake(FakeAnthropic):
    def __init__(self) -> None:
        super().__init__(response=FakeAnthropic.returning(make_assessment()).response)
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


def test_main_built_client_uses_no_retries_and_is_closed(
    ev: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    import anthropic

    created: list[tuple[_ClosableFake, dict[str, Any]]] = []

    def recorder(**kwargs: Any) -> _ClosableFake:
        client = _ClosableFake()
        created.append((client, kwargs))
        return client

    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-not-a-real-key")
    monkeypatch.setattr(anthropic, "AsyncAnthropic", recorder)
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    out = tmp_path / "out"
    assert ev.main(["--labels", str(csv), "--out", str(out)]) == 0
    assert len(created) == 1
    client, kwargs = created[0]
    assert kwargs["max_retries"] == 0
    assert kwargs["api_key"] == "dummy-not-a-real-key"
    assert client.closed == 1
    assert len(client.calls) == 2
    data = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
    assert data["meta"]["client_max_retries"] == 0


def test_main_built_client_closed_on_error(
    ev: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    import anthropic

    created: list[_ClosableFake] = []

    def recorder(**kwargs: Any) -> _ClosableFake:
        client = _ClosableFake()
        created.append(client)
        return client

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("disk full")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-not-a-real-key")
    monkeypatch.setattr(anthropic, "AsyncAnthropic", recorder)
    monkeypatch.setattr(ev, "write_report", boom)
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    with pytest.raises(RuntimeError):
        ev.main(["--labels", str(csv), "--out", str(tmp_path / "out")])
    assert [c.closed for c in created] == [1]


def test_main_injected_client_is_not_closed(
    ev: ModuleType,
    tmp_path: Path,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    client = _ClosableFake()
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    out = tmp_path / "out"
    assert run_main(ev, csv, out, client) == 0
    assert client.closed == 0
    data = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
    assert data["meta"]["client_max_retries"] is None


def test_main_over_budget_with_yes_proceeds(
    ev: ModuleType,
    tmp_path: Path,
    fake: FakeAnthropic,
    refer_jpeg_bytes: bytes,
    norefer_jpeg_bytes: bytes,
    blurry_jpeg_bytes: bytes,
) -> None:
    csv = make_dataset(tmp_path, refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes)
    assert run_main(ev, csv, tmp_path / "out", fake, "--max-cost", "0.000001", "--yes") == 0
    assert len(fake.calls) == 2
