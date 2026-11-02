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

## The finals: Duck fork v1 (top) and v2

The submitted agent is not `agent/my_agent.py`. It is a fork of Daniel
Franzen's ARC-AGI-3 Milestone 2 notebook, which runs Tufa Labs' Duck harness
around an open-weights Qwen3.8-Flash-Next model on Kaggle's own GPU, with
internet off. Kaggle keeps the two best public scores as the finals:

| Final | Variant | Kaggle submission | Public score | Notebook sha256 |
|---|---|---|---|---|
| Top | v1 | 57717186 | 29.55 | `383f4cb43ad39187db0babe5593901713e16985b1227896ea1159ae15539bebf` |
| Second | v2 | 57752683 | 28.38 | `6ce147f0bfa24402b2d6797b6697ac99943c8a59af517dbcfbdd3f2877040ad4` |

v1 is the plain fork: a 40-minute model startup deadline instead of 12, a
short commit run that plays no games, and our own kernel id. v2 adds the
solved-level memory (`duck/solved_level_memory.py`): each cleared level's
facts and the model's one-line rule are pinned at the end of the system
prompt, for the current game only.

Rebuild either final exactly:

    python3 scripts/build_duck_notebook.py --variant v1 --unsplit --out finals/v1
    python3 scripts/build_duck_notebook.py --variant v2 --unsplit --out finals/v2

They print the sha256 values above. `--unsplit` keeps Franzen's harness
patch in one cell, as the notebooks were when they were scored; later
builds cut it into pieces, which changes the bytes but not the patch.

### The last entry: the two-mode player (tm-5-ask)

The last entry, submitted on 2026-11-02, is tm-5-ask (submission 57904471,
public score 24.61). It is below both finals. It adds a two-mode player:
recognise, understand (which object is the player, what it carries, what
ends a level or a life, what drains with each action), test, and hand off to
play. It keeps a rules note for the current game only. It carries no replay
of solved levels and no store shared between games.

    python3 scripts/build_duck_notebook.py --variant tm-5-ask --out notebooks/duck

It prints sha256 `f6ec1363a8c02a4e5ed059d1a05907004b88fec97afa16ab092550a47a3d96d8`,
the hash of `notebooks/duck/arc-agi-3-duck-fork.ipynb` here.

### What is where in the fork

- `scripts/build_duck_notebook.py` is our builder.
- `duck/variants/*.toml` name each variant and the cells it adds;
  v1 and v2 are the finals; tm-5-ask builds on earlier variants there,
  back to v1.
- `duck/twomode/`, `duck/bigmodel/`, `duck/r3/`, `duck/r4/`, `duck/staged/`,
  `duck/hypothesis/`, `duck/twotier/`, `duck/gate_cell.py` and
  `duck/standin_cell.py` are our cells (MIT-0).
- `duck/harness/` is Franzen's harness patch cut into pieces, and
  `duck/upstream/` his notebook, both unchanged (Apache-2.0).
- `duck/NOTICE` names every third-party part and its licence. The Kaggle
  inputs (the Duck source bundle, the Pennyroyal wheelhouse and the model
  weights) are attached to the notebook on Kaggle and never copied here.

## Licence

Our code is MIT-0 (`LICENSE`). docs/setup.md names each third-party
component's licence; none of them is copied into this repository.
