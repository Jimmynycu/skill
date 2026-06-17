<p align="center">
  <img src="assets/hero.svg" alt="Token-Efficiency Coach — find wasted tokens, keep the good stuff" width="100%">
</p>

<p align="center">
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-3be0c4?style=flat-square">
  <img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude%20Code-plugin-3be0c4?style=flat-square">
  <img alt="Token-first" src="https://img.shields.io/badge/metric-token--first-ffcb3b?style=flat-square">
  <img alt="Tested: live A/B" src="https://img.shields.io/badge/tested-live%20A%2FB-54e39b?style=flat-square">
  <img alt="Runs locally" src="https://img.shields.io/badge/privacy-runs%20locally-3be0c4?style=flat-square">
</p>

<p align="center">
  <b>A Claude Code plugin that shows exactly where your AI coding session wasted tokens — and how to fix it.</b>
</p>

<p align="center">
  It flags <i>waste</i>, never quality. It runs on your machine. It speaks tokens, not dollars.
</p>

---

## Quickstart (about a minute)

Two commands. The first adds the **`jimmy-tools`** marketplace from this repo (`Jimmynycu/skill`); the second installs the plugin from it. The `@jimmy-tools` handle is the marketplace name declared in [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) — copy both lines exactly.

```sh
# 1) add the marketplace (registers as: jimmy-tools)
claude plugin marketplace add Jimmynycu/skill
# 2) install the plugin from that marketplace
claude plugin install token-efficiency-coach@jimmy-tools
```

> [!NOTE]
> **What "runs locally" means.** The *coach* does all its analysis on your machine — no session content ever leaves. The **install step above is the exception**: `marketplace add` fetches this repo over the network and may ask you to confirm trusting the marketplace before it registers. Once installed, nothing else phones home.

> [!TIP]
> **What you get, immediately:** a live token-first statusline (`ctx tokens · cache% · ⚠`), an automatic non-blocking coach that summarizes waste when a session ends, and an on-demand `/token-efficiency-coach:coach` you can run any time.

That's it. No API keys, no account. The coach reads your local session and talks back.

---

## What it catches

The coach scans a session for **waste** — the tokens you paid for and didn't need. It does **not** grade whether your code or answers were "good." Six things it flags:

- **Context bloat** — the window quietly ballooning turn over turn
- **Uncached context** — paying full freight for context that could have been cached
- **Oversized tool output** — a single tool dumping a wall of tokens into the window
- **Failed tool calls** — errors you paid to send and paid to read
- **Wrong-tier routing** — a heavyweight model doing featherweight work
- **Redundant reads** — re-reading the same file the model already has

> [!NOTE]
> Every flag is a **token** flag. The coach never says "your code is bad." It says "this part cost more than it had to, here's the cheaper path."

---

## Numbers

We ran a live A/B: **6 sessions per arm, 12 real headless `claude` sessions total**, one fixed task, the actual work held constant. Coached vs. baseline:

<p align="center">
  <img src="assets/benchmark.svg" alt="Live A/B results: tokens 133,146 to 72,834 (-45%); turns 4.5 to 2.5 (-44%); correctness 4/6 to 6/6" width="80%">
</p>

| Metric | Baseline | Coached | Change |
| --- | ---: | ---: | ---: |
| Mean tokens / session | 133,146 | 72,834 | **−45%** |
| Mean turns / session | 4.5 | 2.5 | **−44%** |
| Task correctness | 4 / 6 | 6 / 6 | **+2 solved (4/6 → 6/6)** |

**Why it works:** coaching collapses turns. One exact-compute step replaces a sprawl of exploratory ones — and *every* turn re-bills the cached context it carries. Fewer turns, fewer re-bills, fewer tokens.

> [!NOTE]
> **Honest caveats.**
> - **6 per arm, 12 total** — a small sample.
> - One task, one model.
> - Token-first — we did not measure wall-clock or dollars.
> - Your mileage will vary with task shape and model tier.
>
> We are showing you the experiment, not a guarantee.

---

## How it works

Three surfaces. **One engine.** The same local analyzer powers all of them — so the statusline, the end-of-session note, and the on-demand command always agree.

| Surface | When it fires | What it shows |
| --- | --- | --- |
| **Statusline** | Always, live | `ctx tokens · cache% · ⚠` — token-first, at a glance |
| **SessionEnd hook** | Automatically, on session end | A short, **non-blocking** coaching note: where waste happened |
| **`/token-efficiency-coach:coach` command** | On demand | A full breakdown of the current session's waste + concrete fixes |

```
       ┌──────────────────────────────────────────┐
       │             one local engine             │
       │  (parses your session, scores the waste) │  → no network
       └──────────────────────┬───────────────────┘
                              │
      ┌───────────────────────┼───────────────────────────┐
      ▼                       ▼                            ▼
  statusline            SessionEnd hook        /token-efficiency-coach:coach
 (live, always)        (auto, non-blocking)             (on demand)
```

---

## Commands

| Command | What it does |
| --- | --- |
| `/token-efficiency-coach:coach` | Analyze the current session and print where tokens were wasted, with fixes |
| *(SessionEnd hook)* | Runs itself — no command. Prints a short coaching note when a session ends. Never blocks. |
| *(statusline)* | Always on once installed. Shows `ctx tokens · cache% · ⚠` in your status bar. |

---

## FAQ

**Does it send my code anywhere?**
No. Everything runs locally on your machine. No prompt, no code, no session content ever leaves. There is no server to send it to.

**Will the SessionEnd hook slow me down or block my work?**
No. It's non-blocking by design — it prints a short note as a session ends and gets out of the way. If it ever can't run, your session ends exactly as it would have anyway.

**Does it grade the quality of my code?**
Never. The coach only looks at **token waste** — bloat, uncached context, oversized or failed tool calls, wrong-tier routing, redundant reads. Whether the work was good is your call, not the coach's.

**Why tokens and not dollars?**
Tokens are the thing you actually control turn to turn; dollar prices drift and differ per plan. Optimize the tokens and the bill follows. Token-first keeps the signal honest.

**Do I need an API key or an account?**
No. Install the plugin and it works. The engine reads your local session data directly.

---

## License

[MIT](LICENSE). Use it, fork it, ship it.

<sub>Retro pixel art and the coach mascot are original work for this project — inspired by the early-handheld era, not copied from it.</sub>
