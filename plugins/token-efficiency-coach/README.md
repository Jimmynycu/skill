# Token-Efficiency Coach

A Claude Code **plugin** that shows exactly where a session wasted tokens — and how to
fix it. It runs locally and reads your own session log, so **no prompt ever leaves your
machine.**

It flags *waste* (uncached context, context bloat, oversized tool output, output-heavy
turns, failed tool calls, wrong-tier routing, redundant reads, very long single thread) —
eight patterns in all, **not** *quality*.
There is no score, no ranking, no judgment — just "here's what cost you, here's the fix."

The plugin ships three surfaces, all backed by **one engine** (`scripts/analyze.py`):

| Surface | What it is | When it fires |
|---|---|---|
| `/token-efficiency-coach:coach` | Slash command — runs the full audit and coaches the fix | When you run it |
| End-of-session coach | `SessionEnd` hook — saves a report you can review | Automatically, when a session ends (never blocks) |
| Live statusline | `scripts/statusline.py` — `$cost · ctx tokens · cache-hit% · ⚠` | After every assistant message (you wire this up once) |

---

## Install

This plugin is distributed through the **`jimmy-tools`** marketplace, whose manifest lives
at the repo root ([`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json)).

```bash
# 1) Add the marketplace from GitHub (registers as: jimmy-tools)
claude plugin marketplace add Jimmynycu/skill

# 2) Install the plugin from that marketplace
claude plugin install token-efficiency-coach@jimmy-tools
```

Developing from a local clone instead? Point `marketplace add` at the repo root
(`claude plugin marketplace add .`), then install the same way.

Validate before publishing (run from the repo root):

```bash
claude plugin validate ./plugins/token-efficiency-coach --strict
```

The hooks (and the statusline, once wired) execute shell commands, so Claude Code will
ask you to accept the **workspace trust dialog** the first time — the same gate as any
shell-executing setting. If you set `disableAllHooks: true`, both the hooks and the
statusline are disabled.

---

## The slash command — `/token-efficiency-coach:coach`

Run it any time a session felt expensive or slow:

```
/token-efficiency-coach:coach
/token-efficiency-coach:coach /path/to/session.jsonl
```

With no argument it auto-finds the latest session for the current project; pass a path
to audit a specific transcript. The command injects the engine's ranked report into the
prompt, then Claude relays it and offers to apply the top fix. It adds **zero** analysis
logic — all of it lives in `scripts/analyze.py`.

> The command is namespaced by the plugin and lives at `skills/coach/SKILL.md`, so the
> typed name is `/token-efficiency-coach:coach`. `disable-model-invocation: true` keeps
> it a manual command — analyzing spend never auto-fires.

---

## The hooks

Configured in `hooks/hooks.json` (referenced by `plugin.json`):

### `SessionEnd` → end-of-session coach (non-blocking)
When a session ends, `scripts/session_end_coach.sh` reads the session's
`transcript_path` from the hook's stdin, runs `scripts/analyze.py` on it, and **saves
the full report** to:

```
$CLAUDE_PLUGIN_DATA/last-session-coach.txt
```

It prints one benign pointer line and **always exits 0**. `SessionEnd` is structurally
non-blocking — its exit code and JSON are ignored by Claude Code — so the coach can
**never** trap your session. (That is also why the coach is on `SessionEnd` and not
`Stop`, which *can* block.) To read the saved report live, just run
`/token-efficiency-coach:coach`.

### `PostToolUse` → gentle oversized-output warning (optional, async)
After a `Read`/`Bash`/`Grep`/`WebFetch` call, `scripts/warn_large_output.sh` checks the
size of that one tool result. If it's large enough to meaningfully bloat context (and be
re-billed every later turn), it appends a single gentle note to
`$CLAUDE_PLUGIN_DATA/efficiency-warnings.log`. It is declared `async: true`, so it runs
in the background and adds **zero latency** to the tool call, and it **always exits 0**.
It is pure sugar — the full audit is the `SessionEnd` coach's and the command's job.

> Neither hook ever emits decision JSON, uses exit code 2, or uses `asyncRewake`. By
> design, nothing this plugin does can block you.

---

## Wire up the statusline

A plugin **cannot** register a top-level `statusLine` — the manifest has no such field,
and a plugin's bundled `settings.json` honors only `agent` / `subagentStatusLine`. So the
plugin **ships** the script and **you** wire it into your own settings. The
`/token-efficiency-coach:coach` command will offer to walk you through this.

**Why a stable copy?** `${CLAUDE_PLUGIN_ROOT}` is **not** expanded inside a user
`statusLine` command (that variable only exists for plugin-launched hook/MCP
subprocesses), and the installed plugin lives in a *versioned* cache path that changes on
every update. So copy (or symlink) the script to a stable location and point at that:

```bash
# Copy the shipped statusline to a stable path (re-copy after a plugin update):
cp "$(claude plugin path token-efficiency-coach 2>/dev/null || \
      echo "$HOME/.claude/plugins/cache/token-efficiency-coach@jimmy-tools/1.0.1")/scripts/statusline.py" \
   "$HOME/.claude/statusline-token-coach.py"
```

Then add this to **`~/.claude/settings.json`** (user scope) or **`.claude/settings.json`**
(project scope):

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 \"$HOME/.claude/statusline-token-coach.py\"",
    "padding": 0
  }
}
```

Accept the trust dialog, and you'll see a live line like:

```
$1.23 · ctx 144k · cache 91% · ⚠ ctx
```

- **`$cost`** — running session cost (`cost.total_cost_usd`).
- **`ctx`** — live input-side context tokens (`current_usage.input + cache_creation +
  cache_read`), shown compactly.
- **`cache`** — cache-hit % (`cache_read / total input-side`).
- **`⚠`** — yellow `⚠ ctx` at ≥70% context used, red `⚠ bloat` at ≥90% or when
  `exceeds_200k_tokens` is set.

The statusline runs after every assistant message (debounced ~300ms) and an in-flight run
is cancelled by the next update, so it is intentionally tiny: it operates **only** on its
stdin JSON, never opens the transcript, and never calls the full engine. It does reuse the
same `prices.json` so per-token prices live in exactly one place. Fields that are null
early in a session (or right after `/compact`) are guarded — the line degrades to just the
cost rather than blanking.

---

## Files

```
token-efficiency-coach/
├── .claude-plugin/
│   └── plugin.json              # the plugin manifest (only this lives here)
├── hooks/
│   └── hooks.json               # SessionEnd coach + PostToolUse warner
├── skills/
│   └── coach/
│       └── SKILL.md             # the /token-efficiency-coach:coach command
├── scripts/
│   ├── analyze.py               # THE SHARED ENGINE (cost + waste logic)
│   ├── patterns.json            # waste-pattern catalog (loaded by analyze.py)
│   ├── prices.json              # price table (loaded by analyze.py)
│   ├── session_end_coach.sh     # SessionEnd wrapper (always exit 0)
│   ├── warn_large_output.sh     # PostToolUse wrapper (async, always exit 0)
│   └── statusline.py            # the live statusline (stdin-only, fast)
├── README.md
├── LICENSE
└── CHANGELOG.md
```

Run the engine directly (it is the same code all three surfaces use):

```bash
python3 scripts/analyze.py                        # auto-find latest session
python3 scripts/analyze.py path/to/session.jsonl  # or a specific transcript
```

---

## Design notes

- **One engine, one place.** `scripts/analyze.py` owns all transcript parsing and all
  cost/waste math. The command injects its output, the `SessionEnd` hook routes a
  transcript path into it, and the statusline reuses only its price table — none of them
  re-implement the logic.
- **Local-first / private by default.** Everything reads your own session log on your own
  machine. Any future aggregation would be strictly opt-in and anonymized.
- **Coach, not judge.** Measuring observable waste needs no "is this good?" oracle, which
  is exactly why it stays reliable.
- **Tune it freely.** Thresholds and coaching copy live in `scripts/patterns.json`; prices
  in `scripts/prices.json` (these ship with **illustrative** rates — update them to your
  real provider pricing before trusting the dollar figures).

## Roadmap

1. Cross-tool adapters (Codex, Cursor, Gemini CLI) that map their logs onto the same
   metric keys — the report and patterns stay unchanged.
2. Opt-in, anonymized aggregate → a public cross-provider efficiency index.
3. Team dashboards (aggregate, never per-person ranking).
