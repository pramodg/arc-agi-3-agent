# How we score: RHAE, locally, in competition mode

The rule itself is in docs/requirements.md
("Scoring: RHAE"); this page says how the harness applies it and how far
its numbers can be trusted.

## The rule, as the code applies it

`pipeline/scorer.py` follows the methodology page
(https://docs.arcprize.org/methodology.md) and the arc-agi toolkit's own
calculator (`arc_agi/scorecard.py`, `EnvironmentScoreCalculator`, arc-agi
0.9.9):

- A completed level scores `min(1.15, (human_actions / ai_actions) ** 2)`.
  An uncompleted level scores 0.
- A game scores the average of its level scores weighted by the 1-indexed
  level number, capped at the weight share of the levels it completed. Four
  of five levels caps the game at 10/15 = 66.7%. All levels done at better
  than human pace still gives 100%, not 115%.
- The total is the plain mean over games.

`tests/test_scorer.py` reproduces every worked example on the methodology
page: 10 vs 10 = 1.0, 10 vs 20 = 0.25, 10 vs 100 = 0.01, the 1.15 cap, the
66.7% cap, and the upper median of four and of five players. It also scores
synthetic plays that complete levels with both our scorer and the toolkit's
`EnvironmentScorecard.from_scorecard`, and requires the same score, actions
and per-level actions.

## The human baselines

Each game's metadata, which the toolkit downloads from three.arcprize.org
with the game, carries `baseline_actions`: one number per level, the upper
median first-time human. The toolkit scores against exactly these numbers.
The harness reads them from the cached `metadata.json` and records the
file and its download date beside every game in the result.

## What counts as an action

The same as the toolkit's scorecard, so the counts can be compared step for
step:

- every ACTION1-7 that returns a frame counts, including ones that change
  nothing visible;
- a level RESET counts;
- a full RESET starts a new play and does not count;
- a step that returns no frame (anything but RESET after GAME_OVER or WIN)
  does not count.

## Competition mode, locally

Kaggle forces competition mode: one `make()` per game, resets become level
resets, no score until the end. Locally the harness:

- calls `make()` once per game. That call does the one full reset;
- sets the engine's `ONLY_RESET_LEVELS` switch from then on, so every RESET
  the agent sends is a level reset and the game stays one play. Without it,
  the engine turns any RESET sent with no action since the last reset into
  a full reset, which starts a second play on the local scorecard. That
  covers a RESET sent as the agent's very first action (make() has just
  reset) and a RESET sent straight after another RESET at any point. A
  single RESET after at least one other action is a level reset either way.
  `tests/test_evaluate.py` guards both cases: an agent that resets first,
  and one that resets twice in a row later;
- ends the game at WIN;
- stops the agent before its next action once the per-game wall-clock limit
  has passed. The default is 441 s: 75% of Kaggle's 9-hour runtime
  (docs/submission.md) shared by 55 games. Kaggle plays the games at once in
  one interpreter, and locally they run one after another, so this is each
  game's share of the same compute (`PER_GAME_SECONDS` in
  `pipeline/evaluate.py`);
- keeps the agent's own `MAX_ACTIONS`, as Kaggle does. `--max-actions` can
  only lower it;
- reads the scorecard only after every game has finished.

`--online` plays the same games on the official server with
`OperationMode.COMPETITION` (anonymous key unless `ARC_API_KEY` is set). The
server enforces competition mode itself and its scorecard is the official
one. The server refused requests (HTTP 429) after about 380 in 45 seconds
on 2026-10-25, so an online run sends at most one step every 0.25 s and
waits out a refusal before sending the same step again. A full online run
of an 80-action agent takes about ten minutes. Only the harness talks to the server. The submitted agent never does.

## Running it

    python3 -m pipeline.toolchain run -m pipeline.evaluate run                  # local, every public game
    python3 -m pipeline.toolchain run -m pipeline.evaluate run --online         # the official server
    python3 -m pipeline.toolchain run -m pipeline.evaluate run --agent path/to/agent.py
    python3 -m pipeline.toolchain run -m pipeline.evaluate run --agent scripts/random_agent.py

A full local run over every public game takes about half an hour at 10,000
actions a game, so run it in the background. `--games ls20` is fine in the
foreground for one or two games. `scripts/random_agent.py` is the random
agent we compare against, with its cap committed (docs/setup.md).

Each run writes `var/eval/<time>-<commit>-<agent>-<local|online>.json` in
the shared `var/` beside the primary checkout. It holds the commit, the
agent file's hash, the versions, the limits, and per game: the split half,
how the game ended, the seconds, the baselines and their source, our score,
level actions and level scores, and the toolkit's score, actions and play
count for the same run. It prints a per-game table, developed games first,
then held out, and ends with one line:

    RHAE 0.00% over 25 games (developed 0.00%, held-out 0.00%), levels 0/183, actions 2025, toolkit 0.00% (agrees), local competition, commit ..., 4.1s

"agrees" means our total and the toolkit's are within 0.01 RHAE points. The
JSON's `games_disagreeing` names any game where the score or the action
count differs.

## How far to trust it

- Our scorer and the toolkit's agree by construction on the formula. The
  unit tests check that on plays that complete levels.
- Our action count comes from our own trace of the agent's steps. The
  toolkit's comes from its scorecard. Every run compares the two per game.
- The official server is a separate run of the same agent. A random agent
  plays differently each time, so for it only the action counts and the
  zero scores can be compared, not the exact trace.
- The level weighting cap is applied the toolkit's way: by the levels with a
  non-zero score. A completed level always scores above zero, so this is the
  methodology's "levels completed".
