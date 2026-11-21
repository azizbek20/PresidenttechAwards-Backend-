"""Structured output Claude returns for one fundus photo (MIGRATION_PLAN.md §3.4).

The Anthropic structured-output schema is generated from these models, so the
API guarantees the *shape*. It does not enforce numeric ranges, so
``icdr_grade`` (0..4) and ``referable_probability`` (0..1) are checked locally
in :mod:`app.inference.claude_engine`; anything else is a 500, never a verdict.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Presence = Literal["present", "absent", "uncertain"]
QualityIssue = Literal["blur", "too_dark", "overexposed", "small_field", "obstruction"]


class Lesions(BaseModel):
    microaneurysms: Presence
    retinal_hemorrhages: Presence
    hard_exudates: Presence
    cotton_wool_spots: Presence
    venous_beading: Presence
    irma: Presence
    neovascularization: Presence
    preretinal_or_vitreous_hemorrhage: Presence


class FundusAssessment(BaseModel):
    image_type: Literal["fundus", "external_eye", "other"]
    gradable: bool
    quality_issues: list[QualityIssue]
    lesions: Lesions
    hemorrhages_in_all_4_quadrants: bool
    macular_edema_signs: Presence
    icdr_grade: int  # 0..4, checked locally
    referable_probability: float  # 0..1, checked locally
    rationale: str  # max 2 sentences; logs/admin only
