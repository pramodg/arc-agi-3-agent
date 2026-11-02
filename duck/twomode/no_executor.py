# Two-mode player without the executor (tm-2-think; docs/two-mode-player.md).
# MIT-0.
#
# Pasted after duck/twomode/round2.py. An accepted rulebook is not handed to
# the thinking-off executor: it stays in every turn message and the thinking
# turns keep playing by it. Round 1's executor played 0-3% of each game's
# actions and cleared no level, so this variant measures what recognise,
# understand, test and the time box are worth without it.
#
# Nothing here names or knows a game (RULES.md 3).
if "TM_EXECUTE" not in globals():
    raise RuntimeError("duck/twomode/no_executor.py needs duck/twomode/player.py pasted before it")

TM_EXECUTE = False
print("TM executor off: an accepted rulebook stays in the turn message", flush=True)
