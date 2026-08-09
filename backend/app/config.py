"""Frozen configuration (spec §4.9, C9). DO NOT EDIT.

Mode enforcement, no silent fallback:
  * ``EYE_MODE=demo``   — the mock engine is allowed; every response carries
    ``mode="demo"`` and ``model_version="mock-v0"`` so it can never be mistaken
    for a live model.
  * ``EYE_MODE=shadow`` — requires ``EYE_MODEL_SOURCE=torch`` *and* a
    digest-verified artifact. Without a loaded model, ``/health/ready`` stays
    503 and ``/api/v1/predict`` returns 503 ``model_unavailable``. It never
    serves mock output.

The v1 ``auto`` model source is DELETED (C9): silently degrading to mock
predictions in a live deployment is a safety failure, not a convenience.

DEVICE SELECTION (orchestrator addendum) — the delivered spec file ends at §9
and contains no §10 macOS/MPS addendum, so the device contract is pinned here
from the operator instructions instead:
  * ``EYE_DEVICE=cpu`` (default) — tests, CI, Docker and every gate assertion
    run on cpu, always. Deterministic and portable.
  * ``EYE_DEVICE=mps``  — Apple-silicon dev runs only. Never gates anything.
  * ``EYE_DEVICE=auto`` — mps when actually available, else cpu with a WARNING.
Grad-CAM always runs on cpu regardless of this setting (see gradcam.py).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Which dotenv file to load, if any. Production leaves this unset and gets
#: ``.env``. Setting ``EYE_ENV_FILE=""`` disables dotenv loading entirely — the
#: test suite does exactly that, because `monkeypatch.delenv("EYE_API_KEY")`
#: only removes the *environment* source and a developer's backend/.env would
#: then silently re-supply the key (and the threshold, and the mode...).
_ENV_FILE = os.getenv("EYE_ENV_FILE", ".env") or None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- mode / model ----------------------------------------------------
    eye_mode: Literal["demo", "shadow"] = Field(default="demo", alias="EYE_MODE")
    eye_model_source: Literal["mock", "torch"] = Field(
        default="mock", alias="EYE_MODEL_SOURCE"
    )
    eye_model_dir: Path = Field(default=Path("./models"), alias="EYE_MODEL_DIR")
    eye_model_sha256: str | None = Field(default=None, alias="EYE_MODEL_SHA256")
    eye_model_version: str = Field(default="mock-v0", alias="EYE_MODEL_VERSION")
    eye_device: Literal["cpu", "mps", "auto"] = Field(default="cpu", alias="EYE_DEVICE")
    engine_input_size: int = Field(default=224, ge=64, le=1024, alias="EYE_INPUT_SIZE")

    # ---- api -------------------------------------------------------------
    eye_api_key: str | None = Field(default=None, alias="EYE_API_KEY")
    max_upload_mb: int = Field(default=10, ge=1, le=100, alias="MAX_UPLOAD_MB")
    inference_concurrency: int = Field(
        default=2, ge=1, le=32, alias="INFERENCE_CONCURRENCY"
    )
    dedup_window_min: int = Field(default=10, ge=0, le=1440, alias="DEDUP_WINDOW_MIN")

    # ---- clinical thresholds (server-side only — the client never re-derives) --
    referable_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0, alias="EYE_REFERABLE_THRESHOLD"
    )
    quality_blur_min_var: float = Field(
        default=50.0, ge=0.0, alias="QUALITY_BLUR_MIN_VAR"
    )

    # ---- infra -----------------------------------------------------------
    database_url: str = Field(default="sqlite:///./eye.db", alias="DATABASE_URL")
    storage_dir: Path = Field(default=Path("./storage"), alias="EYE_STORAGE_DIR")

    @model_validator(mode="after")
    def _enforce_mode(self) -> "Settings":
        """Shadow mode must be incapable of serving a mock prediction (C9).

        A shadow deployment wired to the mock engine is a configuration error we
        refuse to boot with — unlike a *missing checkpoint*, which is a runtime
        condition the API reports as 503 ``model_unavailable``.
        """
        if self.eye_mode == "shadow":
            if self.eye_model_source != "torch":
                raise ValueError(
                    "EYE_MODE=shadow requires EYE_MODEL_SOURCE=torch — "
                    "shadow mode must never serve mock output (C9)."
                )
            if not self.eye_model_sha256:
                raise ValueError(
                    "EYE_MODE=shadow requires EYE_MODEL_SHA256 so the artifact "
                    "digest can be verified before loading (C1/C9)."
                )
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def images_dir(self) -> Path:
        return self.storage_dir / "images"

    @property
    def heatmaps_dir(self) -> Path:
        return self.storage_dir / "heatmaps"


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton.

    Tests that mutate the environment must call ``get_settings.cache_clear()``
    before constructing the app.
    """
    return Settings()  # type: ignore[call-arg]
