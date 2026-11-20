"""Wire schema of ``/api/v1/analyze`` — independent of the frozen DR contract.

No nullable fields: absent optional values are sent as ``""`` so a client can
never crash on a ``null`` (same rule the DR contract follows).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "ungradable"]


class FindingOut(BaseModel):
    code: str
    label: str
    probability: float = Field(ge=0.0, le=1.0)
    risk: Literal["low", "medium", "high"]


class AnalyzeResponse(BaseModel):
    analysis_id: str
    analysis_type: str
    analysis_label: str
    patient_id: str
    body_site: str
    risk_level: RiskLevel
    top_finding: str  # condition code, "" when ungradable
    top_label: str
    probability: float = Field(ge=0.0, le=1.0)
    findings: list[FindingOut]  # sorted by probability desc, empty when ungradable
    recommendation: str
    quality: Literal["good", "poor"]
    image_url: str
    model_version: str
    processed_at: str
    disclaimer: str
    is_demo: bool  # True when the result came from the mock analyser
    request_id: str
    mode: Literal["demo", "shadow"]


class AnalysisTypeOut(BaseModel):
    code: str
    label: str
    description: str
    asks_body_site: bool
    model_ready: bool  # a real model file is installed for this type
    conditions: list[str]  # Uzbek labels, catalogue order
