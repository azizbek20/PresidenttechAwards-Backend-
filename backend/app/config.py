"""Configuration (spec §4.9, C9), unfrozen for the Claude migration (plan §3.2).

Mode enforcement, no silent fallback:
  * ``EYE_MODE=demo``   — the mock engine is allowed; every response carries
    ``mode="demo"`` and ``model_version="mock-v0"`` so it can never be mistaken
    for a live model. ``demo`` + ``claude`` is allowed for local trials.
  * ``EYE_MODE=shadow`` — never ``mock``. With ``torch`` (legacy, always 503
    now) it still requires ``EYE_MODEL_SHA256``; with ``claude`` it requires a
    non-empty ``EYE_API_KEY``. Without a loaded model (no checkpoint, or no
    ``ANTHROPIC_API_KEY``), ``/health/ready`` stays 503 and
    ``/api/v1/predict`` returns 503 ``model_unavailable``. It never serves
    mock output.

The v1 ``auto`` model source is DELETED (C9): silently degrading to mock
predictions in a live deployment is a safety failure, not a convenience.

DEVICE SELECTION (orchestrator addendum) — the delivered spec file ends at §9
and contains no §10 macOS/MPS addendum, so the device contract is pinned here
from the operator instructions instead:
  * ``EYE_DEVICE=cpu`` (default) — tests, CI, Docker and every gate assertion
    run on cpu, always. Deterministic and portable.
  * ``EYE_DEVICE=mps``  — Apple-silicon dev runs only. Never gates anything.
  * ``EYE_DEVICE=auto`` — mps when actually available, else cpu with a WARNING.
Since the Claude migration's Phase 1 no engine reads ``EYE_DEVICE``; the field
stays because ``tests/test_frozen_kit.py`` pins its ``cpu`` default.
``EYE_MODEL_SOURCE=torch`` is likewise a legacy value (always 503, plan §3.2).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
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
    eye_model_source: Literal["mock", "torch", "claude"] = Field(
        default="mock", alias="EYE_MODEL_SOURCE"
    )
    eye_model_dir: Path = Field(default=Path("./models"), alias="EYE_MODEL_DIR")
    eye_model_sha256: str | None = Field(default=None, alias="EYE_MODEL_SHA256")
    eye_model_version: str = Field(default="mock-v0", alias="EYE_MODEL_VERSION")
    eye_device: Literal["cpu", "mps", "auto"] = Field(default="cpu", alias="EYE_DEVICE")
    engine_input_size: int = Field(default=224, ge=64, le=1024, alias="EYE_INPUT_SIZE")

    # ---- Claude engine (plan §3.2) ---------------------------------------
    #: Optional at boot: a missing key is a runtime 503, not a refusal to start.
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    #: The ONLY place a model id is written down (backend/CLAUDE.md).
    claude_model: str = Field(default="claude-sonnet-5-5", alias="CLAUDE_MODEL")
    claude_timeout_s: float = Field(
        default=25.0, gt=0.0, le=300.0, alias="CLAUDE_TIMEOUT_S"
    )
    claude_max_tokens: int = Field(
        default=800, ge=1, le=128_000, alias="CLAUDE_MAX_TOKENS"
    )
    #: Selects app/inference/prompts/fundus_<version>.md; also part of
    #: model_version, so bump it whenever the prompt changes.
    prompt_version: str = Field(
        default="v1", pattern=r"^[A-Za-z0-9_-]+$", alias="PROMPT_VERSION"
    )
    uncertain_refers: bool = Field(default=True, alias="UNCERTAIN_REFERS")

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
    #: ``local`` = files under ``storage_dir`` served at /static (default);
    #: ``blob`` = Vercel Blob, nothing written locally (plan §3.8).
    eye_storage: Literal["local", "blob"] = Field(default="local", alias="EYE_STORAGE")

    @field_validator("database_url", mode="after")
    @classmethod
    def _psycopg_scheme(cls, url: str) -> str:
        """Providers hand out ``postgres://``/``postgresql://`` (issue 7).

        SQLAlchemy 2 reads those as the psycopg2 driver, which is not
        installed; the project ships psycopg 3, so the scheme is rewritten.
        Everything after the scheme is kept byte-for-byte.
        """
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @model_validator(mode="after")
    def _enforce_mode(self) -> "Settings":
        """Shadow mode must be incapable of serving a mock prediction (C9).

        A shadow deployment wired to the mock engine is a configuration error we
        refuse to boot with — unlike a *missing checkpoint*, which is a runtime
        condition the API reports as 503 ``model_unavailable``.
        """
        if self.eye_mode == "shadow":
            if self.eye_model_source == "mock":
                raise ValueError(
                    "EYE_MODE=shadow cannot use EYE_MODEL_SOURCE=mock — "
                    "shadow mode must never serve mock output (C9)."
                )
            if self.eye_model_source == "torch" and not self.eye_model_sha256:
                raise ValueError(
                    "EYE_MODE=shadow requires EYE_MODEL_SHA256 so the artifact "
                    "digest can be verified before loading (C1/C9)."
                )
            if self.eye_model_source == "claude" and not (self.eye_api_key or "").strip():
                # Issue 8: an empty key disables auth with only a warning; a
                # live deployment must refuse to start that way instead.
                raise ValueError(
                    "EYE_MODE=shadow with EYE_MODEL_SOURCE=claude requires a "
                    "non-empty EYE_API_KEY — /api/v1 must never run "
                    "unauthenticated in a live deployment."
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
