#!/usr/bin/env bash
# EYE DETECT AI — live smoke test for the Claude engine (MIGRATION_PLAN.md §7
# layer 6). Runs against a DEPLOYED backend (EYE_MODEL_SOURCE=claude) and makes
# up to four real Claude calls — each one is billed.
#
#   bash scripts/smoke_claude.sh <BASE_URL> <API_KEY> <IMAGES_DIR>
#   bash scripts/smoke_claude.sh https://<project>.vercel.app "$EYE_API_KEY" eval/manual
#
# IMAGES_DIR must contain (JPEG or PNG, any of .jpg/.jpeg/.png):
#   referable.*     a public fundus image with referable DR     -> REFER
#   normal.*        a public fundus image without DR            -> NO_REFER
#   external_eye.*  a phone photo of the front of an eye        -> UNGRADABLE
#                                                                  (fundus text)
#   blurred.*       a blurred fundus image                      -> UNGRADABLE
#                                                                  (quality gate)
# Never put patient images in git: eval/manual/ is git-ignored.
#
# Checks: /health, wrong key -> 401, an oversized upload -> 413, then the four
# verdicts. The "zero tokens for the blurred image" half of layer 6 is checked
# in the function logs (no `claude_call` line for that exam_id), not here.
#
# Requires: bash, curl, jq. Exits non-zero on the first failure, naming it.

set -euo pipefail

BASE_URL="${1:-}"
API_KEY="${2:-}"
IMAGES_DIR="${3:-}"

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }

fail() {
  red "FAIL [$1] $2"
  if [[ -n "${3:-}" ]]; then
    printf '  observed: %s\n' "$(printf '%s' "$3" | head -c 800)"
  fi
  exit 1
}
pass() { green "ok   [$1] ${2:-}"; }

usage() {
  echo "usage: $0 <BASE_URL> <API_KEY> <IMAGES_DIR>" >&2
  exit 2
}

[[ -n "$BASE_URL" && -n "$API_KEY" && -n "$IMAGES_DIR" ]] || usage
BASE_URL="${BASE_URL%/}"
[[ -d "$IMAGES_DIR" ]] || fail "args" "IMAGES_DIR not found: $IMAGES_DIR"
command -v curl >/dev/null 2>&1 || fail "deps" "curl not found"
command -v jq   >/dev/null 2>&1 || fail "deps" "jq not found"

find_image() {
  # first match of <name>.jpg|jpeg|png in IMAGES_DIR, or fail
  local name="$1" ext
  for ext in jpg jpeg png JPG JPEG PNG; do
    if [[ -f "$IMAGES_DIR/$name.$ext" ]]; then
      printf '%s' "$IMAGES_DIR/$name.$ext"
      return 0
    fi
  done
  fail "images" "missing $name.(jpg|jpeg|png) in $IMAGES_DIR"
}

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# post <file> <key> -> body on stdout, status in $TMP_DIR/status
post() {
  curl -sS -o "$TMP_DIR/body" -w '%{http_code}' \
       -X POST "$BASE_URL/api/v1/predict" \
       -H "X-API-Key: $2" \
       -F "file=@$1" > "$TMP_DIR/status" || true
  cat "$TMP_DIR/body"
}
status() { cat "$TMP_DIR/status"; }

# 1. health --------------------------------------------------------------------
code="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/health" || true)"
[[ "$code" == "200" ]] || fail "health" "GET /health -> $code"
pass "health" "GET /health -> 200"

# 2. wrong key -> 401 ----------------------------------------------------------
REFERABLE="$(find_image referable)"
body="$(post "$REFERABLE" "wrong-$API_KEY")"
[[ "$(status)" == "401" ]] || fail "auth" "wrong key -> $(status), expected 401" "$body"
pass "auth" "wrong key -> 401"

# 3. oversized upload -> 413 (5 MB of JPEG-magic bytes; never reaches Claude) --
{ printf '\xff\xd8\xff'; head -c $((5 * 1024 * 1024)) /dev/zero; } > "$TMP_DIR/big.jpg"
body="$(post "$TMP_DIR/big.jpg" "$API_KEY")"
[[ "$(status)" == "413" ]] || fail "size" "5 MB upload -> $(status), expected 413" "$body"
pass "size" "5 MB upload -> 413"

# 4-7. verdicts (real Claude calls) --------------------------------------------
expect() {
  # expect <step> <file> <decision> [decision_text substring]
  local step="$1" file="$2" want="$3" text="${4:-}" body got
  body="$(post "$file" "$API_KEY")"
  [[ "$(status)" == "200" ]] || fail "$step" "POST -> $(status), expected 200" "$body"
  got="$(printf '%s' "$body" | jq -r '.decision')"
  [[ "$got" == "$want" ]] || fail "$step" "decision=$got, expected $want" "$body"
  if [[ -n "$text" ]]; then
    printf '%s' "$body" | jq -e --arg t "$text" '.decision_text | contains($t)' >/dev/null \
      || fail "$step" "decision_text does not contain: $text" "$body"
  fi
  pass "$step" "$want  exam_id=$(printf '%s' "$body" | jq -r '.exam_id')  model=$(printf '%s' "$body" | jq -r '.model_version')"
}

expect "referable"    "$REFERABLE"                 "REFER"
expect "normal"       "$(find_image normal)"       "NO_REFER"
expect "external_eye" "$(find_image external_eye)" "UNGRADABLE" "fundus"
expect "blurred"      "$(find_image blurred)"      "UNGRADABLE"

green "all checks passed"
