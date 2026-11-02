# The playbook: one page at a time, chosen by the harness (arc-agi-3 big-model-distill). MIT-0.
#
# Our own cell. Krishan, 2026-10-31: do not dump every lesson into one long
# system prompt for a weaker model; give it an organised playbook, the way a
# surgeon trains an intern, and let it look at the right page at the right
# moment. docs/big-model-distill.md has the design and the evidence.
#
# What it does. The system prompt gets only a short contents list. Each turn
# the harness works out the phase of play from facts it already has (a new
# game or level, how many actions this level has taken, what the last
# sequence did, how many turns since anything changed, the move budget left)
# and, when the phase changes, adds that phase's page to the end of the turn
# message. A page says what a principle means, why it matters, a worked
# example told by mechanic (no public game is named, RULES.md 3) and how to
# apply it to a game never seen before. The full page is shown the first time
# its phase comes up on a level; after that, a three-line checklist. The model
# may also ask for any page with one `Page: <id>` line.
#
# The opening and new-level pages carry the harness's own measurement of the
# board's tile size and offset, read off colour edges, and ask the model to
# write its derivation (Tile, Controls, Win, Plan) before acting. When the
# model's `Tile:` line disagrees with the measurement, the next turn says so.
#
# Every phase change prints one `PLAYBOOK phase` line. pb_phase(agent) returns
# the current (phase, reason): these are the stop-and-think moments a planner
# tier would be called at, so a planner reuses them instead of a second
# detector.
#
# Needs duck/r3/hook.py and duck/r3/lives.py pasted before it. lives.py's own
# MOVE BUDGET block is dropped (r3-budget-lives showed counting the bar every
# turn did not cut budget deaths); its counting is reused on the low-budget
# page only. No model call is made here. Any error leaves the turn unchanged.
import re as _re_pb

for _pb_name in ("r3_register", "R3_SECTIONS", "r3_lives", "r3_moves_left", "r3_bar"):
    if _pb_name not in globals():
        raise RuntimeError("duck/bigmodel/playbook.py needs duck/r3/hook.py and duck/r3/lives.py pasted before it")
R3_SECTIONS[:] = [s for s in R3_SECTIONS if s[0] != "budget"]

PB_EDGE = 4                # border band left out of the tile measurement (HUD bars live there)
PB_TILES = (8, 6, 5, 4, 3, 2)
PB_TILE_FIT = 0.7          # share of colour edges a tile size must line up with to be the answer
PB_TILE_SURE = 0.9         # ... and to be sure enough to name it, or to tell the model it is wrong
PB_TILE_MIN_EDGES = 12     # fewer colour edges than this: too little to measure
PB_TILE_STRIP = 16         # each strip of the board this wide may sit on its own offset (a seam between areas)
PB_EARLY_CHECK_AT = 8      # actions on a level before the early check
PB_MID_LEVEL_AT = 24       # actions on a level before the mid-level page
PB_STUCK_TURNS = 10        # turns on a level with no level change before the stuck page
PB_STUCK_REPEAT = 10       # turns between stuck reminders
PB_SURPRISE_GAP = 3        # turns between surprise pages, at least
PB_FLAT_SEQUENCES = 3      # sequences in a row that changed nothing count as a surprise
PB_LOW_SHARE = 0.3         # low budget: this share of the life or less is left ...
PB_LOW_MIN = 6             # ... or this many moves or fewer
PB_HEADER = "PLAYBOOK PAGE"
PB_CONTENTS_HEADER = "=== PLAYBOOK (the harness shows you the page for the moment you are in; ask for another with one line `Page: <id>`) ==="
PB_CONTENTS_FOOTER = "=== END PLAYBOOK ==="

# id: (title, when, full page, checklist). Examples are told by mechanic; none names a game.
PB_PAGES = {
    "opening": (
        "Opening: read the board before you move",
        "a game has just started",
        """WHAT. Before your first real move, find three things: the grid the game lives on, the status display (HUD), and what each control does.
WHY. Boards are 64x64 pixels, but the game is usually played on tiles of 2 to 8 pixels, sometimes inside a border or beside a HUD row. Once objects are in tile coordinates, a plan is arithmetic and a long batch is safe. Players who skipped this miscounted positions by one tile and paid for it in dozens of actions.
WORKED EXAMPLE. One board was 16 tiles of 4 pixels; another was 21 tiles of 3; one game switched from 4-pixel to 3-pixel tiles at a later level. A thin bar along one edge that loses cells as you act is a move budget: measuring it on the first moves told one player a level allowed about 69 actions per attempt. A player who misread the same kind of bar as half its real length reset levels it was about to win.
HOW TO APPLY. 1. Compute the tile size and offset in python from the frame (the harness's measurement is below; check it). 2. List every object in tile coordinates, and the HUD separately. 3. Try each control once, single actions, and read the diff after each: what moved, how far, what changed at the edges. 4. Note which colours repeat in different places; matching colours usually link a control to the objects it acts on.""",
        ("Find the tile size and offset in code, not by eye.",
         "Locate the HUD: bars, lives, counters. Measure what one action costs.",
         "Probe each control once and read the diff before batching anything."),
    ),
    "early-check": (
        "After the first few moves: check what you learned",
        "a few actions into a level",
        """WHAT. Stop and check your model of the level against what the diffs actually showed, before you commit to a route.
WHY. The costliest mistake strong players made was generalising from one observation. A rule seen once is a guess; a rule seen twice in different places is a rule.
WORKED EXAMPLE. One player decided board edges block movement after one edge did, and planned around a wall that was not there. Another assumed a tile was fixed from a single frame; it rotated every turn and stood on the exit when the player arrived. A control that did nothing in one place was a submit button that only acts when the layout is right; it was nearly written off as dead.
HOW TO APPLY. Answer these in your reply, one line each: Which controls are measured, and which only guessed? What does one action cost from the budget? Which rule have you seen only once, and what is the cheapest move that would show it a second time? What exactly must be true on the board for the level to end? If a control seemed to do nothing, try it once more in a different situation before you drop it.""",
        ("Separate measured rules from guesses; confirm each guess on a second case.",
         "Re-try a silent control once in a new situation before dropping it.",
         "State the win condition as literally seen."),
    ),
    "mid-level": (
        "Mid-level: work it out, then batch the checked plan",
        "the level is understood well enough to plan",
        """WHAT. Derive the answer from the geometry and the rules first, then send the whole checked plan as one batch, stopping before any point where the outcome is uncertain.
WHY. Levels are built to fit exactly, so measurements usually name the answer. Long batches of 15 to 40 actions were the main reason strong players used half the actions a human did, and every bad batch was one that ran through an untested assumption.
WORKED EXAMPLE. In one game the gap between two fixed objects equalled one movable piece's length plus one step, which said which piece went there. In another, a piece always sat at the average of its endpoints, so the endpoints had to sum to a known total. In a third, every jump kept the parity of x and y, which ruled out most moves before any were tried. The bad batches: ten clicks on a control that did nothing, and a walk onto an exit while a moving tile was on the last step.
HOW TO APPLY. 1. Write the target state, then compute the route or the answer in python (a search over the tile grid, or a small solver for the toggles you have measured). 2. Count the route's actions against the budget. 3. Batch up to the next decision point only: a pickup, a moving object, a control not yet seen to work. 4. If anything moves on its own, find the turn order first: does it move before or after you, and does a blocked move advance it?""",
        ("Measure gaps, widths and counts; levels are built to fit exactly.",
         "Compute the route in code and count it against the budget.",
         "Batch only checked steps; stop before moving objects and untested controls."),
    ),
    "surprise": (
        "Surprise: something did not go as predicted",
        "the last sequence ended an attempt, was stopped, or changed nothing again and again",
        """WHAT. An unexpected result is information. Find out exactly what happened before you act again.
WHY. A failure points near the problem, not at the guilty piece. Players who rebuilt their whole plan after a failure spent hundreds of actions; players who changed one thing at a time fixed it in a few.
WORKED EXAMPLE. A player's 'no cells changed' was wrong: its own sprite covered the tile that changed. An action that looked like a no-op played a multi-frame event that ended where it began; the in-between frames held the rule. After several full rebuilds failed, one player solved two levels with tweaks of 2 and 6 actions. Another saw a button rotate a second object every time it was pressed, a side effect that broke the plan until it was noticed.
HOW TO APPLY. 1. Diff the frame before the last action against the one after, including the HUD and the far edges of the board. 2. If an attempt ended, look at the last frame before it ended: what touched what, what ran out. 3. Write one line: what you predicted, what happened, and the one rule that explains both. 4. Change ONE thing and test it with the fewest actions. Do not repeat a sequence that failed unless you have changed something.""",
        ("Diff before and after, HUD and far edges included.",
         "Write: predicted, happened, the rule that explains both.",
         "Change one thing; never repeat a failed sequence unchanged."),
    ),
    "stuck": (
        "Stuck: many turns on this level and no clear",
        "many turns on this level without a level change",
        """WHAT. When a level has eaten many turns, the trouble is usually the frame, not the execution: you are aiming at the wrong goal, or a control you dismissed is the one that matters.
WHY. The weakest strong-model runs locked onto one wrong idea for over a hundred actions. Time spent here is taken from every level still to come.
WORKED EXAMPLE. One player cycled through all 32 combinations of a set of switches without ever pressing the button that submits them; nothing happens until it is pressed. Another believed an ability was impossible when it only needed open space. Another trusted a limit it had made up and decided the level could not be solved as designed.
HOW TO APPLY. Write three lines: GOAL (the goal you have assumed), ALTERNATIVE (a different goal or mechanic that fits the evidence as well), TEST (the cheapest sequence that tells them apart). Then run the test. Check in particular: is there a submit, confirm or execute control you have not pressed on your best candidate? Is a colour or symbol you ignored repeated somewhere else? Is the win condition exactly what you think, counted across everything on the board, including what is hidden or off to the side?""",
        ("Write GOAL, ALTERNATIVE and TEST, then run the test.",
         "Look for a submit or confirm control not yet pressed on your best candidate.",
         "Re-read the win condition literally, across the whole board."),
    ),
    "new-level": (
        "New level: keep the rules, find what is new",
        "a level has just been cleared",
        """WHAT. Write down the rules you learned, then read the new board for what is different before you move.
WHY. A new level usually keeps the controls and adds one mechanic. Rules carry over; move sequences do not. A player that lost its notes part way through a game re-learned a level at three and a half times the actions of one that kept them.
WORKED EXAMPLE. One game kept every control from earlier levels and added a new tile type each level; the players who listed what was new first planned the level in a few actions. Another changed the tile size from 4 to 3 pixels at a later level, so plans that reused old coordinates missed.
HOW TO APPLY. 1. Write the rules note you are asked for: tile size, controls, objects and colours, the literal win condition, the traps. 2. On the new board, re-measure the tile size (the harness's measurement is below) and list the objects that were not on the last level. 3. Confirm one old rule with one probe. 4. Then plan from the rules, as on the mid-level page.""",
        ("Write the rules note: tile, controls, objects, win, traps.",
         "Re-measure the tile size; list what is new on this board.",
         "Confirm one old rule with one probe, then plan."),
    ),
    "low-budget": (
        "Low budget: before you spend the rest of this life or reset",
        "the move budget for this life is nearly gone",
        """WHAT. Moves, lives, resets and one-shot items are the scarce resource. Before you spend what is left, decide whether the plan fits.
WHY. Every reset is a scored action and a full re-walk. Players with the most resets had the lowest scores; strong players used few and learned on one attempt to execute on the next.
WORKED EXAMPLE. A refill pickup that had been used did not come back, and walking back to it cost a life and about 80 actions. One game limited the number of runs, and a run spent as an experiment without the setup in place was wasted.
HOW TO APPLY. Write one line: `FITS: yes` or `FITS: no` -- does your counted route reach the goal within the moves left? If yes, batch it. If no, do not spend the life walking: use the moves left to learn one thing you still need (where the goal is, what one unknown object does). Then, on the fresh attempt, run the plan you stored as one batch.""",
        ("Count the route; write FITS: yes or FITS: no.",
         "If it does not fit, spend the rest of the life learning one thing you need.",
         "Learn on one attempt, execute on the next, as one batch."),
    ),
}
PB_ORDER = ("opening", "early-check", "mid-level", "surprise", "stuck", "new-level", "low-budget")


def _pb_edges(grid):
    """(x positions, y positions) of colour edges inside the border band, or None.
    A colour edge is two neighbouring cells of different colour."""
    rows = [list(r) for r in (grid or [])]
    h = len(rows)
    w = len(rows[0]) if h else 0
    if h <= 2 * PB_EDGE + 2 or w <= 2 * PB_EDGE + 2:
        return None
    xs, ys = [], []
    for i in range(PB_EDGE, h - PB_EDGE):
        for j in range(PB_EDGE + 1, w - PB_EDGE):
            if rows[i][j] != rows[i][j - 1]:
                xs.append(j)
    for i in range(PB_EDGE + 1, h - PB_EDGE):
        for j in range(PB_EDGE, w - PB_EDGE):
            if rows[i][j] != rows[i - 1][j]:
                ys.append(i)
    if len(xs) < PB_TILE_MIN_EDGES or len(ys) < PB_TILE_MIN_EDGES:
        return None
    return xs, ys


def pb_tile_fit(edges, s, strips=False):
    """(x offset, y offset, share of colour edges on the boundaries of s-pixel
    tiles at those offsets). With strips, each PB_TILE_STRIP-wide strip takes
    its own best offset, so a seam where one area's grid is shifted against
    another's does not count against the size; the offsets returned are then
    the whole board's best."""
    xs, ys = edges
    if s <= 1:
        return 0, 0, 1.0
    out = []
    for found in (xs, ys):
        groups = {}
        for e in found:
            groups.setdefault(e // PB_TILE_STRIP if strips else 0, []).append(e)
        hits = 0
        for group in groups.values():
            counts = [0] * s
            for e in group:
                counts[e % s] += 1
            hits += max(counts)
        counts = [0] * s
        for e in found:
            counts[e % s] += 1
        out.append((max(range(s), key=lambda o: counts[o]), hits / len(found)))
    return out[0][0], out[1][0], min(out[0][1], out[1][1])


def pb_tile(grid):
    """(size, x offset, y offset, share, sure), or None.

    On a tiled board every colour edge falls on a tile boundary, so the tile
    size is the largest size whose boundaries take most of the edges. Markers
    drawn inside tiles and seams between areas put some edges off the grid, so
    the answer only needs PB_TILE_FIT of them strip by strip, and it is sure
    only when one offset across the whole board takes PB_TILE_SURE. Taking the
    largest fit first matters: a half-size grid takes every edge of the full
    one, plus the markers', and across a seam it may be the only single grid
    left, so it can score higher than the true size. A random board fits size
    s by chance about 1/s of the time. Size 1 lines up with everything and is
    never answered. The share returned is the whole board's."""
    edges = _pb_edges(grid)
    if edges is None:
        return None
    for s in PB_TILES:
        if pb_tile_fit(edges, s, strips=True)[2] >= PB_TILE_FIT:
            ox, oy, share = pb_tile_fit(edges, s)
            return s, ox, oy, round(share, 3), share >= PB_TILE_SURE
    return None


def pb_tile_check(grid, measured, stated):
    """The TILE CHECK line, or '' -- said only when the harness is sure and the
    board's own edges contradict the model's size. When the measurement is
    unsure, or the stated size also fits the edges, it says nothing. Nor when
    the stated size is a multiple of the measured one: markers inside the
    tiles, or a seam, can make a grid of half the true size the only one that
    fits the whole board, so the multiple may be the truth."""
    if stated is None or not measured or not measured[4] or stated % measured[0] == 0:
        return ""
    edges = _pb_edges(grid)
    if edges is None or stated > 32:
        return ""
    if pb_tile_fit(edges, stated, strips=True)[2] >= PB_TILE_FIT:
        return ""
    return (f"TILE CHECK: you wrote tiles of {stated} pixels; the harness measured {measured[0]} "
            f"({round(100 * measured[3])}% of colour edges). Re-check in code before planning in tiles.")


def pb_tile_line(measured):
    if measured is None or not measured[4]:
        return "Harness measurement: no tile size from 2 to 8 pixels lines up cleanly with this board's colour edges; measure it yourself."
    s, ox, oy, share, _ = measured
    return (f"Harness measurement: tiles of {s} pixels, columns starting at x = {ox} mod {s}, rows at y = {oy} mod {s} "
            f"({round(100 * share)}% of colour edges line up); the true tile may be a multiple of {s} if objects are "
            f"drawn inside tiles. Check it in code before you rely on it.")


def pb_stated_tile(text):
    """The tile size on the model's last `Tile:` line, or None."""
    found = _re_pb.findall(r"Tile\s*(?:size)?\s*[:=][^\n0-9]{0,20}(\d+)", text or "", _re_pb.I)
    return int(found[-1]) if found else None


def _pb_text(msg):
    parts = []
    for key in ("content", "reasoning_content", "reasoning"):
        value = msg.get(key) if isinstance(msg, dict) else None
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts += [p.get("text", "") for p in value if isinstance(p, dict) and isinstance(p.get("text"), str)]
    return "\n".join(p for p in parts if p)


def pb_asked_page(text):
    """The page id on the model's last `Page:` line, or None."""
    for line in reversed(_re_pb.findall(r"Page\s*:[ \t]*([^\n]+)", text or "", _re_pb.I)):
        token = "-".join(_re_pb.findall(r"[a-z0-9]+", line.lower()))
        for pid in PB_ORDER:
            if token.startswith(pid):
                return pid
    return None


def pb_contents():
    lines = [PB_CONTENTS_HEADER]
    lines += [f"- {pid}: {PB_PAGES[pid][0]} (shown when {PB_PAGES[pid][1]})" for pid in PB_ORDER]
    lines.append(PB_CONTENTS_FOOTER)
    return "\n".join(lines)


def pb_page(pid, full):
    title, _, body, checklist = PB_PAGES[pid]
    if full:
        return f"{PB_HEADER} [{pid}] {title}\n{body}"
    return f"{PB_HEADER} [{pid}] {title} (checklist; ask `Page: {pid}` for the whole page)\n" + \
        "\n".join(f"- {c}" for c in checklist)


class PBState:
    def __init__(self):
        self.level = None
        self.turns = 0            # turns on this level
        self.shown = {}           # page id -> turn it was last shown on this level
        self.phase = (None, "")
        self.last_step = None
        self.flat = 0
        self.stated_tile = None
        self.tile = None
        self.low_life = None      # (level, deaths) of the life the low-budget page was shown for
        self.grid = None          # the frame the tile was measured on
        self.last_reply = None    # hash of the newest model reply already read


def _pb_state(view):
    extra = view["state"].extra
    if "playbook" not in extra:
        extra["playbook"] = PBState()
    return extra["playbook"]


def _pb_actions_on_level(entries, level):
    n = 0
    prev = None
    for e in entries:
        lv = getattr(getattr(e, "frame", None), "level", None)
        action = str(getattr(e, "action", "") or "").strip()
        if action and prev == level:
            n += 1
        if isinstance(lv, int):
            prev = lv
    return n


def _pb_surprise(st, summary):
    if not summary or summary.get("stale"):
        return ""
    step = summary.get("end_action_num", summary.get("start_action_num"))
    if step is None or step == st.last_step:
        return ""
    st.last_step = step
    if summary.get("level_transition"):
        st.flat = 0
        return ""
    if summary.get("game_over"):
        return "the attempt ended"
    if summary.get("no_op_stops") or summary.get("guard_stops"):
        return "a sequence was stopped because a move changed nothing"
    changed = summary.get("gameplay_changed", summary.get("board_changed"))
    st.flat = st.flat + 1 if changed is False else 0
    if st.flat >= PB_FLAT_SEQUENCES:
        st.flat = 0
        return f"{PB_FLAT_SEQUENCES} sequences in a row changed nothing on the board"
    return ""


def pb_choose(st, view, summary, life):
    """(page id, reason) for this turn, or (None, ''). The order is the priority."""
    level = view["level"]
    if level != st.level:
        first = st.level is None
        st.level, st.turns, st.shown, st.flat, st.tile = level, 0, {}, 0, None
        return ("opening", "the game has started") if first else ("new-level", f"level {level} has started")
    st.turns += 1
    surprise = _pb_surprise(st, summary)
    if surprise and st.turns - st.shown.get("surprise", -99) >= PB_SURPRISE_GAP:
        return "surprise", surprise
    left, _ = r3_moves_left(life) if life else (None, "")
    if left is not None and life["moves"] > 0:
        total = life["moves"] + left
        key = (level, len(life["deaths"]))
        if left <= max(PB_LOW_MIN, PB_LOW_SHARE * total) and st.low_life != key:
            st.low_life = key
            return "low-budget", f"about {left} moves are left in this life"
    if st.turns >= PB_STUCK_TURNS and st.turns - st.shown.get("stuck", -99) >= PB_STUCK_REPEAT:
        return "stuck", f"{st.turns} turns on level {level} without clearing it"
    acted = _pb_actions_on_level(view["entries"], level)
    if acted >= PB_EARLY_CHECK_AT and "early-check" not in st.shown:
        return "early-check", f"{acted} actions on level {level}"
    if acted >= PB_MID_LEVEL_AT and "mid-level" not in st.shown:
        return "mid-level", f"{acted} actions on level {level}"
    return None, ""


def pb_phase(agent):
    """(phase, reason) the playbook last chose for this game, or (None, '')."""
    st = getattr(agent.__dict__.get("_r3_state"), "extra", {}).get("playbook")
    return st.phase if st else (None, "")


def _pb_set_contents(agent):
    block = pb_contents()
    prompt = getattr(agent, "_system_prompt", None)
    if not isinstance(prompt, str) or block in prompt:
        return
    agent._system_prompt = prompt.rstrip("\n") + "\n\n" + block


def _pb_last_reply(agent, st):
    """The newest model reply, once. Keyed by its text, not its object id: the
    history is trimmed and rebuilt, and a freed id can come back on a new reply."""
    for msg in reversed(getattr(agent, "_history_messages", None) or []):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            text = _pb_text(msg)
            key = hash(text)
            if key == st.last_reply:
                return ""
            st.last_reply = key
            return text
    return ""


def pb_section(agent, view):
    _pb_set_contents(agent)
    st = _pb_state(view)
    summary = getattr(agent, "_last_step_summary", None) or None
    life = r3_lives(view["entries"])
    lines = []
    reply = _pb_last_reply(agent, st)
    asked = pb_asked_page(reply)
    stated = pb_stated_tile(reply)
    pid, reason = pb_choose(st, view, summary, life)
    grid = getattr(view["frame"], "grid", None)
    if pid in ("opening", "new-level"):
        st.tile, st.grid = pb_tile(grid), grid
    check = pb_tile_check(st.grid, st.tile, stated) if stated != st.stated_tile else ""
    if check:
        lines.append(check)
    if stated is not None:
        st.stated_tile = stated
    full = bool(pid) and pid not in st.shown
    if pid:
        st.shown[pid] = st.turns
        st.phase = (pid, reason)
        print(f"PLAYBOOK phase {getattr(agent, '_diag_name', '')} L{view['level']} {pid}: {reason}", flush=True)
        lines.append(f"(Playbook: {reason}.)")
        lines.append(pb_page(pid, full))
        if pid in ("opening", "new-level"):
            lines.append(pb_tile_line(st.tile))
            lines.append("Before your first move on this level, write four lines: `Tile:` (size and offset), "
                         "`Controls:` (what each is known to do, or 'unknown'), `Win:` (the goal as literally seen, "
                         "or your best guess marked as a guess), `Plan:` (your next few actions and what each should show).")
        if pid == "low-budget":
            left, how = r3_moves_left(life)
            bar = r3_bar(life["start"], life["now"])
            fact = f"Harness count: about {left} moves left in this life, by {how}"
            lines.append(fact + (f"; the edge bar has {round(100 * bar[1])}% left." if bar else "."))
    if asked and not (asked == pid and full):
        # A request is answered on the turn it is made, even when the harness also opens a page.
        lines.append(pb_page(asked, True))
    return lines


r3_register("playbook", pb_section)
print(f"PLAYBOOK on: {len(PB_PAGES)} pages, harness-chosen", flush=True)
