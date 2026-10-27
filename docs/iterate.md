# Iterating on the explorer

Every change `iterate` evaluated, in order, with the score that decided it.
Each row is a full local competition run of `pipeline/evaluate.py` over all
25 public games at 10,000 actions a game, through the job runner, with the
toolkit's score agreeing in every run. The rule (design section 1): a change
is kept only if held-out RHAE does not fall. Each candidate builds on the
one before it, so a row's score is the agent with every kept change so far.

All runs were made at base commit c2a4714 with the candidate agent file
passed as `--agent`. The agent sha is the first 12 hex digits of the file's
sha256, so a row can be matched to the file that produced it.

| # | Change | Agent sha | Job | Developed | Held-out | Total | Levels | Wall-clock | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| 0 | baseline explorer | 6194ddc154c3 | 20261025T070716-157a65ca | 0.2194% | 0.0180% | 0.1227% | 20/183 | 1555.6 s | reference |
| 1 | step-counter mask | abe93cb77008 | 20261025T074204-40886a5e | 0.2100% | 0.0239% | 0.1207% | 24/183 | 1325.2 s | kept |
| 2 | reset only when useful, forgive deaths, duds last | 2f7702d37f72 | 20261025T074754-19dfc07b | 0.2430% | 0.0499% | 0.1503% | 24/183 | 1288.6 s | kept |
| 3 | carry the counter mask to the next level | 82d20b696a0d | 20261025T080003-7dfc2236 | 0.1957% | 0.0512% | 0.1263% | 25/183 | 1043.0 s | kept (see note) |
| 4 | click sweep once everything is used up | 1176c4b16ff6 | 20261025T081537-9fae1e72 | 0.1957% | 0.0512% | 0.1263% | 25/183 | 1322.7 s | kept (neutral) |

Row 4 was the agent in `agent/my_agent.py` until iterate-2.

## The changes

1. **Step-counter mask.** The baseline masked an edge band only when it
   changed on 90% of steps. Many games have a counter that ticks on about
   every second step, so every tick made a new state and the graphs grew
   without bound. Now a band is masked when it changes on 40% of steps and
   its colour changes run one way (a cell goes a to b but never b to a back).
   A player walking along the edge goes both ways and stays unmasked.
2. **Fewer wasted actions.**
   - The agent resets to reach unexplored work only if that work is
     reachable from the level's start; before, it reset and then wandered.
   - When everything is used up and some actions were avoided for ending the
     game, it forgives them once and tries again, instead of acting at
     random. Actions that end the game only sometimes (traps) get retried.
   - An action that changed nothing on its first two tries anywhere in the
     level is a dud and waits until every other action has been tried.
3. **Counter mask carried over.** A counter found on one level is masked from
   the first frame of the next, instead of being found again. Held-out rose
   slightly, but developed fell: almost all of it is tu93, which still clears
   5 levels but spends more actions on them (its score went from 1.74% to
   1.10%). Kept by the rule. A reviewer may prefer to revisit it.
   Re-judged on developed RHAE in iterate-2 (row 1 below): dropped.
4. **Click sweep.** When the click tiers are used up, the agent adds clicks on
   a 4-cell lattice over the whole board. Within 10,000 actions no game
   reaches that point, so the score is identical to row 3. It is kept for
   the Kaggle run, which allows up to 100,000 actions a game; a toy test
   (`test_clicks_sweep_the_board_when_no_object_helps`) shows it works.

Along the way, the agent's per-game limits moved to the real Kaggle numbers:
up to 100,000 actions, and 75% of the 9-hour notebook runtime as a wall-clock
cap, since all games run at the same time. It keeps only the last few frames
(the framework keeps every frame otherwise) and stops growing a graph at
20,000 states (about 7 KB a state, measured).

## What was learned

- Clearing levels is not the bottleneck it looked like. Every run spends the
  full 10,000 actions, and a cleared level at 50 times the human count scores
  0.04% after squaring. Efficiency per level is where the score is.
- The developed and held-out numbers move independently at this scale. A
  single game's level can swing the developed total by a third, so a change
  is only believable when it moves several games.

## Not done here

- No change was tried at a larger action budget; the Kaggle run allows ten
  times more actions than these evaluations used.
- World-model learning, goal inference and planning over a learned model
  (the brief's larger directions) need rows of their own.

# Iterate-2

The second round changes the rule: a change is kept only if **developed**
RHAE rises. Held-out RHAE is reported for every row and never used to
choose. Each candidate is its own commit, evaluated as a full local
competition run over all 25 public games at 10,000 actions a game, through
the job runner, from a detached checkout of that commit. The toolkit's score
agreed in every run. Each row builds on the one before it.

| # | Change | Commit | Agent sha | Job | Developed | Held-out | Total | Levels | Wall-clock | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | iterate's agent (row 4 above) | 1ce558a | 1176c4b16ff6 | 20261025T095228-0ee776bc | 0.1957% | 0.0512% | 0.1263% | 25/183 | 1023.8 s | reference |
| 1 | each level finds its step counter afresh (iterate row 3 re-judged) | ef318b9 | 3d7ed1716dff | 20261025T100030-a61437c5 | 0.2430% | 0.0499% | 0.1503% | 24/183 | 1041.7 s | kept |
| 2 | player and goal model: learn what moves, guess the goal, head for it | 078daaa | d16885254cb1 | 20261025T100828-43c79303 | 0.3976% | 0.0500% | 0.2307% | 24/183 | 1405.6 s | kept |
| 3 | mask status bars on the game's first frame too | 959fb33 | d07bb5a254ae | 20261025T100940-b26d878f | 0.7731% | 0.0565% | 0.4291% | 27/183 | 1308.2 s | kept |

Row 3 is the agent in `agent/my_agent.py`. Its run is also the final
agent's score over all 25 public games: **0.4291%** (developed 0.7731%,
held-out 0.0565%), 27 of 183 levels.

Row 0 reproduces iterate's row 4 to the digit, so the runs are
deterministic and a difference between rows is the change, not noise.

## The changes

1. **Each level finds its own step counter.** Row 3 of iterate carried the
   counter mask into the next level. On developed RHAE it lost (0.2430% to
   0.1957%, nearly all of it tu93), so it is undone. The score is iterate's
   row 2 again, to the digit.
2. **Player and goal model.** The frame diff now says what moved: a colour
   whose object kept its size but not its centre. The colour that moves most
   under the simple actions is the player, and each action's usual
   displacement is its step. Rare colours (64 cells or fewer, not the
   background, not the player) are goal guesses, and a colour the player
   was next to when it cleared a level leads the guesses on later levels.
   Within the lowest open tier, the action whose predicted landing spot is
   nearest a guess goes first. The walk to untried work looks up to 8 steps
   past the nearest such work for work that ends nearer a guess. tu93 rose
   from 1.74% to 2.92% and ar25 from 0% to 0.94%. ls20, dc22 and sp80 fell
   slightly. The developed total rose.
3. **Status bars masked from the first frame.** Only later levels had their
   status bars masked. Level 1 started unmasked, so a bar that changed made
   new states until the counter detector caught it. sp80 rose from 0.01% to
   5.48% and r11l and tu93 rose a little. sc25 cleared its first two
   levels. ar25 fell back from 0.94% to 0%: it still clears one level, but
   with many more actions.

## Not done here

- When a level's graph is used up the agent still acts at random. ls20's
  second level and g50t's first spend most of their 10,000 actions that way,
  probably against a per-life energy budget. Re-adding game-ending actions
  and unmasking the counter did not help in probes.
- Goal guesses are rare colours only. Games whose goal is a shape or a
  pattern rather than a colour get no help from them.

# Iterate-3

The third round keeps iterate-2's rule: a change is kept only if
**developed** RHAE rises. Held-out RHAE is reported and never used to
choose. Each candidate is its own commit, evaluated as a full local
competition run over all 25 public games at 10,000 actions a game, through
the job runner, from a detached checkout of that commit. The toolkit's score
agreed in every run. Each row builds on the last kept row.

| # | Change | Commit | Agent sha | Job | Developed | Held-out | Total | Levels | Levels lost on other games | Wall-clock | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | iterate-2's agent plus two fixes (a test for the step majority check, no crash in the win note when the frame shrinks) | 713eeff | b15d4f15f469 | 20261025T114043-922a13a7 | 0.7731% | 0.0565% | 0.4291% | 27/183 | none | 1242.6 s | reference |
| 1 | learn a level's step budget and do not blame the last action for running out of it | bf444f4 | 0c909827bb4b | 20261025T114044-76f87c40 | 0.7736% | 0.0569% | 0.4296% | 23/183 | sc25 2 to 0 (developed), cn04 1 to 0, m0r0 2 to 1 (held-out) | 1261.0 s | kept |
| 2 | reset when that is shorter than walking to untried work | 1a95891 | ae4c2e14d091 | 20261025T120245-bd7e6ab1 | 0.77362% | 0.0522% | 0.4273% | 23/183 | none against row 1 | 1233.1 s | dropped (row 1 had 0.77363%) |
| 3 | a click colour that has never changed anything in 6 tries is a dud | 66386c8 | be3c11774960 | 20261025T122409-6a4f5ee7 | 0.7742% | 0.1122% | 0.4565% | 24/183 | none (cn04 regains 1 level) | 1169.8 s | kept |

Row 3 is the agent in `agent/my_agent.py` (commit 66386c8 also undoes row
2). Its run is the final agent's score over all 25 public games:
**0.4565%** (developed 0.7742%, held-out 0.1122%), 24 of 183 levels.

Row 0 reproduces iterate-2's row 3 to the digit, so the runs are
deterministic and a difference between rows is the change, not noise.

## The changes

1. **Step budget.** Most games end a life after a fixed number of steps
   (cd82 at 100, g50t at 130, wa30 at 200, sp80 at 45). The agent blamed the
   last action for each such death and avoided it. Now, once at least two
   different actions have died at the same life length of 10 or more, and
   those deaths are at least half the level's deaths, that length is the
   budget. Deaths at or past it are excused, earlier ones too. tu93's third
   level took 588 actions instead of 757. sc25 lost its two levels, and on
   held-out cn04 lost one level and m0r0 one of two. Developed RHAE rose
   slightly, so it is kept.
2. **Reset or walk (dropped).** A reset was used only when the current state
   could not reach untried work. The candidate also reset when the walk
   from the start was shorter. ar25's first level took 1,711 actions instead
   of 1,506, and developed RHAE fell by a hair.
3. **Colour duds.** In click games most clicks change nothing (tn36: 9,077
   of 9,610 clicks). A click now remembers the colour it hit. Once a colour
   has had 6 clicks and none changed the frame, further clicks on that
   colour go to the dud tier. lf52's first level took 302 actions instead
   of 364 and cd82's 950 instead of 990. On held-out, lp85 and m0r0 cleared
   their first level much faster, cn04 cleared one again, and ft09 cleared
   its level far slower (2,121 actions instead of 229).

## Not done here

- **Winning click colours** (clicks on colours that were clicked on the
  winning path of an earlier level go first). Its probe on the developed
  games matched row 3 except for small changes on r11l and sp80 that won no
  level, so it was not evaluated.
- When a level's graph is used up, the agent still acts at random. On ls20's
  second level and g50t's first, all the untried work left sits in states
  that no known edge from the current state reaches, so neither a walk nor a
  reset gets there.

# Iterate-4

The fourth round keeps the rule: a change is kept only if **developed**
RHAE rises. Held-out RHAE is reported and never used to choose, and no
change looked at or aimed at a held-out game. Each candidate is its own
commit, evaluated as a full local competition run over all 25 public games
at 10,000 actions a game (250,025 actions a run), through the job runner,
from a detached checkout of that commit. The toolkit's score agreed in every
run. Row 1 builds on row 0.

| # | Change | Commit | Agent sha | Job | Developed | Held-out (reported, not used) | Total | Levels | Levels lost: developed | Levels lost: held-out | Slowdowns | Gain from one game | Wall-clock | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref | iterate-3's agent (iterate-3 row 3) | 66386c8 | be3c11774960 | 20261025T122409-6a4f5ee7 | 0.77421% | 0.1122% | 0.4565% | 24/183 | - | - | - | - | 1169.8 s | reference |
| 0 | the three iterate-3 review fixes: a colour dud reads the colour in the judged state's own grid; tests for a colour kept live by one responding click and for a fixed-route trap making no budget | dcc5eee | 7d9eac84ba85 | 20261025T182144-6d61a814 | 0.78750% | 0.11274% | 0.46361% | 23/183 | none | one level | none | yes: lf52 (first level in 99 actions instead of 302); cd82's first level also faster (868 instead of 950) | 1181.1 s | kept |
| 1 | keep every outcome of an action; when the graph is used up, walk through an earlier outcome before acting at random | 0a28c09 | 5ec383140ab4 | 20261025T191754-b9a33acb | 0.78764% | 0.11274% | 0.46369% | 24/183 | none | none | none | yes: ls20 (second level cleared in 7,631 actions, was not cleared) | 1224.8 s | kept |

Row 1 is the agent in `agent/my_agent.py`. Its run is the final agent's
score over all 25 public games: **0.4637%** (developed 0.7876%, held-out
0.1127%), 24 of 183 levels, commit 0a28c09, 1,224.8 s.

Both gains come from a single developed game each (domain rule 3). Neither
row lost a level or slowed a level on any other developed game.

## The changes

0. **Review fixes.** A click remembered only the colour under it in the
   current frame, and the dud check read that colour for whatever state it
   was judging. Each untried click now carries the colour from its own
   state's grid, and the dud check uses that. Two new tests cover a colour
   that stays live because one of its clicks changed the frame, and an
   action that dies again and again at one length on a fixed route, which
   must not become a step budget. lf52's first level, which depends on which
   colours count as duds, took 99 actions instead of 302.
1. **Earlier outcomes.** An action from a state can lead to different
   states when the game has a hidden variable (a key held, a switch, energy
   left). The graph kept only the latest outcome, so one different result
   could cut off a part of the graph the agent had reached many times. In
   ls20's second level one action reached an island 19 times and somewhere
   else once, and the overwrite left the island's untried work unreachable,
   so the agent acted at random for 9,000 actions. Now the node keeps every
   outcome with a count of times it happened and times it was expected and
   missed. Ordinary walks still use only the latest outcome. Only when no
   walk and no reset reaches untried work does the agent plan through
   earlier outcomes, dropping any that missed more often than they hit.

Row 0 also made dc22's first level slightly faster (4,683 actions instead
of 4,703).

## Guard tests and the mutants they catch

Every new rule of this round has a test in `tests/test_agent.py` that fails
when the rule is switched off. Each mutant below was applied on its own to
a scratch copy of the agent, and the full test suite was run against it.
Each run failed the test named. The budget, lattice, excuse, hit and
expected-outcome mutants were run in the last round of this row (110 tests,
one failure each). The rest were run in earlier rounds, and the review
repeated them.

| Rule | Mutant | Failing test |
|---|---|---|
| colour dud reads the judged state's colour | dud check ignores the colour | `test_a_colour_dud_reads_the_judged_states_own_grid` and one more colour-dud test |
| one responding click keeps a colour live | the change count is not checked | `test_one_responding_click_keeps_a_colour_live` |
| one action at one length makes no budget | `BUDGET_DEATHS = 1` | `test_one_action_dying_at_one_length_makes_no_budget` |
| a budget needs half the level's deaths | `2 * len(died) >= total` removed | `test_a_budget_needs_half_the_deaths_and_a_long_enough_life` |
| a budget needs a life of at least `MIN_BUDGET` | `n >= MIN_BUDGET` removed | `test_a_budget_needs_half_the_deaths_and_a_long_enough_life` |
| lattice clicks outside the current state have no colour | `colours=False` dropped, so they get the current grid's colours | `test_lattice_clicks_elsewhere_have_no_colour` |
| an excused action goes back with its colour | `_excuse` re-queues with `None` | `test_an_excused_click_is_queued_again_with_its_colour` |
| an unclear death keeps the click's colour | the unclear list stores `None` | `test_an_excused_click_is_queued_again_with_its_colour` |
| every outcome is kept | nodes keep no earlier outcomes | `test_a_used_up_graph_walks_through_an_earlier_outcome` |
| a used-up graph walks through an earlier outcome | the fallback route removed | `test_a_used_up_graph_walks_through_an_earlier_outcome` and the miss tests |
| reset when only the start reaches an earlier outcome | the reset condition made `False` | `test_a_used_up_graph_resets_when_only_the_start_reaches_a_door` |
| a walk that lands on its expected outcome counts a hit | hit increment `+= 0` in `Node.note_outcome` | `test_a_walk_that_reaches_its_earlier_outcome_counts_a_hit` |
| only a walk that lands elsewhere counts a miss | the `self.plan[0][1] != k` condition removed | `test_a_walk_that_reaches_its_earlier_outcome_counts_a_hit` |
| a walk that lands elsewhere counts a miss | the miss increment made a no-op | `test_a_walk_that_misses_its_earlier_outcome_counts_it_in_play` |
| an outcome missed more than `ALT_MISSES` times per hit is dropped | the miss filter always keeps | `test_an_earlier_outcome_missed_too_often_is_dropped` and the play-through miss test |

## Probes that were not evaluated

These ran on the developed games only, so they have no full-run row.

- **alt3**: the row 1 code before its docstring was written, run on the
  developed games first. It gave 0.78764%, the same as row 1's full run.
- **altedges**: an earlier form of the every-walk probe below. It never
  wrote a result.

- **Earlier outcomes in every walk** (not only as a fallback). sc25
  cleared its first two levels again, but tu93's fifth level took 3,694
  actions instead of 2,708, and developed RHAE fell to 0.78673%. That led to
  the fallback-only design of row 1, which leaves sc25 at zero.

## Not done here

- **sc25's two levels are not back.** They came back only with the probe
  above, which cost more on tu93 than it won. Its deaths are mostly at one
  life length, a real step budget, and its wins in earlier rounds came late
  (8,619 actions in iterate-2), so they are fragile.
- g50t's first level still ends in random actions even with the fallback.
- In move games the walks back after a death dominate (tu93's sixth level:
  211 deaths and 3,312 walking actions). Learning which colours kill would
  shorten them.
- In click games thousands of no-op clicks still go to the dud tier in every
  state (dc22, tn36). A cap per level was considered, not tried.
