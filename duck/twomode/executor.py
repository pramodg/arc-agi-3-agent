# Two-mode player, stage 4b: the executor
# (arc-agi-3 two-mode-player, docs/two-mode-player.md). MIT-0.
#
# Once a rulebook is accepted (stage 4a, duck/twomode/rulebook.py), each turn
# of the game is one step by the executor instead of one thinking turn: the
# same served model, thinking off, about sixty output tokens. Its system
# prompt is the rulebook. Its message is the board now, the actions this game
# accepts and the last few steps with what each did. It answers with one
# action and what it expects that action to do:
#
#     Action: RIGHT            (or MOUSE <row> <col>, or HANDBACK)
#     Expect: move             (move | change | none | level)
#
# The step is played through the harness's own step_env and its expectation
# checked by the two-tier step checks (duck/twotier/sandbox.py, pasted before
# this cell: _tt_effect and _tt_rule), so a step counts as following the
# rulebook only when the board did what the executor said it would.
#
# It hands back to the thinking turns at its first surprise: an expectation
# the board did not meet, a reply it cannot read, HANDBACK, a step the harness
# refused, a lost life, several steps in a row that changed nothing, a level
# run past its step cap, or the level stalling on the game clock. A cleared
# level is not a surprise: it keeps playing, and the next level is checked
# from the same rulebook. The thinking turn after a hand-back is told what
# the executor played and why it stopped, and asked for a corrected rulebook.
#
# What it does differently from jev-mode-planned's quick reader (docs on that
# branch): that reader scored lettered options against a plan's listed steps
# and agreed with the thinking turn 27% of the time, so it played 2-4% of
# actions. This one is given rules, not steps, picks its own action from the
# board, and is stopped by a measured check, not by its own confidence.
#
# Pure Python apart from the agent calls passed in. Nothing names or knows a
# game (RULES.md 3).
import re as _re_tme

for _tme_name in ("_tt_effect", "_tt_rule", "tm_hex_rows", "tm_model_actions"):
    if _tme_name not in globals():
        raise RuntimeError("duck/twomode/executor.py needs duck/twotier/sandbox.py, "
                           "duck/twomode/recognise.py and duck/twomode/understand.py pasted before it")

TM_EXEC_MAX_TOKENS = 60
TM_EXEC_TIMEOUT_S = 60
TM_EXEC_RECENT = 6             # steps shown back to the executor
TM_EXEC_FLAT = 4               # steps in a row that changed nothing before a hand-back
TM_EXEC_LEVEL_CAP = 40         # executor steps on one level before a hand-back
TM_EXEC_STALL = 0.15           # stalled share of the game clock that ends executing
TM_EXEC_MISSES = 1             # failed expectations in a row before a hand-back
TM_EXEC_STALL_FROM_START = False  # True: count only the stall since this hand-off began
TM_EXEC_EXPECTS = ("move", "change", "none", "level")
TM_EXEC_SYSTEM = (
    "You play a turn-based grid game one step at a time from this rulebook, which an earlier "
    "player wrote after testing the game:\n{book}\n\n"
    "Each message shows the board now as hex digits (one per cell, row 0 at the top), the actions "
    "allowed, and your last steps. Reply with exactly two lines:\n"
    "Action: <one of the allowed actions; MOUSE <row> <col> to click a cell; or HANDBACK>\n"
    "Expect: <move | change | none | level>\n"
    "move: an object moves whole (for UP/DOWN/LEFT/RIGHT, that way); change: something on the board "
    "changes; none: nothing changes; level: this step clears the level. Write HANDBACK when the "
    "rulebook does not say what to do here. No other text.")
TM_EXEC_REASONS = {
    "expectation": "a step did not do what the executor expected",
    "parse": "the executor's reply could not be read",
    "handback": "the executor said the rulebook does not cover this board",
    "refused": "the harness refused a step",
    "life": "a life was lost",
    "flat": f"{TM_EXEC_FLAT} steps in a row changed nothing",
    "long": f"the level ran past {TM_EXEC_LEVEL_CAP} executor steps",
    "stall": "the level stalled on the game clock",
    "error": "the executor's request failed",
}


class TMExec:
    """One game's executor: what it played and how it went."""

    def __init__(self):
        self.recent = []           # [(label, expect, verdict, effect line)]
        self.flat = 0
        self.misses = 0            # failed expectations in a row
        self.stall0 = None         # the stalled share when this hand-off began
        self.level = None
        self.level_steps = 0
        self.run_steps = 0         # steps since the last hand-off
        self.run_held = 0          # ... whose expectation held
        self.run_levels = 0        # ... levels cleared
        self.labels = []           # labels since the last hand-off
        self.steps = 0             # this game, all hand-offs
        self.held = 0
        self.levels = 0
        self.handbacks = {}        # reason -> count

    def start(self):
        self.recent, self.flat, self.misses, self.labels = [], 0, 0, []
        self.stall0 = None
        self.run_steps = self.run_held = self.run_levels = 0


def tm_exec_parse(text, actions):
    """(step for step_env, label, expect) from the executor's reply,
    ("HANDBACK", "HANDBACK", None), or None when it cannot be read or names
    an action the game does not take."""
    text = str(text or "").rsplit("</think>", 1)[-1]
    m = _re_tme.search(r"(?im)^[ \t*>\-#]*action\s*:\s*\**\s*([A-Za-z0-9_]+)((?:[\s,]+\d+){0,2})", text)
    if not m:
        return None
    name = tm_model_actions([m.group(1)])
    name = name[0] if name else m.group(1).upper()
    if name == "HANDBACK":
        return "HANDBACK", "HANDBACK", None
    if name not in actions:
        return None
    e = _re_tme.search(r"(?im)^[ \t*>\-#]*expect\s*:\s*\**\s*([a-z]+)", text)
    expect = e.group(1).lower() if e and e.group(1).lower() in TM_EXEC_EXPECTS else None
    if expect is None:
        return None
    if name == "MOUSE":
        nums = _re_tme.findall(r"\d+", m.group(2) or "")
        if len(nums) != 2:
            return None
        row, col = int(nums[0]), int(nums[1])
        return {"action": "MOUSE", "row": row, "col": col}, f"MOUSE {row} {col}", expect
    return {"action": name}, name, expect


def tm_exec_prompt(rows, actions, ex, level):
    lines = [f"Level {level}. Allowed actions: {', '.join(actions)}"
             + (" (MOUSE row col clicks a cell)." if "MOUSE" in actions else "."),
             "Board now:", *rows]
    if ex.recent:
        lines += ["", "Your last steps (action, what you expected, whether it held, what happened):"]
        lines += [f"- {lab}: expected {exp}, {verdict}; {what}" for lab, exp, verdict, what in ex.recent]
    return "\n".join(lines)


def tm_effect_line(eff):
    if eff["level"]:
        return "the level cleared"
    if eff["over"]:
        return "the attempt ended"
    moved = ", ".join(f"'{ch}' {dr:+d} rows {dc:+d} cols" for ch, dr, dc in eff["moved"][:2])
    if moved:
        return f"moved {moved}"
    return f"{eff['cells']} cells changed" if eff["changed"] else "nothing changed"


def tm_exec_judge(expect, label, eff, after_rows):
    """("pass" | "fail" | "unsure", why) for one executor step."""
    name = label.split()[0]
    return _tt_rule(expect, name, eff, after_rows, after_rows)


def tm_exec_after(ex, verdict, eff, raw):
    """The hand-back reason after a played step, or None to keep going."""
    if not isinstance(raw, dict) or not raw.get("executed"):
        return "refused"
    if eff["over"] or raw.get("game_over"):
        return "life"
    if eff["level"]:
        return None
    ex.misses = ex.misses + 1 if verdict == "fail" else 0
    if ex.misses >= TM_EXEC_MISSES:
        return "expectation"
    ex.flat = 0 if eff["changed"] else ex.flat + 1
    if ex.flat >= TM_EXEC_FLAT:
        return "flat"
    if ex.level_steps >= TM_EXEC_LEVEL_CAP:
        return "long"
    return None


def tm_exec_note(ex, reason):
    """The hand-back line for the next thinking turn."""
    n = len(ex.labels)
    why = TM_EXEC_REASONS.get(reason, reason)
    if n:
        played = ", ".join(ex.labels[-12:])
        return (f"TWO-MODE: the executor played {n} step{'s' * (n != 1)} from your rulebook (last: {played}); "
                f"{ex.run_held} did what it expected and {ex.run_levels} level(s) cleared. It handed back "
                f"because {why}. Look at the board, test what surprised it, then write a corrected Rulebook block.")
    return (f"TWO-MODE: the executor played nothing and handed back because {why}. "
            "Test what the rulebook gets wrong, then write a corrected Rulebook block.")


def tm_exec_step(agent, ex, book_text, grid, level, actions, step_env, load_grid, stall_share=0.0):
    """Play one executor step. Returns (raw step result or None, hand-back
    reason or None, judged verdict). `load_grid()` gives the board after the
    step (the harness rewrites the runtime state after every action)."""
    if level != ex.level:
        ex.level, ex.level_steps, ex.flat = level, 0, 0
    if ex.stall0 is None:
        ex.stall0 = stall_share
    if stall_share - (ex.stall0 if TM_EXEC_STALL_FROM_START else 0.0) >= TM_EXEC_STALL:
        return None, "stall", None
    rows = tm_hex_rows(grid)
    messages = [{"role": "system", "content": TM_EXEC_SYSTEM.format(book=book_text)},
                {"role": "user", "content": tm_exec_prompt(rows, actions, ex, level)}]
    try:
        result = agent._chat_completion(messages, tools=None, max_tokens=TM_EXEC_MAX_TOKENS,
                                        enable_thinking=False, request_timeout_seconds=TM_EXEC_TIMEOUT_S)
    except Exception as exc:
        print(f"TM executor request error ({type(exc).__name__}: {exc})", flush=True)
        return None, "error", None
    try:
        agent._accumulate_usage_tokens(getattr(result, "usage", None), count_toward_turn=False)
    except Exception:
        pass
    content = (getattr(result, "message", None) or {}).get("content")
    if isinstance(content, list):
        content = "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
    pick = tm_exec_parse(content, actions)
    if pick is None:
        return None, "parse", None
    step, label, expect = pick
    if step == "HANDBACK":
        return None, "handback", None
    raw = step_env({"actions": [step]})
    after = tm_hex_rows(load_grid() or grid)
    res = raw if isinstance(raw, dict) else {}
    eff = _tt_effect(rows, after, res)
    verdict = "refused"
    if res.get("executed"):
        ex.steps += 1
        ex.run_steps += 1
        ex.level_steps += 1
        ex.labels.append(label)
        verdict, _why = tm_exec_judge(expect, label, eff, after)
        if verdict != "fail":
            ex.held += 1
            ex.run_held += 1
        if eff["level"]:
            ex.levels += 1
            ex.run_levels += 1
        ex.recent.append((label, expect, {"pass": "held", "fail": "did not hold"}.get(verdict, "unclear"),
                          tm_effect_line(eff)))
        del ex.recent[:-TM_EXEC_RECENT]
    return raw, tm_exec_after(ex, verdict, eff, raw), verdict
