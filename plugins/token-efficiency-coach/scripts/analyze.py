#!/usr/bin/env python3
"""Token-efficiency coach — find token waste in a coding-agent session.

v0 reads a Claude Code transcript (JSONL). Point it at any session .jsonl, or run
with no args inside a Claude Code project to auto-find the latest session. Cross-tool
adapters (Codex, Cursor, Gemini CLI) are the roadmap: each maps its own logs onto the
same metric keys, and everything below stays unchanged.

  python3 analyze.py [path/to/session.jsonl]

Robustness contract: a transcript is untrusted input. Empty files, blank lines,
malformed JSON, lines that aren't objects, messages with no usage, and non-Claude
shapes are all skipped silently — the analyzer never crashes on a bad line, it just
skips it and keeps going. Dollar figures are deliberately conservative; where a number
is an estimate it is framed as an UPPER bound (see max_cache_savings_usd).
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# A single tool_result whose text is bigger than this many characters is flagged as a
# bloated dump: it re-enters context and is re-billed on every later turn. ~4 chars/token
# is the usual English rule of thumb, used only to translate chars -> an approximate
# token count for display.
CHARS_PER_TOKEN = 4


def load_json(name):
    with open(os.path.join(HERE, name)) as fh:
        return json.load(fh)


# A single usage field above this many tokens is implausible (even a 1M-context model
# bills one message far below this); such a value is a corrupt transcript field and is
# dropped to 0 so it can never blow up the headline cost.
MAX_PLAUSIBLE_TOKENS = 20_000_000


def as_int(value):
    """Coerce a usage field to a non-negative int. Transcripts are untrusted, so a
    missing/None/garbage value must never blow up arithmetic — it becomes 0. An
    implausibly large value (a corrupt field) is also dropped to 0."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    if n <= 0 or n > MAX_PLAUSIBLE_TOKENS:
        return 0
    return n


def rate_for(model, prices):
    models = prices.get("models", {})
    if model in models:
        return models[model]
    for key, val in models.items():
        if model and (model.startswith(key) or key in model):
            return val
    return prices["default"]


def find_transcript(arg):
    if arg:
        return arg
    mangled = os.getcwd().replace("/", "-")
    projdir = os.path.expanduser(os.path.join("~/.claude/projects", mangled))
    cands = sorted(glob.glob(os.path.join(projdir, "*.jsonl")), key=os.path.getmtime)
    if not cands:
        sys.exit("No transcript found. Pass a session .jsonl path explicitly.")
    return cands[-1]


def iter_objects(path):
    """Yield one parsed JSON object per non-blank line, skipping anything malformed.

    Streams line-by-line so a huge transcript never loads into memory at once. Any line
    that fails to parse, or parses to something other than a dict, is skipped."""
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError as exc:
        sys.exit("Could not open transcript %s: %s" % (path, exc))
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(obj, dict):
                yield obj


def analyze(path, prices):
    input_cost = output_cost = cache_read_cost = cache_write_cost = 0.0
    fresh_input = cache_read = cache_create = 0
    cacheable_upper = 0.0
    model_cost = {}
    contexts = []
    reads = {}
    n_assistant = n_tool_calls = web_search = web_fetch = 0
    tool_errors = 0
    largest_tool_chars = 0
    # Claude Code writes several JSONL lines per assistant message (thinking, text and
    # tool_use partials each get their own line) and every one of them carries the SAME
    # usage object. Counting usage per-line triple-bills the session, so usage is counted
    # once per unique message id. tool_use / tool_result blocks each carry their own id,
    # so they get their own dedup sets and are counted once each too.
    seen_usage = set()
    seen_tool_use = set()
    seen_tool_result = set()

    for obj in iter_objects(path):
        msg = obj.get("message")
        if not isinstance(msg, dict):
            continue

        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_use":
                    key = block.get("id")
                    if key is not None and key in seen_tool_use:
                        continue
                    if key is not None:
                        seen_tool_use.add(key)
                    n_tool_calls += 1
                    if block.get("name") == "Read":
                        fpath = (block.get("input") or {}).get("file_path")
                        if fpath:
                            reads[fpath] = reads.get(fpath, 0) + 1
                elif btype == "tool_result":
                    key = block.get("tool_use_id")
                    if key is not None and key in seen_tool_result:
                        continue
                    if key is not None:
                        seen_tool_result.add(key)
                    if block.get("is_error"):
                        tool_errors += 1
                    largest_tool_chars = max(largest_tool_chars, _result_chars(block))

        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        # Dedup usage by message id. A message with no id can't be deduped, so it is
        # counted (better to slightly over-count one odd line than drop a real cost).
        mid = msg.get("id")
        if mid is not None:
            if mid in seen_usage:
                continue
            seen_usage.add(mid)

        n_assistant += 1
        model = msg.get("model") or ""
        rate = rate_for(model, prices)
        it = as_int(usage.get("input_tokens"))
        crd = as_int(usage.get("cache_read_input_tokens"))
        cc = as_int(usage.get("cache_creation_input_tokens"))
        ot = as_int(usage.get("output_tokens"))
        cw = usage.get("cache_creation")
        cw = cw if isinstance(cw, dict) else {}
        cw5 = as_int(cw.get("ephemeral_5m_input_tokens"))
        cw1h = as_int(cw.get("ephemeral_1h_input_tokens"))
        if cw5 == 0 and cw1h == 0:
            cw5 = cc
        ic = it / 1e6 * rate["input"]
        rdc = crd / 1e6 * rate["cache_read"]
        wrc = cw5 / 1e6 * rate["cache_write_5m"] + cw1h / 1e6 * rate["cache_write_1h"]
        oc = ot / 1e6 * rate["output"]
        input_cost += ic
        cache_read_cost += rdc
        cache_write_cost += wrc
        output_cost += oc
        model_cost[model] = model_cost.get(model, 0.0) + ic + rdc + wrc + oc
        fresh_input += it
        cache_read += crd
        cache_create += cc
        # UPPER bound on cache savings: if every fresh (full-price) input token had instead
        # been a cache hit, this is the most it could have saved. Fresh input is genuinely
        # new content that can't be cached retroactively, so the real recoverable amount is
        # strictly less — this is a ceiling, not a forecast.
        cacheable_upper += it / 1e6 * max(0.0, rate["input"] - rate["cache_read"])
        contexts.append(it + crd + cc)
        stu = usage.get("server_tool_use")
        stu = stu if isinstance(stu, dict) else {}
        web_search += as_int(stu.get("web_search_requests"))
        web_fetch += as_int(stu.get("web_fetch_requests"))

    total = input_cost + output_cost + cache_read_cost + cache_write_cost
    ctx_in = fresh_input + cache_read + cache_create
    priciest = max(model_cost, key=model_cost.get) if model_cost else "n/a"
    redundant = sum(c - 1 for c in reads.values() if c > 1)
    top_reread = max(reads, key=reads.get) if reads and max(reads.values()) > 1 else "n/a"
    largest_tool_tokens = largest_tool_chars // CHARS_PER_TOKEN

    def pct(a, b):
        return round(a / b * 100, 1) if b else 0.0

    return {
        "total_cost_usd": round(total, 2),
        "input_cost_usd": round(input_cost, 2),
        "output_cost_usd": round(output_cost, 2),
        "cache_read_cost_usd": round(cache_read_cost, 2),
        "cache_write_cost_usd": round(cache_write_cost, 2),
        "output_share_pct": pct(output_cost, total),
        "cache_hit_pct": pct(cache_read, ctx_in),
        "max_cache_savings_usd": round(cacheable_upper, 2),
        "peak_context_tokens": max(contexts) if contexts else 0,
        "avg_context_tokens": int(sum(contexts) / len(contexts)) if contexts else 0,
        "n_assistant_msgs": n_assistant,
        "n_tool_calls": n_tool_calls,
        "tool_error_count": tool_errors,
        "tool_error_pct": pct(tool_errors, n_tool_calls),
        "largest_tool_output_tokens": largest_tool_tokens,
        "redundant_read_count": redundant,
        "top_reread_file": os.path.basename(top_reread) if top_reread != "n/a" else "n/a",
        "n_models": len(model_cost),
        "priciest_model": priciest or "unknown",
        "pct_on_priciest": pct(model_cost.get(priciest, 0.0), total),
        "web_search_requests": web_search,
        "web_fetch_requests": web_fetch,
    }


def _result_chars(block):
    """Approximate the character size of a tool_result's payload, across the string and
    list-of-text-blocks shapes Claude Code emits. Unknown shapes count as 0."""
    cont = block.get("content")
    if isinstance(cont, str):
        return len(cont)
    if isinstance(cont, list):
        total = 0
        for part in cont:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    total += len(text)
        return total
    return 0


OPS = {"<": lambda a, b: a < b, ">": lambda a, b: a > b,
       "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b}
SEV_RANK = {"high": 0, "medium": 1, "low": 2}
SEV_TAG = {0: "[HIGH]", 1: "[MED] ", 2: "[LOW] "}


class _Safe(dict):
    def __missing__(self, key):
        return "?"


def main():
    prices = load_json("prices.json")
    patterns = load_json("patterns.json")
    path = find_transcript(sys.argv[1] if len(sys.argv) > 1 else None)
    metrics = analyze(path, prices)

    findings = []
    for pat in patterns["patterns"]:
        val = metrics.get(pat["metric"])
        if val is None or not OPS[pat["op"]](val, pat["threshold"]):
            continue
        try:
            text = pat["message"].format_map(_Safe(metrics))
        except (KeyError, IndexError, ValueError):
            text = pat["message"]
        sav = metrics.get(pat.get("savings_metric", ""), 0) or 0
        findings.append((SEV_RANK.get(pat["severity"], 9), -sav, pat["title"], text, sav))
    findings.sort()

    print("=" * 72)
    print("  TOKEN-EFFICIENCY COACH  ·  v0  ·  flags waste, never grades quality")
    print("=" * 72)
    if metrics["n_assistant_msgs"] == 0:
        print("session : %s" % os.path.basename(path))
        print("\nNo billable assistant turns found in this transcript.")
        print("(Empty session, or not a Claude Code / supported transcript shape.)")
        return
    print("session : %s" % os.path.basename(path))
    print("usage   : %d turns - %d tool calls"
          % (metrics["n_assistant_msgs"], metrics["n_tool_calls"]))
    print("context : peak %s tok - avg %s tok - %.1f%% cache hit"
          % (format(metrics["peak_context_tokens"], ","),
             format(metrics["avg_context_tokens"], ","), metrics["cache_hit_pct"]))
    print("")

    if not findings:
        print("No major waste patterns tripped. Clean session.")
        return
    for i, (sev, _, title, text, _sav) in enumerate(findings, 1):
        print("%d. %s %s" % (i, SEV_TAG.get(sev, "[--] "), title))
        print("   %s\n" % text)
    print("-" * 72)
    print("Token-first: this coach measures token/work, not dollars - no pricing needed.")
    print("Patterns/thresholds live in patterns.json - tune freely.")


if __name__ == "__main__":
    main()
