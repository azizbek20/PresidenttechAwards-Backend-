#!/usr/bin/env python3
"""Write the five deterministic smoke-test inputs into ``scripts/out/``.

SPEC.md §5-D D2. Run from ``backend/``::

    python scripts/make_test_images.py

Files produced (5):

===================  ==========================  ==========================
file                 what the backend must say   why
===================  ==========================  ==========================
``refer.jpg``        ``decision="REFER"``        mean gray 160 -> mock grade 4
``no_dr.jpg``        ``decision="NO_REFER"``     mean gray 100 -> mock grade 0
``blurry.jpg``       ``decision="UNGRADABLE"``   21px Gaussian -> blur gate
``dark.jpg``         ``decision="UNGRADABLE"``   mean gray 8   -> brightness gate
``not_an_image.txt`` ``400 invalid_image``       no JPEG/PNG magic bytes
===================  ==========================  ==========================

THE GENERATORS ARE IMPORTED, NEVER RE-IMPLEMENTED
-------------------------------------------------
``tests/synthetic.py`` is frozen and is the same module ``tests/conftest.py``
uses. If this script grew its own copy of the generators the two would drift,
and the smoke test and the test suite would eventually disagree about which
image is REFER — the one disagreement that would make a red/green demo
unreproducible. ``blurry.jpg`` in particular is only UNGRADABLE because the
quality gate fires *before* the engine; a re-implementation with a different
kernel could quietly turn it into a NO_REFER.

The import needs ``backend/`` on ``sys.path`` (``tests`` is a package there),
which is arranged below so the script works from any cwd. Note that ``tests/``
is excluded from the container image, so this script is a host/CI tool — the
smoke test runs against the container from outside it.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = BACKEND_ROOT / "scripts" / "out"


def main() -> int:
    # Imported inside main, after the path shim: `tests` is a package under
    # backend/, but running `python scripts/make_test_images.py` puts
    # backend/scripts on sys.path, not backend/. Doing this at module scope
    # would be a module-level import after code, which ruff flags as E402.
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    from tests.synthetic import (
        blurry_jpeg,
        dark_jpeg,
        norefer_jpeg,
        not_an_image,
        refer_jpeg,
    )

    #: name -> (generator, expected backend verdict). The verdict is console
    #: documentation for whoever runs this, not an assertion.
    files: tuple[tuple[str, Callable[[], bytes], str], ...] = (
        ("refer.jpg", refer_jpeg, "REFER"),
        ("no_dr.jpg", norefer_jpeg, "NO_REFER"),
        ("blurry.jpg", blurry_jpeg, "UNGRADABLE (blur)"),
        ("dark.jpg", dark_jpeg, "UNGRADABLE (dark)"),
        ("not_an_image.txt", not_an_image, "400 invalid_image"),
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for name, generator, expected in files:
        raw = generator()
        target = OUT_DIR / name
        target.write_bytes(raw)
        print(f"{target.relative_to(BACKEND_ROOT)}  {len(raw):>7,d} B  -> {expected}")

    print(f"\n{len(files)} files in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
