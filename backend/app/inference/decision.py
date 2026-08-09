"""Frozen decision logic (spec §4.6, C3). DO NOT EDIT.

The referable threshold lives here and ONLY here — the client never re-derives
it. C3: the wire keeps non-null placeholders for UNGRADABLE (the deployed APK
crashes on nulls) while the DB stores NULL, so future training exports stay
clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
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
