# Two-tier play, sandbox side (arc-agi-3 two-tier-expect-batches). MIT-0.
# See docs/two-tier.md in our repository.
#
# The thinking turn writes an action list with one expectation per step; this
# code plays the list one step at a time and stops at the first step that did
# not do what was expected:
#
#     action(['RIGHT', 'RIGHT', 'UP', 'SPACE'], expect=['move', 'move', 'move', 'change'])
#
# An expectation is one of:
#   'move'            an object moved whole; for UP/DOWN/LEFT/RIGHT, that way
#   'change'          something inside the board changed
#   'none'            nothing inside the board changed
#   'level'           this step cleared the level
#   {'b': (r, c)}     the object drawn with character b has its top-left cell
#                     at (r, c) after the step (the shared prediction format of
#                     duck/workout/predict.py)
#   lambda frame: ... a test on the frame after the step
#   any other string  free text: settled by rule when the board alone can (it
#                     did not change at all; the object moved the way the text
#                     says), otherwise put to the Jev judge on the host (the
#                     same served model, thinking off) as one yes/no question
#   None              no check for this step
# A list gives one per step; anything else is the expectation for the last
# step. A call without `expect` runs through the harness's own `action`,
# unchanged, and is only counted.
#
# Checks are rule-first: a rule that settles the step costs nothing, and only
# what no rule can settle reaches the judge. An "unsure" answer lets the step
# stand, so the judge can stop a list but never invent a stop it cannot name.
#
# Provenance: _tt_rows through _tt_shift are copied from duck/macro/dsl.py
# (macro-bet, MIT-0, ours), renamed from `_mc` to `_tt`.
#
# This source is pasted verbatim into the harness's sandbox bootstrap by the
# cell duck/twotier/render.py writes. So it uses the standard library only,
# every top-level name starts with `_tt` or `_TT`, and it defines nothing the
# model sees until `_tt_install(...)` runs, right after `action` is registered.
# Nothing here names or targets a game.
import json as _tt_json

_TT_MARK = "\x1ett "
_TT_UNIT = {"UP": (-1, 0), "DOWN": (1, 0), "LEFT": (0, -1), "RIGHT": (0, 1)}
_TT_BORDER = 2          # outer cells left out of change counts (timer and move bars sit there)
_TT_MAX_LIST = 60       # a longer list is cut to this many steps
_TT_JUDGE = "tt_judge"  # the request kind the host's judge answers
_TT_QUIET = ("nothing", "no change", "unchanged", "stay", "blocked", "wall", "not move", "no effect",
             "same", "does not", "doesn't", "won't", "no-op", "noop")
_TT_DIRS = {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT",
            "north": "UP", "south": "DOWN", "west": "LEFT", "east": "RIGHT"}
_TT_MOVE_WORDS = ("move", "moves", "walk", "go ", "goes", "step", "slide", "shift")


# ---- grid helpers (copied from duck/macro/dsl.py) ----
def _tt_rows(frame):
    """The board as a list of row strings (the letter-coded ascii)."""
    if frame is None:
        return []
    text = getattr(frame, "ascii", frame)
    if isinstance(text, (list, tuple)):
        return [str(r) for r in text]
    return [r for r in str(text).split("\n") if r]


def _tt_at(rows, r, c):
    if 0 <= r < len(rows) and 0 <= c < len(rows[r]):
        return rows[r][c]
    return None


def _tt_cells(rows, ch):
    return {(r, c) for r, row in enumerate(rows) for c, x in enumerate(row) if x == ch}


def _tt_components(rows, ch, within=None):
    """4-connected components of colour `ch`, as sets of (row, col)."""
    todo = set(within) if within is not None else _tt_cells(rows, ch)
    comps = []
    while todo:
        seed = todo.pop()
        comp, queue = {seed}, [seed]
        while queue:
            r, c = queue.pop()
            for p in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if p in todo:
                    todo.discard(p)
                    comp.add(p)
                    queue.append(p)
        comps.append(comp)
    comps.sort(key=lambda s: (min(s), len(s)))
    return comps


def _tt_changed(a, b):
    out = set()
    for r in range(max(len(a), len(b))):
        ra = a[r] if r < len(a) else ""
        rb = b[r] if r < len(b) else ""
        for c in range(max(len(ra), len(rb))):
            if (ra[c] if c < len(ra) else None) != (rb[c] if c < len(rb) else None):
                out.add((r, c))
    return out


def _tt_interior(cells, rows):
    h = len(rows)
    w = max((len(r) for r in rows), default=0)
    b = _TT_BORDER
    return {(r, c) for r, c in cells if b <= r < h - b and b <= c < w - b}


def _tt_shift(before, after):
    """[(colour, dr, dc, cells before)] for each object that moved whole, smallest first."""
    changed = _tt_changed(before, after)
    if not changed:
        return []
    out = []
    for ch in {_tt_at(before, r, c) for r, c in changed} | {_tt_at(after, r, c) for r, c in changed}:
        if ch is None:
            continue
        left = {p for p in changed if _tt_at(before, *p) == ch and _tt_at(after, *p) != ch}
        entered = {p for p in changed if _tt_at(after, *p) == ch and _tt_at(before, *p) != ch}
        if not left or not entered:
            continue
        moved = set().union(*[s for s in _tt_components(before, ch) if s & left])
        landed = set().union(*[s for s in _tt_components(after, ch) if s & entered])
        if not moved or len(moved) != len(landed) or len(moved) > 400:
            continue
        dr = min(r for r, _ in landed) - min(r for r, _ in moved)
        dc = min(c for _, c in landed) - min(c for _, c in moved)
        if (dr, dc) != (0, 0) and {(r + dr, c + dc) for r, c in moved} == landed:
            out.append((ch, dr, dc, moved))
    out.sort(key=lambda m: len(m[3]))
    return out


# ---- what one step did ----
def _tt_name(a):
    if isinstance(a, dict):
        return str(a.get("action", "MOUSE")).strip().upper() or "MOUSE"
    s = str(a or "").strip().upper()
    return s.split()[0] if s else s


def _tt_display(a):
    if isinstance(a, dict) and "row" in a and "col" in a:
        return f"{_tt_name(a)}@{a['row']},{a['col']}"
    if isinstance(a, dict) and "x" in a and "y" in a:
        return f"{_tt_name(a)}@x{a['x']},y{a['y']}"
    return _tt_name(a)


def _tt_effect(before, after, res):
    """What one step did, from the board before and after and the harness's result."""
    changed = _tt_changed(before, after)
    interior = _tt_interior(changed, after)
    flag = res.get("gameplay_changed") if isinstance(res, dict) else None
    pairs = {}
    for r, c in interior:
        key = (_tt_at(before, r, c), _tt_at(after, r, c))
        pairs[key] = pairs.get(key, 0) + 1
    return {"cells": len(interior), "hud": len(changed) - len(interior),
            "changed": bool(interior) if flag is None else bool(flag),
            "moved": [(ch, dr, dc) for ch, dr, dc, _cells in _tt_shift(before, after)],
            "pairs": sorted(pairs.items(), key=lambda kv: -kv[1])[:6],
            "level": bool(isinstance(res, dict) and res.get("level_completed")),
            "over": bool(isinstance(res, dict) and res.get("game_over"))}


def _tt_facts(eff):
    """The effect as plain sentences, for the judge and for the stop message."""
    moved = ", ".join(f"'{ch}' by {dr:+d} rows, {dc:+d} cols" for ch, dr, dc in eff["moved"][:4])
    pairs = ", ".join(f"{o}->{n} x{k}" for (o, n), k in eff["pairs"])
    return (f"{eff['cells']} cell(s) inside the board changed ({pairs or 'none'}); "
            f"{eff['hud']} border cell(s) changed; objects that moved whole: {moved or 'none'}.")


def _tt_way(name, dr, dc):
    ur, uc = _TT_UNIT[name]
    return (ur and dr and (dr > 0) == (ur > 0) and not dc) or (uc and dc and (dc > 0) == (uc > 0) and not dr)


def _tt_top_left(rows, ch):
    cells = _tt_cells(rows, ch)
    return (min(r for r, _ in cells), min(c for _, c in cells)) if cells else None


def _tt_steps(n, expect):
    """One expectation per step."""
    if isinstance(expect, (list, tuple)):
        steps = list(expect)[:n]
        return steps + [None] * (n - len(steps))
    return [None] * (n - 1) + [expect]


def _tt_rule(exp, name, eff, rows, frame):
    """("pass" | "fail" | "unsure", why) for one step's expectation, by rule alone."""
    if callable(exp):
        try:
            return ("pass", "") if exp(frame) else ("fail", "your test on the frame is False.")
        except Exception as exc:
            return "fail", f"your test raised {type(exc).__name__}: {exc}."
    if isinstance(exp, dict):
        objects = {k: v for k, v in exp.items() if isinstance(k, str) and len(k) == 1}
        if not objects:
            text = "; ".join(f"{k}: {v}" for k, v in exp.items())
            return _tt_rule(text, name, eff, rows, frame)
        for ch, want in objects.items():
            try:
                want = (int(want[0]), int(want[1]))
            except (TypeError, ValueError, IndexError):
                return "fail", f"'{ch}': {want!r} is not a (row, col) pair."
            got = _tt_top_left(rows, ch)
            if got != want:
                where = f"at {got}" if got else "not on the board"
                return "fail", f"you expected '{ch}' with its top-left at {want}; it is {where}."
        return "pass", ""
    text = " ".join(str(exp).lower().split())
    if text in ("change", "changes", "changed"):
        return ("pass", "") if eff["changed"] else ("fail", "nothing inside the board changed.")
    if text in ("none", "nothing", "no change", "no-op", "noop", "same"):
        return ("pass", "") if not eff["changed"] else ("fail", "the board changed.")
    if text in ("level", "clear", "win", "level complete", "level_completed"):
        return ("pass", "") if eff["level"] else ("fail", "the level did not clear.")
    if text in ("move", "moves", "moved"):
        if name in _TT_UNIT:
            if any(_tt_way(name, dr, dc) for _ch, dr, dc in eff["moved"]):
                return "pass", ""
            return "fail", f"no object moved {name.lower()}."
        return ("pass", "") if eff["moved"] else ("fail", "no object moved whole.")
    # free text: the board settles what it can, the judge the rest
    quiet = any(w in text for w in _TT_QUIET)
    if not eff["changed"] and not eff["level"] and not quiet:
        return "fail", "nothing inside the board changed at all."
    if eff["changed"] and any(w in text for w in _TT_MOVE_WORDS):
        named = {d for w, d in _TT_DIRS.items() if f" {w}" in f" {text}"}
        if named and any(_tt_way(d, dr, dc) for d in named for _ch, dr, dc in eff["moved"]):
            return "pass", ""
    return "unsure", ""


def _tt_install(g, send=None, recv=None, unstale=None, base=BaseException):
    """Wrap the sandbox's `action` so a list carries per-step expectations.

    `base` is the class of the harness's own refusals: the sandbox's last-chance
    handler names those classes and `Exception`, so a stop derived from a bare
    BaseException would escape it and kill the sandbox process, losing the
    snippet's stdout and the message."""
    raw_action = g.get("action")
    if not callable(raw_action) or getattr(raw_action, "_tt", False):
        return

    class ExpectationFailed(base):
        pass  # raised after the failing step ran; the rest of the list was not sent

    def emit(**report):
        print(_TT_MARK + _tt_json.dumps(report))

    def terminal(res):
        if not isinstance(res, dict):
            return ""
        for flag, kind in (("run_complete", "run_complete"), ("done", "run_complete"),
                           ("level_completed", "level"), ("game_over", "game_over")):
            if res.get(flag):
                return kind
        return ""

    def judge(text, disp, eff):
        """The host's yes/no on a free-text expectation, or "unsure"."""
        if not callable(send) or not callable(recv):
            return "unsure"
        send({"type": "animation", "request": {"kind": _TT_JUDGE, "action": disp,
                                               "expect": str(text)[:300], "facts": _tt_facts(eff)}})
        reply = recv() or {}
        if reply.get("type") != "animation_result":
            return "unsure"
        answer = (reply.get("animation") or {}).get("answer")
        return answer if answer in ("yes", "no") else "unsure"

    def action(actions, expect=None):
        items = actions if isinstance(actions, list) else [actions]
        if expect is None or not items:
            res = raw_action(actions)
            done = int(res.get("executed_count") or (1 if res.get("executed") else 0)) if isinstance(res, dict) else 0
            emit(list=len(items), stated=0, played=done, first=_tt_display(items[0]) if items else "")
            return res
        items = items[:_TT_MAX_LIST]
        steps = _tt_steps(len(items), expect)
        report = {"list": len(items), "stated": sum(1 for e in steps if e is not None), "played": 0,
                  "rule": 0, "judged": 0, "judge_no": 0, "unsure": 0, "stop": "done",
                  "first": _tt_display(items[0])}
        res = {}
        for i, (a, exp) in enumerate(zip(items, steps)):
            before = _tt_rows(g.get("current_frame"))
            try:
                res = raw_action([a]) or {}
            except BaseException:
                report["stop"] = "refused"
                emit(**report)
                raise
            report["played"] += 1
            frame = g.get("current_frame")
            after = _tt_rows(frame)
            end = terminal(res)
            if end:
                report["stop"] = end
                emit(**report)
                return res
            if exp is None:
                continue
            eff = _tt_effect(before, after, res)
            disp = _tt_display(a)
            verdict, why = _tt_rule(exp, _tt_name(a), eff, after, frame)
            by = "rule"
            if verdict == "unsure":
                answer = judge(exp, disp, eff)
                report["judged"] += 1
                if answer == "no":
                    verdict, by, why = "fail", "judge", "a quick judge read the change as not what you said."
                    report["judge_no"] += 1
                else:
                    report["unsure"] += answer != "yes"
                    verdict = "pass"
            else:
                report["rule"] += 1
            if verdict == "fail":
                rest = [_tt_display(x) for x in items[i + 1:]]
                report.update(stop="expect", at=i + 1, by=by, next=rest[0] if rest else "")
                emit(**report)
                res["stop_reason"] = "expect_failed"
                res["stop_detail"] = why
                res["skipped_actions"] = rest
                raise ExpectationFailed(
                    f"EXPECTATION FAILED at step {i + 1} of {len(items)} ({disp}): you expected {exp!r}, "
                    f"but {why} What it did: {_tt_facts(eff)} The other {len(rest)} action(s) "
                    f"{rest!r} were NOT sent; no actions were spent on them. Re-read current_frame, say "
                    "which belief was wrong, and send the next list with an expectation per step.")
            if not eff["changed"] and callable(unstale):
                # an expected no-change must not leave the next step refused as stale
                unstale()
        emit(**report)
        return res

    action._tt = True
    g["action"] = action
    g["ExpectationFailed"] = ExpectationFailed
    return action
