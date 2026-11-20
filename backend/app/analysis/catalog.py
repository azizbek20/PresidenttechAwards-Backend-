"""Catalogue of the non-fundus analysis types (external eye, skin, oral, nail).

This is a *separate* product line from the frozen DR screening contract
(``app/schemas.py``): it has its own endpoint (``POST /api/v1/analyze``), its
own wire schema and its own table, so nothing here can change what the
deployed APK reads from ``/api/v1/predict``.

Each condition lists, in a fixed order, the classes a real model for that
type must output (``models/analysis/<type>.onnx`` → logits in exactly this
order). The ``cue`` is used only by the demo mock analyser to pick a
plausible-looking finding from simple colour statistics; it carries no
clinical meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Risk = Literal["low", "medium", "high"]
Cue = Literal["normal", "red", "yellow", "dark", "pale"]


@dataclass(frozen=True)
class Condition:
    code: str
    label: str  # Uzbek, shown verbatim on the phone
    risk: Risk
    cue: Cue


@dataclass(frozen=True)
class AnalysisType:
    code: str
    label: str
    description: str
    specialist: str  # who to refer to, Uzbek, used in the recommendation text
    conditions: tuple[Condition, ...]
    #: Whether the client should ask for a body site (e.g. "chap bilak").
    asks_body_site: bool = False


ANALYSIS_TYPES: tuple[AnalysisType, ...] = (
    AnalysisType(
        code="external_eye",
        label="Ko'zning tashqi ko'rinishi",
        description="Oddiy kamera bilan olingan ko'z rasmi: gavhar xiraligi, qizarish, sarg'ayish",
        specialist="oftalmolog",
        conditions=(
            Condition("normal", "Sezilarli o'zgarish topilmadi", "low", "normal"),
            Condition("conjunctivitis", "Kon'yunktivit belgilari (qizarish)", "medium", "red"),
            Condition("scleral_icterus", "Ko'z oqining sarg'ayishi (sariqlik belgisi)", "high", "yellow"),
            Condition("cataract", "Katarakta belgilari (gavhar xiraligi)", "medium", "pale"),
            Condition("pterygium", "Pterigium (ko'z oqida o'simta)", "medium", "dark"),
        ),
    ),
    AnalysisType(
        code="skin",
        label="Teri",
        description="Teri dog'lari, xollar va toshmalar",
        specialist="dermatolog",
        conditions=(
            Condition("normal", "Sezilarli o'zgarish topilmadi", "low", "normal"),
            Condition("benign_nevus", "Xavfsiz ko'rinishdagi xol (nevus)", "low", "pale"),
            Condition("eczema_dermatitis", "Ekzema / dermatit belgilari", "medium", "red"),
            Condition("fungal_infection", "Zamburug'li infeksiya belgilari", "medium", "yellow"),
            Condition("melanoma_suspect", "Melanomaga shubhali dog'", "high", "dark"),
        ),
        asks_body_site=True,
    ),
    AnalysisType(
        code="oral",
        label="Og'iz bo'shlig'i va til",
        description="Til, milk va og'iz shilliq qavati",
        specialist="stomatolog",
        conditions=(
            Condition("normal", "Sezilarli o'zgarish topilmadi", "low", "normal"),
            Condition("gingivitis", "Milk yallig'lanishi (gingivit)", "medium", "red"),
            Condition("candidiasis", "Og'iz kandidozi (oq karash)", "medium", "pale"),
            Condition("coated_tongue", "Til karashi", "low", "yellow"),
            Condition("leukoplakia_suspect", "Leykoplakiyaga shubha", "high", "dark"),
        ),
    ),
    AnalysisType(
        code="nail",
        label="Tirnoq",
        description="Qo'l va oyoq tirnoqlari",
        specialist="dermatolog yoki terapevt",
        conditions=(
            Condition("normal", "Sezilarli o'zgarish topilmadi", "low", "normal"),
            Condition("onychomycosis", "Tirnoq zamburug'i (onixomikoz)", "medium", "yellow"),
            Condition("pallor", "Tirnoq oqarishi (kamqonlik belgisi bo'lishi mumkin)", "medium", "pale"),
            Condition("paronychia", "Tirnoq atrofi yallig'lanishi (paronixiya)", "medium", "red"),
            Condition("subungual_melanoma_suspect", "Tirnoq ostidagi qora chiziq (melanomaga shubha)", "high", "dark"),
        ),
    ),
)

_BY_CODE: dict[str, AnalysisType] = {t.code: t for t in ANALYSIS_TYPES}

#: Accepted ``analysis_type`` values, in catalogue order.
TYPE_CODES: tuple[str, ...] = tuple(_BY_CODE)


def get_type(code: str) -> AnalysisType | None:
    return _BY_CODE.get(code)


def recommendation(analysis_type: AnalysisType, risk: str) -> str:
    """Uzbek, user-visible advice for the overall risk level."""
    who = analysis_type.specialist
    if risk == "high":
        return f"Imkon qadar tezroq {who} ko'rigiga yuboring."
    if risk == "medium":
        return f"Rejali ravishda {who} ko'rigiga yuborish tavsiya etiladi."
    if risk == "low":
        return "Shoshilinch yo'llanma talab qilinmaydi. O'zgarish kuzatilsa, qayta tekshiring."
    return "Rasm sifati yetarli emas — yorug' joyda, yaqinroqdan va aniq qilib qayta suratga oling."


ANALYSIS_DISCLAIMER = (
    "Bu skrining vositasi, tashxis emas. Yakuniy xulosani tegishli mutaxassis beradi."
)
