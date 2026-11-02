# Two-mode player: rulebooks stay inside their own game (round 5 on;
# docs/two-mode-player.md, "Round 5"). MIT-0.
#
# Pasted after duck/twomode/player.py. An accepted rulebook is no longer put
# in the run store that recognise matches other games against, so no game
# starts from another game's rulebook (qwen-wins-every-public-game rule 3:
# nothing crosses games but general lessons). Within a game, a new level
# still starts from that game's own rulebook. In rounds 1-4 the cross-game
# match never fired, so this changes no measured behaviour.
#
# Nothing here names or knows a game (RULES.md 3).
for _tmg_name in ("tm_store_book", "tm_store_clear", "tm_accept"):
    if _tmg_name not in globals():
        raise RuntimeError("duck/twomode/game_only.py needs duck/twomode/player.py pasted before it")


def tm_store_book(sig, book, level):
    """Rulebooks are kept by their own game only."""
    return None


tm_store_clear()
print("TM rulebooks stay in their own game: no cross-game run store", flush=True)
