#!/usr/bin/env bash
# PostToolUse hook -- gentle oversized-output nudge (ASYNC, NON-BLOCKING, optional).
#
# Wired in hooks/hooks.json with `async: true`, so it runs in the background and adds
# ZERO latency to the tool call. It is purely advisory.
#
# Contract:
#   * NEVER blocks and NEVER delays anything. No decision JSON, no exit 2, no
#     asyncRewake. Always `exit 0`.
#   * It does NOT call analyze.py -- the full-transcript audit is the SessionEnd
#     coach's / the /coach command's job. This warner only eyeballs the size of the
#     ONE tool result it just received and, if it's large enough to meaningfully bloat
#     context (and be re-billed every later turn), appends a single gentle line to a
#     log under $CLAUDE_PLUGIN_DATA. Tasteful: one short note per event, no scolding.
#   * Fail-silent on everything (no jq, weird JSON, no data dir) -> quiet exit 0.
#
# PostToolUse stdin adds: tool_name, tool_input{...}, and the result under either
# `tool_response` or `tool_output` depending on client version. We measure whichever
# is present; we never depend on the transcript.

# Byte threshold for a "large" single tool result. ~4 chars/token, so 40000 bytes is
# ~10k tokens -- comfortably above the engine's 8k-token oversized-output pattern, kept
# conservative here so the nudge is rare and welcome rather than noisy.
THRESHOLD_BYTES=40000

ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$ROOT" ]; then
  ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
fi

DATA_DIR="${CLAUDE_PLUGIN_DATA:-${TMPDIR:-/tmp}}"
mkdir -p "$DATA_DIR" 2>/dev/null
LOG="$DATA_DIR/efficiency-warnings.log"

STDIN_JSON="$(cat 2>/dev/null)"
[ -z "$STDIN_JSON" ] && exit 0

# jq is the clean path; if absent, just exit quietly (this hook is optional sugar).
command -v jq >/dev/null 2>&1 || exit 0

TOOL_NAME="$(printf '%s' "$STDIN_JSON" | jq -r '.tool_name // "tool"' 2>/dev/null)"

# Size of the result text, across the shapes Claude Code emits:
#   tool_response / tool_output may be a string, or {content:"..."},
#   or {content:[{type:"text",text:"..."}]}. Sum any text we can see; default 0.
SIZE="$(printf '%s' "$STDIN_JSON" | jq -r '
  (.tool_response // .tool_output // empty) as $r
  | if   ($r | type) == "string" then ($r | length)
    elif ($r | type) == "object" then
      ( ($r.content // empty) as $c
        | if   ($c | type) == "string" then ($c | length)
          elif ($c | type) == "array"  then
            ([ $c[]? | (.text? // "") | length ] | add) // 0
          else 0 end )
    else 0 end
' 2>/dev/null)"

# Coerce to an integer; bail quietly if jq gave us nothing usable.
case "$SIZE" in
  ''|*[!0-9]*) exit 0 ;;
esac

if [ "$SIZE" -gt "$THRESHOLD_BYTES" ]; then
  APPROX_TOKENS=$(( SIZE / 4 ))
  {
    printf '[%s] %s returned a large result (~%d tokens). ' \
      "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$TOOL_NAME" "$APPROX_TOKENS"
    printf 'It now rides in context and is re-billed every later turn -- consider '
    printf 'targeted line ranges, a grep, or piping through head/tail next time.\n'
  } >> "$LOG" 2>/dev/null
fi

exit 0
