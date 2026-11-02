# Two-mode player, stage 4a: the rulebook hand-off
# (arc-agi-3 two-mode-player, docs/two-mode-player.md). MIT-0.
#
# Once the thinking turns have tested their guesses, the player writes a
# rulebook and the harness hands it to the cheap executor (stage 4b,
# duck/twomode/executor.py). The rulebook extends the rules memory's note
# (duck/bigmodel/rules_memory.py: tile, controls, objects, win condition,
# traps) and holds GENERAL rules only. The executor sees the board at every
# step, so it never needs a position or a route written down.
#
# The hand-off refuses a rulebook that carries a solution instead of rules
# (constraint qwen-wins-every-public-game rule 3, RULES.md 3):
# - coordinates: "(12, 30)", "row 3", "row three", "x = 12", "at 12,30",
#   "at 12 30", a click with numbers;
# - an action sequence: a key with a repeat count ("RIGHT x3", "3 times",
#   "twice"), keys chained by an arrow or "then", three or more keys in a row
#   with one repeated, three or more keys after a verb ("go UP, LEFT, DOWN"),
#   or a field named as a plan, route or move list. A control mapped to a
#   direction ("ACTION1 UP", "ACTION1 -> UP") is a control, not a step, so
#   such pairs are read as one control first;
# - a game id: any four-character word mixing letters and digits, with or
#   without an eight-hex-digit version, or the name the harness gave this
#   game. The shape covers every public id without naming one.
# A refused rulebook is not handed off; the next turn is told why.
#
# Pure Python, no harness. Nothing here names or knows a game.
import re as _re_tmr

TM_RULE_FIELDS = ("Tile", "Controls", "Objects", "Win", "Traps")
TM_RULE_NEEDED = ("Controls", "Win")
TM_RULE_FIELD_CHARS = 300
TM_RULE_CHARS = 1200
TM_RULE_HEADER = "Rulebook"
_TMR_KEY = r"(?:UP|DOWN|LEFT|RIGHT|SPACE|UNDO|RESET|MOUSE|CLICK|ACTION[1-7])"
_TMR_NUMBER = (r"(?:\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen"
               r"|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty)")
_TMR_MAPPED = r"\bACTION[1-7]\s*(?:[=:]|->|→|=>|is)?\s*(?=(?:UP|DOWN|LEFT|RIGHT|SPACE|UNDO|CLICK|MOUSE)\b)"
_TMR_COORDS = (
    (r"\(\s*\d+\s*,\s*\d+\s*\)", "a coordinate pair"),
    (r"\b(?:row|rows|col|cols|column|columns)\s*(?:number\s*)?[=:#]?\s*" + _TMR_NUMBER + r"\b",
     "a row or column number"),
    (r"\b[xy]\s*[=:]\s*\d+", "an x or y position"),
    (r"\bat\s+\d+\s*[,\s]\s*\d+", "a position"),
    (r"\b(?:MOUSE|CLICK|ACTION6)\s*\(?\s*\d+", "a click with a position"),
)
_TMR_SEQUENCES = (
    (r"\b" + _TMR_KEY + r"\s*(?:x|×|\*)\s*\d+\b", "a key with a repeat count"),
    (r"\b\d+\s*(?:x|×)\s*" + _TMR_KEY + r"\b", "a key with a repeat count"),
    (r"\b" + _TMR_KEY + r"\s+(?:twice|thrice|" + _TMR_NUMBER + r"\s+times)\b", "a key with a repeat count"),
    (r"\b" + _TMR_KEY + r"\s*(?:->|→|=>|,?\s*then)\s*" + _TMR_KEY + r"\b", "keys chained into a sequence"),
    (r"\b(?:go|press|play|do|input|enter|type|hit|tap)\s*:?\s+" + _TMR_KEY + r"(?:(?:\s*,\s*|\s+)" + _TMR_KEY
     + r"){2,}\b(?!\s*,?\s*(?:or|and)\b)", "keys listed in an order to press"),
)
_TMR_PLAN_FIELD = r"(?im)^[ \t>*\-#]*\**(?:plan|route|moves|sequence|solution|steps|path)\**\s*:"
_TMR_GAME_ID = r"\b(?!\d+px\b)(?!\d+x\d+\b)(?=[a-z0-9]*\d)(?=[a-z0-9]*[a-z])[a-z0-9]{4}\b(?:-[0-9a-f]{8}\b)?"


def _tmr_field(body, key):
    m = _re_tmr.search(r"(?im)^[ \t>*\-#]*\**" + key + r"\**\s*:\s*(.*)$", body)
    if not m:
        return ""
    value = m.group(1).strip(" *")
    if not value or value.startswith("<") or value in ("...", "..", "?"):
        return ""
    return value[:TM_RULE_FIELD_CHARS]


def tm_parse_rulebook(text):
    """{"tile", "controls", "objects", "win", "traps", "raw"} from the last
    `Rulebook:` block holding Controls and Win, or None. `raw` is the block as
    written, which the checks read, so nothing hides outside the fields."""
    for m in reversed(list(_re_tmr.finditer(r"(?i)\**" + TM_RULE_HEADER + r"\**\s*:", text or ""))):
        rest = text[m.end():]
        if rest.strip().lower().startswith("not yet"):
            continue
        body = _re_tmr.split(r"\n[ \t]*\n(?![ \t>*\-#]*\**(?:" + "|".join(TM_RULE_FIELDS) + r"|plan|route|moves"
                             r"|sequence|solution|steps|path)\**\s*:)", rest.lstrip(" \t\n"), maxsplit=1)[0]
        book = {k.lower(): _tmr_field(body, k) for k in TM_RULE_FIELDS}
        if all(book[k.lower()] for k in TM_RULE_NEEDED):
            book["raw"] = body.strip()[:2 * TM_RULE_CHARS]
            return book
    return None


def _tmr_sequence_run(text):
    """True when three or more keys follow each other with only commas or
    spaces between them and one of them repeats: an ordered list of moves,
    not a list of controls."""
    for m in _re_tmr.finditer(r"(?:\b" + _TMR_KEY + r"\b[\s,]*){3,}", text):
        keys = _re_tmr.findall(_TMR_KEY, m.group(0))
        if len(keys) != len(set(keys)):
            return True
    return False


def tm_rulebook_problems(book, game_names=()):
    """Why `book` is not a general rulebook, as short reasons; [] when it is."""
    if not book:
        return ["no Rulebook block with Controls and Win"]
    raw = book.get("raw") or tm_rulebook_text(book)
    keyed = _re_tmr.sub(_TMR_MAPPED, "", raw, flags=_re_tmr.I)   # "ACTION1 UP" is one control
    out = []
    for pattern, why in _TMR_COORDS:
        if _re_tmr.search(pattern, raw, _re_tmr.I):
            out.append(f"it carries {why}")
            break
    for pattern, why in _TMR_SEQUENCES:
        if _re_tmr.search(pattern, keyed, _re_tmr.I):
            out.append(f"it carries {why}")
            break
    else:
        if _tmr_sequence_run(keyed.upper()):
            out.append("it carries an action sequence")
    if _re_tmr.search(_TMR_PLAN_FIELD, raw):
        out.append("it has a plan or move-list field")
    names = [str(n).lower() for n in game_names if n and len(str(n)) >= 3]
    low = raw.lower()
    if _re_tmr.search(_TMR_GAME_ID, low) or any(n in low for n in names):
        out.append("it names a game")
    if len(tm_rulebook_text(book)) > TM_RULE_CHARS:
        out.append(f"it is longer than {TM_RULE_CHARS} characters")
    return out


def tm_rulebook_text(book):
    """The rulebook as the executor and the run store keep it."""
    return "\n".join(f"{k}: {book[k.lower()]}" for k in TM_RULE_FIELDS if book.get(k.lower()))


TM_HANDOFF_ASK = (
    "When your tests have settled the rules, write this block in your reply, before your tool call:\n"
    "Rulebook:\n"
    "Tile: <the tile size in pixels>\n"
    "Controls: <what each control does, as measured>\n"
    "Objects: <what each object or colour is and does>\n"
    "Win: <the win condition exactly as seen>\n"
    "Traps: <what costs moves or lives, and what to avoid>\n"
    "General rules only: no coordinates, no list of moves, no game name. A fast executor then plays "
    "from it one step at a time, looking at the board each step, and hands back to you at its first "
    "surprise.")
