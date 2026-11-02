# Round-3 turn hook (arc-agi-3 bets-round-3, docs/bets-round-3.md). MIT-0.
#
# The shared wiring for the round-3 cells (duck/r3/lives.py, duck/r3/clock.py),
# pasted before them, after the customization cell. Each of those cells
# registers one section with r3_register(name, fn). Once per turn, before the
# harness's analyze runs, this cell reads the game's runtime state (the current
# frame and the whole action history, the same file the player's python tool
# reads), asks every section for its lines, and keeps the text. The harness's
# user-prompt builder then gets that text appended at its end, like the Jev and
# ledger cells: the prompt is only appended to, so the cached prefix of the
# conversation is untouched. A section's error drops that section for the turn
# and leaves the rest of the turn unchanged. No model call is made here.
import time as _time_r3

import inference.agent.tool_agent as _ta_r3
from inference.agent.runtime_state import load_runtime_state as _r3_load_state

R3_SECTIONS = []


def r3_register(name, fn):
    """Add or replace section `name`: fn(agent, view) -> list of prompt lines."""
    R3_SECTIONS[:] = [s for s in R3_SECTIONS if s[0] != name] + [(name, fn)]


class R3State:
    """Per-game state, kept on the agent. Sections keep their own in `extra`."""

    def __init__(self, session):
        self.session = session
        self.started = _time_r3.monotonic()
        self.extra = {}


def r3_state(agent):
    session = getattr(agent, "_session_runtime_dir", None)
    st = agent.__dict__.get("_r3_state")
    if st is None or st.session != session:
        st = R3State(session)
        agent.__dict__["_r3_state"] = st
    return st


def r3_game_seconds(agent, st):
    """Seconds since the game started: the session clock the harness ends the
    game by, once a step has reported it, else this cell's own clock."""
    elapsed = getattr(agent, "_game_elapsed_seconds", None)
    if isinstance(elapsed, (int, float)):
        return float(elapsed)
    return _time_r3.monotonic() - st.started


def r3_game_budget_seconds():
    """The per-game time limit the benchmark was given, or None."""
    solver = getattr(globals().get("bm"), "solver", None)
    limit = getattr(solver, "max_runtime_s_per_game", None)
    return float(limit) if isinstance(limit, (int, float)) and limit > 0 else None


def r3_view(agent, state_path):
    st = r3_state(agent)
    frame, entries = _r3_load_state(state_path)
    level = getattr(frame, "level", None)
    if not isinstance(level, int):
        level = (getattr(agent, "_last_step_summary", None) or {}).get("level")
    return {"frame": frame, "entries": list(entries or []), "level": level if isinstance(level, int) else 1,
            "now": r3_game_seconds(agent, st), "budget": r3_game_budget_seconds(), "state": st}


def r3_suffix(agent, state_path):
    if not R3_SECTIONS:
        return ""
    view = r3_view(agent, state_path)
    blocks = []
    for name, fn in R3_SECTIONS:
        try:
            lines = fn(agent, view)
        except Exception as exc:
            print(f"R3 {name} error (section dropped this turn): {exc}", flush=True)
            continue
        if lines:
            blocks.append("\n".join(lines))
    return "".join("\n\n" + b for b in blocks)


def r3_install(tool_agent_module):
    """Wrap analyze and the user-prompt builder. Returns the originals for tests."""
    cls = tool_agent_module.ToolAgent
    for attr in ("analyze", "_build_user_prompt"):
        if not callable(getattr(cls, attr, None)):
            raise RuntimeError(f"ToolAgent has no {attr}; the round-3 hook cannot attach")
    analyze, user_prompt = cls.analyze, cls._build_user_prompt
    if getattr(analyze, "_r3_wrapped", False):
        return analyze, user_prompt

    def _r3_analyze(self, state_path, *args, **kwargs):
        self.__dict__["_r3_suffix"] = ""
        try:
            self.__dict__["_r3_suffix"] = r3_suffix(self, state_path)
        except Exception as exc:
            print(f"R3 error (turn unchanged): {exc}", flush=True)
        return analyze(self, state_path, *args, **kwargs)

    def _r3_user_prompt(self, *args, **kwargs):
        return user_prompt(self, *args, **kwargs) + self.__dict__.get("_r3_suffix", "")

    _r3_analyze._r3_wrapped = True
    cls.analyze, cls._build_user_prompt = _r3_analyze, _r3_user_prompt
    return analyze, user_prompt


r3_install(_ta_r3)
print("R3 hook on", flush=True)
