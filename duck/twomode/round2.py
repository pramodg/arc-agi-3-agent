# Two-mode player, round 2 settings (tm-2, tm-2-think;
# docs/two-mode-player.md, "Round 1"). MIT-0.
#
# Pasted after duck/twomode/player.py. Each change answers something round 1
# measured on the developed games, and each is a general rule:
#
# - The time box fired on games that had barely played. Games share one GPU,
#   so a game's clock runs while it waits for its turn: three games were
#   stopped at 19 minutes after 0-2 actions. Now the box also needs
#   TM_BOX_MIN_ACTIONS actions since the last clear, and its shares are those
#   of the landed stall stop (40%) and a little more with a rulebook.
# - The understand request's 6000 thinking tokens never ended in a written
#   answer: every answer came from the short thinking-off follow-up. A smaller
#   thinking budget gets the same answer for less GPU time.
# - Half the executor's hand-backs were the executor declining at once, and
#   most of the rest came at the first unmet expectation. It now hands back
#   after two unmet expectations in a row, and is told to decline only when
#   no allowed action fits the rulebook.
#
# Nothing here names or knows a game (RULES.md 3).
for _tm2_name in ("TM_BOX_NO_BOOK", "TM_EXEC_SYSTEM", "tm_install"):
    if _tm2_name not in globals():
        raise RuntimeError("duck/twomode/round2.py needs duck/twomode/player.py pasted before it")

TM_BOX_NO_BOOK = 0.40
TM_BOX_BOOK = 0.55
TM_BOX_MIN_ACTIONS = 80
TM_UNDERSTAND_MAX_TOKENS = 2000
TM_EXEC_MISSES = 2
TM_EXEC_SYSTEM = (
    "You play a turn-based grid game one step at a time from this rulebook, which an earlier "
    "player wrote after testing the game:\n{book}\n\n"
    "Each message shows the board now as hex digits (one per cell, row 0 at the top), the actions "
    "allowed, and your last steps. Pick the allowed action that brings the board closest to the "
    "rulebook's Win line while avoiding its Traps. Reply with exactly two lines:\n"
    "Action: <one of the allowed actions; MOUSE <row> <col> to click a cell; or HANDBACK>\n"
    "Expect: <move | change | none | level>\n"
    "move: an object moves whole (for UP/DOWN/LEFT/RIGHT, that way); change: something on the board "
    "changes; none: nothing changes; level: this step clears the level. Write HANDBACK only when no "
    "allowed action fits the rulebook at all; a guess the board can check is better. No other text.")
print(f"TM round 2: time box {round(100 * TM_BOX_NO_BOOK)}%/{round(100 * TM_BOX_BOOK)}% and "
      f"{TM_BOX_MIN_ACTIONS} actions since the last clear; understand {TM_UNDERSTAND_MAX_TOKENS} tokens; "
      f"executor hands back after {TM_EXEC_MISSES} unmet expectations", flush=True)
