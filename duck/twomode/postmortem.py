# Two-mode player: understand asks the post-mortem's questions
# (tm-5-ask, tm-5-both; docs/two-mode-player.md, "Round 5"). MIT-0.
#
# Pasted after duck/twomode/understand.py and its round cells. The Opus-Qwen
# post-mortem (docs/opus-qwen-postmortem.md) found the same missing model in
# most lost games: Qwen never wrote down which object it was, what that
# object carried, what ended a level or a life, or what drained as it acted.
# Understand's answer block now has a line for each, after Win, so the
# answer shown in every later turn message names them too. Only the Win line
# is still required for an answer to count.
#
# These are general questions about any game, not a game's answer: nothing
# here names a game, place or move (RULES.md 3).
for _tmq_name in ("TM_UNDERSTAND_FIELDS", "tm_understand_prompt", "tm_parse_understanding",
                  "TM_IN_TURN_LINE"):
    if _tmq_name not in globals():
        raise RuntimeError("duck/twomode/postmortem.py needs duck/twomode/understand.py and player.py "
                           "pasted before it")

TM_POSTMORTEM = (
    ("Me", "<which object your actions control, and how you can tell>"),
    ("Carry", "<what that object holds or shows: a colour, a shape, a facing, an item, a mark in a side "
              "panel; or none seen>"),
    ("Ends", "<what ends the level or a life besides winning: touching something, a counter running out, "
             "a reset>"),
    ("Drains", "<what goes down or fills up with each action: a bar, a row of marks, a timer; or none seen>"),
)
TM_UNDERSTAND_FIELDS = tuple(TM_UNDERSTAND_FIELDS) + tuple(k for k, _ in TM_POSTMORTEM
                                                           if k not in TM_UNDERSTAND_FIELDS)
_tm_prompt_before_postmortem = tm_understand_prompt


def tm_understand_prompt(grid, actions, level, tile, rulebook_hint=""):
    """The understand request with the post-mortem's lines after Win."""
    lines = _tm_prompt_before_postmortem(grid, actions, level, tile, rulebook_hint).split("\n")
    at = next((i + 1 for i, line in enumerate(lines) if line.startswith("Win: <")), len(lines))
    return "\n".join(lines[:at] + [f"{k}: {q}" for k, q in TM_POSTMORTEM] + lines[at:])


TM_IN_TURN_LINE = TM_IN_TURN_LINE.replace(
    "as the board would show it), ",
    "as the board would show it), " + ", ".join(f"{k}:" for k, _ in TM_POSTMORTEM)
    + " (which object is you, what it carries, what ends a level or life, what drains each action), ")
print(f"TM understand asks the post-mortem's questions: {', '.join(k for k, _ in TM_POSTMORTEM)}", flush=True)
