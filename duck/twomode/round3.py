# Two-mode player, round 3 settings (tm-3, tm-3-tools, tm-3-think;
# docs/two-mode-player.md, "Round 2"). MIT-0.
#
# Pasted after duck/twomode/round2.py. Each change answers something round 2
# measured on the developed games, and each is a general rule:
#
# - About a third of the executor's hand-backs were "stall" with no step
#   played. The executor's stall check read the level's stalled share of the
#   whole game clock, so a level that had already spent that share on its
#   thinking turns handed back before the executor moved. Now it counts only
#   the stall since the hand-off began.
# - Asked for a rulebook, the model wrote "not yet" about thirty times a pass
#   and half the games never reached the executor. The executor checks every
#   step against the board and hands back at its first surprise, so a guessed
#   rulebook costs a step or two. The ask now wants the best current guess.
#
# Nothing here names or knows a game (RULES.md 3).
for _tm3_name in ("TM_ASK_NOT_YET", "TM_EXEC_STALL_FROM_START", "TM_BOX_MIN_ACTIONS", "tm_install"):
    if _tm3_name not in globals():
        raise RuntimeError("duck/twomode/round3.py needs duck/twomode/player.py and "
                           "duck/twomode/round2.py pasted before it")

TM_EXEC_STALL_FROM_START = True
TM_ASK_NOT_YET = ("Write your best current guess even if some rules are unsure: the executor checks every "
                  "step against the board and hands back at the first surprise, and you then correct it. "
                  "Mark an unsure rule with (unsure).")
print("TM round 3: the executor's stall counts from its hand-off; the rulebook ask wants a best guess", flush=True)
