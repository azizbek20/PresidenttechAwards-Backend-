# EYE DETECT AI backend — SPEC.md §5-D / D1
#
# Multi-stage, non-root (uid 10001), single worker, HEALTHCHECK on /health/ready.
# Builds natively for the host architecture. On this Apple-silicon dev machine
# that is linux/arm64 — NEVER pass `--platform amd64`; emulated builds are slow
# and native aarch64 wheels exist upstream for every dependency.
#
# The image must build with NO model weights present (`models/` is bind-mounted
# read-only at run time), so nothing here touches the network for artifacts.

# ---------------------------------------------------------------------------
# Stage 1 — builder: resolve wheels into a self-contained virtualenv.
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# build-essential is only needed here; it never reaches the runtime image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip setuptools wheel

WORKDIR /build
COPY requirements.txt requirements-admin.txt ./

# Everything from PyPI. Torch and grad-cam are gone (migration Phase 1), and
# with grad-cam went the GUI `opencv-python` it used to drag in, so no
# uninstall/reinstall fix is needed any more. The admin service runs from this
# image (docker-compose.yml), so its requirements are installed too.
RUN pip install -r requirements.txt -r requirements-admin.txt

# Fail the BUILD, not production, if a GUI OpenCV ever sneaks back in (slim
# images ship no libGL). Repeated in the runtime stage, which is what ships.
RUN python -c "import cv2; print('cv2', cv2.__version__)"

# ---------------------------------------------------------------------------
# Stage 2 — runtime.
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

# libgomp1: OpenMP runtime (was required by torch; kept until the image is
# re-verified without it). libglib2.0-0: still dlopened by the headless OpenCV
# wheel. Deliberately NO libgl1 — a GUI OpenCV must fail loudly, not hide.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EYE_MODE=demo \
    EYE_MODEL_SOURCE=mock \
    EYE_DEVICE=cpu \
    EYE_STORAGE_DIR=/app/storage \
    EYE_MODEL_DIR=/app/models

COPY --from=builder /opt/venv /opt/venv

# The guard that counts: this stage has the SHIPPED system libraries, so it is
# where a re-introduced `opencv-python` would blow up with
# `libGL.so.1: cannot open shared object file`. onnxruntime (the /analyze skin
# model) and streamlit (the admin service) must import here too.
RUN python -c "import cv2, onnxruntime, streamlit; print('cv2', cv2.__version__, '| onnxruntime', onnxruntime.__version__)"

WORKDIR /app

# SPEC.md D1: the admin service runs admin/dashboard.py from THIS image, so
# admin/ must exist inside it (the v1 Dockerfile copied only app/ and the admin
# container crashed on startup). scripts/ ships too so smoke_test.sh and
# make_test_images.py can run from the container in CI.
#
# NOTE: written as three COPY lines on purpose. The single-line form
# `COPY app/ admin/ scripts/ ./` FLATTENS — Docker copies the *contents* of
# each source directory into the destination, so app/main.py would land at
# /app/main.py and `uvicorn app.main:app` could never import.
COPY app/    ./app/
COPY admin/  ./admin/
COPY scripts/ ./scripts/

# Non-root. Storage and model mountpoints are pre-created and owned so the
# read-only models bind and the storage volume both work without a chown at
# container start.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin eyeapp && \
    mkdir -p /app/storage/images /app/storage/heatmaps /app/models /app/data && \
    chown -R 10001:10001 /app

USER 10001

EXPOSE 8000

# /health/ready is the real readiness contract (DB pings, storage writable,
# and in shadow mode a digest-verified model). /health/live would be useless
# as a container gate — it is 200 even when the app cannot serve.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4).status == 200 else 1)"

# --workers 1: the inference semaphore and the dedup window are per-process
# state; a second worker would silently double the concurrency budget.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
