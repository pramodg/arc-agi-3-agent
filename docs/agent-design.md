# Agent design notes

The running record of what was tried on the agent, what it scored, and what
was learned. Newest first. Every agent row adds an entry at the top: the
change, the developed and held-out RHAE from a run of
`pipeline/evaluate.py` (RULES.md 2: commit, actions and wall-clock beside
it), and one or two lines on what it taught. Keep entries short; the method
in full lives in docs/baseline.md and the scoring in docs/scoring.md.

Held-out games (pipeline/split.json) are scored, never watched: replays on
the project page are developed games only (docs/design.md section 6).

## 2026-10-25 · review fixes, earlier outcomes (iterate-4)

- **Change:** two kept changes, each judged on developed RHAE
  (docs/iterate.md, iterate-4): a colour dud reads the colour in the grid of
  the state being judged; an action that has led to different states keeps
  every outcome, and when nothing else reaches untried work the agent walks
  through an earlier outcome instead of acting at random.
- **Result:** RHAE 0.46% over 25 games (developed 0.79%, held-out 0.11%),
  levels 24/183, 250,025 actions, toolkit agrees. Local competition run, job
  20261025T191754-b9a33acb, commit 0a28c09082c5, 1,224.8 s.
- **Learned:** hidden variables make an action's outcome change, and
  overwriting the edge cut ls20 off from work it had reached 19 times. Using
  every outcome in every walk won sc25 back but slowed tu93, so the earlier
  outcomes are a last resort only. Each gain came from a single game.

## 2026-10-25 · step budget, colour duds (iterate-3)

- **Change:** two kept changes, each judged on developed RHAE
  (docs/iterate.md, iterate-3): a learned per-level step budget, so running
  out of steps is not blamed on the last action; clicks on a colour that
  never changed anything in 6 tries become duds. A reset-or-walk change was
  dropped.
- **Result:** RHAE 0.46% over 25 games (developed 0.77%, held-out 0.11%),
  levels 24/183, 250,025 actions, toolkit agrees. Local competition run, job
  20261025T122409-6a4f5ee7, commit 66386c8ef202, 1,169.8 s.
- **Learned:** the developed games are stuck behind levels the agent cannot
  reach at all, so changes that only make it faster move developed RHAE by
  hundredths of a percent. Held-out moved more than developed this round.

## 2026-10-25 · player and goal model, first-frame status mask (iterate-2)

- **Change:** three kept changes, each judged on developed RHAE
  (docs/iterate.md, iterate-2): each level finds its step counter afresh
  (iterate's row 3 undone); a player and goal model that learns what moves
  and heads for rare colours; status bars masked on the first frame too.
- **Result:** RHAE 0.43% over 25 games (developed 0.77%, held-out 0.06%),
  levels 27/183, 250,025 actions, toolkit agrees. Local competition run, job
  20261025T100940-b26d878f, commit 959fb3329417, 1,308.2 s. Best games:
  sp80 5.48%, tu93 3.22%, r11l 1.31%.
- **Learned:** small fixes to the first level pay most, because a level
  cleared near the human count scores far more than several cleared slowly.
  Masking the status bar from the first frame doubled the developed score.

## 2026-10-25 · counter mask, fewer wasted actions, click sweep (iterate)

- **Change:** four rows (docs/iterate.md): a step-counter mask; resets only
  when useful, forgiven deaths and duds last; the counter mask carried to the
  next level; a click sweep when everything is used up.
- **Result:** the last row scored RHAE 0.13% (developed 0.20%, held-out
  0.05%), levels 25/183, job 20261025T081537-9fae1e72, 1,322.7 s. The best
  developed row was row 2 at 0.24%.
- **Learned:** the developed and held-out totals move independently at this
  scale, so one game's level can swing a row.

## 2026-10-25 · baseline explorer, first RHAE (gameplay-pane)

- **Change:** none to the agent; the baseline explorer scored by the harness
  for the first time, with `--record` on.
- **Result:** RHAE 0.12% over 25 games (developed 0.22%, held-out 0.02%),
  levels 20/183, 250,025 actions, toolkit 0.12% (agrees). Local competition
  run, job 20261025T071047-d8db2360, commit 3932ca0b49da, 1,098.9 s. Best
  games: tu93 1.41% (5/9 levels), r11l 1.00%, ar25 0.33%; held-out best
  vc33 0.12% (3/7).
- **Learned:** levels are being cleared, but at many times the human action
  count, so each cleared level scores near zero after squaring. Every game
  spent the full 10,001 actions. Fewer wasted actions per level is now worth
  as much as clearing new ones. Replays of the 13 developed games are in
  var/replays/20261025T073316/.

## 2026-10-25 · baseline explorer (baseline-agent)

- **Change:** a graph explorer replaces the random agent
  (`agent/my_agent.py`, docs/baseline.md). Masked-frame state hashing, a
  graph per level, object clicks in four priority tiers, a breadth-first walk
  to the nearest untried action, undo as a step back, game-ending actions
  avoided.
- **Result:** levels only, from `scripts/play_local.py` at 10,000 actions a
  game (job 20261025T054258-bc750b65, commit ae8288711cd4, 1,099.5 s): 20
  levels over 25 games against random's 5. Developed 13 levels, held-out 7
  (random: 2 and 3). No RHAE was measured for this run.
- **Learned:** every game used the whole 10,000-action budget. About half the
  games stall, open boards are slow to explore depth-first, and some state
  graphs reach 1,000 to 1,700 states. Click-only games with tiny changes run
  out of click targets. The held-out levels being more than twice random's
  says the method is not just fitted to the developed games.

## 2026-10-25 · starter random agent (setup, eval-harness)

- **Change:** none; the starter kit's random agent at 80 actions a game, the
  harness's first measured RHAE.
- **Result:** RHAE 0.00% (developed 0.00%, held-out 0.00%), 0/183 levels,
  2,025 actions over 25 games. Local competition run at commit 918448e00295
  (3.8 s), confirmed online at 6bf87b4c12c4 (526.4 s), toolkit agreeing both
  times.
- **Learned:** 80 random actions clear nothing. RHAE is zero for any game with
  no completed level, so completion comes before efficiency.
