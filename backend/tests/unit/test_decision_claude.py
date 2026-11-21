"""`decide_from_assessment` — one table per rule of plan §3.5.

`app` is imported inside helpers: the frozen conftest purges `app.*` between
tests, so module-level imports would bind to a stale module tree.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes.assessments import make_assessment

NOT_FUNDUS_TEXT = (
    "Bu ko'z tubi (fundus) rasmi emas — fundus kamera yoki adapter bilan oling"
)
GENERIC_UNGRADABLE_TEXT = "Sifatsiz rasm — qayta suratga oling"
REFER_TEXT = "Referable DR — oftalmologga yuboring"
NO_REFER_TEXT = "Referable DR aniqlanmadi — 12 oydan keyin qayta tekshiruv"
UNGRADABLE_LABEL = "Baholab bo'lmadi"
LABELS = {
    0: "DR yo'q",
    1: "Yengil NPDR",
    2: "O'rtacha NPDR",
    3: "Og'ir NPDR",
    4: "Proliferativ DR",
}

GRADE_2_PLUS_LESIONS = (
    "retinal_hemorrhages",
    "hard_exudates",
    "cotton_wool_spots",
    "venous_beading",
    "irma",
    "neovascularization",
    "preretinal_or_vitreous_hemorrhage",
)


def run(
    a: Any,
    *,
    quality_ok: bool = True,
    threshold: float = 0.5,
    uncertain_refers: bool = True,
) -> Any:
    from app.inference.decision import decide_from_assessment

    return decide_from_assessment(a, quality_ok, threshold, uncertain_refers)


def assert_ungradable(r: Any, text: str) -> None:
    assert r.decision == "UNGRADABLE"
    assert r.referable is False
    assert r.quality == "poor"
    assert r.decision_text == text
    # C3: the wire carries placeholders, the DB carries NULL.
    assert r.probability == 0.0
    assert r.icdr_grade == 0
    assert r.grade_label == UNGRADABLE_LABEL
    assert r.db_probability is None
    assert r.db_icdr_grade is None


# --------------------------------------------------------------------------
# rule 1 — gate failure / no assessment == decide(None, False, threshold)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("threshold", [0.0, 0.35, 0.5, 1.0])
def test_rule1_gate_failure_equals_the_frozen_decide(threshold: float) -> None:
    from app.inference.decision import decide

    expected = decide(None, False, threshold)
    got = run(
        make_assessment(icdr_grade=4, referable_probability=0.99),
        quality_ok=False,
        threshold=threshold,
    )
    assert got == expected


@pytest.mark.parametrize("quality_ok", [True, False])
def test_rule1_no_assessment_equals_the_frozen_decide(quality_ok: bool) -> None:
    from app.inference.decision import decide

    assert run(None, quality_ok=quality_ok) == decide(None, False, 0.5)


def test_rule1_gate_failure_text_is_the_generic_one() -> None:
    assert_ungradable(run(None, quality_ok=False), GENERIC_UNGRADABLE_TEXT)


# --------------------------------------------------------------------------
# rule 2 — not a fundus image
# --------------------------------------------------------------------------
@pytest.mark.parametrize("image_type", ["external_eye", "other"])
@pytest.mark.parametrize("gradable", [True, False])
def test_rule2_non_fundus_is_ungradable_with_the_fundus_text(
    image_type: str, gradable: bool
) -> None:
    a = make_assessment(
        image_type=image_type,
        gradable=gradable,
        icdr_grade=4,
        referable_probability=0.95,
        quality_issues=["blur"],
    )
    assert_ungradable(run(a), NOT_FUNDUS_TEXT)


# --------------------------------------------------------------------------
# rule 3 — not gradable
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("issues", "reasons"),
    [
        (["blur"], "rasm xira"),
        (["too_dark"], "juda qorong'i"),
        (["overexposed"], "juda yorug'"),
        (["small_field"], "ko'z tubi to'liq ko'rinmaydi"),
        (["obstruction"], "to'siq bor"),
        (["blur", "too_dark"], "rasm xira, juda qorong'i"),
        (
            ["overexposed", "small_field", "obstruction"],
            "juda yorug', ko'z tubi to'liq ko'rinmaydi, to'siq bor",
        ),
    ],
)
def test_rule3_ungradable_lists_the_reasons(issues: list[str], reasons: str) -> None:
    a = make_assessment(gradable=False, quality_issues=issues)
    assert_ungradable(run(a), f"Baholab bo'lmadi: {reasons} — qayta suratga oling")


def test_rule3_empty_issue_list_uses_the_generic_text() -> None:
    a = make_assessment(gradable=False, quality_issues=[])
    assert_ungradable(run(a), GENERIC_UNGRADABLE_TEXT)


def test_rule3_ungradable_wins_over_lesions_and_grade() -> None:
    a = make_assessment(
        gradable=False,
        quality_issues=["blur"],
        lesions={"neovascularization": "present"},
        icdr_grade=4,
        referable_probability=0.99,
    )
    assert run(a).decision == "UNGRADABLE"


def test_rule3_quality_issues_alone_do_not_make_a_gradable_image_ungradable() -> None:
    a = make_assessment(gradable=True, quality_issues=["blur"])
    assert run(a).decision == "NO_REFER"


# --------------------------------------------------------------------------
# rule 4 + 5 — rule grade from lesions, final = max(claude, rule)
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("lesion", "grade"),
    [
        ("neovascularization", 4),
        ("preretinal_or_vitreous_hemorrhage", 4),
        ("venous_beading", 3),
        ("irma", 3),
        ("retinal_hemorrhages", 2),
        ("hard_exudates", 2),
        ("cotton_wool_spots", 2),
        ("microaneurysms", 1),
    ],
)
def test_rule4_present_lesion_sets_the_rule_grade(lesion: str, grade: int) -> None:
    r = run(make_assessment(lesions={lesion: "present"}, icdr_grade=0))
    assert r.icdr_grade == grade
    assert r.grade_label == LABELS[grade]


def test_rule4_four_quadrant_hemorrhages_is_grade_3() -> None:
    r = run(make_assessment(hemorrhages_in_all_4_quadrants=True, icdr_grade=0))
    assert r.icdr_grade == 3
    assert r.decision == "REFER"


def test_rule4_clean_image_is_grade_0() -> None:
    r = run(make_assessment())
    assert r.icdr_grade == 0
    assert r.grade_label == LABELS[0]


@pytest.mark.parametrize("presence", ["absent", "uncertain"])
def test_rule4_only_present_counts_for_the_rule_grade(presence: str) -> None:
    r = run(
        make_assessment(
            lesions={"neovascularization": presence, "microaneurysms": presence}
        ),
        uncertain_refers=False,
    )
    assert r.icdr_grade == 0


@pytest.mark.parametrize(
    ("claude_grade", "lesions", "quadrants", "expected"),
    [
        (3, {"microaneurysms": "present"}, False, 3),
        (1, {"irma": "present"}, False, 3),
        (0, {"neovascularization": "present"}, False, 4),
        (4, {}, False, 4),
        (4, {"microaneurysms": "present"}, False, 4),
        (2, {"hard_exudates": "present"}, False, 2),
        (1, {}, True, 3),
        (3, {}, True, 3),
    ],
)
def test_rule5_final_grade_is_the_max(
    claude_grade: int,
    lesions: dict[str, str],
    quadrants: bool,
    expected: int,
) -> None:
    a = make_assessment(
        lesions=lesions,
        hemorrhages_in_all_4_quadrants=quadrants,
        icdr_grade=claude_grade,
    )
    assert run(a).icdr_grade == expected


# --------------------------------------------------------------------------
# rule 6 — when to refer
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("grade", "decision"),
    [(0, "NO_REFER"), (1, "NO_REFER"), (2, "REFER"), (3, "REFER"), (4, "REFER")],
)
def test_rule6_refer_from_grade_two_up(grade: int, decision: str) -> None:
    r = run(make_assessment(icdr_grade=grade))
    assert r.decision == decision
    assert r.referable is (decision == "REFER")


@pytest.mark.parametrize("edema", ["present", "uncertain"])
@pytest.mark.parametrize("grade", [0, 1])
def test_rule6_edema_refers_and_the_wire_keeps_the_low_grade(
    edema: str, grade: int
) -> None:
    r = run(
        make_assessment(macular_edema_signs=edema, icdr_grade=grade),
        uncertain_refers=False,
    )
    assert r.decision == "REFER"
    assert r.referable is True
    assert r.icdr_grade == grade
    assert r.grade_label == LABELS[grade]


def test_rule6_edema_absent_does_not_refer() -> None:
    assert run(make_assessment(macular_edema_signs="absent")).decision == "NO_REFER"


@pytest.mark.parametrize("lesion", GRADE_2_PLUS_LESIONS)
def test_rule6_uncertain_grade2_lesion_refers_when_configured(lesion: str) -> None:
    a = make_assessment(lesions={lesion: "uncertain"}, icdr_grade=0)
    r = run(a, uncertain_refers=True)
    assert r.decision == "REFER"
    # Uncertain is not "present": the grade itself is not raised.
    assert r.icdr_grade == 0


@pytest.mark.parametrize("lesion", GRADE_2_PLUS_LESIONS)
def test_rule6_uncertain_grade2_lesion_is_ignored_when_not_configured(
    lesion: str,
) -> None:
    a = make_assessment(lesions={lesion: "uncertain"}, icdr_grade=0)
    assert run(a, uncertain_refers=False).decision == "NO_REFER"


@pytest.mark.parametrize("uncertain_refers", [True, False])
def test_rule6_uncertain_microaneurysms_never_refers(uncertain_refers: bool) -> None:
    a = make_assessment(lesions={"microaneurysms": "uncertain"}, icdr_grade=1)
    r = run(a, uncertain_refers=uncertain_refers)
    assert r.decision == "NO_REFER"
    assert r.icdr_grade == 1


def test_rule6_edema_uncertain_refers_regardless_of_the_uncertain_flag() -> None:
    a = make_assessment(macular_edema_signs="uncertain")
    assert run(a, uncertain_refers=False).decision == "REFER"


# --------------------------------------------------------------------------
# rule 7 — probability clamp and rounding
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("grade", "p", "threshold", "expected"),
    [
        # REFER: raised up to the threshold, never lowered
        (3, 0.1, 0.5, 0.5),
        (3, 0.0, 0.5, 0.5),
        (3, 0.5, 0.5, 0.5),
        (3, 0.9, 0.5, 0.9),
        (3, 0.2, 0.7, 0.7),
        # NO_REFER: capped strictly below the threshold, never negative
        (0, 0.9, 0.5, 0.4999),
        (0, 0.5, 0.5, 0.4999),
        (0, 0.3, 0.5, 0.3),
        (0, 1.0, 0.7, 0.6999),
        (0, 0.0, 0.5, 0.0),
        (0, 0.4, 0.0, 0.0),
        (0, 0.4, 1.0, 0.4),
        # rounding to 4 places
        (0, 0.123456, 0.5, 0.1235),
        (3, 0.87654, 0.5, 0.8765),
    ],
)
def test_rule7_probability_clamp(
    grade: int, p: float, threshold: float, expected: float
) -> None:
    r = run(
        make_assessment(icdr_grade=grade, referable_probability=p),
        threshold=threshold,
    )
    assert r.probability == expected


@pytest.mark.parametrize("p", [0.0, 0.2, 0.49, 0.5, 0.8, 1.0])
@pytest.mark.parametrize("grade", [0, 1, 2, 4])
def test_rule7_probability_never_contradicts_the_decision(
    grade: int, p: float
) -> None:
    threshold = 0.5
    r = run(
        make_assessment(icdr_grade=grade, referable_probability=p),
        threshold=threshold,
    )
    if r.decision == "REFER":
        assert r.probability >= threshold
    else:
        assert 0.0 <= r.probability < threshold


# --------------------------------------------------------------------------
# rule 8 — texts, labels, quality
# --------------------------------------------------------------------------
@pytest.mark.parametrize("grade", [0, 1, 2, 3, 4])
def test_rule8_label_text_and_quality(grade: int) -> None:
    r = run(make_assessment(icdr_grade=grade))
    refer = grade >= 2
    assert r.grade_label == LABELS[grade]
    assert r.decision == ("REFER" if refer else "NO_REFER")
    assert r.decision_text == (REFER_TEXT if refer else NO_REFER_TEXT)
    assert r.quality == "good"


def test_rule8_labels_match_the_frozen_table() -> None:
    from app.inference.decision import GRADE_LABELS

    assert dict(GRADE_LABELS) == LABELS


# --------------------------------------------------------------------------
# rule 9 — C3 split
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "build",
    [
        lambda: None,
        lambda: make_assessment(image_type="other"),
        lambda: make_assessment(gradable=False, quality_issues=["blur"]),
    ],
    ids=["no-assessment", "non-fundus", "not-gradable"],
)
def test_rule9_ungradable_wire_placeholders_and_db_nulls(build: Any) -> None:
    r = run(build())
    assert r.decision == "UNGRADABLE"
    assert (r.probability, r.icdr_grade, r.grade_label) == (0.0, 0, UNGRADABLE_LABEL)
    assert (r.db_probability, r.db_icdr_grade) == (None, None)


@pytest.mark.parametrize("grade", [0, 2, 4])
def test_rule9_graded_db_values_mirror_the_wire(grade: int) -> None:
    r = run(make_assessment(icdr_grade=grade, referable_probability=0.31))
    assert r.db_probability == r.probability
    assert r.db_icdr_grade == r.icdr_grade == grade


def test_graded_results_are_good_quality_and_ungradable_are_poor() -> None:
    assert run(make_assessment()).quality == "good"
    assert run(make_assessment(gradable=False)).quality == "poor"
    assert run(make_assessment(image_type="other")).quality == "poor"
    assert run(None, quality_ok=False).quality == "poor"
