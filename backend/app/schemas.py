"""Frozen wire contract. Doc 5 §3 + Android PredictResponse.kt. DO NOT EDIT.

Verified against repo HEAD f6e4a0c:
app/src/main/java/com/eyedetect/ai/data/PredictResponse.kt declares exactly the
15 legacy keys below, with `patient_id`, `eye`, `heatmap_url`, `image_url` as
the only nullable ones. `request_id` and `mode` are C12 additive keys — the
installed APK's Gson ignores unknown fields, so adding them is safe.
"""

from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal["REFER", "NO_REFER", "UNGRADABLE"]
Eye = Literal["right", "left"]
Quality = Literal["good", "poor"]

DISCLAIMER = "Bu skrining/triaj vositasi; yakuniy tashxis oftalmolog mas'uliyati."


class PredictResponse(BaseModel):
    exam_id: str
    patient_id: str | None
    eye: Eye | None
    referable: bool
    probability: float = Field(ge=0.0, le=1.0)
    icdr_grade: int = Field(ge=0, le=4)
    grade_label: str
    decision: Decision
    decision_text: str
    quality: Quality
    heatmap_url: str | None
    image_url: str | None
    model_version: str
    processed_at: str  # ISO-8601 UTC "....Z"
    disclaimer: str
    # C12 additive keys — safe: the installed APK's Gson ignores unknown fields
    request_id: str  # uuid4 per request; also goes in server logs
    mode: Literal["demo", "shadow"]


class ExamSummary(BaseModel):
    exam_id: str
    patient_id: str | None
    eye: Eye | None
    referable: bool
    probability: float
    icdr_grade: int
    decision: Decision
    processed_at: str


class ErrorEnvelope(BaseModel):
    error: str  # invalid_image|unauthorized|not_found|payload_too_large|validation_error|inference_error|persistence_error|model_unavailable
    detail: str  # C15: USER-VISIBLE on the phone — short, human-readable Uzbek string, never a list


#: The 15 keys the deployed APK deserialises. Frozen; used by tests to prove no
#: legacy key was ever dropped or renamed.
LEGACY_KEYS: tuple[str, ...] = (
    "exam_id",
    "patient_id",
    "eye",
    "referable",
    "probability",
    "icdr_grade",
    "grade_label",
    "decision",
    "decision_text",
    "quality",
    "heatmap_url",
    "image_url",
    "model_version",
    "processed_at",
    "disclaimer",
)
