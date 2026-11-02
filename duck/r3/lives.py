# Budget-aware lives (arc-agi-3 bets-round-3, variant r3-budget-lives). MIT-0.
#
# The loss autopsy's biggest single mode is move_limit (docs/autopsy.md): a
# life's move budget, usually a bar along the grid's edge, runs out before the
# goal is reached. Nothing in the harness counts that budget for the player.
# This cell does, from the frames alone, and treats moves as the resource they
# are. Each turn on a level whose edge bar drains, or where a life has already
# ended, it adds a MOVE BUDGET block to the user prompt:
#
# - the moves spent in this life, how much of the edge bar is left and, at its
#   drain rate so far, about how many moves remain;
# - how earlier lives on the level ended, and the life's move limit when the
#   deaths show one (the same rule the autopsy uses: two lives of one length,
#   or one that ended with the bar run out);
# - the rule: count a route's moves in code before batching it, and find the
#   goal before walking to it.
#
# When few moves are left it adds a Jev-style typed check, answered by the
# player in the same turn (no extra model call): `FITS: yes|no`, does the
# planned route reach the goal within the moves left? At the first turn of a
# life after one ran out of moves, it asks for the goal and the counted
# shortest route before any move. Nothing here knows any particular game: the
# bar is any border colour that shrinks while the player moves.
#
# Needs duck/r3/hook.py pasted before it.
if "r3_register" not in globals():
    raise RuntimeError("duck/r3/lives.py needs duck/r3/hook.py pasted before it")

R3_EDGE = 4                # rows and columns at each edge where bars are drawn
R3_BAR_MIN_CELLS = 8       # a colour needs this many border cells to be a bar
R3_DRAINED = 0.8           # a death with this much of the bar gone was at the budget
R3_LIMIT_MIN_MOVES = 10    # shorter lives are hazards, not a move limit
R3_TIGHT_SHARE = 0.3       # ask FITS when this share of the life or less is left
R3_TIGHT_MIN = 6           # ... or this many moves or fewer
R3_RATE_MIN_MOVES = 3      # moves in a life before the bar's drain rate is read
R3_BUDGET_HEADER = ("MOVE BUDGET (counted by the harness from this level's frames; "
                    "facts to plan with, not orders):")


def r3_edge_counts(grid):
    """{colour: cells} in the R3_EDGE-wide band around the grid's border."""
    rows = [list(r) for r in (grid or [])]
    h = len(rows)
    out = {}
    for i, row in enumerate(rows):
        w = len(row)
        for j, v in enumerate(row):
            if i < R3_EDGE or i >= h - R3_EDGE or j < R3_EDGE or j >= w - R3_EDGE:
                out[v] = out.get(v, 0) + 1
    return out


def r3_bar(start, now):
    """(colour, share of the bar left) for the border colour that has drained
    most since `start`, or None when no border colour shrank."""
    s, e = r3_edge_counts(start), r3_edge_counts(now)
    best = None
    for colour, n in s.items():
        if n < R3_BAR_MIN_CELLS:
            continue
        gone = (n - e.get(colour, 0)) / n
        if gone > 0 and (best is None or gone > best[1]):
            best = (colour, gone)
    return None if best is None else (best[0], round(1.0 - best[1], 3))


def r3_drain(start, *ends):
    """The largest share of any bar colour gone in any of `ends`."""
    out = 0.0
    for end in ends:
        bar = r3_bar(start, end)
        if bar is not None:
            out = max(out, 1.0 - bar[1])
    return round(out, 3)


def _r3_game_over(entry):
    result = getattr(entry, "result", None) or {}
    state = " ".join(str(x or "") for x in (result.get("state"), getattr(getattr(entry, "frame", None), "state", "")))
    return bool(result.get("game_over")) or "GAME_OVER" in state.upper()


def r3_lives(entries):
    """The level in progress, read off the history: {level, moves (in this
    life), start (the grid the life began from), now (the latest grid), deaths
    [(moves, drained share)]}. history[i].frame is the frame after
    history[i].action, so an action belongs to the level of the frame before
    it; a RESET or a level change starts a new life."""
    level, start, now, moves, deaths = None, None, None, 0, []
    for e in entries:
        frame = getattr(e, "frame", None)
        grid = getattr(frame, "grid", None)
        lv = getattr(frame, "level", None)
        action = str(getattr(e, "action", "") or "").strip().upper()
        if level is None:
            level, start, now = lv, grid, grid
            if not action or action.startswith("RESET"):
                continue
        if lv != level:
            level, start, now, moves, deaths = lv, grid, grid, 0, []
            continue
        if action.startswith("RESET"):
            if (getattr(e, "result", None) or {}).get("automatic") and moves > 0:
                # the harness reset after a death this history did not flag
                deaths.append((moves, r3_drain(start, now)))
            start, now, moves = grid, grid, 0
            continue
        moves += 1
        if _r3_game_over(e):
            deaths.append((moves, r3_drain(start, now, grid)))
            start, now, moves = grid, grid, 0
            continue
        now = grid
    return {"level": level, "moves": moves, "start": start, "now": now, "deaths": deaths}


def r3_move_limit(deaths):
    """The life's move limit, when the deaths show one."""
    lengths = [n for n, _ in deaths if n >= R3_LIMIT_MIN_MOVES]
    for n in sorted(set(lengths), reverse=True):
        if lengths.count(n) >= 2:
            return n
    drained = [n for n, d in deaths if d >= R3_DRAINED and n >= R3_LIMIT_MIN_MOVES]
    return max(drained) if drained else None


def r3_moves_left(life):
    """(moves left in this life or None, how it was found)."""
    limit = r3_move_limit(life["deaths"])
    if limit is not None:
        return max(0, limit - life["moves"]), f"the move limit of {limit}"
    bar = r3_bar(life["start"], life["now"])
    if bar is None or life["moves"] < R3_RATE_MIN_MOVES:
        return None, ""
    gone = 1.0 - bar[1]
    return max(0, round(bar[1] * life["moves"] / gone)), "the edge bar's drain rate"


def r3_budget_lines(life, level=None):
    """The MOVE BUDGET block for this turn, or [] when the level shows no budget."""
    deaths, moves = life["deaths"], life["moves"]
    bar = r3_bar(life["start"], life["now"])
    if bar is None and not deaths:
        return []
    level = life["level"] if level is None else level
    left, how = r3_moves_left(life)
    lines = [R3_BUDGET_HEADER,
             f"- Level {level}, life {len(deaths) + 1}: {moves} moves spent in this life."]
    if bar is not None:
        lines.append(f"- Edge bar (colour {bar[0]}): {round(100 * bar[1])}% of it left.")
    if left is not None:
        lines.append(f"- About {left} more moves in this life, by {how}.")
    if deaths:
        ran_out = sum(1 for _, d in deaths if d >= R3_DRAINED)
        lines.append(f"- {len(deaths)} earlier life/lives on this level ended in game over, after "
                     + ", ".join(str(n) for n, _ in deaths[-6:]) + " moves"
                     + (f"; {ran_out} with the edge bar run out." if ran_out else "."))
    lines.append("- Moves are the scarce resource. Before a batch, count the route's moves in code and "
                 "compare them with the moves left. Find where the goal is before walking to it.")
    total = moves + left if left is not None else None
    if left is not None and moves > 0 and left <= max(R3_TIGHT_MIN, R3_TIGHT_SHARE * total):
        lines.append(f"BUDGET CHECK (answer in your reply, one line: `FITS: yes` or `FITS: no`): does your "
                     f"planned route reach the goal within {left} moves? If no, do not spend this life walking: "
                     "use the moves left to learn something you need (where the goal is, what an unknown object "
                     "does), or RESET and replay the shortest route you know.")
    if moves == 0 and deaths and deaths[-1][1] >= R3_DRAINED:
        lines.append(f"NEW LIFE: the last life ran out of moves after {deaths[-1][0]} with the level unsolved. "
                     "Before moving, write the goal's position and the shortest route to it, counted in moves. "
                     "If you do not know where the goal is, the first moves of this life are for finding it.")
    return lines


def r3_budget_section(agent, view):
    life = r3_lives(view["entries"])
    lines = r3_budget_lines(life, view["level"])
    if lines and any(line.startswith(("BUDGET CHECK", "NEW LIFE")) for line in lines):
        print(f"R3 BUDGET {getattr(agent, '_diag_name', '')} L{view['level']} moves={life['moves']} "
              f"deaths={len(life['deaths'])} {lines[-1].split(':', 1)[0]}", flush=True)
    return lines


r3_register("budget", r3_budget_section)
print("R3 budget-aware lives on", flush=True)
