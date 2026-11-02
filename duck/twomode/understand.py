# Two-mode player, stage 2: understand a new game from first principles
# (arc-agi-3 two-mode-player, docs/two-mode-player.md). MIT-0.
#
# For a game or level that stage 1 called new, the harness asks Qwen, thinking
# on, to write its understanding down before it moves: what the problem is,
# what the parts are (objects, colours, controls, tile size), how they
# connect, and the literal win condition, then two to four hypotheses, each
# with the few moves that test it. The hypotheses go into the hypothesis
# ledger (duck/hypothesis/ledger.py, pasted before this cell) in its own
# HYPOTHESIS line format, and stage 3 records each one's verdict there.
#
# The question is sent as its own request with no tools offered. Question
# learning round 2 (docs/question-learning.md) found that the model's first
# reply in a turn is a tool call with no text, so questions asked inside the
# turn went unanswered; a request without tools can only be answered in text.
# The opening questions come from the stage question bank
# (duck/staged/questions.py, pasted before this cell) and the tile line from
# the playbook's measurement (duck/bigmodel/playbook.py), so nothing new is
# asked that those do not already ask.
#
# Pure Python here; duck/twomode/player.py makes the request. Nothing names or
# knows a game (RULES.md 3).
import re as _re_tmu

for _tmu_name in ("SQ_QUESTIONS", "hyp_parse", "pb_tile_line"):
    if _tmu_name not in globals():
        raise RuntimeError("duck/twomode/understand.py needs duck/staged/questions.py, "
                           "duck/hypothesis/ledger.py and duck/bigmodel/playbook.py pasted before it")

TM_HEX = "0123456789abcdef"
TM_UNDERSTAND_FIELDS = ("Problem", "Parts", "Connections", "Win")
TM_FIELD_CHARS = 400
TM_UNDERSTAND_SYSTEM = (
    "You are about to play a turn-based grid game you have never seen. It has no instructions. "
    "Before any move, think it through from first principles, the way a strong engineer meets a new "
    "system: what is the problem, what are its parts, how do they connect, and what does success look "
    "like. Then name the few cheapest experiments that would confirm or refute your guesses. "
    "You cannot act in this reply; answer in text only.")


def tm_hex_rows(grid):
    """The board as hex rows, one character per cell (colours 0-15 as 0-f)."""
    return ["".join(TM_HEX[int(v) & 15] for v in row) for row in (grid or ())]


def tm_understand_prompt(grid, actions, level, tile, rulebook_hint=""):
    """The user message of the understand request."""
    opening = SQ_QUESTIONS["opening"][1]
    lines = [f"Level {level}. Actions this game accepts: {', '.join(actions) or 'unknown'}"
             + (" (MOUSE clicks a cell: MOUSE row col)." if "MOUSE" in actions else "."),
             pb_tile_line(tile),
             "Board now, one hex digit per cell, row 0 at the top:",
             *tm_hex_rows(grid), ""]
    if rulebook_hint:
        lines += ["A rulebook from earlier play did not hold here. It said:", rulebook_hint, ""]
    lines += ["Questions to settle first (from the opening stage):"]
    lines += [f"- {k}: {q}" for k, q in opening]
    lines += ["",
              "Answer with this block, one line each, nothing invented that the board does not show:",
              "Problem: <what this level asks of the player, in one sentence>",
              "Parts: <the objects and colours, the controls, the tile size, any bar or counter>",
              "Connections: <how the parts act on each other: which control moves what, what touches what>",
              "Win: <the literal condition that would end the level, as you would see it on the board>",
              "Then two to four hypotheses, one per line, each tested by a few moves:",
              "HYPOTHESIS: <a rule or the goal> | TEST: <the few actions> | PREDICT: <what the frame will show> "
              "| BUDGET: <n actions>"]
    return "\n".join(lines)


def _tmu_field(text, key):
    """The text after the last `Key:` line, up to the next field or blank line."""
    # A line may copy a literal `Key:` before the field (`Key: Win: ...`, as
    # question learning round 2 saw); that prefix is skipped.
    hits = list(_re_tmu.finditer(r"(?im)^[ \t>*\-#]*(?:[`*]*key[`*]*\s*:\s*)?\**" + key + r"\**\s*:\s*(.*)$",
                                 text or ""))
    for m in reversed(hits):
        value = m.group(1).strip(" *")
        if value and not value.startswith("<") and value not in ("...", "..", "?"):
            return value[:TM_FIELD_CHARS]
    return ""


def tm_parse_understanding(text):
    """{"problem", "parts", "connections", "win", "hyps"} from a reply, or
    None when it names no win condition (the one field stage 3 cannot work
    without)."""
    out = {k.lower(): _tmu_field(text, k) for k in TM_UNDERSTAND_FIELDS}
    if not out["win"]:
        return None
    out["hyps"] = hyp_parse(text or "")
    return out


def tm_understanding_lines(u):
    """The understanding as the turn message shows it."""
    if not u:
        return []
    return [f"{k}: {u[k.lower()]}" for k in TM_UNDERSTAND_FIELDS if u.get(k.lower())]
