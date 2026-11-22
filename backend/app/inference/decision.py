"""Decision logic (spec §4.6, C3). ``decide()`` is FROZEN — do not edit it.

``decide_from_assessment()`` (Claude migration, plan §3.5) is added below it
and returns the same :class:`DecisionResult`.

The referable threshold lives here and ONLY here — the client never re-derives
it. C3: the wire keeps non-null placeholders for UNGRADABLE (the deployed APK
crashes on nulls) while the DB stores NULL, so future training exports stay
clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.inference.assessment import FundusAssessment
    from app.inference.engine import Prediction

GRADE_LABELS = {
    0: "DR yo'q",
    1: "Yengil NPDR",
    2: "O'rtacha NPDR",
    3: "Og'ir NPDR",
    4: "Proliferativ DR",
}


@dataclass(frozen=True)
class DecisionResult:
    decision: str
    referable: bool
    probability: float
    icdr_grade: int
    grade_label: str
    decision_text: str
    quality: str
    # DB-truth fields (C3): None for UNGRADABLE, mirror wire values otherwise
    db_probability: float | None
    db_icdr_grade: int | None


def decide(
    pred: "Prediction | None", quality_ok: bool, threshold: float
) -> DecisionResult:
    if not quality_ok or pred is None:
        return DecisionResult(
            "UNGRADABLE",
            False,
            0.0,
            0,
            "Baholab bo'lmadi",
            "Sifatsiz rasm — qayta suratga oling",
            "poor",
            db_probability=None,
            db_icdr_grade=None,
        )
    p_ref = round(sum(pred["probs"][2:]), 4)
    referable = p_ref >= threshold
    return DecisionResult(
        "REFER" if referable else "NO_REFER",
        referable,
        p_ref,
        pred["grade"],
        GRADE_LABELS[pred["grade"]],
        "Referable DR — oftalmologga yuboring"
        if referable
        else "Referable DR aniqlanmadi — 12 oydan keyin qayta tekshiruv",
        "good",
        db_probability=p_ref,
        db_icdr_grade=pred["grade"],
    )


# ---------------------------------------------------------------------------
# Claude engine (MIGRATION_PLAN.md §3.5) — added next to the frozen decide().
# ---------------------------------------------------------------------------
_NOT_FUNDUS_TEXT = (
    "Bu ko'z tubi (fundus) rasmi emas — fundus kamera yoki adapter bilan oling"
)
_GENERIC_POOR_TEXT = "Sifatsiz rasm — qayta suratga oling"
_QUALITY_REASONS = {
    "blur": "rasm xira",
    "too_dark": "juda qorong'i",
    "overexposed": "juda yorug'",
    "small_field": "ko'z tubi to'liq ko'rinmaydi",
    "obstruction": "to'siq bor",
}
_REFER_TEXT = "Referable DR — oftalmologga yuboring"
_NO_REFER_TEXT = "Referable DR aniqlanmadi — 12 oydan keyin qayta tekshiruv"


def _ungradable(decision_text: str) -> DecisionResult:
    # C3: non-null wire placeholders, NULL in the database.
    return DecisionResult(
        "UNGRADABLE",
        False,
        0.0,
        0,
        "Baholab bo'lmadi",
        decision_text,
        "poor",
        db_probability=None,
        db_icdr_grade=None,
    )


def _rule_grade(a: "FundusAssessment") -> int:
    """ICDR grade implied by the lesions marked ``present`` (rule 4)."""
    les = a.lesions
    if "present" in (les.neovascularization, les.preretinal_or_vitreous_hemorrhage):
        return 4
    if (
        "present" in (les.venous_beading, les.irma)
        or a.hemorrhages_in_all_4_quadrants
    ):
        return 3
    if "present" in (les.retinal_hemorrhages, les.hard_exudates, les.cotton_wool_spots):
        return 2
    if les.microaneurysms == "present":
        return 1
    return 0


def decide_from_assessment(
    a: "FundusAssessment | None",
    quality_ok: bool,
    threshold: float,
    uncertain_refers: bool,
) -> DecisionResult:
    """Verdict for a Claude assessment; same ``DecisionResult`` as :func:`decide`."""
    # Rule 1: a failed gate (or no assessment) is exactly today's UNGRADABLE.
    if not quality_ok or a is None:
        return decide(None, False, threshold)
    # Rule 2: not a fundus photo at all.
    if a.image_type != "fundus":
        return _ungradable(_NOT_FUNDUS_TEXT)
    # Rule 3: a fundus photo Claude could not grade.
    if not a.gradable:
        reasons = list(dict.fromkeys(_QUALITY_REASONS[q] for q in a.quality_issues))
        if not reasons:
            return _ungradable(_GENERIC_POOR_TEXT)
        return _ungradable(
            f"Baholab bo'lmadi: {', '.join(reasons)} — qayta suratga oling"
        )

    # Rules 4-5: the grade can only be raised by the lesion checklist.
    final_grade = max(a.icdr_grade, _rule_grade(a))

    # Rule 6.
    les = a.lesions
    grade2_lesions = (
        les.retinal_hemorrhages,
        les.hard_exudates,
        les.cotton_wool_spots,
        les.venous_beading,
        les.irma,
        les.neovascularization,
        les.preretinal_or_vitreous_hemorrhage,
    )
    referable = (
        final_grade >= 2
        or a.macular_edema_signs in ("present", "uncertain")
        or (uncertain_refers and "uncertain" in grade2_lesions)
    )

    # Rule 7: the probability must agree with the verdict.
    p = round(a.referable_probability, 4)
    if referable:
        p = max(p, threshold)
    else:
        p = max(0.0, min(p, round(threshold - 0.0001, 4)))

    # Rule 8.
    return DecisionResult(
        "REFER" if referable else "NO_REFER",
        referable,
        p,
        final_grade,
        GRADE_LABELS[final_grade],
        _REFER_TEXT if referable else _NO_REFER_TEXT,
        "good",
        db_probability=p,
        db_icdr_grade=final_grade,
    )
