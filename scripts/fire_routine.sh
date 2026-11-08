#!/usr/bin/env bash
# Fire the Claude Routine's API trigger with a text payload.
#   FIRE_URL=... FIRE_TOKEN=... scripts/fire_routine.sh "DEAL_REFRESH_REQUEST ISSUE 12"
# Prints the Routine session URL (or "n/a"); exit 1 and the HTTP error on failure.
set -euo pipefail
text="${1:?payload text required}"
: "${FIRE_URL:?ROUTINE_FIRE_URL not set}" "${FIRE_TOKEN:?ROUTINE_TOKEN not set}"
out="$(mktemp)"
status=$(curl -sS -o "$out" -w '%{http_code}' -X POST "$FIRE_URL" \
  -H "Authorization: Bearer $FIRE_TOKEN" \
  -H "anthropic-beta: experimental-cc-routine-2026-04-01" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg t "$text" '{text:$t}')")
if [ "$status" != "200" ] && [ "$status" != "201" ]; then
  echo "HTTP $status: $(head -c 500 "$out")" >&2
  exit 1
fi
jq -r '.claude_code_session_url // "n/a"' "$out"
