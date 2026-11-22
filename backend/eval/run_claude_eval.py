"""Phase 4 accuracy eval: Claude through the backend's own screening path.

MIGRATION_PLAN.md §6 Phase 4 and §8. Every image goes through exactly what
``POST /api/v1/predict`` does — size cap, format sniff, decode, quality gate,
``ClaudeEngine.assess`` (only when the gate passed), ``decide_from_assessment``
— so these are the verdicts the phone would get. Run from ``backend/``::

    python eval/run_claude_eval.py --labels eval/data/labels.csv \\
        --non-fundus eval/data/non_fundus

The labelled CSV has ``image_path, icdr_grade, patient_id, split`` (paths
relative to the CSV). ``--non-fundus`` is a folder of phone photos that are not
fundus images; every one of them must come back UNGRADABLE.

Cost and safety:

* Each image that passes the quality gate is one **billed** Claude call. The
  script prints an upper-bound cost estimate before sending anything, and above
  ``--max-cost`` (default $10) it sends nothing unless ``--yes`` is given.
  ``--limit N`` runs a small pilot first.
* At most ``--concurrency`` (default 2) calls are in flight.
* Only the image bytes reach Claude. ``patient_id`` is read only to check that
  no patient is on both sides of a split (§8); it is never sent and never
  written to the report.
* No threshold, rule or prompt is changed here: the settings come from the
  environment and ``.env`` as in production. Set ``QUALITY_BLUR_MIN_VAR=8``
  like every real deployment.
* The client is built like production's (``max_retries=0``), so a timeout or
  API error shows up as an error for that image, as the phone would see a 500.

Writes ``eval/results/<date>-<model>-<prompt>.json`` plus a Markdown summary.
While it runs, every finished image is appended to a ``.partial.jsonl`` file
there, so a crash or Ctrl-C keeps the calls already paid for; the file is
removed once the report is written. The report names images by file name: if
your file names carry patient identity, rename them before committing results.

The pass bar (§8) counts only images that were actually scored (UNGRADABLE
excluded), and never passes unless ``--split`` names a held-out split.
"""

import argparse
import asyncio
import csv
import io
import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

# No `from __future__ import annotations`: the tests load this file by path
# without registering it in sys.modules, and dataclasses with string
# annotations look their module up there.

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

#: USD per million tokens, (input, output). Override with --price-in/--price-out.
PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}
DEFAULT_MAX_COST = 10.0
DEFAULT_CONCURRENCY = 2
DEFAULT_OUT = BACKEND / "eval" / "results"

_COLUMNS = ("image_path", "icdr_grade", "patient_id", "split")
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
_DECISIONS = ("REFER", "NO_REFER", "UNGRADABLE")


@dataclass(frozen=True)
class LabelRow:
    image_path: Path
    icdr_grade: int
    patient_id: str
    split: str


@dataclass(frozen=True)
class Item:
    path: Path
    kind: str  # "fundus" | "non_fundus"
    true_grade: int | None  # None for non_fundus


@dataclass
class ImageResult:
    image: str  # file name only: never a directory, never a patient id
    kind: str
    true_grade: int | None
    decision: str | None  # REFER / NO_REFER / UNGRADABLE; None on error
    pred_grade: int | None  # DecisionResult.db_icdr_grade (None for UNGRADABLE)
    image_type: str | None  # Claude's image_type when it answered
    quality_ok: bool | None  # None if the image never reached the gate
    called_claude: bool  # True iff engine.assess was awaited, even if it raised
    latency_ms: float | None
    input_tokens: int
    output_tokens: int
    error: str | None  # "too_large" | "invalid_image" | exception class name


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for ``k`` successes out of ``n``; ``None`` if n == 0."""
    if n == 0:
        return None
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def read_labels(csv_path: Path) -> list[LabelRow]:
    """Parse the labelled CSV; raise ``ValueError`` naming the bad column or line."""
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = [name.strip() for name in (reader.fieldnames or [])]
        for column in _COLUMNS:
            if column not in header:
                raise ValueError(f"{Path(csv_path).name}: missing column {column!r}")
        reader.fieldnames = header
        rows: list[LabelRow] = []
        for line, record in enumerate(reader, start=2):  # header is line 1
            values = {c: (record.get(c) or "").strip() for c in _COLUMNS}
            try:
                grade = int(values["icdr_grade"])
            except ValueError:
                raise ValueError(
                    f"line {line}: icdr_grade {values['icdr_grade']!r} is not an integer"
                ) from None
            if not 0 <= grade <= 4:
                raise ValueError(f"line {line}: icdr_grade {grade} is outside 0..4")
            for column in ("image_path", "patient_id", "split"):
                if not values[column]:
                    raise ValueError(f"line {line}: {column} is empty")
            path = Path(values["image_path"])
            if not path.is_absolute():
                path = Path(csv_path).parent / path
            rows.append(LabelRow(path, grade, values["patient_id"], values["split"]))
    return rows


def patients_across_splits(rows: list[LabelRow]) -> list[str]:
    """Patient ids found in more than one split (both eyes must share a side, §8)."""
    splits: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        splits[row.patient_id].add(row.split)
    return sorted(pid for pid, seen in splits.items() if len(seen) > 1)


def list_images(folder: Path) -> list[Path]:
    """JPEG/PNG files directly in ``folder``, sorted."""
    return sorted(
        p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES
    )


# ---------------------------------------------------------------------------
# cost
# ---------------------------------------------------------------------------


def estimate_input_tokens(raw: bytes, system_prompt: str) -> int:
    """An upper-bound guess of one request's input tokens (no API call)."""
    from PIL import Image

    from app.inference.assessment import FundusAssessment
    from app.inference.claude_engine import USER_INSTRUCTION, prepare_jpeg

    with Image.open(io.BytesIO(prepare_jpeg(raw))) as prepared:
        width, height = prepared.size
    schema = json.dumps(FundusAssessment.model_json_schema())
    text_chars = len(system_prompt) + len(USER_INSTRUCTION) + len(schema)
    return math.ceil(width * height / 750) + math.ceil(text_chars / 3) + 100


def upper_bound_cost(
    input_tokens_total: int, n_calls: int, max_tokens: int, price_in: float, price_out: float
) -> float:
    """USD if every answer used all of ``max_tokens``."""
    return input_tokens_total * price_in / 1e6 + n_calls * max_tokens * price_out / 1e6


# ---------------------------------------------------------------------------
# the screening path
# ---------------------------------------------------------------------------


def _local_checks(raw: bytes, settings: Any) -> tuple[str | None, bool | None]:
    """Steps before Claude, in predict's order: ``(error, quality_ok)``."""
    import app.inference.preprocess as preprocess
    import app.inference.quality as quality
    import app.storage as storage

    if len(raw) > settings.max_upload_bytes:
        return "too_large", None
    if storage.sniff_ext(raw) is None:
        return "invalid_image", None
    img = preprocess.load_rgb(raw)
    if img is None:
        return "invalid_image", None
    return None, bool(quality.assess(img, settings).ok)


async def evaluate(
    items: list[Item],
    engine: Any,
    settings: Any,
    concurrency: int = DEFAULT_CONCURRENCY,
    on_result: Callable[[ImageResult], None] | None = None,
) -> list[ImageResult]:
    """Screen every item; results in input order. Claude sees only the bytes.

    A failure on one image (unreadable file, a local check, the Claude call, the
    decision) becomes that image's ``error``; the rest of the run goes on.
    ``on_result`` gets each finished result as soon as it is done.
    """
    from app.inference.decision import decide_from_assessment

    # Bounds the whole per-image work, so at most `concurrency` files are held.
    semaphore = asyncio.Semaphore(concurrency)
    calls_done = 0

    async def screen(item: Item) -> ImageResult:
        fields: dict[str, Any] = {
            "image": item.path.name, "kind": item.kind, "true_grade": item.true_grade,
            "decision": None, "pred_grade": None, "image_type": None, "quality_ok": None,
            "called_claude": False, "latency_ms": None, "input_tokens": 0,
            "output_tokens": 0, "error": None,
        }
        try:
            raw = await asyncio.to_thread(item.path.read_bytes)
            error, ok = await asyncio.to_thread(_local_checks, raw, settings)
            if error is not None:
                fields["error"] = error
                return ImageResult(**fields)
            fields["quality_ok"] = ok
            pred = None
            if ok:  # the gate passed: one Claude call, with the bytes and nothing else
                fields["called_claude"] = True
                pred = await engine.assess(raw)
                fields.update(
                    image_type=pred["assessment"].image_type,
                    latency_ms=float(pred["latency_ms"]),
                    input_tokens=int(pred["input_tokens"]),
                    output_tokens=int(pred["output_tokens"]),
                )
            result = decide_from_assessment(
                pred["assessment"] if pred else None,
                bool(ok),
                settings.referable_threshold,
                settings.uncertain_refers,
            )
            fields.update(decision=result.decision, pred_grade=result.db_icdr_grade)
        except Exception as exc:  # noqa: BLE001 - no fallback verdict; the run goes on
            fields.update(error=type(exc).__name__, decision=None, pred_grade=None)
        return ImageResult(**fields)

    async def bounded(item: Item) -> ImageResult:
        nonlocal calls_done
        async with semaphore:
            result = await screen(item)
        if on_result is not None:
            on_result(result)
        if result.called_claude:
            calls_done += 1
            if calls_done % 10 == 0:
                print(f"  ... {calls_done} Claude calls done", file=sys.stderr)
        return result

    return list(await asyncio.gather(*(bounded(item) for item in items)))


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def _rate(k: int, n: int) -> float | None:
    return k / n if n else None


def _ci(k: int, n: int) -> list[float] | None:
    interval = wilson_ci(k, n)
    return list(interval) if interval else None


def summarize(results: list[ImageResult], price_in: float, price_out: float) -> dict[str, Any]:
    """Every number the report needs; ``None`` where a denominator is zero."""
    import numpy as np

    fundus = [r for r in results if r.kind == "fundus" and r.error is None]
    graded = [r for r in fundus if r.decision in ("REFER", "NO_REFER")]
    referable = [r for r in fundus if (r.true_grade or 0) >= 2]
    non_referable = [r for r in fundus if (r.true_grade or 0) < 2]

    def is_ungradable(r: ImageResult) -> bool:
        return r.decision == "UNGRADABLE"

    tp = sum(1 for r in graded if (r.true_grade or 0) >= 2 and r.decision == "REFER")
    fn = sum(1 for r in graded if (r.true_grade or 0) >= 2 and r.decision == "NO_REFER")
    fp = sum(1 for r in graded if (r.true_grade or 0) < 2 and r.decision == "REFER")
    tn = sum(1 for r in graded if (r.true_grade or 0) < 2 and r.decision == "NO_REFER")

    confusion = [[0] * 5 for _ in range(5)]
    for r in graded:
        if r.true_grade is not None and r.pred_grade is not None:
            confusion[r.true_grade][r.pred_grade] += 1
    by_grade = {str(g): {d: 0 for d in _DECISIONS} for g in range(5)}
    for r in fundus:
        if r.true_grade is not None and r.decision in _DECISIONS:
            by_grade[str(r.true_grade)][r.decision] += 1

    non_fundus = [r for r in results if r.kind == "non_fundus" and r.error is None]
    rejected = [r for r in non_fundus if is_ungradable(r)]

    answered = [r for r in results if r.called_claude and r.error is None]
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    cost = (
        sum(r.input_tokens for r in results) * price_in / 1e6
        + sum(r.output_tokens for r in results) * price_out / 1e6
    )
    ungradable = sum(1 for r in fundus if is_ungradable(r))
    return {
        "n_images": len(results),
        "n_errors": sum(1 for r in results if r.error is not None),
        "errors": dict(Counter(r.error for r in results if r.error is not None)),
        "n_referable": len(referable),
        "n_non_referable": len(non_referable),
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "sensitivity": _rate(tp, tp + fn),
        "sensitivity_ci": _ci(tp, tp + fn),
        "specificity": _rate(tn, tn + fp),
        "specificity_ci": _ci(tn, tn + fp),
        # Strict variants: an UNGRADABLE fundus image counts as a miss. Reported
        # only; pass_bar does not read them (an owner/ophthalmologist decision).
        "sensitivity_incl_ungradable": _rate(tp, len(referable)),
        "sensitivity_incl_ungradable_ci": _ci(tp, len(referable)),
        "specificity_incl_ungradable": _rate(tn, len(non_referable)),
        "specificity_incl_ungradable_ci": _ci(tn, len(non_referable)),
        "ungradable": ungradable,
        "ungradable_rate": _rate(ungradable, len(fundus)),
        "ungradable_rate_referable": _rate(
            sum(1 for r in referable if is_ungradable(r)), len(referable)
        ),
        "ungradable_rate_non_referable": _rate(
            sum(1 for r in non_referable if is_ungradable(r)), len(non_referable)
        ),
        "grade_confusion": confusion,
        "decision_by_true_grade": by_grade,
        "non_fundus_n": len(non_fundus),
        "non_fundus_rejected": len(rejected),
        "non_fundus_rejection_rate": _rate(len(rejected), len(non_fundus)),
        "non_fundus_not_rejected": sorted(r.image for r in non_fundus if not is_ungradable(r)),
        "claude_calls": sum(1 for r in results if r.called_claude),
        "latency_p50_ms": float(np.percentile(latencies, 50)) if latencies else None,
        "latency_p95_ms": float(np.percentile(latencies, 95)) if latencies else None,
        "mean_input_tokens": (
            sum(r.input_tokens for r in answered) / len(answered) if answered else None
        ),
        "mean_output_tokens": (
            sum(r.output_tokens for r in answered) / len(answered) if answered else None
        ),
        "cost_total_usd": cost,
        "cost_per_scan_usd": cost / len(answered) if answered else None,
    }


def _at_least(value: float | None, bar: float) -> bool:
    return value is not None and value >= bar


_NOT_HELD_OUT = {"all", "train", "training"}


def _held_out(split: str | None) -> bool:
    name = (split or "").strip().lower()
    return bool(name) and name not in _NOT_HELD_OUT


def pass_bar(summary: dict[str, Any], split: str | None = None) -> dict[str, Any]:
    """MIGRATION_PLAN.md §8, one boolean per criterion.

    The 100-image minimums count images that were actually scored (REFER or
    NO_REFER), so UNGRADABLE ones cannot make a small sample look large. An
    unknown, ``all`` or training split never passes: §8 is about held-out data.
    """
    criteria = {
        "referable_scored>=100": summary["tp"] + summary["fn"] >= 100,
        "non_referable_scored>=100": summary["tn"] + summary["fp"] >= 100,
        "sensitivity>=0.90": _at_least(summary["sensitivity"], 0.90),
        "specificity>=0.80": _at_least(summary["specificity"], 0.80),
        "non_fundus_all_ungradable": (
            summary["non_fundus_n"] > 0 and summary["non_fundus_rejection_rate"] == 1.0
        ),
        "no_errors": summary["n_errors"] == 0,
        "held_out_split": _held_out(split),
    }
    return {"criteria": criteria, "passed": all(criteria.values())}


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _pct_ci(ci: list[float] | None) -> str:
    return "—" if not ci else f"{ci[0] * 100:.1f}%–{ci[1] * 100:.1f}%"


def _markdown(summary: dict[str, Any], meta: dict[str, Any], bar: dict[str, Any]) -> str:
    s = summary

    def ms(value: float | None) -> str:
        return "—" if value is None else f"{value:.0f} ms"

    lines = [
        f"# Claude DR eval — {meta.get('date', '')}, {meta.get('model')}, "
        f"prompt {meta.get('prompt_version')}",
        "",
        f"Labels `{meta.get('labels')}` (split `{meta.get('split')}`): "
        f"{s['n_images']} images, {s['claude_calls']} Claude calls, {s['n_errors']} errors.",
        "",
        "| Metric | Value | 95% CI |",
        "|---|---|---|",
        f"| Sensitivity (referable DR, grade ≥ 2), excluding UNGRADABLE | "
        f"{_pct(s['sensitivity'])} ({s['tp']}/{s['tp'] + s['fn']}) "
        f"| {_pct_ci(s['sensitivity_ci'])} |",
        f"| Sensitivity, counting UNGRADABLE as a miss | "
        f"{_pct(s['sensitivity_incl_ungradable'])} ({s['tp']}/{s['n_referable']}) "
        f"| {_pct_ci(s['sensitivity_incl_ungradable_ci'])} |",
        f"| Specificity, excluding UNGRADABLE | {_pct(s['specificity'])} "
        f"({s['tn']}/{s['tn'] + s['fp']}) | {_pct_ci(s['specificity_ci'])} |",
        f"| Specificity, counting UNGRADABLE as not cleared | "
        f"{_pct(s['specificity_incl_ungradable'])} ({s['tn']}/{s['n_non_referable']}) "
        f"| {_pct_ci(s['specificity_incl_ungradable_ci'])} |",
        f"| Ungradable fundus | {_pct(s['ungradable_rate'])} (referable "
        f"{_pct(s['ungradable_rate_referable'])}, non-referable "
        f"{_pct(s['ungradable_rate_non_referable'])}) | |",
        f"| Non-fundus rejected | {_pct(s['non_fundus_rejection_rate'])} "
        f"({s['non_fundus_rejected']}/{s['non_fundus_n']}) | |",
        f"| Latency p50 / p95 | {ms(s['latency_p50_ms'])} / {ms(s['latency_p95_ms'])} | |",
        f"| Cost | ${s['cost_total_usd']:.2f} total, "
        + ("—" if s["cost_per_scan_usd"] is None else f"${s['cost_per_scan_usd']:.4f}")
        + " per scan | |",
        "",
        f"Referable 2×2 (UNGRADABLE excluded): TP {s['tp']}, FN {s['fn']}, "
        f"FP {s['fp']}, TN {s['tn']}.",
        "",
        "## Pass bar (MIGRATION_PLAN.md §8)",
        "",
        f"Split `{meta.get('split')}`"
        + (f", pilot limited to {meta['limit']} per folder" if meta.get("limit") else "")
        + ". The minimums count scored images only; the sensitivity and specificity "
        "criteria use the rows that exclude UNGRADABLE.",
        "",
        "| Criterion | Result |",
        "|---|---|",
    ]
    lines += [f"| {name} | {'PASS' if ok else 'FAIL'} |" for name, ok in bar["criteria"].items()]
    lines += [
        "",
        f"**Overall: {'PASS' if bar['passed'] else 'FAIL'}.** Until the pass bar is met, "
        "results are decision support only and every result is confirmed by an "
        "ophthalmologist.",
        "",
    ]
    if s["non_fundus_not_rejected"]:
        lines += ["Non-fundus images not rejected: " + ", ".join(s["non_fundus_not_rejected"]), ""]
    return "\n".join(lines)


def write_report(
    summary: dict[str, Any],
    meta: dict[str, Any],
    results: list[ImageResult],
    out_dir: Path,
    today: date,
) -> tuple[Path, Path]:
    """Write ``<date>-<model>-<prompt>.json`` and ``.md``; never overwrite."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{today.isoformat()}-{meta['model']}-{meta['prompt_version']}"
    base, n = stem, 1
    while (out_dir / f"{base}.json").exists() or (out_dir / f"{base}.md").exists():
        n += 1
        base = f"{stem}-{n}"
    bar = pass_bar(summary, meta.get("split"))
    payload = {
        "meta": meta,
        "summary": summary,
        "pass_bar": bar,
        "images": [asdict(r) for r in results],
    }
    json_path = out_dir / f"{base}.json"
    md_path = out_dir / f"{base}.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(summary, {**meta, "date": today.isoformat()}, bar), encoding="utf-8")
    return json_path, md_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--labels", type=Path, required=True, help="CSV: image_path, icdr_grade, patient_id, split")
    ap.add_argument("--non-fundus", type=Path, default=None, help="folder of non-fundus phone eye photos")
    ap.add_argument("--split", default="test", help="split to score; 'all' = every row (default: test)")
    ap.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    ap.add_argument("--max-cost", type=float, default=DEFAULT_MAX_COST, help="USD; above it, ask for --yes")
    ap.add_argument("--yes", action="store_true", help="confirm a run above --max-cost")
    ap.add_argument("--limit", type=int, default=None, help="first N fundus rows and first N non-fundus files")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--price-in", type=float, default=None, help="USD per MTok input")
    ap.add_argument("--price-out", type=float, default=None, help="USD per MTok output")
    args = ap.parse_args(argv)
    if args.concurrency < 1:
        ap.error("--concurrency must be at least 1")
    if args.limit is not None and args.limit < 1:
        ap.error("--limit must be at least 1")
    return args


def main(argv: list[str] | None = None, *, client: Any = None) -> int:
    args = _parse_args(argv)

    # 1-2. labels, split hygiene, files
    try:
        rows = read_labels(args.labels)
    except (OSError, ValueError) as exc:
        print(f"labels: {exc}")
        return 2
    leaked = patients_across_splits(rows)
    if leaked:
        print(f"{len(leaked)} patient(s) appear in more than one split (§8 forbids it): "
              + ", ".join(leaked[:10]) + (" ..." if len(leaked) > 10 else ""))
        return 2
    if args.split != "all":
        rows = [r for r in rows if r.split == args.split]
    if args.limit is not None:
        rows = rows[: args.limit]
    if not rows:
        print(f"no labelled rows in split {args.split!r}")
        return 2
    missing = [r.image_path for r in rows if not r.image_path.is_file()]
    if missing:
        print(f"{len(missing)} image file(s) missing, e.g. {missing[0]}")
        return 2
    items = [Item(r.image_path, "fundus", r.icdr_grade) for r in rows]
    if args.non_fundus is not None:
        if not args.non_fundus.is_dir():
            print(f"--non-fundus {args.non_fundus} is not a folder")
            return 2
        extra = list_images(args.non_fundus)
        if args.limit is not None:
            extra = extra[: args.limit]
        items += [Item(p, "non_fundus", None) for p in extra]

    # 3. settings exactly as production reads them, engine source forced to claude
    from app.config import Settings
    from app.inference.claude_engine import (
        ClaudeEngine,
        fewshot_input_tokens,
        load_system_prompt,
    )

    # Init kwargs (by alias) win over env and .env; nothing else is overridden.
    overrides: dict[str, Any] = {"EYE_MODE": "demo", "EYE_MODEL_SOURCE": "claude"}
    try:
        settings = Settings(**overrides)
        system_prompt = load_system_prompt(settings.prompt_version)
        fewshot_tokens = fewshot_input_tokens(settings.prompt_version)
    except (ValueError, OSError) as exc:
        print(f"settings: {exc}")
        return 2
    model = settings.claude_model
    default_in, default_out = PRICES.get(model, (None, None))
    price_in = args.price_in if args.price_in is not None else default_in
    price_out = args.price_out if args.price_out is not None else default_out
    if price_in is None or price_out is None:
        print(f"no price for {model}; pass --price-in and --price-out (USD per MTok)")
        return 2

    # 4. local pre-pass: which images reach Claude, and an upper-bound cost
    n_calls = n_gated = n_bad = tokens = 0
    for item in items:
        raw = item.path.read_bytes()
        error, ok = _local_checks(raw, settings)
        if error is not None:
            n_bad += 1
        elif not ok:
            n_gated += 1
        else:
            n_calls += 1
            tokens += estimate_input_tokens(raw, system_prompt) + fewshot_tokens
    estimate = upper_bound_cost(tokens, n_calls, settings.claude_max_tokens, price_in, price_out)
    n_fundus = sum(1 for i in items if i.kind == "fundus")
    print(f"Images: {n_fundus} fundus (split {args.split!r}), {len(items) - n_fundus} non-fundus")
    print(f"Local checks: {n_calls} reach Claude, {n_gated} stopped by the quality gate, "
          f"{n_bad} unreadable or too large")
    print(f"Settings: model={model} prompt={settings.prompt_version} "
          f"threshold={settings.referable_threshold} uncertain_refers={settings.uncertain_refers} "
          f"QUALITY_BLUR_MIN_VAR={settings.quality_blur_min_var} "
          f"CLAUDE_MAX_TOKENS={settings.claude_max_tokens} concurrency={args.concurrency}")
    print(f"Cost estimate (upper bound, every answer at CLAUDE_MAX_TOKENS): "
          f"${estimate:.2f} for {n_calls} calls")

    # 5. confirmation gate: nothing is sent above --max-cost without --yes
    if estimate > args.max_cost and not args.yes:
        print(f"The estimate is above --max-cost ${args.max_cost:.2f}. Nothing was sent. "
              "Re-run with --yes to confirm, or use --limit for a pilot.")
        return 3

    # 6. engine: the production ClaudeEngine
    owned = client is None
    if owned:
        key = (settings.anthropic_api_key or "").strip()
        if not key:
            print("ANTHROPIC_API_KEY is not set (backend/.env or the shell)")
            return 2
        from app.inference import claude_http

        # Same as production (app/inference/claude_engine.py): raw HTTP, no
        # SDK, no retries; the engine applies the timeout per call.
        client = claude_http.ClaudeHTTPClient(api_key=key)
    engine = ClaudeEngine(settings, client=client)

    # 7. run, saving each finished image as it comes; summarise; report
    today = date.today()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    partial = out_dir / f"{today.isoformat()}-{model}-{settings.prompt_version}-{stamp}.partial.jsonl"
    with partial.open("a", encoding="utf-8") as progress:

        def save(result: ImageResult) -> None:
            progress.write(json.dumps(asdict(result)) + "\n")
            progress.flush()

        async def run() -> list[ImageResult]:
            try:
                return await evaluate(items, engine, settings, args.concurrency, on_result=save)
            finally:
                close = getattr(client, "close", None)
                if owned and close is not None:
                    await close()

        print(f"Saving results as they finish to {partial}")
        results = asyncio.run(run())
        summary = summarize(results, price_in, price_out)
        meta = _meta(args, settings, engine, price_in, price_out, estimate, owned)
        json_path, md_path = write_report(summary, meta, results, out_dir, today)
    partial.unlink(missing_ok=True)  # the report now holds every result
    bar = pass_bar(summary, args.split)
    print(f"Report: {json_path}\n        {md_path}")
    print(f"Sensitivity {_pct(summary['sensitivity'])}, specificity {_pct(summary['specificity'])}, "
          f"cost ${summary['cost_total_usd']:.2f} -> pass bar {'PASS' if bar['passed'] else 'FAIL'}")
    return 0


def _meta(
    args: argparse.Namespace,
    settings: Any,
    engine: Any,
    price_in: float,
    price_out: float,
    estimate: float,
    owned: bool,
) -> dict[str, Any]:
    return {
        "model": settings.claude_model,
        "prompt_version": settings.prompt_version,
        "model_version": engine.model_version,
        "labels": Path(args.labels).name,  # the file name, never its directory
        "split": args.split,
        "limit": args.limit,
        "concurrency": args.concurrency,
        "threshold": settings.referable_threshold,
        "uncertain_refers": settings.uncertain_refers,
        "quality_blur_min_var": settings.quality_blur_min_var,
        "claude_max_tokens": settings.claude_max_tokens,
        "client_max_retries": 0 if owned else None,  # None: a client was injected
        "price_in_per_mtok": price_in,
        "price_out_per_mtok": price_out,
        "estimate_usd": estimate,
    }


if __name__ == "__main__":
    raise SystemExit(main())
