# Two-mode player: understand looks past "reach the goal" (tm-2-wins;
# docs/two-mode-player.md, "Round 1"). MIT-0.
#
# Pasted after duck/twomode/round2.py. In round 1 the understand answer named
# "move the player to the goal" as the win on 12 of 13 developed games, while
# the rulebooks the player wrote after testing named other kinds: objects
# pushed onto marks, bars extended onto targets, pockets filled, pieces
# reflected onto outlines. The system prompt now lists the common kinds of win
# condition and asks for hypotheses of at least two different kinds, so a
# test can tell them apart before the player settles on one.
#
# A general framework, not a game's answer: it names no game, place or move
# (RULES.md 3).
if "TM_UNDERSTAND_SYSTEM" not in globals():
    raise RuntimeError("duck/twomode/win_kinds.py needs duck/twomode/understand.py pasted before it")

TM_WIN_KINDS = (
    "reach: the player gets to a cell or region",
    "place: objects pushed or carried onto matching marks",
    "match: a shape, colour or pattern made equal to a reference shown elsewhere on the board",
    "fill or clear: every cell of some kind filled, covered, emptied or removed",
    "connect or extend: a path, line or bar joined or grown until it meets its target",
    "set: switches, toggles or a dial put into one particular state",
)
TM_UNDERSTAND_SYSTEM = TM_UNDERSTAND_SYSTEM + (
    " Reaching a goal is only one kind of win. Others are common: "
    + "; ".join(TM_WIN_KINDS) + ". A small separate figure, a bar, or a row of marks often shows the "
    "target or the progress. Write hypotheses of at least two different kinds, and make the first test "
    "the one that tells them apart.")
print(f"TM win kinds: understand asks for hypotheses of at least two of {len(TM_WIN_KINDS)} kinds", flush=True)
