#!/usr/bin/env bash
# EYE DETECT AI — end-to-end smoke test (SPEC.md §5-D D3).
#
#   bash scripts/smoke_test.sh <BASE_URL> [API_KEY]
#   bash scripts/smoke_test.sh http://localhost:8000 demo123
#
# Exercises the whole demo chain against a RUNNING API: health, the three
# verdicts the demo shows, the server-generated patient ID (C2), the frozen
# error envelope (C4), unauthenticated static media (C6), auth (C2 §5-C), and
# live idempotency (C14).
#
# Exits non-zero on the first failure with a NAMED step, because "smoke test
# failed" 40 lines up a CI log is not an actionable message.
#
# Requires: bash, curl, jq. Run it from `backend/` (it needs scripts/out/,
# which it regenerates if missing).

set -euo pipefail

BASE_URL="${1:-}"
API_KEY="${2:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
OUT_DIR="$SCRIPT_DIR/out"

PASSED=0

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

fail() {
  # $1 = step name, $2 = what went wrong, $3 = (optional) observed payload
  red "FAIL [$1] $2"
  if [[ -n "${3:-}" ]]; then
    printf '  observed: %s\n' "$(printf '%s' "$3" | head -c 800)"
  fi
  exit 1
}

pass() {
  green "ok   [$1] ${2:-}"
  PASSED=$((PASSED + 1))
}

usage() {
  cat >&2 <<EOF
usage: $0 <BASE_URL> [API_KEY]

  BASE_URL  e.g. http://localhost:8000   (no trailing slash needed)
  API_KEY   optional; when given, step 7 also proves a wrong key is rejected
EOF
  exit 2
}

[[ -n "$BASE_URL" ]] || usage
BASE_URL="${BASE_URL%/}"

command -v curl >/dev/null 2>&1 || fail "deps" "curl not found"
command -v jq   >/dev/null 2>&1 || fail "deps" "jq not found (brew install jq / apt-get install jq)"

# Auth header, as an array so the empty case adds no argument at all (an empty
# `-H ''` makes curl send a malformed request).
#
# Two bash traps avoided on purpose:
#   * `[[ ... ]] && AUTH=(...)` would be the last command of an AND-list, so
#     under `set -e` an empty API_KEY would EXIT THE SCRIPT instead of skipping.
#   * a bare `"${AUTH[@]}"` on an empty array is "unbound variable" under
#     `set -u` in bash 3.2 — still the default /bin/bash on macOS. Hence the
#     `${AUTH[@]+...}` guard at every call site below.
AUTH=()
if [[ -n "$API_KEY" ]]; then
  AUTH=(-H "X-API-Key: $API_KEY")
fi

# POST /api/v1/predict. curl's `-w '%{http_code}'` appends the status to the
# body, so the helper splits them: body goes to stdout for `$(...)` capture,
# the 3-digit status goes to a temp file (a variable would not survive the
# pipeline's subshell). Callers then assert on both.
STATUS_FILE="$(mktemp)"
trap 'rm -f "$STATUS_FILE"' EXIT

predict() {
  # usage: predict <file> [extra curl args...]
  local file="$1"; shift
  curl -sS -o - -w '%{http_code}' \
       -X POST "$BASE_URL/api/v1/predict" \
       ${AUTH[@]+"${AUTH[@]}"} \
       -F "file=@${file}" \
       "$@" \
    | { body="$(cat)"; printf '%s' "${body%???}"; printf '%s' "${body: -3}" > "$STATUS_FILE"; }
}

http_status() { cat "$STATUS_FILE"; }

# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
bold "EYE DETECT AI smoke test -> $BASE_URL"
if [[ ! -f "$OUT_DIR/refer.jpg" ]]; then
  echo "… scripts/out missing, generating fixtures"
  ( cd "$BACKEND_DIR" && python scripts/make_test_images.py >/dev/null ) \
    || fail "fixtures" "python scripts/make_test_images.py failed"
fi
for f in refer.jpg no_dr.jpg blurry.jpg dark.jpg not_an_image.txt; do
  [[ -f "$OUT_DIR/$f" ]] || fail "fixtures" "missing $OUT_DIR/$f — run: python scripts/make_test_images.py"
done

# ==========================================================================
# STEP 1 — GET /health -> .status == "ok"
# ==========================================================================
STEP="1 health"
HEALTH="$(curl -sS --max-time 10 "$BASE_URL/health")" \
  || fail "$STEP" "GET /health did not respond"
jq -e '.status == "ok"' >/dev/null 2>&1 <<<"$HEALTH" \
  || fail "$STEP" '.status != "ok"' "$HEALTH"
pass "$STEP" "model_loaded=$(jq -r '.model_loaded // "?"' <<<"$HEALTH")"

# ==========================================================================
# STEP 2 — predict refer.jpg -> all 15 legacy keys + decision REFER
# The key check is the contract with the DEPLOYED APK: a dropped or renamed
# key crashes an installed phone, and only this assertion catches it.
# ==========================================================================
STEP="2 predict refer.jpg"
REFER_JSON="$(predict "$OUT_DIR/refer.jpg" -F "patient_id=P-SMOKE" -F "eye=right")" \
  || fail "$STEP" "request failed"
[[ "$(http_status)" == "200" ]] || fail "$STEP" "expected HTTP 200, got $(http_status)" "$REFER_JSON"

jq -e '
  has("exam_id") and has("patient_id") and has("eye") and has("referable")
  and has("probability") and has("icdr_grade") and has("grade_label")
  and has("decision") and has("decision_text") and has("quality")
  and has("heatmap_url") and has("image_url") and has("model_version")
  and has("processed_at") and has("disclaimer")
' >/dev/null 2>&1 <<<"$REFER_JSON" \
  || fail "$STEP" "one of the 15 legacy keys is missing" "$REFER_JSON"

jq -e '.decision == "REFER"' >/dev/null 2>&1 <<<"$REFER_JSON" \
  || fail "$STEP" "expected .decision == \"REFER\", got $(jq -c '.decision' <<<"$REFER_JSON")" "$REFER_JSON"

REFER_EXAM_ID="$(jq -r '.exam_id' <<<"$REFER_JSON")"
pass "$STEP" "15/15 keys, decision=REFER, exam_id=$REFER_EXAM_ID"

# ==========================================================================
# STEP 3 — no_dr.jpg -> NO_REFER ; blurry.jpg -> UNGRADABLE with probability 0.0
# The probability assertion is the C3 wire contract: UNGRADABLE must carry the
# non-null placeholder 0.0, never null (the deployed APK crashes on nulls).
# ==========================================================================
STEP="3a predict no_dr.jpg"
NOREFER_JSON="$(predict "$OUT_DIR/no_dr.jpg" -F "eye=left")" || fail "$STEP" "request failed"
[[ "$(http_status)" == "200" ]] || fail "$STEP" "expected HTTP 200, got $(http_status)" "$NOREFER_JSON"
jq -e '.decision == "NO_REFER"' >/dev/null 2>&1 <<<"$NOREFER_JSON" \
  || fail "$STEP" "expected .decision == \"NO_REFER\", got $(jq -c '.decision' <<<"$NOREFER_JSON")" "$NOREFER_JSON"
pass "$STEP" "decision=NO_REFER"

STEP="3b predict blurry.jpg"
BLURRY_JSON="$(predict "$OUT_DIR/blurry.jpg" -F "eye=right")" || fail "$STEP" "request failed"
[[ "$(http_status)" == "200" ]] || fail "$STEP" "expected HTTP 200, got $(http_status)" "$BLURRY_JSON"
jq -e '.decision == "UNGRADABLE"' >/dev/null 2>&1 <<<"$BLURRY_JSON" \
  || fail "$STEP" "expected .decision == \"UNGRADABLE\", got $(jq -c '.decision' <<<"$BLURRY_JSON")" "$BLURRY_JSON"
jq -e '.probability == 0.0' >/dev/null 2>&1 <<<"$BLURRY_JSON" \
  || fail "$STEP" "expected .probability == 0.0 (C3 placeholder, never null), got $(jq -c '.probability' <<<"$BLURRY_JSON")" "$BLURRY_JSON"
pass "$STEP" "decision=UNGRADABLE, probability=0.0"

# ==========================================================================
# STEP 4 — predict with NO patient_id -> server generates P-XXXXXX (C2)
# The UI promises "ID kiritilmasa avtomatik raqam beriladi" but sends nothing,
# so the server has to keep that promise.
#
# WHY dark.jpg AND NOT AN IMAGE AN EARLIER STEP ALREADY SENT:
# `find_recent_duplicate(patient_code=None)` means UNCONSTRAINED on patient,
# not `patient_id IS NULL` — C2 gives every blank-ID upload a code, so matching
# NULL would never dedup and every blank-ID retry would create exactly the
# duplicate C14 exists to prevent. Consequence here: a blank-ID post dedups on
# fingerprint+eye ALONE and would replay an earlier exam's explicit patient_id
# (e.g. "P-SMOKE"), failing this regex for a reason that has nothing to do with
# autogeneration. dark.jpg is posted nowhere else in this run, so its
# fingerprint is unique no matter what the eye argument is.
# ==========================================================================
STEP="4 auto patient_id"
AUTOID_JSON="$(predict "$OUT_DIR/dark.jpg" -F "eye=left")" || fail "$STEP" "request failed"
[[ "$(http_status)" == "200" ]] || fail "$STEP" "expected HTTP 200, got $(http_status)" "$AUTOID_JSON"
jq -e '.patient_id | type == "string" and test("^P-[0-9A-F]{6}$")' >/dev/null 2>&1 <<<"$AUTOID_JSON" \
  || fail "$STEP" "patient_id does not match ^P-[0-9A-F]{6}$: $(jq -c '.patient_id' <<<"$AUTOID_JSON")" "$AUTOID_JSON"
pass "$STEP" "patient_id=$(jq -r '.patient_id' <<<"$AUTOID_JSON")"

# ==========================================================================
# STEP 5 — missing `file` part -> 422 with the FROZEN envelope (C4/C15)
# FastAPI's default validation body is {"detail":[{...}]}; the client calls
# optString("detail") on it and silently shows nothing. This asserts the
# override is in place and that `detail` is a plain string.
# ==========================================================================
STEP="5 missing file -> 422"
MISSING_BODY="$(curl -sS -o - -w '%{http_code}' -X POST "$BASE_URL/api/v1/predict" \
                  ${AUTH[@]+"${AUTH[@]}"} -F "eye=right")" || fail "$STEP" "request failed"
MISSING_STATUS="${MISSING_BODY: -3}"
MISSING_JSON="${MISSING_BODY%???}"
[[ "$MISSING_STATUS" == "422" ]] || fail "$STEP" "expected HTTP 422, got $MISSING_STATUS" "$MISSING_JSON"
jq -e '.error == "validation_error"' >/dev/null 2>&1 <<<"$MISSING_JSON" \
  || fail "$STEP" "expected .error == \"validation_error\"" "$MISSING_JSON"
jq -e '.detail | type == "string" and length > 0' >/dev/null 2>&1 <<<"$MISSING_JSON" \
  || fail "$STEP" "detail must be a NON-EMPTY STRING, never a list (C15)" "$MISSING_JSON"
pass "$STEP" "422 validation_error, detail is a string"

# ==========================================================================
# STEP 6 — GET /api/v1/exams >= 3 rows; first image_url fetches 200
# Media is unauthenticated on purpose (C6): Coil sends no API key.
# ==========================================================================
STEP="6 exams list + media"
EXAMS_JSON="$(curl -sS --max-time 15 ${AUTH[@]+"${AUTH[@]}"} "$BASE_URL/api/v1/exams?limit=50")" \
  || fail "$STEP" "GET /api/v1/exams failed"
# Accept a bare list or an {"items": [...]} envelope.
EXAMS_ARR="$(jq -c 'if type == "array" then . else (.items // .exams // .results // .data // []) end' <<<"$EXAMS_JSON")" \
  || fail "$STEP" "response is not JSON" "$EXAMS_JSON"
EXAMS_LEN="$(jq 'length' <<<"$EXAMS_ARR")"
[[ "$EXAMS_LEN" -ge 3 ]] || fail "$STEP" "expected >= 3 exams, got $EXAMS_LEN" "$EXAMS_JSON"

# The list returns ExamSummary, which carries no media URL, so the first row's
# image_url normally has to come from the detail endpoint. Try the row first
# anyway — it costs one jq and keeps this step working if list ever returns the
# full predict shape.
FIRST_ID="$(jq -r '.[0].exam_id' <<<"$EXAMS_ARR")"
IMAGE_URL="$(jq -r '.[0].image_url // empty' <<<"$EXAMS_ARR")"
if [[ -z "$IMAGE_URL" ]]; then
  DETAIL_JSON="$(curl -sS --max-time 15 ${AUTH[@]+"${AUTH[@]}"} "$BASE_URL/api/v1/exams/$FIRST_ID")" \
    || fail "$STEP" "GET /api/v1/exams/$FIRST_ID failed"
  IMAGE_URL="$(jq -r '.image_url // empty' <<<"$DETAIL_JSON")"
  [[ -n "$IMAGE_URL" ]] || fail "$STEP" "exam $FIRST_ID has no image_url" "$DETAIL_JSON"
fi
# image_url is relative by design (C6) so it survives a change of host.
case "$IMAGE_URL" in
  http://*|https://*) IMAGE_ABS="$IMAGE_URL" ;;
  *)                  IMAGE_ABS="$BASE_URL/${IMAGE_URL#/}" ;;
esac
# NOTE: deliberately NO auth header — /static must serve without a key.
IMG_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$IMAGE_ABS")" \
  || fail "$STEP" "GET $IMAGE_ABS failed"
[[ "$IMG_STATUS" == "200" ]] || fail "$STEP" "expected HTTP 200 for $IMAGE_ABS (unauthenticated), got $IMG_STATUS"
pass "$STEP" "$EXAMS_LEN exams, image_url 200 without a key"

# ==========================================================================
# STEP 7 — a WRONG key must be 401 (only meaningful when a key was supplied)
# ==========================================================================
STEP="7 wrong api key -> 401"
if [[ -n "$API_KEY" ]]; then
  WRONG_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 \
                    -H "X-API-Key: definitely-not-the-key" \
                    "$BASE_URL/api/v1/exams?limit=1")" || fail "$STEP" "request failed"
  [[ "$WRONG_STATUS" == "401" ]] || fail "$STEP" "expected HTTP 401, got $WRONG_STATUS"
  pass "$STEP" "401"
else
  echo "skip [$STEP] no API_KEY argument given — auth is not enforced in this run"
fi

# ==========================================================================
# STEP 8 — C14 dedup, live: the EXACT same bytes + patient + eye replay
# step 2's exam instead of creating a second one. This is the failure the
# client provokes for real: retry() resends the retained bytes after a
# server-success + client-timeout.
# ==========================================================================
STEP="8 idempotent re-POST (C14)"
DUP_JSON="$(predict "$OUT_DIR/refer.jpg" -F "patient_id=P-SMOKE" -F "eye=right")" \
  || fail "$STEP" "request failed"
[[ "$(http_status)" == "200" ]] || fail "$STEP" "expected HTTP 200, got $(http_status)" "$DUP_JSON"
DUP_EXAM_ID="$(jq -r '.exam_id' <<<"$DUP_JSON")"
[[ "$DUP_EXAM_ID" == "$REFER_EXAM_ID" ]] \
  || fail "$STEP" "duplicate upload created a NEW exam: $DUP_EXAM_ID != $REFER_EXAM_ID (dedup window: DEDUP_WINDOW_MIN)" "$DUP_JSON"
pass "$STEP" "same exam_id replayed: $DUP_EXAM_ID"

# --------------------------------------------------------------------------
bold ""
green "SMOKE TEST PASSED — $PASSED checks against $BASE_URL"
