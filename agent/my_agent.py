"""The ARC-AGI-3 agent that gets submitted: a graph explorer.

`scripts/build_notebook.py` splices this one file into the Kaggle notebook, so
local play and the submission run the same code, and everything the agent
needs lives here:

    [edit agent/my_agent.py] -> [make play-local] -> [make submit]

Contract (enforced by the ARC-AGI-3-Agents framework):
  - Subclass `agents.agent.Agent`, and name the class `MyAgent`.
  - `is_done(frames, latest_frame) -> bool`.
  - `choose_action(frames, latest_frame) -> GameAction`.

The method (docs/baseline.md says where each idea came from):
  - Each frame becomes a state key: a hash of the grid with status bars and
    step counters masked out. A bar is found on a level's first frame by its
    shape at the screen edge, or later by changing at the edge step after step.
  - Per level, the agent keeps a graph of states and the actions between them.
    It diffs each step: an action that changes nothing is a self-loop, so it
    is tried once and never chosen again from that state.
  - The actions of a state are the simple actions the game offers and, when
    ACTION6 is offered, one click per same-colour object, in priority tiers:
    salient-coloured button-sized objects first, plain big areas last.
  - It takes an untried action of the current tier from the current state. If
    there is none, it walks the shortest known path to the nearest state that
    has one, using ACTION7 (undo) to step back when that is shorter. When the
    tier is used up everywhere it can reach, it opens the next tier.
  - An action that has led to different states from one state keeps every
    outcome. When everything else is used up, a walk may plan through an
    earlier outcome, before the agent falls back to random actions.
  - An action that ended the game (GAME_OVER) is avoided. After GAME_OVER, or
    when what it can reach is used up, it resets the level and keeps the graph.
    When lives end at the same length again and again, that length is a step
    budget, and running out of it is not blamed on the last action.
  - A new level starts a new graph. Simple actions that were on earlier
    winning paths go first.

Nothing here may name a public game (RULES.md 3), and nothing calls a network
or a model (RULES.md 1).
"""
from __future__ import annotations

import hashlib
import random
import time
from collections import Counter, deque
from typing import Any, Iterable, Optional

from arcengine import FrameData, GameAction, GameState

# The framework (MIT, ARC Prize) puts its `agents` package on sys.path both
# locally and on Kaggle.
from agents.agent import Agent

RESET, CLICK, UNDO = 0, 6, 7

# The state graph stops growing at this size, which bounds memory and time.
# A state costs about 7 KB (measured on a click game), so 55 games at this
# cap stay near 8 GB.
MAX_STATES = 20000
# At most this many click targets per state.
MAX_CLICKS = 64
# Status bars sit within this many cells of the screen edge.
EDGE = 3
# A static bar is at least this long against its width.
BAR_ASPECT = 5
# A row of status dots has at least this many same-looking objects.
DOT_TWINS = 3
# An edge band that changes on at least this share of steps, once there have
# been this many, holds a step counter and is masked whole, provided at least
# ONE_WAY_SHARE of its changes went one way: no cell turned from colour a to
# b while another turned from b to a. A counter tick only fills or empties
# cells; a player moving along the edge paints itself and the background in
# the same step.
TICK_SHARE = 0.4
ONE_WAY_SHARE = 0.9
TICK_MIN_STEPS = 16
# A game-over edge is avoided once it has ended the game this often, or at
# once if it never led anywhere else.
DEATHS_TO_AVOID = 2
# Many games end a life after a fixed number of actions, whatever the last
# one was. Once lives on a level have ended at the same length on
# BUDGET_DEATHS different actions, that length is the level's budget (a trap
# on a fixed route also kills at one length, but always on the same action),
# provided it is at least MIN_BUDGET and at least half the level's deaths
# came at it, and a death at or past it says nothing
# about the action that happened to be last: it is not held against it, and
# an untried action goes back to be tried again. The same action ending the
# game DEATHS_TO_AVOID times this way counts as a real death.
BUDGET_DEATHS = 2
MIN_BUDGET = 10
# An action that has led to different states from one state (a hidden
# variable decides) keeps every outcome: a walk may plan through an earlier
# outcome while walks expecting it have missed it at most ALT_MISSES times
# per time it happened.
ALT_MISSES = 1
# Click tiers. Simple actions are always tier 0.
SALIENT = range(6, 16)
BUTTON = range(2, 33)
LAST_TIER = 3
# An action (a simple action, or a click on the same cell) that has changed
# nothing in DUD_TRIES states of a level is a dud: it waits in DUD_TIER,
# after every other tier, in the states where it is still untried.
DUD_TRIES = 2
DUD_TIER = LAST_TIER + 1
# A colour that has changed nothing on any of COLOUR_DUD_TRIES clicks in a
# level makes every click on it a dud, wherever it is: in click games most
# colours are scenery, and scenery is drawn in few colours.
COLOUR_DUD_TRIES = 6
# When every tier is used up in a game that takes clicks, every state also
# gets a click on a lattice of cells SWEEP_STEP apart, background included,
# in SWEEP_TIER; a lattice click that is a dud waits in SWEEP_DUD_TIER.
SWEEP_STEP = 4
SWEEP_TIER = DUD_TIER + 1
SWEEP_DUD_TIER = SWEEP_TIER + 1
# Goal guessing. A colour whose cells all move together when a simple action
# changes the frame belongs to the player; a colour moved at least
# MOVER_SHARE as often as the most-moved one counts too. An action's step is
# the player's most common displacement under it, once seen STEP_VOTES times.
MOVER_SHARE = 0.5
STEP_VOTES = 2
# A colour with at most RARE_CELLS unmasked cells on a level's frame, that is
# neither the player nor the background, is a guess at the goal. When a level
# is won, the guessed colours within GOAL_REACH steps of the player are
# preferred on every later level.
RARE_CELLS = 64
GOAL_REACH = 2
# Untried work up to GOAL_SLACK hops farther than the nearest is weighed by
# its hops plus the player's distance, in steps, to the nearest guess after it.
GOAL_SLACK = 8
# The player's object is found by flood fill, up to this many cells.
MAX_PLAYER_CELLS = 400

Grid = tuple    # tuple of row tuples of ints
Cell = tuple    # (row, col)
Action = tuple  # (action_id, x, y); x = y = -1 for simple actions


def to_grid(frame: FrameData) -> Optional[Grid]:
    """The last grid of a frame (a step may return an animation), or None."""
    if not frame.frame:
        return None
    return tuple(tuple(int(v) for v in row) for row in frame.frame[-1])


def changed_cells(a: Grid, b: Grid) -> set:
    """The cells that differ between two grids of the same size."""
    out = set()
    for r, (ra, rb) in enumerate(zip(a, b)):
        if ra != rb:
            for c, (va, vb) in enumerate(zip(ra, rb)):
                if va != vb:
                    out.add((r, c))
    return out


def blobs(cells: Iterable[Cell]) -> list:
    """Group cells into 4-connected blobs."""
    todo = set(cells)
    out = []
    while todo:
        seed = todo.pop()
        blob, queue = [seed], deque([seed])
        while queue:
            r, c = queue.popleft()
            for n in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if n in todo:
                    todo.remove(n)
                    blob.append(n)
                    queue.append(n)
        out.append(blob)
    return out


class Obj:
    """A 4-connected same-colour region of a grid."""

    __slots__ = ("colour", "cells", "top", "left", "bottom", "right")

    def __init__(self, colour: int, cells: list) -> None:
        self.colour = colour
        self.cells = cells
        rows = [p[0] for p in cells]
        cols = [p[1] for p in cells]
        self.top, self.bottom = min(rows), max(rows)
        self.left, self.right = min(cols), max(cols)

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    def at_edge(self, h: int, w: int) -> bool:
        """Whether the whole object lies within EDGE cells of one screen edge."""
        return (self.bottom < EDGE or self.top >= h - EDGE
                or self.right < EDGE or self.left >= w - EDGE)


def objects(grid: Grid) -> list:
    """Every same-colour region of a grid."""
    h = len(grid)
    w = len(grid[0]) if h else 0
    seen = [[False] * w for _ in range(h)]
    out = []
    for r in range(h):
        row = grid[r]
        for c in range(w):
            if seen[r][c]:
                continue
            colour = row[c]
            seen[r][c] = True
            cells, queue = [], deque([(r, c)])
            while queue:
                y, x = queue.popleft()
                cells.append((y, x))
                for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= ny < h and 0 <= nx < w and not seen[ny][nx] \
                            and grid[ny][nx] == colour:
                        seen[ny][nx] = True
                        queue.append((ny, nx))
            out.append(Obj(colour, cells))
    return out


def _centre(cells: list) -> tuple:
    return (sum(p[0] for p in cells) / len(cells),
            sum(p[1] for p in cells) / len(cells))


def background(objs: list) -> Optional[Obj]:
    return max(objs, key=lambda o: len(o.cells)) if objs else None


def status_cells(grid: Grid) -> set:
    """Cells that look like a status bar or a row of status dots.

    An object counts if it lies against one screen edge and either is long
    and thin along it, or has DOT_TWINS others of the same colour and size
    against the edge too.
    """
    h = len(grid)
    w = len(grid[0]) if h else 0
    objs = objects(grid)
    bg = background(objs)
    edge = [o for o in objs if o is not bg and o.at_edge(h, w)]
    looks = Counter((o.colour, len(o.cells)) for o in edge)
    out = set()
    for o in edge:
        long_side = max(o.width, o.height)
        short_side = min(o.width, o.height)
        if long_side >= BAR_ASPECT * short_side \
                or looks[(o.colour, len(o.cells))] > DOT_TWINS:
            out.update(o.cells)
    return out


def click_tier(o: Obj) -> int:
    """0: salient and button-sized. 1: button-sized. 2: salient. 3: the rest."""
    sized = o.width in BUTTON and o.height in BUTTON
    salient = o.colour in SALIENT
    if sized and salient:
        return 0
    if sized:
        return 1
    if salient:
        return 2
    return LAST_TIER


def click_targets(grid: Grid, masked: set) -> list:
    """(tier, action, colour) entries: one ACTION6 click per object worth
    clicking, with the colour it lands on.

    The background and masked status cells are skipped. Within a tier, compact
    objects (that fill their bounding box) go first, then small ones. The click
    lands on the object's cell nearest its centre.
    """
    objs = objects(grid)
    bg = background(objs)
    ranked = []
    for o in objs:
        if o is bg:
            continue
        free = [p for p in o.cells if p not in masked]
        if not free:
            continue
        cy = sum(p[0] for p in free) / len(free)
        cx = sum(p[1] for p in free) / len(free)
        r, c = min(free, key=lambda p: ((p[0] - cy) ** 2 + (p[1] - cx) ** 2, p))
        fill = len(o.cells) / (o.width * o.height)
        ranked.append(((click_tier(o), -fill, len(o.cells), r, c),
                       (CLICK, c, r), o.colour))
    ranked.sort()
    return [(key[0], a, colour) for key, a, colour in ranked[:MAX_CLICKS]]


class Node:
    """One state in a level graph."""

    __slots__ = ("untried", "edges", "deaths", "alts")

    def __init__(self, untried: list) -> None:
        # [(tier, action, colour)], best first. `colour` is the colour a
        # click lands on in this state's grid, None when not known.
        self.untried = untried
        self.edges: dict = {}          # action -> next state key, the latest
        self.deaths: Counter = Counter()  # action -> times it ended the game
        # action -> {state key: [times it led there, times a walk expected
        # it and got something else]}, only for actions seen to lead to more
        # than one state (a hidden variable decides).
        self.alts: dict = {}

    def note_outcome(self, act: Action, k: str) -> None:
        """Record that `act` led to `k`, keeping earlier outcomes."""
        old = self.edges.get(act)
        if old is not None and old != k and act not in self.alts:
            self.alts[act] = {old: [1, 0]}
        if act in self.alts:
            self.alts[act].setdefault(k, [0, 0])[0] += 1
        self.edges[act] = k

    def outcomes(self, act: Action) -> list:
        """The states `act` may lead to: the latest, and every earlier one
        that walks have not missed more often than they reached it."""
        latest = self.edges[act]
        alts = self.alts.get(act)
        if not alts:
            return [latest]
        return [latest] + [k for k, (hit, miss) in alts.items()
                           if k != latest and miss <= ALT_MISSES * hit]

    def avoid(self, act: Action) -> bool:
        d = self.deaths[act]
        return d >= DEATHS_TO_AVOID or (d > 0 and act not in self.edges)

    def best_untried(self, tier: int, dud=None) -> Optional[int]:
        """Index of the first untried action at or below `tier`, or None.

        `dud(action, colour)` says the action waits in a dud tier whatever
        its tier.
        """
        for i, (t, a, colour) in enumerate(self.untried):
            if dud is not None and dud(a, colour):
                t = SWEEP_DUD_TIER if t >= SWEEP_TIER else DUD_TIER
            if t <= tier:
                return i
        return None


class Explorer:
    """The game-independent explorer: grids in, actions out.

    `observe` is told what each step produced and `next_action` says what to
    do next. It knows nothing of the framework, so toy games can test it.
    """

    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)
        self.win_counts: Counter = Counter()  # simple action id -> wins
        self.level = -1
        self.cur: Optional[str] = None
        self.cur_grid: Optional[Grid] = None
        self.prev: Optional[tuple] = None
        self.available: list = []
        self.why = ""                         # why the last action was chosen
        self.rebuilds = 0                     # graphs dropped for a new mask
        self.moves: Counter = Counter()       # colour -> times it moved
        self.step_votes: dict = {}            # action id -> Counter of steps
        self.goal_votes: Counter = Counter()  # colour -> wins it was near
        self.mover_size = 0                   # cells in the player's object
        self.life = 0                         # actions since a reset or a win
        self.prev_tier = 0                    # tier of the last action tried
        self.prev_colour = None               # the colour it clicked on
        self._new_level(0, None)

    # -- state keys -------------------------------------------------------

    def key(self, grid: Grid) -> str:
        h = hashlib.blake2b(digest_size=16)
        m = self.masked
        for r, row in enumerate(grid):
            if r in self.masked_rows:
                row = tuple(16 if (r, c) in m else v for c, v in enumerate(row))
            h.update(bytes(row))
        return h.hexdigest()

    def _mask(self, cells: Iterable[Cell]) -> None:
        self.masked.update(cells)
        self.masked_rows = {r for r, _ in self.masked}

    def _learn_ticks(self, before: Grid, after: Grid) -> bool:
        """Mask an edge band that changes on almost every step.

        A step counter ticks whatever the action; a player only touches the
        edge now and then. True if the mask grew.
        """
        h, w = len(after), len(after[0])
        turns: dict = {}  # side -> {(colour before, colour after)}
        for r, c in changed_cells(before, after):
            pair = (before[r][c], after[r][c])
            if r < EDGE:
                turns.setdefault("top", set()).add(pair)
            if r >= h - EDGE:
                turns.setdefault("bottom", set()).add(pair)
            if c < EDGE:
                turns.setdefault("left", set()).add(pair)
            if c >= w - EDGE:
                turns.setdefault("right", set()).add(pair)
        self.steps_seen += 1
        self.side_hits.update(turns.keys())
        for side, pairs in turns.items():
            if not any((b, a) in pairs for a, b in pairs):
                self.side_one_way[side] += 1
        if self.steps_seen < TICK_MIN_STEPS:
            return False
        new = set()
        for side, hits in self.side_hits.items():
            if side in self.ticking or hits < TICK_SHARE * self.steps_seen \
                    or self.side_one_way[side] < ONE_WAY_SHARE * hits:
                continue
            self.ticking.add(side)
            new.update(self._band(side, h, w))
        self._mask(new)
        return bool(new)

    @staticmethod
    def _band(side: str, h: int, w: int) -> list:
        """The cells of one edge band, EDGE cells deep."""
        rows = {"top": range(EDGE), "bottom": range(h - EDGE, h)}.get(
            side, range(h))
        cols = {"left": range(EDGE), "right": range(w - EDGE, w)}.get(
            side, range(w))
        return [(r, c) for r in rows for c in cols]

    # -- the player and the goal ------------------------------------------

    def mover(self) -> set:
        """The colours of the player: those that move under simple actions."""
        if not self.moves:
            return set()
        top = self.moves.most_common(1)[0][1]
        if top < STEP_VOTES:
            return set()
        return {c for c, n in self.moves.items() if n >= MOVER_SHARE * top}

    def step_of(self, act_id: int) -> Optional[tuple]:
        """The player's usual (row, col) displacement under `act_id`."""
        votes = self.step_votes.get(act_id)
        if not votes:
            return None
        d, n = votes.most_common(1)[0]
        if n < STEP_VOTES or 2 * n < sum(votes.values()):
            return None
        return d

    def goal_colours(self) -> set:
        """The colours the player was near when it won, most often."""
        if not self.goal_votes:
            return set()
        top = self.goal_votes.most_common(1)[0][1]
        return {c for c, n in self.goal_votes.items() if 2 * n >= top}

    def _step_len(self) -> float:
        steps = [d for d in map(self.step_of, list(self.step_votes)) if d]
        if not steps:
            return 1.0
        return max(1.0, sum(abs(r) + abs(c) for r, c in steps) / len(steps))

    def _learn_moves(self, before: Grid, after: Grid, act_id: int,
                     pk: str, k: str) -> None:
        """Note which colours moved, the player's step, and where it is.

        A colour moved when as many of its cells vanished as appeared, and
        its object kept its size but not its centre. The background is never
        the player, though it seems to move the other way.
        """
        gone: dict = {}
        came: dict = {}
        for r, c in changed_cells(before, after):
            if (r, c) in self.masked:
                continue
            gone.setdefault(before[r][c], []).append((r, c))
            came.setdefault(after[r][c], []).append((r, c))
        moved = {}
        for colour, old in gone.items():
            new = came.get(colour)
            if colour == self._bg() or not new or len(new) != len(old) \
                    or len(old) > MAX_PLAYER_CELLS:
                continue
            was, now = self._fill(before, old[0]), self._fill(after, new[0])
            if len(was) != len(now):
                continue
            pw, pn = _centre(was), _centre(now)
            d = (round(pn[0] - pw[0]), round(pn[1] - pw[1]))
            if d != (0, 0):
                moved[colour] = (d, pn, len(now))
        self.moves.update(moved.keys())
        player = self.mover() & moved.keys()
        if player:
            colour = max(player, key=lambda c: (self.moves[c], c))
            d, p, size = moved[colour]
            self.step_votes.setdefault(act_id, Counter())[d] += 1
            self.mover_size = size
            self.pos[k] = p
        elif self.pos.get(k) is None and self.pos.get(pk) is not None:
            self.pos[k] = self.pos[pk]

    def _bg(self) -> Optional[int]:
        """This level's background colour: its most common one."""
        if self._bg_colour is None and self.level_grid is not None:
            self._bg_colour = Counter(
                v for row in self.level_grid for v in row).most_common(1)[0][0]
        return self._bg_colour

    def _locate(self, grid: Grid) -> Optional[tuple]:
        """The player's centre in `grid`, when exactly one object fits."""
        mover = self.mover()
        if not mover or not self.mover_size:
            return None
        found = [o for o in objects(grid) if o.colour in mover
                 and len(o.cells) == self.mover_size]
        return _centre(found[0].cells) if len(found) == 1 else None

    @staticmethod
    def _fill(grid: Grid, seed: Cell) -> list:
        """The same-colour cells 4-connected to `seed`, up to a cap."""
        h, w = len(grid), len(grid[0])
        colour = grid[seed[0]][seed[1]]
        seen, queue = {seed}, deque([seed])
        while queue and len(seen) < MAX_PLAYER_CELLS:
            r, c = queue.popleft()
            for n in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if n not in seen and 0 <= n[0] < h and 0 <= n[1] < w \
                        and grid[n[0]][n[1]] == colour:
                    seen.add(n)
                    queue.append(n)
        return list(seen)

    def _guesses(self) -> list:
        """The cells of this level's goal guesses (rare colours)."""
        mover = frozenset(self.mover())
        if self._guessed is not None and self._guessed[0] == mover:
            return self._guessed[1]
        grid = self.level_grid
        cells: dict = {}
        if grid is not None and mover:
            for r, row in enumerate(grid):
                for c, v in enumerate(row):
                    if (r, c) not in self.masked:
                        cells.setdefault(v, []).append((r, c))
        out = []
        if cells:
            rare = {v for v, ps in cells.items() if len(ps) <= RARE_CELLS
                    and v != self._bg() and v not in mover}
            use = (self.goal_colours() & rare) or rare
            out = [p for v in sorted(use) for p in cells[v]]
        self._guessed = (mover, out)
        self.gdist = {}
        return out

    def _distance(self, p: Optional[tuple]) -> Optional[float]:
        """Steps from a player position to the nearest goal guess."""
        guesses = self._guesses()
        if p is None or not guesses:
            return None
        return min(abs(p[0] - r) + abs(p[1] - c)
                   for r, c in guesses) / self._step_len()

    def _state_distance(self, k: str) -> Optional[float]:
        if k not in self.gdist:
            d = self._distance(self.pos.get(k))
            if d is None:
                return None
            self.gdist[k] = d
        return self.gdist[k]

    def _action_distance(self, k: str, act: Action) -> Optional[float]:
        """Steps to the nearest guess after `act` from state `k`, as far as
        the learned steps can tell."""
        d = self.step_of(act[0]) if act[0] not in (CLICK, UNDO) else None
        p = self.pos.get(k)
        if d is not None and p is not None:
            return self._distance((p[0] + d[0], p[1] + d[1]))
        return self._state_distance(k)

    def _note_win(self) -> None:
        """Vote for the guessed colours near the player as it won."""
        if self.prev is None or self.cur_grid is None:
            return
        pk, act = self.prev
        p = self.pos.get(pk)
        if p is None or not self._guesses():
            return
        d = self.step_of(act[0]) if act[0] not in (CLICK, UNDO) else None
        spots = [p] + ([(p[0] + d[0], p[1] + d[1])] if d else [])
        reach = GOAL_REACH * self._step_len() + 1
        # The guesses come from the level's first frame. If the frame has
        # changed size since, a guess off the current frame keeps its colour
        # from that first frame.
        grid, first = self.cur_grid, self.level_grid
        near = {grid[r][c] if r < len(grid) and c < len(grid[r])
                else first[r][c]
                for r, c in self._guesses()
                if any(abs(r - q[0]) <= reach and abs(c - q[1]) <= reach
                       for q in spots)}
        self.goal_votes.update(near)

    def _pick(self, k: str, node: Node) -> Optional[int]:
        """Index of the untried action to take next in state `k`, or None.

        The lowest open tier comes first. Within it, once a goal guess and
        the player are known, the action that the learned steps say ends
        nearest a guess goes first.
        """
        if self.pos.get(k) is None or not self._guesses():
            return node.best_untried(self.tier, self.dud)
        best, best_key = None, None
        for i, (t, a, colour) in enumerate(node.untried):
            if self.dud(a, colour):
                t = SWEEP_DUD_TIER if t >= SWEEP_TIER else DUD_TIER
            if t > self.tier:
                continue
            d = self._action_distance(k, a)
            key = (t, d if d is not None else float("inf"), i)
            if best_key is None or key < best_key:
                best, best_key = i, key
        return best

    # -- the graph --------------------------------------------------------

    def _new_level(self, level: int, grid: Optional[Grid]) -> None:
        self.level = level
        self.masked: set = set()
        self.masked_rows: set = set()
        self.level_grid: Optional[Grid] = grid
        self._guessed: Optional[tuple] = None  # (mover, guesses) cache
        self._bg_colour: Optional[int] = None
        self.steps_seen = 0
        self.side_hits: Counter = Counter()
        self.side_one_way: Counter = Counter()  # changes that went one way
        # Each level finds its own step counter. Carrying the last level's
        # mask over cost more actions than it saved (docs/iterate.md).
        self.ticking: set = set()
        self.life = 0
        self.death_lives: dict = {}  # life length -> {(state, action)} died
        self.unclear: list = []   # [(state, action, tier, colour, life)]
        self.budget_deaths: Counter = Counter()  # (state, action) -> deaths
        if grid is not None:
            self._mask(status_cells(grid))
        self._new_graph()

    def _new_graph(self) -> None:
        self.nodes: dict = {}
        self.tier = 0
        self.start: Optional[str] = None   # state right after the last reset
        self.history: list = []            # states an undo steps back to
        self.plan: list = []               # [(action, expected state)]
        self.prev = None
        self.after_reset = True
        self.forgiven = False              # deaths cleared since the last try
        self.sweeping = False              # lattice clicks added
        self.top_tier = DUD_TIER           # the last tier to open
        self.tries: Counter = Counter()    # action -> times tried, this level
        self.changes: Counter = Counter()  # action -> times it changed state
        self.colour_tries: Counter = Counter()    # colour -> clicks on it
        self.colour_changes: Counter = Counter()  # colour -> clicks that did
        self.pos: dict = {}                # state key -> player (row, col)
        self.gdist: dict = {}              # state key -> steps to a guess

    def dud(self, act: Action, colour: Optional[int] = None) -> bool:
        """Whether `act` has changed nothing every time, DUD_TRIES times, or
        is a click on a colour that has changed nothing every time,
        COLOUR_DUD_TRIES times. `colour` is what the click lands on in the
        grid of the state being judged; the same cell may hold another
        colour in another state."""
        if self.tries[act] >= DUD_TRIES and not self.changes[act]:
            return True
        if act[0] != CLICK or colour is None:
            return False
        return self.colour_tries[colour] >= COLOUR_DUD_TRIES \
            and not self.colour_changes[colour]

    def _actions_for(self, grid: Grid, available: list) -> list:
        simple = [a for a in available if a not in (RESET, CLICK, UNDO)]
        simple.sort(key=lambda a: (-self.win_counts[a], a))
        acts = [(0, (a, -1, -1), None) for a in simple]
        if CLICK in available:
            acts += click_targets(grid, self.masked)
            acts.sort(key=lambda ta: ta[0])  # stable: simple first in tier 0
            if self.sweeping:
                acts += self._lattice(grid)
        return acts

    def _lattice(self, grid: Grid, colours: bool = True) -> list:
        """Lattice clicks for the sweep tier, skipping masked cells, with the
        colour each lands on in `grid`, or None if not `colours`."""
        h = len(grid)
        w = len(grid[0]) if h else 0
        half = SWEEP_STEP // 2
        return [(SWEEP_TIER, (CLICK, c, r), grid[r][c] if colours else None)
                for r in range(half, h, SWEEP_STEP)
                for c in range(half, w, SWEEP_STEP)
                if (r, c) not in self.masked]

    def _node(self, k: str, grid: Grid, available: list) -> Node:
        node = self.nodes.get(k)
        if node is None:
            node = Node(self._actions_for(grid, available)
                        if len(self.nodes) < MAX_STATES else [])
            self.nodes[k] = node
        return node

    def observe(self, grid: Grid, state: str, level: int,
                available: list) -> None:
        """Record what the last action produced.

        `state` is the GameState name and `level` is levels_completed.
        """
        self.available = list(available)
        if self.level_grid is None:
            # The game's first frame: look for status bars as each new
            # level's first frame does.
            self.level_grid = grid
            self._mask(status_cells(grid))
        if level != self.level:
            self._note_win()
            for a, _, _ in self._winning_path():
                if a not in (CLICK, UNDO):
                    self.win_counts[a] += 1
            self._new_level(level, grid)
            self.cur_grid = None
        if self.cur_grid is not None and self.prev is not None \
                and self._learn_ticks(self.cur_grid, grid):
            # The keys changed meaning: what the graph knows is stale.
            self.rebuilds += 1
            self._new_graph()
        k = self.key(grid)
        self._node(k, grid, available)
        if self.prev is not None:
            pk, act = self.prev
            pnode = self.nodes.get(pk)
            if act[0] != UNDO:
                self.tries[act] += 1
                changed = state == "GAME_OVER" or k != pk
                if changed:
                    self.changes[act] += 1
                g = self.cur_grid
                if act[0] == CLICK and g is not None                         and 0 <= act[2] < len(g) and 0 <= act[1] < len(g[0]):
                    c = g[act[2]][act[1]]
                    self.colour_tries[c] += 1
                    self.colour_changes[c] += changed
            if self.plan and self.plan[0][0] == act and self.plan[0][1] != k \
                    and pnode is not None and act in pnode.alts:
                got = pnode.alts[act].get(self.plan[0][1])
                if got is not None:
                    got[1] += 1
            if state == "GAME_OVER":
                self._note_death(pk, act)
            elif act[0] == UNDO:
                if self.history:
                    self.history.pop()
            else:
                if pnode is not None:
                    pnode.note_outcome(act, k)
                if k != pk:
                    self.history.append(pk)
                    if act[0] != CLICK and self.cur_grid is not None:
                        self._learn_moves(self.cur_grid, grid, act[0], pk, k)
        if self.after_reset:
            self.start, self.history, self.after_reset = k, [], False
        if k not in self.pos and state != "GAME_OVER" and self.mover():
            self.pos[k] = self._locate(grid)
        if self.plan:
            if state == "GAME_OVER" or self.plan[0][1] != k:
                self.plan = []
            else:
                self.plan.pop(0)
        if state == "GAME_OVER":
            self.cur, self.cur_grid = None, None
        else:
            self.cur, self.cur_grid = k, grid

    def budget(self) -> Optional[int]:
        """This level's step budget: a life length of at least MIN_BUDGET
        at which BUDGET_DEATHS different actions, and at least half of the
        level's deaths, have ended the game. None if there is none."""
        total = sum(map(len, self.death_lives.values()))
        lives = [n for n, died in self.death_lives.items()
                 if len(died) >= BUDGET_DEATHS and n >= MIN_BUDGET
                 and 2 * len(died) >= total]
        return min(lives) if lives else None

    def _note_death(self, pk: str, act: Action) -> None:
        """Hold a GAME_OVER against the action that led to it, unless the
        life simply ran out of budget."""
        known = self.budget()
        self.death_lives.setdefault(self.life, set()).add((pk, act))
        if known is None:
            self.unclear.append((pk, act, self.prev_tier, self.prev_colour,
                                 self.life))
        budget = self.budget()
        if budget is None:
            self._blame(pk, act)
            return
        if known is None:
            # The budget is new: deaths at or past it were blamed wrongly.
            for k, a, t, colour, life in self.unclear[:-1]:
                if life >= budget:
                    self._excuse(k, a, t, colour)
        if self.life >= budget:
            self._excuse(pk, act, self.prev_tier, self.prev_colour,
                         fresh=True)
        else:
            self._blame(pk, act)

    def _blame(self, k: str, act: Action) -> None:
        node = self.nodes.get(k)
        if node is not None:
            node.deaths[act] += 1

    def _excuse(self, k: str, act: Action, tier: int,
                colour: Optional[int] = None, fresh: bool = False) -> None:
        """Take back a death that came from the budget. A known move is
        never blamed. An untried action ending the game DEATHS_TO_AVOID
        times this way still counts as a death: it may be a trap."""
        node = self.nodes.get(k)
        if node is None:
            return
        if not fresh and node.deaths[act] > 0:
            node.deaths[act] -= 1
        if act in node.edges:
            return
        self.budget_deaths[(k, act)] += 1
        if self.budget_deaths[(k, act)] >= DEATHS_TO_AVOID:
            node.deaths[act] = max(node.deaths[act], DEATHS_TO_AVOID)
            return
        if all(a != act for _, a, _ in node.untried):
            node.untried.insert(0, (tier, act, colour))

    def _winning_path(self) -> list:
        """The shortest known path from the level start to the winning step."""
        if self.prev is None or self.start is None:
            return []
        last_key, last_act = self.prev
        parent = {self.start: None}
        queue = deque([self.start])
        while queue:
            k = queue.popleft()
            if k == last_key:
                route = [last_act]
                while parent[k] is not None:
                    k, a = parent[k]
                    route.append(a)
                return route[::-1]
            for a, nk in self.nodes[k].edges.items():
                if nk not in parent and nk in self.nodes:
                    parent[nk] = (k, a)
                    queue.append(nk)
        return [last_act]

    def next_action(self) -> Action:
        """The next action to take: RESET when there is no current state."""
        if self.cur is None:
            self.why = "reset after game over"
            return self._reset()
        node = self.nodes[self.cur]
        if self.plan:
            act = self.plan[0][0]
            self.why = "walk to untried work"
        else:
            i = self._pick(self.cur, node)
            if i is not None:
                self.prev_tier, act, self.prev_colour = node.untried.pop(i)
                self.why = "try"
                self.forgiven = False
            else:
                act = self._head_for_frontier()
                if act is None:
                    self.why = "reset to reach untried work"
                    return self._reset()
        self.prev = (self.cur, act)
        self.life += 1
        return act

    def _reset(self) -> Action:
        self.life = 0
        self.prev, self.plan, self.history = None, [], []
        self.after_reset = True
        self.cur, self.cur_grid = None, None
        return (RESET, -1, -1)

    def _head_for_frontier(self) -> Optional[Action]:
        """Plan a route to untried work and return its first step.

        None means: reset the level, because untried work exists that the
        start state can reach and the current state cannot. When the graph is used up, a random action
        keeps the agent moving rather than resetting in a loop.
        """
        while True:
            route = self._route(self.tier)
            if route:
                self.plan = route
                self.why = "walk to untried work"
                return route[0][0]
            if self.cur != self.start and self.start in self.nodes \
                    and self._route(self.tier, self.start):
                return None
            if self.tier < self.top_tier:
                self.tier += 1
                node = self.nodes[self.cur]
                i = self._pick(self.cur, node)
                if i is not None:
                    self.why = "try"
                    self.prev_tier, act, self.prev_colour = \
                        node.untried.pop(i)
                    return act
                continue
            if not self.forgiven and any(n.deaths for n in self.nodes.values()):
                # A move may have ended the game only because a hidden clock
                # ran out. With nothing else left, plan through it again.
                for n in self.nodes.values():
                    n.deaths.clear()
                self.forgiven = True
                continue
            if CLICK in self.available and not self.sweeping \
                    and self.cur_grid is not None:
                # Click where no object suggested it: on a lattice, in every
                # state already known and every state found from now on.
                # Only the current state's grid is at hand, so elsewhere a
                # lattice click's colour is unknown and never a colour dud.
                self.sweeping, self.top_tier = True, SWEEP_DUD_TIER
                lattice = self._lattice(self.cur_grid, colours=False)
                for k, n in self.nodes.items():
                    n.untried.extend(self._lattice(self.cur_grid)
                                     if k == self.cur else lattice)
                continue
            # Untried work may sit where an action led once and leads no
            # more: plan through every outcome actions have had.
            route = self._route(self.tier, alts=True)
            if route:
                self.plan = route
                self.why = "walk through an earlier outcome"
                return route[0][0]
            if self.cur != self.start and self.start in self.nodes \
                    and self._route(self.tier, self.start, alts=True):
                return None
            self.why = "random: graph used up"
            simple = [a for a in self.available if a not in (RESET, CLICK, UNDO)]
            if simple:
                return (self.rng.choice(simple), -1, -1)
            if CLICK in self.available:
                return (CLICK, self.rng.randrange(64), self.rng.randrange(64))
            return None

    def _route(self, tier: int, start: Optional[str] = None,
               alts: bool = False) -> list:
        """Shortest known path to a state with untried work at `tier`.

        Edges are the recorded transitions minus the ones to avoid; with
        `alts`, every outcome an action has had, not just its latest. From the
        current state, k undos lead back k states along the history. From
        any other `start` (the state a reset would lead to) undo is no use.
        """
        can_undo = UNDO in self.available and start in (None, self.cur)
        start = self.cur if start is None else start
        parent = {start: (None, None)}
        undo_depth = {start: 0}
        depth = {start: 0}
        # With a goal guess, look GOAL_SLACK steps past the nearest untried
        # work for work that ends nearer the guess.
        aim = tier == self.tier and bool(self._guesses())
        best, best_score, limit = None, None, None
        queue = deque([start])
        while queue:
            k = queue.popleft()
            if limit is not None and depth[k] > limit:
                break
            node = self.nodes[k]
            if k != start and node.best_untried(tier, self.dud) is not None:
                if not aim:
                    best = k
                    break
                i = self._pick(k, node)
                d = self._action_distance(k, node.untried[i][1]) \
                    if i is not None else None
                score = depth[k] + (d if d is not None else GOAL_SLACK)
                if best_score is None or score < best_score:
                    best, best_score = k, score
                if limit is None:
                    limit = depth[k] + GOAL_SLACK
            steps = [(a, nk) for a in node.edges if not node.avoid(a)
                     for nk in (node.outcomes(a) if alts else (node.edges[a],))
                     if nk != k]
            d = undo_depth.get(k)
            if can_undo and d is not None and d < len(self.history):
                steps.append(((UNDO, -1, -1), self.history[-1 - d]))
            for a, nk in steps:
                if nk not in parent and nk in self.nodes:
                    parent[nk] = (k, a)
                    if a[0] == UNDO:
                        undo_depth[nk] = d + 1
                    depth[nk] = depth[k] + 1
                    queue.append(nk)
        route = []
        k = best
        while k is not None and parent[k][0] is not None:
            pk, a = parent[k]
            route.append((a, k))
            k = pk
        return route[::-1]


class MyAgent(Agent):
    """Explores each level as a graph of frame states. No per-game logic."""

    # Upper bound on actions per game. Actions on a level never cleared cost
    # nothing, so the cap is set by memory and time, not by the score.
    MAX_ACTIONS = 100000
    # Wall-clock cap per game. Kaggle allows 9 h and plays every game at once
    # in its own thread (docs/submission.md), so each game may run for most
    # of the 9 h; 75% leaves room for setup and scoring.
    MAX_SECONDS = 0.75 * 9 * 3600
    # Frames the framework keeps for us. It appends every frame forever, and
    # 55 games of 100,000 frames would not fit in memory.
    KEEP_FRAMES = 4

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.explorer = Explorer(seed=0)
        self.started = time.time()

    def append_frame(self, frame: FrameData) -> None:
        super().append_frame(frame)
        if len(self.frames) > 2 * self.KEEP_FRAMES:
            del self.frames[:-self.KEEP_FRAMES]

    def is_done(self, frames: list[FrameData], latest_frame: FrameData) -> bool:
        if latest_frame.state is GameState.WIN:
            return True
        return time.time() - self.started > self.MAX_SECONDS

    def choose_action(
        self, frames: list[FrameData], latest_frame: FrameData
    ) -> GameAction:
        grid = to_grid(latest_frame)
        if latest_frame.state is GameState.NOT_PLAYED or grid is None:
            return GameAction.RESET
        ex = self.explorer
        available = [int(getattr(a, "value", a))
                     for a in latest_frame.available_actions or []]
        ex.observe(grid, latest_frame.state.name,
                   latest_frame.levels_completed, available)
        act_id, x, y = ex.next_action()
        action = GameAction.from_id(act_id)
        if act_id == CLICK:
            action.set_data({"x": x, "y": y})
            action.reasoning = {"why": "explore", "x": x, "y": y}
        else:
            action.reasoning = {"why": "explore", "states": len(ex.nodes)}
        return action
