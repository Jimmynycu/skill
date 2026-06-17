#!/usr/bin/env bash
# SessionEnd hook -- token-efficiency coach (NON-BLOCKING, informational only).
#
# Contract (see hooks/hooks.json + plugin README):
#   * Reads the SessionEnd stdin JSON, pulls .transcript_path, and runs the SHARED
#     engine scripts/analyze.py on it. No analysis logic lives here -- one engine,
#     one place.
#   * SessionEnd CANNOT block: Claude Code ignores this hook's exit code and JSON.
#     We still guarantee `exit 0` on every path so nothing ever traps the user's stop.
#   * SessionEnd stdout is NOT shown to the user (debug log only). So we persist the
#     full report to a log under $CLAUDE_PLUGIN_DATA and print ONE benign pointer
#     line to stderr (the only channel a SessionEnd hook surfaces). The
#     /token-efficiency-coach:coach command re-renders the live report on demand.
#   * Fail-silent: a missing transcript, missing jq, a broken engine -- any of these
#     just ends quietly with exit 0. Never emit decision JSON, never use exit 2.
#
# Env provided by Claude Code to plugin hooks:
#   CLAUDE_PLUGIN_ROOT  absolute path to this installed plugin (always set for hooks)
#   CLAUDE_PLUGIN_DATA  per-plugin writable dir (may be unset in older clients)

# Resolve the plugin root even if the env var is somehow absent (script lives in
# <root>/scripts/, so the root is one dir up). Belt-and-suspenders for fail-silence.
ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$ROOT" ]; then
  ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
fi

ENGINE="$ROOT/scripts/analyze.py"

# Where to persist the report. Prefer the plugin's data dir; fall back to a temp dir.
DATA_DIR="${CLAUDE_PLUGIN_DATA:-${TMPDIR:-/tmp}}"
mkdir -p "$DATA_DIR" 2>/dev/null
LOG="$DATA_DIR/last-session-coach.txt"

# Slurp stdin once (it is consumed on read).
STDIN_JSON="$(cat 2>/dev/null)"

# Extract transcript_path. Prefer jq; degrade to a tiny python fallback; never fail.
TRANSCRIPT=""
if command -v jq >/dev/null 2>&1; then
  TRANSCRIPT="$(printf '%s' "$STDIN_JSON" | jq -r '.transcript_path // empty' 2>/dev/null)"
fi
if [ -z "$TRANSCRIPT" ] && command -v python3 >/dev/null 2>&1; then
  TRANSCRIPT="$(printf '%s' "$STDIN_JSON" | python3 -c \
    'import sys,json
try:
    print(json.load(sys.stdin).get("transcript_path",""))
except Exception:
    pass' 2>/dev/null)"
fi

# Guard: no usable transcript, no engine, or no python -> quit quietly.
if [ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ] || [ ! -f "$ENGINE" ] \
   || ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi

# Run the shared engine. analyze.py treats argv[1] as an explicit transcript path.
# Capture stdout; on any non-zero exit (e.g. it sys.exit's on an unreadable file),
# swallow it and leave quietly.
REPORT="$(python3 "$ENGINE" "$TRANSCRIPT" 2>/dev/null)"
if [ $? -ne 0 ] || [ -z "$REPORT" ]; then
  exit 0
fi

# Persist the full report (timestamped) so it can be re-read / re-rendered later.
{
  printf '# token-efficiency coach -- %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)"
  printf '%s\n' "$REPORT"
} > "$LOG" 2>/dev/null

# Surface ONE benign pointer line. stderr is the only channel a SessionEnd hook shows;
# exit 0 keeps it framed as an informational hook line, never an error/block.
printf 'token-efficiency coach: session report saved to %s (run /token-efficiency-coach:coach to view).\n' \
  "$LOG" >&2

exit 0
