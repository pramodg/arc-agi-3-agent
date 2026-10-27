# The baseline agent

`agent/my_agent.py` is a graph explorer. It needs no training, makes no
network or model call (RULES.md 1), and names no public game (RULES.md 3). It
is one file because `scripts/build_notebook.py` splices that one file into the
Kaggle notebook. It is the loop of design section 1, and `iterate` improves its
parts rather than replacing it.

This page describes the agent as the baseline row left it. The changes
`iterate` made since, and the scores that decided each one, are in
`docs/iterate.md`; where the two disagree, `docs/iterate.md` is current.

## The method

1. **State keys.** Each frame's last grid is hashed (blake2b, 128 bits) after
   status cells are set to a sentinel. Two rules find status cells:
   - On a level's first frame: an object lying against one screen edge
     (within 3 cells) that is at least 5 times longer than it is wide, or that
     has more than 3 same-colour, same-size twins against the edge.
   - While playing: an edge band (3 cells deep) that changed on at least 90%
     of the level's steps, after at least 16 steps, is masked whole. A step
     counter ticks whatever the action, while a player only reaches the edge
     now and then. When the mask grows, the level graph starts again, because
     the old keys no longer mean the same thing.
2. **The graph.** Per level, a node per state key, holding the actions not yet
   tried, the recorded transitions, and how often each action ended the game.
   An action that changes nothing is recorded as a self-loop and is never
   chosen again from that state.
3. **The actions of a state.** These are the simple actions the frame's
   `available_actions` offers (never RESET, which the agent controls itself,
   and never ACTION7, which is only used to step back). When ACTION6 is
   offered, the agent adds one click per same-colour 4-connected object. The
   background (the largest object) and status cells are skipped. Each click
   lands on the object's cell nearest its centre. Clicks are sorted into tiers:
   - tier 0: salient colour (6 to 15) and both sides 2 to 32 cells (simple
     actions are tier 0 too)
   - tier 1: button-sized only
   - tier 2: salient only
   - tier 3: the rest

   Within a tier, objects that fill their bounding box go first, then smaller
   ones.
4. **Choosing.** The agent takes the first untried action, at or below the
   current tier, of the current state. If there is none, it walks the shortest
   known path (breadth-first) to the nearest state that has one. The path
   skips transitions that ended the game. From the current state, k undos
   (ACTION7, when offered) count as a way back k states along the history. If
   nothing at the current tier is reachable, but some exists elsewhere, the
   agent resets the level to reach it from the start. If the tier is used up
   everywhere, the next tier opens. When everything is used up, it takes
   random offered actions rather than resetting in a loop.
5. **Game over.** The action that ended the game is counted against that
   state. It is avoided once it has ended the game twice, or at once if it has
   never led anywhere else. Then the agent resets the level and keeps its
   graph, so the next attempt walks straight back to unexplored work.
6. **Later levels.** A level-up starts a new graph and a new mask. The
   simple actions on the shortest known path to the last win are tried first
   on the next level.
7. **Limits.** 10,000 actions per game. A wall-clock cap per game of 80% of an
   assumed 12-hour Kaggle limit spread over 55 games, about 628 seconds,
   until the real limit is known (design section 5). The graph stops growing
   at 50,000 states per level.

## Ideas taken from published agents, and why

The sources were read from their code and papers on 2026-10-25. Kaggle's
discussion pages could not be read without a login, so nothing here comes
from them.

- **Rudakov, Shock and Cowley, "Graph-Based Exploration for ARC-AGI-3
  Interactive Reasoning Tasks"** (arXiv:2512.24156, code at
  github.com/dolphin-in-a-coma/arc-agi-3-just-explore). This agent came third
  in the ARC-AGI-3 preview competition, and it is the closest published match
  to design section 1, with no training. Taken from it:
  - same-colour objects as click targets
  - the four click-priority tiers and their thresholds
  - the static status-bar rule (edge, aspect ratio 5, dot twins)
  - masked-frame hashing
  - a breadth-first walk to the nearest untried action
  - a new graph per level

  Their official score fell because actions that triggered a reset were never
  marked as tried, and the agent looped on them. That is why this agent counts
  game-over actions against their state and routes around them.
- **Blind Squirrel** (Will Dick, second in the preview,
  github.com/wd13ca/ARC-AGI-3-Agents). Taken: ranking click objects by how
  completely they fill their bounding box, and never repeating an action that
  left the frame unchanged. Not taken: its ResNet value model, which needs
  training.
- **StochasticGoose** (Tufa Labs, first in the preview). Not taken. It is a
  CNN trained online to predict which actions change the frame. Its useful
  lesson, to prefer actions that change the frame, is covered more cheaply here
  by dropping self-loops.
- **The ARC-AGI-3 technical report** (arXiv:2603.24621, section 3.5.2). The
  organisers' own validation built hash-based state graphs with self-loops and
  terminal states, and noted that lives and step counters inflate the state
  count. That is the reason for the dynamic counter mask. The "Hill-climbing
  ARC-AGI-3" harness it cites drives a reasoning LLM, so RULES.md 1 rules it
  out.
- **The official templates** (github.com/arcprize/ARC-AGI-3-Agents). Only the
  random agent uses no LLM. Its contract (RESET on NOT_PLAYED and GAME_OVER,
  stop on WIN) is kept.

Added here and not taken from any of them: the dynamic edge-band counter mask,
undo as a planned step back along the history, and ordering the next level's
actions by the shortest winning path.

## Developed against and held out

The split is `pipeline/split.json` (setup wrote it, and this row did not change
it).

- **Developed against (13):** ar25, cd82, dc22, g50t, lf52, ls20, r11l,
  s5i5, sc25, sp80, tn36, tu93, wa30. Every development run and diagnostic
  played only these.
- **Held out (12):** bp35, cn04, ft09, ka59, lp85, m0r0, re86, sb26, sk48,
  su15, tr87, vc33. No change was made on the evidence of any of them.

One disclosure: the first probe of the frame format, before any agent code
existed, reset two held-out games (ft09 and vc33) and printed their frame
shape, colours and available actions. Nothing was played or tuned on them,
and the method above was not changed because of what that probe showed.

The toy games in `tests/test_agent.py` encode no public game.

## Reproducing a run

    make play-local STEPS=10000
    python3 -m pipeline.toolchain run scripts/play_local.py --offline --max-steps 10000 --json var/play.json

`play_local` reports levels and actions per game. RHAE is the evaluation
harness's job (design section 4).
