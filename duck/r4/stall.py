# Stalled-level clock (arc-agi-3 bets-round-4, docs/bets-round-4.md). MIT-0.
#
# The shared wiring for the round-4 cells (duck/r4/stop.py, duck/r4/short.py),
# pasted before them, after the customization cell. Each of those cells
# registers one action with r4_register(name, fn).
#
# A level is STALLED when the game's own clock has run a share of the game's
# time limit since the last level was cleared (or since the game started, if
# none has been). The clock is the session's, the one max_runtime_s_per_game
# ends the game by, so a game waiting for a server slot is ageing here as it
# is there. The harness asks every game's session should_stop() at each loop
# boundary, many times a turn. This cell wraps should_stop: it reads the
# session's levels completed and its clock, works out the stalled share, and
# hands it to every registered action. An action returns True to end the game
# now, the same exit the time limit takes, or None to let it go on. An
# action's error is printed and ignored for that call.
#
# Nothing here adds a model call or a prompt line, and nothing knows any
# particular game.
import time as _time_r4

import inference.framework.solver as _solver_r4

R4_ACTIONS = []
R4_GAME_S_DEFAULT = 63 * 60       # the loop's per-game limit, when the solver names none


def r4_register(name, fn):
    """Add or replace action `name`: fn(session, stall) -> True to stop, else None."""
    R4_ACTIONS[:] = [a for a in R4_ACTIONS if a[0] != name] + [(name, fn)]


class R4Stall:
    """Where one game is: levels cleared, and when the last one was."""

    def __init__(self, now):
        self.levels = None
        self.mark = now           # game clock (s) of the last clear, or of the start
        self.share = 0.0          # the stalled time as a share of the game's limit
        self.stopped = False


def r4_game_seconds(session):
    """Seconds on the game's own clock (started_at is time.monotonic())."""
    started = getattr(session, "started_at", None)
    if not isinstance(started, (int, float)):
        started = session.__dict__.setdefault("_r4_started", _time_r4.monotonic())
    return max(0.0, _time_r4.monotonic() - float(started))


def r4_budget_seconds(session):
    limit = getattr(getattr(session, "solver", None), "max_runtime_s_per_game", None)
    return float(limit) if isinstance(limit, (int, float)) and limit > 0 else float(R4_GAME_S_DEFAULT)


def r4_game_name(session):
    run = getattr(getattr(session, "game", None), "game_run", None)
    return getattr(run, "game_id", None) or getattr(session, "game_index", "?")


def r4_levels(session):
    state = getattr(getattr(session, "game", None), "current_state", None)
    try:
        return int(getattr(state, "levels_completed"))
    except (TypeError, ValueError):
        return None


def r4_advance(stall, levels, now, budget):
    """Move `stall` to (`levels` cleared, `now` seconds) and return its share."""
    if levels is not None and levels != stall.levels:
        if stall.levels is not None:
            stall.mark = now      # a clear: the stall clock starts again
        stall.levels = levels
    stall.share = max(0.0, now - stall.mark) / budget
    return stall.share


def r4_check(session):
    """Run the registered actions once; True means end the game now."""
    now = r4_game_seconds(session)
    stall = session.__dict__.get("_r4_stall")
    if stall is None:
        stall = session.__dict__["_r4_stall"] = R4Stall(0.0)
    r4_advance(stall, r4_levels(session), now, r4_budget_seconds(session))
    stop = False
    for name, fn in R4_ACTIONS:
        try:
            stop = bool(fn(session, stall)) or stop
        except Exception as exc:
            print(f"R4 {name} error (ignored this call): {exc}", flush=True)
    return stop


def r4_install(solver_module):
    """Wrap _HarnessGameSession.should_stop. Returns the original for tests."""
    cls = getattr(solver_module, "_HarnessGameSession", None)
    for attr in ("should_stop", "token_limit_reached"):
        if not callable(getattr(cls, attr, None)):
            raise RuntimeError(f"_HarnessGameSession has no {attr}; the round-4 stall clock cannot attach")
    should_stop = cls.should_stop
    if getattr(should_stop, "_r4_wrapped", False):
        return should_stop

    def _r4_should_stop(self, *args, **kwargs):
        if should_stop(self, *args, **kwargs):
            return True
        try:
            return r4_check(self)
        except Exception as exc:
            print(f"R4 error (game goes on): {exc}", flush=True)
            return False

    _r4_should_stop._r4_wrapped = True
    cls.should_stop = _r4_should_stop
    return should_stop


r4_install(_solver_r4)
print("R4 stall clock on", flush=True)
