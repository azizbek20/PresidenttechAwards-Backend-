"""Read-only Streamlit admin panel — step 5 of the demo script (SPEC.md C5).

    API_URL=http://localhost:8000 EYE_API_KEY=demo123 \
        streamlit run admin/dashboard.py

DEMO-ONLY. THIS PANEL HAS NO LOGIN.
-----------------------------------
There is no authentication, no session, no per-user scoping and no audit of who
looked at what. Anyone who can reach port 8501 sees every exam. That is
acceptable *only* under C13 — this stack runs on synthetic or consented test
data until the C8 Android PHI items land — and only on a trusted LAN. Do not
port-forward it, do not point it at a deployment holding real patient data.
Per-device credentials and multi-tenant scoping are C7 pilot-phase work.

It is also strictly READ-ONLY: it issues GETs against the public API and owns
no database session. If a row is here, the API served it — which is exactly the
property the demo is meant to show, so the panel deliberately has no privileged
back channel that could make it disagree with the phone.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.getenv("EYE_API_KEY", "")
REQUEST_TIMEOUT = 15
PAGE_SIZE = 100

DECISION_BADGE = {"REFER": "🔴 REFER", "NO_REFER": "🟢 NO_REFER", "UNGRADABLE": "⚪ UNGRADABLE"}

st.set_page_config(page_title="EYE DETECT AI — admin", page_icon="👁", layout="wide")


# ---------------------------------------------------------------------------
# API access
# ---------------------------------------------------------------------------
def _headers() -> dict[str, str]:
    # Absent key = the API was started without EYE_API_KEY; sending an empty
    # header would look like a wrong key rather than like no key.
    return {"X-API-Key": API_KEY} if API_KEY else {}


def _absolute(url: str | None) -> str | None:
    """`/static/images/<id>.jpg` -> `<API_URL>/static/images/<id>.jpg`.

    The API returns *relative* media paths on purpose (C6): the app persists
    them in Room, so they must survive a change of host. Everything that
    renders them has to join them itself.
    """
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        return url
    return urljoin(API_URL + "/", url.lstrip("/"))


@st.cache_data(ttl=10, show_spinner=False)
def fetch_exams(limit: int) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{API_URL}/api/v1/exams",
        params={"limit": limit},
        headers=_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    # Tolerate both a bare list and a {"items": [...]} envelope so the panel
    # does not become the thing that blocks the demo over a wrapper key.
    if isinstance(payload, dict):
        for key in ("items", "exams", "results", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return []
    return payload if isinstance(payload, list) else []


@st.cache_data(ttl=10, show_spinner=False)
def fetch_exam(exam_id: str) -> dict[str, Any] | None:
    resp = requests.get(
        f"{API_URL}/api/v1/exams/{exam_id}",
        headers=_headers(),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# header
# ---------------------------------------------------------------------------
st.title("👁 EYE DETECT AI — admin")
st.caption(
    f"Read-only demo panel · API `{API_URL}` · "
    f"API key {'set' if API_KEY else '**not set**'} · synthetic/non-PHI data only (C13)"
)

with st.sidebar:
    st.header("Ko'rinish")
    limit = st.slider("Nechta tekshiruv", min_value=10, max_value=PAGE_SIZE, value=50, step=10)
    decision_filter = st.multiselect(
        "Qaror (decision)", options=list(DECISION_BADGE), default=[]
    )
    if st.button("🔄 Yangilash"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption(
        "Demo-only: login yo'q, faqat o'qish uchun. "
        "Haqiqiy bemor ma'lumotlari bilan ishlatilmaydi."
    )

try:
    exams = fetch_exams(limit)
except requests.RequestException as exc:
    st.error(f"API bilan bog'lanib bo'lmadi ({API_URL}): {exc}")
    st.info("Backend ishlayaptimi? `uvicorn app.main:app --port 8000` yoki `docker compose up -d api`.")
    st.stop()

# --- stats header ----------------------------------------------------------
total = len(exams)
refer_n = sum(1 for e in exams if e.get("decision") == "REFER")
ungradable_n = sum(1 for e in exams if e.get("decision") == "UNGRADABLE")


def pct(n: int) -> float:
    return (100.0 * n / total) if total else 0.0



c1, c2, c3, c4 = st.columns(4)
c1.metric("Jami tekshiruvlar", total)
c2.metric("🔴 REFER", refer_n, f"{pct(refer_n):.1f}%")
c3.metric("⚪ UNGRADABLE", ungradable_n, f"{pct(ungradable_n):.1f}%")
c4.metric("🟢 NO_REFER", total - refer_n - ungradable_n)

st.divider()

if not total:
    st.info("Hali tekshiruvlar yo'q. Telefondan bitta rasm yuboring.")
    st.stop()

rows = [e for e in exams if not decision_filter or e.get("decision") in decision_filter]
if not rows:
    st.warning("Tanlangan filtrga mos tekshiruv yo'q.")
    st.stop()


# ---------------------------------------------------------------------------
# exams table
# ---------------------------------------------------------------------------
def _table_row(e: dict[str, Any]) -> dict[str, Any]:
    return {
        "Sana (processed_at)": e.get("processed_at", ""),
        "Bemor": e.get("patient_id") or "—",
        "Ko'z": e.get("eye") or "—",
        "Qaror": DECISION_BADGE.get(str(e.get("decision")), str(e.get("decision"))),
        # UNGRADABLE carries the C3 wire placeholder 0.0; showing it as a
        # probability would imply a measurement that was never made.
        "Ehtimollik": (
            "—"
            if e.get("decision") == "UNGRADABLE"
            else f"{float(e.get('probability') or 0.0):.3f}"
        ),
        # str, not int: a column mixing "—" with ints makes Arrow guess a type,
        # log a serialisation warning and coerce it anyway.
        "ICDR": "—" if e.get("decision") == "UNGRADABLE" else str(e.get("icdr_grade", "—")),
        "Model": e.get("model_version", "—"),
        "exam_id": e.get("exam_id", ""),
    }


st.subheader(f"Tekshiruvlar ({len(rows)})")
st.dataframe(
    [_table_row(e) for e in rows],
    use_container_width=True,
    hide_index=True,
)

# ---------------------------------------------------------------------------
# row select -> original + heatmap side by side
# ---------------------------------------------------------------------------
st.subheader("Tafsilot")
labels = {
    f"{e.get('processed_at', '')} · {e.get('patient_id') or '—'} · "
    f"{e.get('eye') or '—'} · {e.get('decision')}": e.get("exam_id", "")
    for e in rows
}
chosen = st.selectbox("Tekshiruvni tanlang", options=list(labels), index=0)
exam_id = labels[chosen]

# The list endpoint returns ExamSummary, which carries no media URLs; the
# detail endpoint returns the full predict-shaped body. Fall back to the list
# row so the panel still shows something if detail is unavailable.
try:
    detail = fetch_exam(exam_id) or next((e for e in rows if e.get("exam_id") == exam_id), {})
except requests.RequestException as exc:
    st.error(f"Tafsilotni olishda xato: {exc}")
    detail = next((e for e in rows if e.get("exam_id") == exam_id), {})

meta_l, meta_r = st.columns(2)
with meta_l:
    st.write(f"**exam_id** `{detail.get('exam_id', exam_id)}`")
    st.write(f"**Bemor** {detail.get('patient_id') or '—'} · **Ko'z** {detail.get('eye') or '—'}")
    st.write(f"**Qaror** {DECISION_BADGE.get(str(detail.get('decision')), '—')}")
with meta_r:
    st.write(f"**Model** `{detail.get('model_version', '—')}` · **Rejim** `{detail.get('mode', '—')}`")
    st.write(f"**Sifat** {detail.get('quality', '—')} · **ICDR** {detail.get('grade_label', '—')}")
    st.write(f"**Vaqt** {detail.get('processed_at', '—')}")

img_col, heat_col = st.columns(2)
image_url = _absolute(detail.get("image_url"))
heatmap_url = _absolute(detail.get("heatmap_url"))

with img_col:
    st.caption("Original")
    if image_url:
        st.image(image_url, use_column_width=True)
    else:
        st.info("Rasm yo'q.")

with heat_col:
    st.caption("Grad-CAM")
    if heatmap_url:
        st.image(heatmap_url, use_column_width=True)
    else:
        # Expected for UNGRADABLE: the engine never ran, so there is nothing
        # to explain.
        st.info("Heatmap yo'q (UNGRADABLE yoki render muvaffaqiyatsiz).")

st.caption(
    "Diagnoz emas — skrining/triaj. Yakuniy qaror oftalmolog mas'uliyatida. "
    "Chegara (threshold) faqat serverda: `EYE_REFERABLE_THRESHOLD`."
)
