"""The graph-explorer agent, tested on toy games that encode no public game."""
import importlib
import importlib.util
import os
import re
import sys
import unittest
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "vendor", "ARC-AGI-3-Agents")
HAVE_ARC = importlib.util.find_spec("arcengine") is not None
if os.path.isdir(VENDOR):
    sys.path.insert(0, VENDOR)
READY = HAVE_ARC and os.path.isdir(VENDOR)

if READY:
    my_agent = importlib.import_module("agent.my_agent")


class Toy:
    """A tiny game: a player on a grid, walls, a goal, optional extras.

    Actions 1-4 move up, down, left, right. Reaching the goal clears the
    level. `trap` cells end the game. `counter` draws a step counter on the
    bottom row. `button`, if set, is a cell ACTION6 must click to win.
    `flaky` cells end the game only on every second entry. `bar` draws a
    static status bar on the top row whose length changes with the level.
    `secret` is an unmarked cell that wins when ACTION6 clicks exactly it.
    `full_restart` copies the engine's rule that a RESET with no action since
    the last RESET restarts the whole game, not just the level. `decoys` are
    cells drawn in their own rare colour that do nothing. `budget` ends the
    game after that many actions since the last reset or win, whatever the
    last action was.
    """

    def __init__(self, size=24, start=(8, 8), goal=(14, 14), walls=(),
                 traps=(), counter=False, button=None, actions=(1, 2, 3, 4),
                 levels=1, undo=False, flaky=(), bar=False,
                 full_restart=False, secret=None, decoys=(), budget=None):
        self.size, self.start, self.goal = size, start, goal
        self.walls, self.traps = set(walls), set(traps)
        self.counter, self.button, self.levels = counter, button, levels
        self.flaky, self.entries = set(flaky), 0
        self.bar, self.full_restart = bar, full_restart
        self.secret, self.decoys = secret, set(decoys)
        self.budget, self.life = budget, 0
        self.actions = list(actions) + ([7] if undo else [])
        self.done_levels, self.steps, self.resets = 0, 0, 0
        self.full_restarts = 0
        self.last_was_reset = False
        self.trail = []
        self.reset()

    def reset(self):
        if self.full_restart and self.last_was_reset:
            self.done_levels = 0
            self.full_restarts += 1
        self.pos, self.state, self.trail = self.start, "NOT_FINISHED", []
        self.resets += 1
        self.life = 0

    def grid(self):
        g = [[0] * self.size for _ in range(self.size)]
        for r, c in self.walls:
            g[r][c] = 5
        for r, c in self.decoys:
            g[r][c] = 14
        gr, gc = self.goal
        g[gr][gc] = 3
        if self.button:
            br, bc = self.button
            for dr in (0, 1):
                for dc in (0, 1):
                    g[br + dr][bc + dc] = 12
        if self.bar:
            for c in range(2, 8 + 3 * self.done_levels):
                g[0][c] = 11
        r, c = self.pos
        g[r][c] = 9
        if self.counter:
            for c in range(self.steps % self.size):
                g[self.size - 1][c] = 4
        return tuple(tuple(row) for row in g)

    def step(self, act):
        a, x, y = act
        self.steps += 1
        if a == 0:
            self.reset()
            self.last_was_reset = True
            return
        self.last_was_reset = False
        if self.state == "GAME_OVER":
            return
        self.life += 1
        self._act(a, x, y)
        if self.budget and self.life >= self.budget \
                and self.state == "NOT_FINISHED":
            self.state = "GAME_OVER"

    def _act(self, a, x, y):
        if a == 7 and self.trail:
            self.pos = self.trail.pop()
            return
        if a == 6 and self.secret == (y, x):
            self._clear()
            return
        if a == 6 and self.button:
            br, bc = self.button
            if br <= y <= br + 1 and bc <= x <= bc + 1:
                self._clear()
            return
        moves = {1: (-1, 0), 2: (1, 0), 3: (0, -1), 4: (0, 1)}
        if a in moves:
            dr, dc = moves[a]
            r, c = self.pos[0] + dr, self.pos[1] + dc
            if (1 if self.bar else 0) <= r < self.size - 1 \
                    and 0 <= c < self.size \
                    and (r, c) not in self.walls:
                self.trail.append(self.pos)
                self.pos = (r, c)
            if self.pos in self.flaky:
                self.entries += 1
            if self.pos in self.traps or (self.pos in self.flaky
                                          and self.entries % 2 == 0):
                self.state = "GAME_OVER"
            elif self.pos == self.goal and not self.button:
                self._clear()

    def _clear(self):
        self.done_levels += 1
        self.state = "WIN" if self.done_levels >= self.levels else "NOT_FINISHED"
        self.pos, self.trail = self.start, []
        self.life = 0


def play(toy, explorer, max_steps):
    """Drive the explorer on a toy until it wins or runs out of steps.

    Returns the (position, action) pairs it played.
    """
    log = []
    for _ in range(max_steps):
        explorer.observe(toy.grid(), toy.state, toy.done_levels, toy.actions)
        if toy.state == "WIN":
            break
        act = explorer.next_action()
        log.append((toy.pos, act))
        toy.step(act)
    return log


@unittest.skipUnless(READY, "needs the 3.12 env and vendor/ (make setup)")
class ExplorerTest(unittest.TestCase):
    def test_agent_finds_the_goal_behind_a_wall(self):
        # A wall between start and goal, open only at the bottom.
        toy = Toy(walls=[(r, 11) for r in range(19)])
        play(toy, my_agent.Explorer(), 2000)
        self.assertEqual(toy.state, "WIN")

    def test_agent_keeps_going_on_later_levels(self):
        toy = Toy(levels=3)
        ex = my_agent.Explorer()
        play(toy, ex, 6000)
        self.assertEqual(toy.done_levels, 3)
        # The shortest win is 6 down and 6 right: those lead the next level.
        self.assertEqual({a for a, _ in ex.win_counts.most_common(2)}, {2, 4})

    def test_agent_only_uses_offered_actions(self):
        toy = Toy(actions=(2, 4))
        log = play(toy, my_agent.Explorer(), 1000)
        self.assertEqual(toy.state, "WIN")
        self.assertTrue({a for _, (a, _, _) in log} <= {0, 2, 4})

    def test_an_action_that_changes_nothing_is_not_repeated(self):
        # In the top-left corner, up and left change nothing.
        toy = Toy(start=(0, 0), goal=(6, 6))
        log = play(toy, my_agent.Explorer(), 1000)
        self.assertEqual(toy.state, "WIN")
        for blocked in (1, 3):
            tries = [1 for pos, (a, _, _) in log if pos == (0, 0) and a == blocked]
            self.assertEqual(len(tries), 1, blocked)

    def test_the_step_counter_is_masked_out_of_the_state(self):
        # A wall with a gap at its far end keeps the goal out of reach for
        # 60 steps, so the agent has to watch the counter tick.
        toy = Toy(counter=True, walls=[(11, c) for c in range(23)])
        ex = my_agent.Explorer()
        play(toy, ex, 60)
        self.assertEqual(ex.ticking, {"bottom"})
        self.assertTrue(all(r >= toy.size - my_agent.EDGE for r, _ in ex.masked))
        # The graph was rebuilt once the counter was masked: 60 steps cannot
        # have made 60 states.
        self.assertLess(len(ex.nodes), 60 - my_agent.TICK_MIN_STEPS)
        play(toy, ex, 3000)
        self.assertEqual(toy.state, "WIN")

    def test_each_level_finds_its_step_counter_afresh(self):
        # Kept on developed RHAE (iterate-2 row 1): a counter found on one
        # level is not assumed on the next, which starts unmasked and finds
        # it again by watching.
        toy = Toy(counter=True, levels=2)
        ex = my_agent.Explorer()
        for _ in range(3000):
            ex.observe(toy.grid(), toy.state, toy.done_levels, toy.actions)
            if toy.done_levels == 1:
                break
            toy.step(ex.next_action())
        self.assertEqual(ex.level, 1)
        self.assertEqual(ex.ticking, set())
        bottom = {(r, c) for r in range(toy.size - my_agent.EDGE, toy.size)
                  for c in range(toy.size)}
        self.assertFalse(bottom <= ex.masked)
        play(toy, ex, 3000)
        self.assertEqual(toy.state, "WIN")

    def test_a_deadly_action_is_not_taken_again(self):
        # Stepping down from the start lands on a trap, on the way to the
        # goal, so the goal guess tempts the agent through it.
        toy = Toy(traps=[(9, 8)], goal=(16, 8))
        log = play(toy, my_agent.Explorer(), 2000)
        self.assertEqual(toy.state, "WIN")
        deaths = [1 for pos, (a, _, _) in log if pos == (8, 8) and a == 2]
        self.assertEqual(len(deaths), 1)

    def test_an_action_that_kills_on_some_tries_is_avoided_after_two(self):
        # Entering (9, 8) kills on every second entry. Down from the start
        # led somewhere the first time, so it stays usable until that very
        # move has ended the game twice, and then it is never planned again.
        # A wall with two gaps (the flaky cell and a far detour) splits the
        # board, and traps below force many resets, so the short way through
        # the flaky cell keeps tempting the planner.
        walls = [(9, c) for c in range(24) if c not in (8, 23)]
        traps = [(14, c) for c in range(3, 20, 4)] \
            + [(17, c) for c in range(1, 22, 5)]
        toy = Toy(flaky=[(9, 8)], walls=walls, traps=traps, goal=(21, 2))
        ex = my_agent.Explorer()
        deaths = Counter()
        for _ in range(8000):
            ex.observe(toy.grid(), toy.state, toy.done_levels, toy.actions)
            if toy.state == "WIN":
                break
            act = ex.next_action()
            pos = toy.pos
            toy.step(act)
            if toy.state == "GAME_OVER":
                deaths[(pos, act[0])] += 1
        self.assertEqual(toy.state, "WIN")
        self.assertGreaterEqual(sum(deaths.values()), 2)
        # The literal 2, not the constant: raising the limit must fail here.
        self.assertLessEqual(max(deaths.values()), 2)

    def test_running_out_of_steps_is_not_blamed_on_the_last_action(self):
        # Every life ends after 20 actions, whatever the last one was. Once
        # two lives have ended at 20, the budget is known: the actions that
        # happened to be last are not avoided, and those never seen to lead
        # anywhere are tried again.
        toy = Toy(size=32, start=(4, 4), goal=(28, 28), budget=20,
                  walls=[(r, 16) for r in range(31)])
        ex = my_agent.Explorer()
        last = []
        for _ in range(4000):
            ex.observe(toy.grid(), toy.state, toy.done_levels, toy.actions)
            if toy.state == "WIN":
                break
            if ex.cur is not None and ex.budget() is None:
                k = ex.cur
            act = ex.next_action()
            toy.step(act)
            if toy.state == "GAME_OVER" and len(last) < 2:
                last.append((k, act))
        self.assertEqual(ex.budget(), 20)
        for k, act in last:
            self.assertFalse(ex.nodes[k].avoid(act), act)
            self.assertTrue(act in ex.nodes[k].edges
                            or act in [a for _, a, _ in ex.nodes[k].untried], act)

    def test_an_untried_action_that_dies_at_the_budget_twice_is_avoided(self):
        # A budget death is excused, but not forever: the same untried
        # action ending the game twice may be a trap after all.
        ex = my_agent.Explorer()
        node = my_agent.Node([])
        ex.nodes["s"] = node
        ex.death_lives[20] = {("a", (1, -1, -1)), ("b", (2, -1, -1))}
        act = (1, -1, -1)
        for _ in range(2):
            ex.life = 20
            ex._note_death("s", act)
        self.assertTrue(node.avoid(act))

    def test_one_action_dying_at_one_length_makes_no_budget(self):
        # A trap on a fixed route kills at the same life length every time,
        # but always on the same action from the same state: that is a trap,
        # not a step budget, and it stays blamed.
        ex = my_agent.Explorer()
        node = my_agent.Node([])
        ex.nodes["s"] = node
        act = (2, -1, -1)
        for _ in range(4):
            ex.life = 20
            ex._note_death("s", act)
        self.assertIsNone(ex.budget())
        self.assertEqual(node.deaths[act], 4)
        self.assertTrue(node.avoid(act))

    def _hidden_door_graph(self):
        # Down from "a" once led to "r", where untried work waits, and then
        # did nothing (a hidden variable decides). Every other state is used
        # up, so only that earlier outcome leads anywhere new.
        ex = my_agent.Explorer()
        up, down = (1, -1, -1), (2, -1, -1)
        nodes = {k: my_agent.Node([]) for k in ("s", "a")}
        nodes["r"] = my_agent.Node([(0, up, None)])
        nodes["s"].note_outcome(down, "a")
        nodes["a"].note_outcome(down, "r")
        nodes["a"].note_outcome(down, "a")
        nodes["a"].note_outcome(up, "s")
        ex.nodes, ex.cur, ex.start, ex.available = nodes, "a", "s", [1, 2]
        ex.tier = ex.top_tier
        return ex, down

    def test_a_used_up_graph_walks_through_an_earlier_outcome(self):
        ex, down = self._hidden_door_graph()
        self.assertEqual(ex.nodes["a"].edges[down], "a")
        self.assertEqual(ex.next_action(), down)
        self.assertEqual(ex.why, "walk through an earlier outcome")
        self.assertEqual(ex.plan, [(down, "r")])

    def test_an_earlier_outcome_missed_too_often_is_dropped(self):
        # Walks expecting "r" got something else twice for the one time it
        # happened: it is no longer planned through.
        ex, down = self._hidden_door_graph()
        ex.nodes["a"].alts[down]["r"] = [1, 2]
        ex.next_action()
        self.assertEqual(ex.why, "random: graph used up")
        self.assertEqual(my_agent.ALT_MISSES, 1)

    def _played_door(self):
        # The hidden door graph with real frames, for play through observe:
        # down from "a" led to "r" once, then back to "a".
        def frame(v):
            g = [[0] * 8 for _ in range(8)]
            g[0][0] = g[7][7] = v
            return tuple(tuple(r) for r in g)
        gs, ga, gr = frame(1), frame(2), frame(3)
        ex = my_agent.Explorer()
        ex._learn_ticks = lambda *a: False
        ex._learn_moves = lambda *a: None
        ex.observe(gs, "NOT_FINISHED", 0, [1, 2])
        ks, ka, kr = ex.key(gs), ex.key(ga), ex.key(gr)
        up, down = (1, -1, -1), (2, -1, -1)
        nodes = {ks: my_agent.Node([]), ka: my_agent.Node([])}
        nodes[kr] = my_agent.Node([(0, up, None)])
        nodes[ks].note_outcome(down, ka)
        nodes[ks].note_outcome(up, ks)
        nodes[ka].note_outcome(down, kr)
        nodes[ka].note_outcome(down, ka)
        nodes[ka].note_outcome(up, ks)
        ex.nodes, ex.cur, ex.cur_grid, ex.start = nodes, ka, ga, ks
        ex.tier = ex.top_tier
        return ex, down, (ga, gr), (ka, kr)

    def test_a_walk_that_misses_its_earlier_outcome_counts_it_in_play(self):
        # Played through observe: the hidden door stays shut, so each walk
        # through it lands back on "a". Each landing is counted as a miss,
        # and after ALT_MISSES misses per hit the door is no longer planned.
        ex, down, (ga, gr), (ka, kr) = self._played_door()
        for misses in range(1, 3):
            self.assertEqual(ex.next_action(), down)
            self.assertEqual(ex.why, "walk through an earlier outcome")
            ex.observe(ga, "NOT_FINISHED", 0, [1, 2])
            self.assertEqual(ex.nodes[ka].alts[down][kr], [1, misses])
        ex.next_action()
        self.assertEqual(ex.why, "random: graph used up")

    def test_a_walk_that_reaches_its_earlier_outcome_counts_a_hit(self):
        # The door opens on the first walk: that is a hit and not a miss.
        # With two hits the door survives two misses, which one hit would
        # not allow, and is still planned through.
        ex, down, (ga, gr), (ka, kr) = self._played_door()
        self.assertEqual(ex.next_action(), down)
        ex.observe(gr, "NOT_FINISHED", 0, [1, 2])
        self.assertEqual(ex.nodes[ka].alts[down][kr], [2, 0])
        # The door shuts again: back on "a", down now leads to "a".
        ex.nodes[ka].note_outcome(down, ka)
        ex.cur, ex.cur_grid, ex.plan = ka, ga, []
        for misses in range(1, 3):
            self.assertEqual(ex.next_action(), down)
            self.assertEqual(ex.why, "walk through an earlier outcome")
            ex.observe(ga, "NOT_FINISHED", 0, [1, 2])
            self.assertEqual(ex.nodes[ka].alts[down][kr], [2, misses])
        ex.next_action()
        self.assertEqual(ex.why, "walk through an earlier outcome")

    def test_lattice_clicks_elsewhere_have_no_colour(self):
        # When the sweep starts, only the current state's grid is at hand:
        # its lattice clicks carry that grid's colours, every other state's
        # carry None and so can never be colour duds.
        ex = my_agent.Explorer()
        ex.nodes = {"s": my_agent.Node([]), "b": my_agent.Node([])}
        ex.cur, ex.start, ex.available = "s", "s", [6]
        ex.cur_grid = tuple(tuple([5] * 16) for _ in range(16))
        ex.tier = ex.top_tier
        ex.next_action()
        self.assertTrue(ex.sweeping)
        here = {c for _, _, c in ex.nodes["s"].untried}
        there = {c for _, _, c in ex.nodes["b"].untried}
        self.assertEqual(here, {5})
        self.assertEqual(there, {None})

    def test_an_excused_click_is_queued_again_with_its_colour(self):
        # A click on colour 7 dies at life 20 before any budget is known and
        # is blamed. A different action then dies at 20 too: the budget is
        # known, and the click goes back to untried with colour 7, both from
        # the list of unclear deaths and when it is excused at once.
        ex = my_agent.Explorer()
        node = my_agent.Node([])
        ex.nodes["s"] = node
        click, move = (6, 4, 4), (1, -1, -1)
        ex.life, ex.prev_tier, ex.prev_colour = 20, 2, 7
        ex._note_death("s", click)
        self.assertIsNone(ex.budget())
        ex.life, ex.prev_tier, ex.prev_colour = 20, 0, None
        ex._note_death("s", move)
        self.assertEqual(ex.budget(), 20)
        self.assertIn((2, click, 7), node.untried)
        other = my_agent.Node([])
        ex.nodes["t"] = other
        ex.life, ex.prev_tier, ex.prev_colour = 20, 2, 9
        ex._note_death("t", click)
        self.assertEqual(other.untried[0], (2, click, 9))

    def test_a_budget_needs_half_the_deaths_and_a_long_enough_life(self):
        a, b, c = (1, -1, -1), (2, -1, -1), (3, -1, -1)
        ex = my_agent.Explorer()
        # Two actions died at 20, but three deaths elsewhere outnumber them.
        ex.death_lives = {20: {("s", a), ("s", b)}, 12: {("s", c)},
                          13: {("t", a)}, 14: {("t", b)}}
        self.assertIsNone(ex.budget())
        ex.death_lives[20].add(("t", c))
        self.assertEqual(ex.budget(), 20)
        # Lives shorter than MIN_BUDGET are never a budget.
        self.assertEqual(my_agent.MIN_BUDGET, 10)
        ex.death_lives = {9: {("s", a), ("s", b)}}
        self.assertIsNone(ex.budget())
        ex.death_lives = {10: {("s", a), ("s", b)}}
        self.assertEqual(ex.budget(), 10)

    def test_a_used_up_graph_resets_when_only_the_start_reaches_a_door(self):
        # From "b" no walk reaches the earlier outcome, but the start does:
        # the agent resets rather than act at random.
        ex, down = self._hidden_door_graph()
        ex.nodes["b"] = my_agent.Node([])
        ex.cur = "b"
        self.assertEqual(ex.next_action()[0], 0)
        self.assertEqual(ex.why, "reset to reach untried work")

    def test_the_status_bar_is_masked_on_each_new_level(self):
        # The bar grows with the level; each level's first frame finds it.
        toy = Toy(bar=True, levels=3)
        ex = my_agent.Explorer()
        play(toy, ex, 6000)
        self.assertEqual(toy.done_levels, 3)
        # The winning frame opens level 3's mask, with the longest bar.
        self.assertEqual(ex.level, 3)
        self.assertEqual({c for r, c in ex.masked if r == 0},
                         set(range(2, 8 + 3 * 3)))

    def test_the_status_bar_is_masked_on_the_first_frame(self):
        # The game's very first frame is checked for status bars too, not
        # only the first frame of each later level.
        toy = Toy(bar=True)
        ex = my_agent.Explorer()
        ex.observe(toy.grid(), toy.state, toy.done_levels, toy.actions)
        self.assertEqual({c for r, c in ex.masked if r == 0}, set(range(2, 8)))

    def test_reset_and_undo_never_join_the_ordinary_actions(self):
        ex = my_agent.Explorer()
        acts = ex._actions_for(Toy().grid(), [0, 1, 2, 6, 7])
        ids = {a for _, (a, _, _), _ in acts}
        self.assertNotIn(0, ids)
        self.assertNotIn(7, ids)
        self.assertTrue({1, 2, 6} <= ids)

    def test_never_two_resets_in_a_row_so_levels_are_kept(self):
        # The engine restarts the whole game on a RESET straight after a
        # RESET. Here the only way into the lower half is a cell that kills
        # on every second entry, so once that move is avoided the start has
        # work it cannot reach: the agent must not reset again from there.
        walls = [(9, c) for c in range(24) if c != 8]
        traps = [(14, c) for c in range(3, 20, 4)] \
            + [(17, c) for c in range(1, 22, 5)]
        toy = Toy(flaky=[(9, 8)], walls=walls, traps=traps, goal=(21, 2),
                  levels=2, full_restart=True)
        log = play(toy, my_agent.Explorer(), 8000)
        acts = [a for _, (a, _, _) in log]
        self.assertFalse(any(a == b == 0 for a, b in zip(acts, acts[1:])))
        self.assertEqual(toy.full_restarts, 0)
        self.assertEqual(toy.state, "WIN")

    def test_an_action_that_never_does_anything_waits_till_last(self):
        # ACTION5 does nothing anywhere. Once it has failed in DUD_TRIES
        # states it is not tried in each new state any more.
        toy = Toy(actions=(1, 2, 3, 4, 5), walls=[(r, 11) for r in range(19)])
        log = play(toy, my_agent.Explorer(), 3000)
        self.assertEqual(toy.state, "WIN")
        fives = [1 for _, (a, _, _) in log if a == 5]
        self.assertLessEqual(len(fives), 2)
        self.assertEqual(my_agent.DUD_TRIES, 2)

    def test_a_colour_that_never_responds_makes_its_clicks_duds(self):
        # Six clicks on six different grey blocks changed nothing, so a click
        # on a seventh grey block waits with the duds. A click on a colour
        # that has not been tried does not.
        ex = my_agent.Explorer()
        g = [[0] * 24 for _ in range(24)]
        for i in range(7):
            for dr in (0, 1):
                for dc in (0, 1):
                    g[2 + 3 * i + dr][2 + dc] = 5
        g[20][20] = 12
        grid = tuple(tuple(r) for r in g)
        ex.observe(grid, "NOT_FINISHED", 0, [6])
        grey = [(6, 2, 2 + 3 * i) for i in range(7)]
        for act in grey[:5]:
            ex.prev = (ex.cur, act)
            ex.observe(grid, "NOT_FINISHED", 0, [6])
        self.assertFalse(ex.dud(grey[6], 5))
        ex.prev = (ex.cur, grey[5])
        ex.observe(grid, "NOT_FINISHED", 0, [6])
        self.assertTrue(ex.dud(grey[6], 5))
        self.assertFalse(ex.dud((6, 20, 20), 12))
        self.assertEqual(my_agent.COLOUR_DUD_TRIES, 6)

    def test_one_responding_click_keeps_a_colour_live(self):
        # Five grey clicks changed nothing and the sixth changed the frame:
        # grey has responded once, so its clicks are not duds, however many
        # silent ones follow.
        ex = my_agent.Explorer()

        def frame(lit):
            g = [[0] * 24 for _ in range(24)]
            for i in range(7):
                for dr in (0, 1):
                    for dc in (0, 1):
                        g[2 + 3 * i + dr][2 + dc] = 5
            g[20][20] = 12 if lit else 1
            return tuple(tuple(r) for r in g)

        grey = [(6, 2, 2 + 3 * i) for i in range(7)]
        ex.observe(frame(False), "NOT_FINISHED", 0, [6])
        for i, act in enumerate(grey[:6] + grey[:4]):
            ex.prev = (ex.cur, act)
            ex.observe(frame(i >= 5), "NOT_FINISHED", 0, [6])
        self.assertEqual(ex.colour_tries[5], 10)
        self.assertEqual(ex.colour_changes[5], 1)
        self.assertFalse(ex.dud(grey[6], 5))

    def test_a_colour_dud_reads_the_judged_states_own_grid(self):
        # The cell at (2, 2) is grey in one state and red in another. Grey
        # never responds, so the click there is a dud in the grey state and
        # not in the red one, whichever state offered it last.
        ex = my_agent.Explorer()

        def frame(colour):
            g = [[0] * 24 for _ in range(24)]
            for i in range(7):
                for dr in (0, 1):
                    for dc in (0, 1):
                        g[2 + 3 * i + dr][2 + dc] = 5
                        g[2 + 3 * i + dr][9 + dc] = 5
            for dr in (0, 1):
                for dc in (0, 1):
                    g[2 + dr][2 + dc] = colour
            return tuple(tuple(r) for r in g)

        grey, red = frame(5), frame(12)
        ex.observe(grey, "NOT_FINISHED", 0, [6])
        silent = [(6, 9, 2 + 3 * i) for i in range(6)]
        for act in silent:
            ex.prev = (ex.cur, act)
            ex.observe(grey, "NOT_FINISHED", 0, [6])
        ex.prev = (ex.cur, (6, 20, 20))  # a background click led to `red`
        ex.observe(red, "NOT_FINISHED", 0, [6])
        cell = (6, 2, 2)
        at_grey = ex.nodes[ex.key(grey)]
        at_red = ex.nodes[ex.key(red)]
        self.assertEqual([c for _, a, c in at_grey.untried if a == cell], [5])
        self.assertEqual([c for _, a, c in at_red.untried if a == cell], [12])
        self.assertNotIn(cell, [a for _, a, c in at_grey.untried
                                if not ex.dud(a, c)])
        self.assertIn(cell, [a for _, a, c in at_red.untried
                             if not ex.dud(a, c)])

    def test_clicks_sweep_the_board_when_no_object_helps(self):
        # Nothing on the board marks the winning cell, so object clicks are
        # used up quickly and the lattice sweep has to find it.
        toy = Toy(actions=(6,), secret=(10, 10))
        play(toy, my_agent.Explorer(), 100)
        self.assertEqual(toy.state, "WIN")

    def test_clicks_find_a_button_first(self):
        toy = Toy(actions=(6,), button=(4, 4))
        log = play(toy, my_agent.Explorer(), 50)
        self.assertEqual(toy.state, "WIN")
        self.assertEqual(len(log), 1)

    def test_the_player_and_its_steps_are_learned_from_what_moves(self):
        toy = Toy(goal=(20, 20))
        ex = my_agent.Explorer()
        play(toy, ex, 40)
        self.assertEqual(ex.mover(), {9})
        self.assertEqual(ex.step_of(1), (-1, 0))
        self.assertEqual(ex.step_of(2), (1, 0))
        self.assertEqual(ex.step_of(3), (0, -1))
        self.assertEqual(ex.step_of(4), (0, 1))

    def test_a_step_needs_a_majority_of_the_moves(self):
        # Once the player is known, action 1 moves it up twice, down twice
        # and right once: no displacement has a majority, so the action has
        # no learned step. Two more moves up make four in seven, a majority.
        ex = my_agent.Explorer()
        size, pos = 24, [12, 12]

        def frame():
            g = [[0] * size for _ in range(size)]
            g[pos[0]][pos[1]] = 9
            g[2][20] = 3
            return tuple(tuple(r) for r in g)

        def move(dr, dc):
            ex.prev = (ex.cur, (1, -1, -1))
            pos[0] += dr
            pos[1] += dc
            ex.observe(frame(), "NOT_FINISHED", 0, [1, 2])

        ex.observe(frame(), "NOT_FINISHED", 0, [1, 2])
        move(0, 1)  # the player is not known yet: no vote
        for d in ((-1, 0), (1, 0), (-1, 0), (1, 0), (0, 1)):
            move(*d)
        self.assertEqual(ex.mover(), {9})
        self.assertEqual(sum(ex.step_votes[1].values()), 5)
        self.assertIsNone(ex.step_of(1))
        move(-1, 0)
        move(-1, 0)
        self.assertEqual(ex.step_votes[1][(-1, 0)], 4)
        self.assertEqual(ex.step_of(1), (-1, 0))

    def test_a_win_on_a_smaller_frame_does_not_crash(self):
        # The frame shrinks within a level, and the level is won on the
        # small frame next to a goal guess that the level's first, larger
        # frame showed and the small frame cuts off. The guess still counts.
        ex = my_agent.Explorer()
        pos = [4, 10]

        def frame(size):
            g = [[0] * 24 for _ in range(24)]
            g[pos[0]][pos[1]] = 9
            g[4][17] = 3
            g[20][6] = 14
            return tuple(tuple(r[:size]) for r in g[:size])

        def step(size, level=0):
            ex.prev = (ex.cur, (4, -1, -1))
            pos[1] += 1
            ex.observe(frame(size), "NOT_FINISHED", level, [1, 2, 3, 4])

        ex.observe(frame(24), "NOT_FINISHED", 0, [1, 2, 3, 4])
        step(24)
        step(24)
        step(16)
        self.assertEqual(len(ex.cur_grid), 16)
        self.assertIn((4, 17), ex._guesses())
        step(24, level=1)
        self.assertEqual(ex.level, 1)
        self.assertEqual(ex.goal_colours(), {3})

    def test_exploration_heads_for_a_rare_object(self):
        # An open board with the one rare cell 22 moves away. Exploring
        # without a goal took 716 actions here; walking at it takes 22 and
        # a few more to learn what each action does.
        toy = Toy(size=32, start=(4, 4), goal=(26, 4))
        log = play(toy, my_agent.Explorer(), 2000)
        self.assertEqual(toy.state, "WIN")
        self.assertLessEqual(len(log), 40)

    def test_the_colour_reached_on_a_win_leads_the_next_level(self):
        # A decoy of another rare colour is nearer than the goal. Level 1
        # cannot know which matters; level 2 heads straight for the colour
        # the player reached when it won.
        toy = Toy(size=32, start=(16, 16), goal=(28, 16), decoys=[(10, 16)],
                  levels=2)
        ex = my_agent.Explorer()
        level2 = []
        for _ in range(4000):
            ex.observe(toy.grid(), toy.state, toy.done_levels, toy.actions)
            if toy.state == "WIN":
                break
            if toy.done_levels == 1:
                level2.append(toy.pos)
            toy.step(ex.next_action())
        self.assertEqual(toy.state, "WIN")
        self.assertEqual(ex.goal_colours(), {3})
        self.assertNotIn((10, 16), level2)
        self.assertLessEqual(len(level2), 12 + 4)

    def test_undo_steps_back_where_moves_cannot(self):
        # Only down and right: the way back from a dead end is undo.
        toy = Toy(actions=(2, 4), undo=True, goal=(10, 12))
        log = play(toy, my_agent.Explorer(), 3000)
        self.assertEqual(toy.state, "WIN")
        self.assertIn(7, {a for _, (a, _, _) in log})


@unittest.skipUnless(READY, "needs the 3.12 env and vendor/ (make setup)")
class HelpersTest(unittest.TestCase):
    def test_objects_split_by_colour_and_contact(self):
        g = ((1, 1, 0), (0, 0, 0), (2, 0, 1))
        objs = my_agent.objects(g)
        self.assertEqual(sorted((o.colour, len(o.cells)) for o in objs),
                         [(0, 5), (1, 1), (1, 2), (2, 1)])

    def test_status_bar_on_the_edge_is_masked(self):
        g = [[0] * 20 for _ in range(20)]
        for c in range(2, 18):
            g[19][c] = 4          # a long bar on the bottom edge
        g[10][10] = 9             # a player in the middle
        cells = my_agent.status_cells(tuple(tuple(r) for r in g))
        self.assertIn((19, 5), cells)
        self.assertNotIn((10, 10), cells)

    def test_click_targets_skip_background_and_rank_salient_first(self):
        g = [[0] * 20 for _ in range(20)]
        for r in range(5, 8):
            for c in range(5, 8):
                g[r][c] = 12      # a salient button
        for r in range(12, 15):
            for c in range(12, 15):
                g[r][c] = 1       # a dull block
        targets = my_agent.click_targets(tuple(tuple(r) for r in g), set())
        self.assertEqual(len(targets), 2)
        tier, (a, x, y), colour = targets[0]
        self.assertEqual((tier, a, x, y, colour), (0, 6, 6, 6, 12))


@unittest.skipUnless(READY, "needs the 3.12 env and vendor/ (make setup)")
class MyAgentTest(unittest.TestCase):
    def test_resets_first_then_plays_only_offered_actions(self):
        from arcengine import FrameData, GameAction, GameState
        agent = object.__new__(my_agent.MyAgent)
        agent.explorer = my_agent.Explorer()
        import time
        agent.started = time.time()
        first = FrameData(state=GameState.NOT_PLAYED)
        self.assertIs(agent.choose_action([], first), GameAction.RESET)
        grid = [[0] * 64 for _ in range(64)]
        grid[10][10] = 9
        playing = FrameData(state=GameState.NOT_FINISHED, frame=[grid],
                            available_actions=[GameAction.ACTION3,
                                               GameAction.ACTION6])
        for _ in range(10):
            act = agent.choose_action([], playing)
            self.assertIn(act, (GameAction.ACTION3, GameAction.ACTION6))
        self.assertTrue(agent.is_done([], FrameData(state=GameState.WIN)))
        self.assertFalse(agent.is_done([], playing))

    def test_stops_at_the_per_game_time_limit(self):
        from arcengine import FrameData, GameState
        import time
        agent = object.__new__(my_agent.MyAgent)
        agent.explorer = my_agent.Explorer()
        playing = FrameData(state=GameState.NOT_FINISHED)
        agent.started = time.time() - my_agent.MyAgent.MAX_SECONDS + 60
        self.assertFalse(agent.is_done([], playing))
        agent.started = time.time() - my_agent.MyAgent.MAX_SECONDS - 1
        self.assertTrue(agent.is_done([], playing))


class SourceTest(unittest.TestCase):
    def test_agent_is_offline(self):
        # RULES.md 1: no network or hosted-model client in the agent.
        with open(os.path.join(ROOT, "agent", "my_agent.py")) as f:
            src = f.read()
        for word in ("requests", "urllib", "http.client", "socket", "openai",
                     "anthropic"):
            self.assertIsNone(re.search(rf"\bimport {re.escape(word)}\b", src),
                              word)


if __name__ == "__main__":
    unittest.main()
