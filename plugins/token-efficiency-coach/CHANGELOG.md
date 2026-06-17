# Changelog

All notable changes to the Token-Efficiency Coach plugin are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-16

First packaged release as a Claude Code plugin.

### Added
- **Plugin manifest** (`.claude-plugin/plugin.json`) under the `token-efficiency-coach`
  namespace.
- **Slash command** `/token-efficiency-coach:coach` (`skills/coach/SKILL.md`): runs the
  full token-waste audit on a session transcript and coaches the top fix. Injects the
  shared engine's report via dynamic-context (`!`) execution; adds no analysis logic.
- **`SessionEnd` hook** (`scripts/session_end_coach.sh`): a non-blocking end-of-session
  coach that runs the engine on the session transcript and saves the report to
  `$CLAUDE_PLUGIN_DATA/last-session-coach.txt`. Always exits 0; can never trap the user.
- **`PostToolUse` hook** (`scripts/warn_large_output.sh`): an optional, async, gentle
  warning when a single tool result is large enough to bloat context. Always exits 0.
- **Live statusline** (`scripts/statusline.py`): prints `$cost · ctx tokens · cache-hit%
  · ⚠` from the statusline stdin JSON only. Reuses `prices.json`; never opens the
  transcript. The README documents wiring it into the user's `settings.json` (a plugin
  cannot register a `statusLine` itself).
- **Marketplace** (`../token-efficiency-marketplace/.claude-plugin/marketplace.json`):
  lists the plugin via a relative `./token-efficiency-coach` source under the
  `jimmy-tools` marketplace.
- `LICENSE` (MIT) and this `CHANGELOG.md`.

### Changed
- Packaged the previously flat repo into the plugin layout: the shared engine
  (`analyze.py`, `patterns.json`, `prices.json`) moved to `scripts/`, and the skill moved
  from a root `SKILL.md` to `skills/coach/SKILL.md`. The engine is unchanged — it loads
  its sidecar JSON relative to its own location, so co-locating the three files in
  `scripts/` required no code change.

### Notes
- One engine, one place: `scripts/analyze.py` owns all cost/waste logic; the command,
  the `SessionEnd` hook, and the statusline reuse it (the statusline reuses only its
  price table, by design — it must stay sub-300ms and stateless).
- `version` is pinned here in `plugin.json` only (not duplicated in the marketplace
  entry), since `plugin.json` wins silently and must be bumped for users to get updates.
