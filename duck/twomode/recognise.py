# Two-mode player, stage 1: recognise a game or level as familiar or new
# (arc-agi-3 two-mode-player, docs/two-mode-player.md). MIT-0.
#
# The player has two modes. A familiar game is played at once from a rulebook
# by a cheap executor (stage 4). A new one is first understood from first
# principles (stage 2) and tested with a few moves (stage 3). This cell makes
# that call at the start of every game and every level, and says why.
#
# What counts as familiar, from general patterns only:
# - a new level of a game that already has an accepted rulebook: the rules
#   memory's own observation (docs/big-model-distill.md) is that a new level
#   usually keeps the last level's rules and adds one new mechanic, so the
#   executor starts from the rulebook and hands back at its first surprise;
# - a new game whose controls and measured tile size match a rulebook another
#   game of this run handed off. Rulebooks hold general rules only (stage 4
#   refuses coordinates, move lists and game ids), so one can cross games.
# Anything else is new. The run store lives in memory only, so every run
# starts empty: nothing is carried from one run to the next.
#
# Pure Python, no harness. Nothing here names or knows a game (RULES.md 3).
import threading as _threading_tm

TM_RUN_BOOKS = []          # [{"sig", "book", "level"}], newest last; this run only
TM_RUN_BOOKS_MAX = 40
TM_RUN_LOCK = _threading_tm.Lock()
TM_KEY_NAMES = ("UP", "DOWN", "LEFT", "RIGHT", "SPACE", "UNDO")
TM_ENGINE_TO_MODEL = {"ACTION1": "UP", "ACTION2": "DOWN", "ACTION3": "LEFT", "ACTION4": "RIGHT",
                      "ACTION5": "SPACE", "ACTION6": "MOUSE", "ACTION7": "UNDO"}


def tm_model_actions(valid_actions):
    """The game's actions in the model's own names (UP ... MOUSE), whichever
    names the harness passed."""
    out = []
    for a in valid_actions or ():
        name = str(a).strip().upper()
        name = TM_ENGINE_TO_MODEL.get(name, name)
        if name and name != "RESET" and name not in out:
            out.append(name)
    return out


def tm_signature(actions, tile):
    """A game's general shape: its keys, whether it takes clicks, and the
    tile size when the measurement is sure (else None). `tile` is the
    playbook's pb_tile answer, (size, x offset, y offset, share, sure)."""
    size = tile[0] if isinstance(tile, (tuple, list)) and len(tile) == 5 and tile[4] else None
    return {"keys": tuple(sorted(a for a in actions if a in TM_KEY_NAMES)),
            "click": "MOUSE" in actions, "tile": size}


def tm_store_book(sig, book, level):
    with TM_RUN_LOCK:
        TM_RUN_BOOKS.append({"sig": dict(sig), "book": dict(book), "level": level})
        del TM_RUN_BOOKS[:-TM_RUN_BOOKS_MAX]


def tm_store_clear():
    with TM_RUN_LOCK:
        TM_RUN_BOOKS.clear()


def tm_recognise(level, sig, game_book, store=None):
    """(verdict, reason, rulebook or None) for a game's first frame or a new
    level. `game_book` is this game's accepted rulebook, if any."""
    if game_book:
        return ("familiar", f"level {level}: this game's rulebook was accepted earlier "
                            "(a new level usually keeps the rules and adds one mechanic)", game_book)
    with TM_RUN_LOCK:
        books = list(TM_RUN_BOOKS if store is None else store)
    kind = "clicks" if sig["click"] and not sig["keys"] else (
        "keys and clicks" if sig["click"] else "keys")
    if sig["tile"] is None:
        return "new", f"no rulebook for this game yet, and the tile size is not sure ({kind})", None
    for entry in reversed(books):
        s = entry["sig"]
        if s["keys"] == sig["keys"] and s["click"] == sig["click"] and s["tile"] == sig["tile"]:
            return ("familiar", f"same controls ({kind}) and the same {sig['tile']}-pixel tile as a "
                                "rulebook handed off earlier in this run", entry["book"])
    return "new", f"no rulebook in this run matches its controls ({kind}) and {sig['tile']}-pixel tile", None
