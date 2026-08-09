"""Contract-suite setup: install the pre-merge import shim, add helpers.

Nothing here weakens an assertion — the shim only supplies modules that do not
exist on this branch yet (see `_shim.py`), and it disables itself once Agents
A and B merge.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tests.contract import _shim

_shim.install()

#: The wire timestamp format the Android client parses (§5-C C6).
PROCESSED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

#: C2's server-generated patient code.
PATIENT_CODE_RE = re.compile(r"^P-[0-9A-F]{6}$")


def upload(
    raw: bytes,
    *,
    name: str = "eye.jpg",
    content_type: str = "image/jpeg",
) -> dict[str, Any]:
    """The multipart `files=` payload every predict test posts."""
    return {"file": (name, raw, content_type)}


@pytest.fixture
def post_predict(client: Any) -> Any:
    """`post_predict(bytes, patient_id=..., eye=...)` against the open client."""

    def _post(raw: bytes, **form: Any) -> Any:
        data = {k: v for k, v in form.items() if v is not None}
        return client.post("/api/v1/predict", files=upload(raw), data=data)

    return _post
