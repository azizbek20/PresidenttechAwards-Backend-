"""Builders for ``FundusAssessment`` values.

``app`` is imported inside the function on purpose: the frozen conftest purges
and re-imports ``app.*`` per test, so a module-level import would bind to a
discarded module tree.
"""

from __future__ import annotations

from typing import Any

LESION_NAMES = (
    "microaneurysms",
    "retinal_hemorrhages",
    "hard_exudates",
    "cotton_wool_spots",
    "venous_beading",
    "irma",
    "neovascularization",
    "preretinal_or_vitreous_hemorrhage",
)


def make_assessment(lesions: dict[str, str] | None = None, **overrides: Any) -> Any:
    """A clean, gradable fundus assessment; override any field per test.

    ``lesions={"irma": "present"}`` changes single lesions; every other keyword
    replaces a top-level field (``icdr_grade=3``, ``image_type="other"`` ...).
    """
    from app.inference.assessment import FundusAssessment, Lesions

    lesion_values = {name: "absent" for name in LESION_NAMES}
    lesion_values.update(lesions or {})
    fields: dict[str, Any] = {
        "image_type": "fundus",
        "gradable": True,
        "quality_issues": [],
        "lesions": Lesions(**lesion_values),
        "hemorrhages_in_all_4_quadrants": False,
        "macular_edema_signs": "absent",
        "icdr_grade": 0,
        "referable_probability": 0.1,
        "rationale": "No diabetic lesions are visible.",
    }
    fields.update(overrides)
    return FundusAssessment(**fields)
