#!/usr/bin/env python3
"""Live token-efficiency statusline for Claude Code.

Reads the statusline stdin JSON (model, cost, context_window, ...) and prints ONE
concise line, e.g.:

    $1.23 · ctx 142k · cache 91% · ⚠ bloat

Deliberate boundary (see invocationContract): this is the cheap-live-glance surface.
It runs after every assistant message (300ms debounce) and an in-flight run is
cancelled by the next update, so it must be O(1) over the stdin JSON ONLY. It NEVER
opens the transcript and NEVER calls analyze.analyze() — full-transcript audits are the
hook's and the /coach command's job. It DOES reuse analyze.py's price table (load_json +
rate_for) so per-token prices are defined in exactly one place (prices.json).

Fail-silent contract: a non-zero exit or empty output blanks the statusline, and the
stdin is partly null early in a session (current_usage is null before the first API call
and right after /compact). So every field is guarded, all work is wrapped, and on any
error we print a minimal line (the precomputed $cost if we have it, else nothing) and
always exit 0. The statusline must never error out.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Context-usage percentages at which we surface the bloat warning. >=90% is the loud
# red zone; >=70% is an early heads-up. exceeds_200k_tokens (set by Claude Code) also
# forces the warning on regardless of percentage.
WARN_PCT = 70
RED_PCT = 90

# ANSI styling. Kept tiny and optional — if anything here is unavailable the line still
# reads fine as plain text. Colors are only emitted when stdout is a TTY-ish stream and
# NO_COLOR is unset, so piped/captured output (and our own tests) stay clean.
RESET = "\033[0m"
DIM = "\033[2m"
YELLOW = "\033[33m"
RED = "\033[31m"
SEP = " · "


def _use_color():
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _paint(text, code, on):
    return ("%s%s%s" % (code, text, RESET)) if (on and code) else text


def _num(value):
    """Coerce a possibly-missing/None/garbage numeric field to a float >= 0."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0.0
    return n if n > 0 else 0.0


def _fmt_tokens(n):
    """Compact token count: 142000 -> '142k', 1_900_000 -> '1.9M', 850 -> '850'."""
    n = int(n)
    if n >= 1_000_000:
        return ("%.1fM" % (n / 1_000_000)).replace(".0M", "M")
    if n >= 1_000:
        return "%dk" % round(n / 1_000)
    return str(n)


def _context_tokens(cw):
    """Total input-side context tokens that match used_percentage.

    Prefer current_usage (input + cache_creation + cache_read) — the live, post-/compact
    truth. current_usage is null before the first API call and right after /compact, so
    fall back to the cumulative context_window.total_input_tokens, then to 0.
    """
    cu = cw.get("current_usage")
    if isinstance(cu, dict):
        it = _num(cu.get("input_tokens"))
        cc = _num(cu.get("cache_creation_input_tokens"))
        cr = _num(cu.get("cache_read_input_tokens"))
        total = it + cc + cr
        if total > 0:
            return total, it, cc, cr
    return _num(cw.get("total_input_tokens")), 0.0, 0.0, 0.0


def _cache_hit_pct(it, cc, cr):
    """cache_read / (input + cache_creation + cache_read), as an int percent. Returns
    None when there is no input-side context yet (avoids a meaningless 0%/division)."""
    denom = it + cc + cr
    if denom <= 0:
        return None
    return int(round(cr / denom * 100))


def _used_pct(cw, ctx_tokens):
    """The context-window fill percentage. Prefer the value Claude Code computes; if
    it's null (early/after compact) derive it from ctx_tokens / context_window_size."""
    up = cw.get("used_percentage")
    if isinstance(up, (int, float)):
        return float(up)
    size = _num(cw.get("context_window_size"))
    if size > 0 and ctx_tokens > 0:
        return ctx_tokens / size * 100
    return None


def _marginal_resend_usd(model_id, ctx_tokens):
    """Optional efficiency hint: what one more full-context turn costs at the model's
    full (uncached) input rate. Reuses analyze.py's price table + resolver so prices
    live in exactly ONE place. Pure arithmetic, no transcript I/O. Returns None on any
    problem (unknown model, import failure, no context) so it can't break the line."""
    if ctx_tokens <= 0 or not model_id:
        return None
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import analyze  # noqa: PLC0415 (lazy, kept off the critical path)

        prices = analyze.load_json("prices.json")
        rate = analyze.rate_for(model_id, prices)
        return ctx_tokens / 1e6 * float(rate["input"])
    except Exception:
        return None


def build_line(data, color):
    cw = data.get("context_window")
    cw = cw if isinstance(cw, dict) else {}

    segments = []

    # Token-first: this coach tracks the token/work ratio, not dollars — no $ is shown.
    # 1) live context tokens — the always-on efficiency signal.
    ctx_tokens, it, cc, cr = _context_tokens(cw)
    segments.append("ctx %s" % _fmt_tokens(ctx_tokens))

    # 3) cache-hit %.
    hit = _cache_hit_pct(it, cc, cr)
    if hit is not None:
        segments.append("cache %d%%" % hit)

    # (A per-token $ "resend" estimate is intentionally omitted — token-first, no price.)

    # 5) bloat warning — red at >=RED_PCT or exceeds_200k_tokens, yellow at >=WARN_PCT.
    used = _used_pct(cw, ctx_tokens)
    over_200k = bool(data.get("exceeds_200k_tokens"))
    if over_200k or (used is not None and used >= RED_PCT):
        segments.append(_paint("⚠ bloat", RED, color))
    elif used is not None and used >= WARN_PCT:
        segments.append(_paint("⚠ ctx", YELLOW, color))

    return SEP.join(segments)


def main():
    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    color = _use_color()
    try:
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            data = {}
        line = build_line(data, color)
        if line:
            sys.stdout.write(line + "\n")
    except Exception:
        # Token-first: on any error, print nothing rather than a misleading line.
        pass
    # Always succeed: a non-zero exit blanks the statusline.
    return 0


if __name__ == "__main__":
    sys.exit(main())
