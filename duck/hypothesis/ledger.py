# Hypothesis ledger (arc-agi-3 hypothesis-bet, docs/hypothesis.md). MIT-0.
#
# The first of three cells the hypothesis-* variants add after Franzen's
# customization cell; runner.py and cell.py follow it in the same namespace.
# Pure Python, no harness: the tests run it as it is.
#
# The bet: the player keeps an explicit, typed ledger per game of what it
# believes about the controls (rules) and about the goal of each level. Every
# entry is a hypothesis with a predicted outcome, a cheap test (a few actions)
# and an action budget. The outcome is judged by a typed question (did the
# frame change as predicted: yes, no or unsure), first by a rule over facts
# the harness already reports. A refuted hypothesis is dropped and stays
# dropped. A stuck level asks for a new hypothesis unlike the refuted ones
# instead of more of the same.
#
# Everything here is general: no named game, no memorised solution
# (RULES.md 3). The goal frames below are first principles about grid games,
# offered as starting points, never as answers.
import re as _re_hyp

HYP_YES, HYP_NO, HYP_UNSURE = "yes", "no", "unsure"

# What a test predicts, as a type the rule can judge. "free" is anything
# else, judged by a model question or by the main turn.
HYP_PREDICTIONS = ("level_completes", "game_over", "nothing_changes", "status_bar_changes",
                   "objects_change", "free")

# The order matters: the first pattern that matches wins, so "the block moves
# onto the marker and the level completes" reads as level_completes.
_HYP_PREDICT_PATTERNS = (
    ("level_completes", r"\blevel\b.*\b(complete|completes|completed|clear|clears|cleared|ends|advance|advances)"
                        r"|\bnext level\b|\bwin\b|\bwins\b|\bsolve[sd]?\b"),
    ("game_over", r"\bgame over\b|\b(die|dies|lose|loses|lost a life|life ends)\b"),
    ("nothing_changes", r"\bnothing\b|\bno change\b|\bunchanged\b|\bno effect\b"),
    ("status_bar_changes", r"\b(bar|counter|status|hud|meter|timer)\b"),
    ("objects_change", r"\b(move|moves|moved|appear|appears|disappear|disappears|turn|turns|open|opens|"
                       r"change|changes|rotate|rotates|grow|grows|shrink|shrinks|swap|swaps)\b"),
)

# First-principles goal frames, offered when a level is stuck. General kinds
# of goal, never a named public game.
HYP_GOAL_FRAMES = (
    "the goal is to reach or touch one distinct object",
    "the goal is to make part of the board match a pattern shown elsewhere on it",
    "the goal is to collect or clear every object of one kind",
    "the goal is to push or carry an object onto a marked cell",
    "the goal is to fill, empty or align a bar or counter",
    "the goal needs a key, switch or button first, which opens the way",
    "the order of the moves matters: the same moves in another order do something else",
)

HYP_DEFAULT_BUDGET = 12
HYP_MAX_BUDGET = 40
HYP_STATEMENT_CHARS = 160

_HYP_LINE = _re_hyp.compile(r"(?im)\bHYPOTHESIS\s*:\s*(.+)$")
_HYP_FIELD = _re_hyp.compile(r"(?i)\|\s*(TEST|PREDICT|BUDGET)\s*:\s*")


def hyp_norm(text):
    """A statement reduced for comparison: lower case, words only."""
    return " ".join(_re_hyp.findall(r"[a-z0-9]+", str(text).lower()))


def hyp_prediction_kind(text):
    low = str(text).lower()
    for kind, pattern in _HYP_PREDICT_PATTERNS:
        if _re_hyp.search(pattern, low):
            return kind
    return "free"


def hyp_parse(reply):
    """The hypotheses the player wrote in a reply, one per HYPOTHESIS line:
    `HYPOTHESIS: <statement> | TEST: <actions> | PREDICT: <outcome> | BUDGET: <n>`.
    TEST, PREDICT and BUDGET are optional. Returns dicts."""
    out = []
    for m in _HYP_LINE.finditer(reply or ""):
        parts = _HYP_FIELD.split(m.group(1))
        statement = parts[0].strip(" .|")
        fields = {parts[i].upper(): parts[i + 1].strip(" .|") for i in range(1, len(parts) - 1, 2)}
        if not statement or statement.startswith("<"):    # the format itself, echoed
            continue
        budget = HYP_DEFAULT_BUDGET
        digits = _re_hyp.search(r"\d+", fields.get("BUDGET", ""))
        if digits:
            budget = max(1, min(HYP_MAX_BUDGET, int(digits.group(0))))
        predict = fields.get("PREDICT", "")
        kind = "rule" if _re_hyp.match(r"(?i)\s*(rule|control)\b", statement) else "goal"
        statement = _re_hyp.sub(r"(?i)^\s*(rule|goal|control)\s*[:\-]\s*", "", statement)
        out.append({"statement": statement[:HYP_STATEMENT_CHARS], "test": fields.get("TEST", "")[:120],
                    "predict": predict[:120] or "the level completes", "budget": budget, "kind": kind})
    return out


def hyp_judge_rule(kind, flags, budget_left):
    """The rule's answer to "did the frame change as predicted?" from the
    harness's step flags, or HYP_UNSURE. `budget_left` is False once the
    test's actions are spent: a prediction that never came true is then a no."""
    done = budget_left <= 0
    lt, go = flags.get("level_transition"), flags.get("game_over")
    board, play = flags.get("board_changed"), flags.get("gameplay_changed")
    if kind == "level_completes":
        if lt:
            return HYP_YES
        return HYP_NO if (go or done) else HYP_UNSURE
    if kind == "game_over":
        if go:
            return HYP_YES
        return HYP_NO if (lt or done) else HYP_UNSURE
    if kind == "nothing_changes":
        if lt or go or play:
            return HYP_NO
        return HYP_YES if not board else HYP_UNSURE
    if kind == "status_bar_changes":
        if board and not play:
            return HYP_YES
        return HYP_NO if (done and not board) else HYP_UNSURE
    if kind == "objects_change":
        if play or lt:
            return HYP_YES
        return HYP_NO if not board else HYP_UNSURE
    # free: only a frame that did not change at all settles it
    if not board and not play and not lt and not go:
        return HYP_NO if done else HYP_UNSURE
    return HYP_UNSURE


class Hypothesis:
    """One ledger entry."""

    def __init__(self, hid, level, kind, statement, test, predict, budget, source):
        self.hid, self.level, self.kind = hid, level, kind
        self.statement, self.test, self.predict = statement, test, predict
        self.pkind = hyp_prediction_kind(predict)
        self.budget, self.spent, self.source = budget, 0, source
        self.status = "open"        # open, testing, confirmed, refuted, unsure
        self.evidence = []

    @property
    def closed(self):
        return self.status in ("confirmed", "refuted", "unsure")

    def line(self):
        test = f" Test: {self.test}." if self.test else ""
        return f"[{self.hid}] {self.statement}.{test} Predict: {self.predict}."


class HypLedger:
    """Every hypothesis of one game, with the controls' observed effects."""

    def __init__(self, game=""):
        self.game = game
        self.items = []
        self.controls = {}          # action -> "effect" | "no effect"
        self.level = None
        self.level_turns = 0        # turns on this level since the last verdict or level change
        self.lives_ended = 0
        self.lives_ended_testing = 0
        self.events = []            # (level, hid, verdict, statement), for the log

    # --- bookkeeping ---------------------------------------------------
    def on_level(self, level):
        """Move to `level`. Open hypotheses of the old level are left as they are."""
        if level != self.level:
            self.level, self.level_turns = level, 0
            for h in self.items:
                if h.status == "testing":
                    h.status = "open"
            return True
        return False

    def known(self, statement):
        n = hyp_norm(statement)
        return any(hyp_norm(h.statement) == n and h.level == self.level for h in self.items)

    def refuted_here(self):
        return [h for h in self.items if h.level == self.level and h.status in ("refuted", "unsure")]

    def confirmed_here(self):
        return [h for h in self.items if h.level == self.level and h.status == "confirmed"]

    def active(self):
        return next((h for h in self.items if h.status == "testing" and h.level == self.level), None)

    def open_here(self):
        return [h for h in self.items if h.status == "open" and h.level == self.level]

    def add(self, kind, statement, test, predict, budget, source):
        if not statement or self.known(statement):
            return None
        h = Hypothesis(f"H{len(self.items) + 1}", self.level, kind, statement, test, predict, budget, source)
        self.items.append(h)
        return h

    def add_parsed(self, parsed):
        return [h for h in (self.add(p["kind"], p["statement"], p["test"], p["predict"], p["budget"], "player")
                            for p in parsed) if h]

    def untried_frame(self):
        """The first goal frame not yet tried on this level."""
        for frame in HYP_GOAL_FRAMES:
            if not self.known(frame):
                return frame
        return None

    def start_next(self):
        """Make the oldest open hypothesis of this level the active test."""
        if self.active():
            return self.active()
        # the player's own designed tests go before the fallback goal frames
        pending = sorted(self.open_here(), key=lambda h: h.source == "frame")
        if pending:
            pending[0].status = "testing"
            return pending[0]
        return None

    def close(self, h, verdict, why):
        h.status = {HYP_YES: "confirmed", HYP_NO: "refuted"}.get(verdict, "unsure")
        h.evidence.append(why)
        self.level_turns = 0
        self.events.append((h.level, h.hid, h.status, h.statement))
        return h.status

    # --- controls ------------------------------------------------------
    def observe_controls(self, flags):
        """What the turn's executed actions say about each control. With the
        no-op guard on, a sequence stops at the first action that changed
        nothing, so the actions before it had an effect."""
        executed = [str(a).split("(")[0].strip() for a in (flags.get("executed_actions") or [])]
        stopped = bool(flags.get("no_op_stops"))
        if not executed:
            return
        effective = executed[:-1] if stopped else executed
        if flags.get("gameplay_changed") or flags.get("level_transition"):
            for a in effective:
                if a and a != "RESET":
                    self.controls[a] = "effect"
        elif len(set(executed)) == 1 and not flags.get("board_changed"):
            stopped = True
        last = executed[-1]
        if stopped and last != "RESET" and self.controls.get(last) != "effect":
            self.controls[last] = "no effect"

    def summary(self):
        """Totals for the log: tested, confirmed, refuted, unsure."""
        out = {"tested": 0, "confirmed": 0, "refuted": 0, "unsure": 0}
        for h in self.items:
            if h.closed:
                out["tested"] += 1
                out[h.status] += 1
        out["lives_ended"], out["lives_ended_testing"] = self.lives_ended, self.lives_ended_testing
        return out
