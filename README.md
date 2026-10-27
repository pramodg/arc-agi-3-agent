# arc-agi-3

An offline agent for ARC Prize 2026's ARC-AGI-3 track: beat unseen,
instruction-free grid games in as few actions as a first-time human.

## The goal

A notebook submitted to the Kaggle competition `arc-prize-2026-arc-agi-3`
before the final deadline (2026-11-02), scored on the hidden set, with the
agent's code open-sourced under CC0 or MIT-0 as the prize rules require.

## The constraints that shape everything (docs/requirements.md)

- The evaluation runs on Kaggle **with no internet**: no Claude, GPT or other
  API calls. The agent must be self-contained (code, plus any open weights
  shipped with it).
- Scoring is RHAE: per level `min(1.15, (human_actions / ai_actions)^2)`,
  levels weighted by their number, games averaged. Completion first, then
  action efficiency.
- The 55 competition games are private and harder than the 25 public ones.
  Anything tuned to the public games is expected not to transfer.

## Running it offline

    make setup          # the Python 3.12 environment and the agents framework
    make play-local     # the agent on every public game (GAME=ls20 for one)
    make play-random    # the random agent we compare against
    make test           # the unit tests
    python3 -m pipeline.toolchain run -m pipeline.evaluate run   # RHAE over every public game
    make notebook       # the Kaggle notebook, from agent/my_agent.py

The first play downloads the public games into a local cache. After that,
`scripts/play_local.py --offline` and the evaluator need no network
(docs/setup.md). `make submit` pushes the notebook to Kaggle
(docs/submission.md).

## What is where

- `agent/my_agent.py` is the submitted agent. docs/agent-design.md and
  docs/baseline.md describe how it works and how each change scored.
- `pipeline/` is the harness: the shared Python 3.12 toolchain, the held-out
  split, local evaluation in competition mode, and the RHAE scorer
  (docs/scoring.md).
- `scripts/` and the `Makefile` play agents locally and build the Kaggle
  notebook.
- `docs/requirements.md` is the competition's rules, with sources.
- `var/` is runtime output (game caches, recordings, logs). Ignored by git.

## Licence

Our code is MIT-0 (`LICENSE`). docs/setup.md names each third-party
component's licence; none of them is copied into this repository.
