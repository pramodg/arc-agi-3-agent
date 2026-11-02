# Two-mode player: the wiring (arc-agi-3 two-mode-player,
# docs/two-mode-player.md). MIT-0.
#
# Recognise, understand, test, hand off, time-box. The last of the tm-1
# cells; everything it calls is pasted before it:
#   duck/r3/hook.py, duck/r3/lives.py, duck/bigmodel/playbook.py (its tile
#   measurement only: its page section is dropped below),
#   duck/staged/questions.py, duck/r4/stall.py, duck/hypothesis/ledger.py,
#   duck/twotier/sandbox.py, then duck/twomode/recognise.py, understand.py,
#   rulebook.py and executor.py.
#
# Per game, kept on the agent:
# 1. Recognise (stage 1). At the first frame and at every new level, familiar
#    or new, with the reason.
# 2. Understand (stage 2). For a new game or level, one request with no
#    tools, thinking on, for the written understanding and two to four
#    hypotheses. Its answer is shown in every later turn message.
# 3. Test (stage 3). The harness's own thinking turns play, with the
#    hypotheses in the hypothesis ledger: each turn's step flags judge the
#    active one by the ledger's own rule (hyp_judge_rule), and the player may
#    close one itself with `RESULT H1: yes`. The turn message asks for a
#    Rulebook block once the rules are settled; after a few turns with none,
#    one no-tools request, thinking off, asks for it outright.
# 4. Hand off (stage 4). An accepted rulebook (general rules only) moves the
#    game to the executor (duck/twomode/executor.py), which plays turn by
#    turn until its first surprise and then hands back, with a note, to the
#    thinking turns. A hand-back reopens stage 3 on that level.
# 5. Time box (stage 5). Registered as an action of the stalled-level clock
#    (duck/r4/stall.py, as duck/r4/stop.py does): a game ends once a share of
#    its time limit has passed since its last clear, a smaller share when it
#    never got a rulebook, and the harness moves on to the next game.
#
# Each stage prints one `TM <stage>` line per game or level saying what it
# decided; `TM game` sums the game up when it ends. The round reads in
# docs/two-mode-player.md are taken from these lines.
#
# Nothing here names or targets a game, and nothing is carried between runs:
# the rulebooks other games handed off live in memory for this run only and
# hold no positions, moves or game ids (RULES.md 3).
import re as _re_tmp

import inference.agent.tool_agent as _ta_tm
import inference.framework.solver as _solver_tm

for _tmp_name in ("r3_register", "R3_SECTIONS", "_r3_load_state", "r4_register", "r4_game_name",
                  "r4_game_seconds", "r4_levels", "HypLedger", "hyp_judge_rule", "pb_tile",
                  "tm_recognise", "tm_parse_understanding", "tm_parse_rulebook", "tm_exec_step"):
    if _tmp_name not in globals():
        raise RuntimeError("duck/twomode/player.py needs the r3, r4, hypothesis, playbook, two-tier and "
                           "other twomode cells pasted before it")

# The playbook is pasted for its tile measurement; its pages are not this
# variant's (bm-playbook measured them, +0.9 games, inside the noise).
R3_SECTIONS[:] = [s for s in R3_SECTIONS if s[0] != "playbook"]

TM_UNDERSTAND_MAX_TOKENS = 6000
TM_UNDERSTAND_FOLLOWUP_TOKENS = 700
TM_UNDERSTAND_TIMEOUT_S = 600
TM_UNDERSTAND_PER_GAME = 3
TM_ASK_AFTER = 5               # test turns on a level before the rulebook is asked for outright
TM_ASK_AFTER_CONFIRMED = 2     # ... or this many once a hypothesis is confirmed
TM_ASK_GAP = 3                 # turns between asks, at least
TM_ASK_PER_LEVEL = 2
TM_ASK_MAX_TOKENS = 700
TM_ASK_TIMEOUT_S = 120
TM_ASK_CONTEXT = 2500          # characters of each recent reply the ask is shown
TM_HANDOFFS_PER_LEVEL = 4
TM_BOX_NO_BOOK = 0.30          # stalled share of the game's limit that ends a game with no rulebook
TM_BOX_BOOK = 0.45             # ... and one that has a rulebook
TM_BOX_MIN_ACTIONS = 0         # actions since the last clear before the box may fire
TM_EXECUTE = True              # False: an accepted rulebook stays in the turn message, no executor
TM_ASK_NOT_YET = "If the rules are not yet settled enough, write `Rulebook: not yet`."
TM_UNDERSTAND_IN_TURN = False  # True: understand is asked in the turn message, tools offered
TM_IN_TURN_TRIES = 3           # turns a level's in-turn question is shown before it is dropped
TM_IN_TURN_LINE = (
    "Stage answers first: before your tool call, write a block starting `Stage answers:` with one line "
    "each, Problem:, Parts:, Connections:, Win: (the literal condition that ends the level, as the board "
    "would show it), then two to four HYPOTHESIS lines (HYPOTHESIS: ... | TEST: ... | PREDICT: ... | "
    "BUDGET: n). Then make your move.")
TM_SEEN = 400
TM_HEADER = "=== TWO-MODE PLAYER ==="
TM_RESULT = r"(?im)^[\s*\-#>]*RESULT\s+(H\d+)\s*:\s*(yes|no|unsure)\b"
TM_ASK_SYSTEM = (
    "You have been playing a turn-based grid game and testing guesses about its rules. Write down "
    "what you now know as a rulebook a fast executor can play from, looking at the board each step. "
    "General rules only: no coordinates, no list of moves, no game name. Answer in text only.")


class TMState:
    def __init__(self, session=None):
        self.session = session
        self.game = None
        self.level = None
        self.mode = "new"          # new, test, execute
        self.why = ""
        self.sig = None
        self.u = None              # the written understanding
        self.understands = 0
        self.ledger = HypLedger("")
        self.book = None           # the accepted rulebook
        self.book_text = ""
        self.note = ""
        self.ex = TMExec()
        self.level_turns = 0
        self.asks_level = 0
        self.last_ask = -99
        self.handoffs_level = 0
        self.handoffs = {"accepted": 0, "rejected": 0, "asked": 0}
        self.recognised = []       # [(level, verdict)]
        self.seen = {}
        self.judged = None         # the step summary already judged
        self.replies = []          # the last few reply texts, for the ask
        self.thinking = 0
        self.turns = 0
        self.yielded = False
        self.timebox = None
        self.shown_ask = None
        self.want_u = None         # the level whose understanding is asked in the turn
        self.u_tries = 0


def _tm_state(agent):
    """This game's state on the agent; a change of runtime dir is a new game
    (a state begun before the harness set the dir is kept, as _sq_state does)."""
    session = getattr(agent, "_session_runtime_dir", None)
    st = agent.__dict__.get("_tm_state")
    if st is None or (st.session is not None and st.session != session):
        st = TMState(session)
        agent.__dict__["_tm_state"] = st
    st.session = session
    return st


def _tm_game(agent):
    return agent.__dict__.get("_tm_game") or getattr(agent, "_diag_name", "?")


def _tm_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(p.get("text", "") for p in value
                         if isinstance(p, dict) and isinstance(p.get("text"), str))
    return ""


def _tm_reply_text(msg):
    """A model message as one text: its content, then its thinking, then its
    tool-call arguments (a rulebook written in any of them counts)."""
    content = _tm_text(msg.get("content"))
    thinking = "\n".join(t for t in (_tm_text(msg.get(k)) for k in ("reasoning_content", "reasoning")) if t)
    calls = [c for c in msg.get("tool_calls") or [] if isinstance(c, dict)]
    tools = "\n".join(str((c.get("function") or {}).get("arguments", "")) for c in calls)
    return content, thinking, tools


def _tm_new_replies(agent, st):
    out = []
    for msg in getattr(agent, "_history_messages", None) or []:
        if not (isinstance(msg, dict) and msg.get("role") == "assistant"):
            continue
        parts = _tm_reply_text(msg)
        key = hash(parts)
        if key in st.seen:
            continue
        st.seen[key] = None
        out.append(parts)
    while len(st.seen) > TM_SEEN:
        del st.seen[next(iter(st.seen))]
    return out


def _tm_chat(agent, messages, max_tokens, thinking, timeout):
    """One no-tools request; (content, thinking text). Errors give ("", "")."""
    try:
        result = agent._chat_completion(messages, tools=None, max_tokens=max_tokens,
                                        enable_thinking=thinking, request_timeout_seconds=timeout)
    except Exception as exc:
        print(f"TM request error ({type(exc).__name__}: {exc})", flush=True)
        return "", ""
    try:
        agent._accumulate_usage_tokens(getattr(result, "usage", None), count_toward_turn=False)
    except Exception:
        pass
    msg = getattr(result, "message", None) or {}
    content, reasoning, _tools = _tm_reply_text(msg)
    if "</think>" in content:
        head, content = content.rsplit("</think>", 1)
        reasoning = reasoning + "\n" + head
    return content, reasoning


def tm_understand(agent, st, grid, actions, level, tile, hint=""):
    """Stage 2: the written understanding, parsed, or None. The content is
    read first, then the thinking; failing both, one short follow-up, thinking
    off, asks for the block alone."""
    st.understands += 1
    user = tm_understand_prompt(grid, actions, level, tile, hint)
    messages = [{"role": "system", "content": TM_UNDERSTAND_SYSTEM}, {"role": "user", "content": user}]
    content, reasoning = _tm_chat(agent, messages, TM_UNDERSTAND_MAX_TOKENS, True, TM_UNDERSTAND_TIMEOUT_S)
    u, source = tm_parse_understanding(content), "content"
    if u is None:
        u, source = tm_parse_understanding(reasoning), "thinking"
    if u is None:
        follow = messages + [{"role": "assistant", "content": (content or reasoning)[-4000:] or "(no answer)"},
                             {"role": "user", "content": "Write the block now: Problem, Parts, Connections, Win, "
                                                         "then the HYPOTHESIS lines. Nothing else."}]
        content2, _r = _tm_chat(agent, follow, TM_UNDERSTAND_FOLLOWUP_TOKENS, False, TM_ASK_TIMEOUT_S)
        u, source = tm_parse_understanding(content2), "follow-up"
    added = st.ledger.add_parsed(u["hyps"]) if u else []
    st.ledger.start_next()
    if u:
        st.u = u
    print(f"TM understand game={_tm_game(agent)} L{level} source={source if u else 'none'} "
          f"hyps={len(added)} win={(u or {}).get('win', '')[:160]!r} "
          f"problem={(u or {}).get('problem', '')[:160]!r}", flush=True)
    return u


def tm_recognise_turn(agent, st, frame, actions):
    """Stage 1 at a new game or level, and the mode it leads to."""
    level = int(getattr(frame, "level", 0) or 0)
    grid = [list(r) for r in frame.grid]
    first = st.level is None
    st.level, st.level_turns, st.asks_level, st.handoffs_level = level, 0, 0, 0
    st.last_ask = -99
    st.ledger.on_level(level)
    tile = None
    try:
        tile = pb_tile(grid)
    except Exception:
        pass
    st.sig = tm_signature(actions, tile)
    verdict, reason, book = tm_recognise(level, st.sig, st.book)
    st.recognised.append((level, verdict))
    print(f"TM recognise game={_tm_game(agent)} L{level} {verdict}: {reason}", flush=True)
    st.why = f"level {level} is {verdict}: {reason}"
    if verdict == "familiar" and not TM_EXECUTE:
        st.book, st.book_text, st.mode = book, tm_rulebook_text(book), "test"
        return
    if verdict == "familiar":
        if st.mode != "execute":
            st.ex.start()
        st.book, st.book_text, st.mode = book, tm_rulebook_text(book), "execute"
        return
    st.mode = "test"
    if st.understands < TM_UNDERSTAND_PER_GAME and TM_UNDERSTAND_IN_TURN:
        st.understands += 1
        st.want_u, st.u_tries = level, 0
    elif st.understands < TM_UNDERSTAND_PER_GAME:
        tm_understand(agent, st, grid, actions, level, tile)
    else:
        print(f"TM understand game={_tm_game(agent)} L{level} skipped: {TM_UNDERSTAND_PER_GAME} "
              f"understand requests used{' (first level)' if first else ''}", flush=True)


def tm_accept(agent, st, book, how):
    """Stage 4a: check a rulebook and hand it off, or say why not."""
    game = _tm_game(agent)
    names = [agent.__dict__.get("_tm_game"), getattr(agent, "_diag_name", None)]
    problems = tm_rulebook_problems(book, names)
    if problems:
        st.handoffs["rejected"] += 1
        st.note = ("TWO-MODE: your Rulebook was not handed off because " + "; ".join(problems)
                   + ". Write it again with general rules only.")
        print(f"TM handoff game={game} L{st.level} rejected ({how}): {'; '.join(problems)}", flush=True)
        return False
    st.handoffs["accepted"] += 1
    st.book, st.book_text = book, tm_rulebook_text(book)
    tm_store_book(st.sig or {"keys": (), "click": False, "tile": None}, book, st.level)
    print(f"TM handoff game={game} L{st.level} accepted ({how}) after {st.level_turns} test turn(s): "
          f"win={book.get('win', '')[:120]!r}", flush=True)
    if not TM_EXECUTE:
        st.note = "TWO-MODE: your Rulebook was accepted. Keep playing by it, and correct it when the board disagrees."
    elif st.handoffs_level < TM_HANDOFFS_PER_LEVEL:
        st.mode = "execute"
        st.ex.start()
    else:
        print(f"TM handoff game={game} L{st.level} held: {TM_HANDOFFS_PER_LEVEL} hand-backs on this level",
              flush=True)
    return True


def tm_read_replies(agent, st):
    """Stage 3's bookkeeping from the thinking turns' replies: new hypotheses,
    the player's own RESULT lines, and a Rulebook block."""
    book = None
    for content, thinking, tools in _tm_new_replies(agent, st):
        st.replies = (st.replies + [(content, thinking, tools)])[-3:]
        if st.want_u is not None:
            tm_read_understanding(agent, st, (content, thinking, tools))
        st.ledger.add_parsed(hyp_parse(content))
        for hid, verdict in _re_tmp.findall(TM_RESULT, content):
            h = next((x for x in st.ledger.items if x.hid == hid.upper() and not x.closed), None)
            if h is not None:
                status = st.ledger.close(h, verdict.lower(), "the player's RESULT line")
                print(f"TM test game={_tm_game(agent)} L{h.level} {h.hid} {status} by player: {h.statement}",
                      flush=True)
        for text in (content, thinking, tools):
            got = tm_parse_rulebook(text)
            if got:
                book = got
                break
    return book


def tm_read_understanding(agent, st, texts):
    """The in-turn understanding from one reply (content, then thinking,
    then tool arguments), recorded as stage 2's answer."""
    for source, text in zip(("turn", "turn-thinking", "turn-tools"), texts):
        u = tm_parse_understanding(text)
        if u:
            added = st.ledger.add_parsed(u["hyps"])
            st.ledger.start_next()
            st.u, st.want_u = u, None
            print(f"TM understand game={_tm_game(agent)} L{st.level} source={source} hyps={len(added)} "
                  f"win={u.get('win', '')[:160]!r} problem={u.get('problem', '')[:160]!r}", flush=True)
            return u
    return None


def tm_judge(agent, st):
    """The active hypothesis judged from the last thinking turn's step flags."""
    summary = getattr(agent, "_last_step_summary", None) or {}
    key = (summary.get("start_action_num"), summary.get("end_action_num"), summary.get("level"))
    if not summary or summary.get("stale") or key == st.judged:
        return
    st.judged = key
    h = st.ledger.active() or st.ledger.start_next()
    if h is None:
        return
    h.spent += len(summary.get("executed_actions") or [])
    verdict = hyp_judge_rule(h.pkind, summary, h.budget - h.spent)
    if verdict != HYP_UNSURE:
        status = st.ledger.close(h, verdict, "the step flags")
        print(f"TM test game={_tm_game(agent)} L{h.level} {h.hid} {status} by rule after {h.spent}/{h.budget} "
              f"actions: {h.statement}", flush=True)
        st.ledger.start_next()


def tm_ask(agent, st):
    """One no-tools request, thinking off, for the Rulebook block."""
    st.asks_level += 1
    st.last_ask = st.level_turns
    st.handoffs["asked"] += 1
    known = tm_understanding_lines(st.u)
    for h in st.ledger.items:
        if h.level == st.level and h.closed:
            known.append(f"{h.hid} {h.status}: {h.statement}")
    recent = []
    for content, thinking, _tools in st.replies[-2:]:
        recent.append((content or thinking)[-TM_ASK_CONTEXT:])
    user = "\n".join(["What you wrote and found so far:", *known, "", "Your last notes:", *recent, "",
                      TM_HANDOFF_ASK, TM_ASK_NOT_YET])
    content, reasoning = _tm_chat(agent, [{"role": "system", "content": TM_ASK_SYSTEM},
                                          {"role": "user", "content": user}],
                                  TM_ASK_MAX_TOKENS, False, TM_ASK_TIMEOUT_S)
    book = tm_parse_rulebook(content) or tm_parse_rulebook(reasoning)
    if book is None:
        print(f"TM handoff game={_tm_game(agent)} L{st.level} asked: no rulebook yet", flush=True)
        return
    tm_accept(agent, st, book, "asked")


def tm_section(agent, view):
    st = agent.__dict__.get("_tm_state")
    if st is None or st.mode == "new":
        return []
    lines = [TM_HEADER, f"Mode: {'executor' if st.mode == 'execute' else 'test'} ({st.why})"]
    if st.want_u is not None and st.want_u == st.level:
        if st.u_tries < TM_IN_TURN_TRIES:
            st.u_tries += 1
            lines.append(TM_IN_TURN_LINE)
        else:
            print(f"TM understand game={_tm_game(agent)} L{st.level} source=none: not answered in "
                  f"{TM_IN_TURN_TRIES} turns", flush=True)
            st.want_u = None
    if st.u:
        lines += ["Your understanding:", *tm_understanding_lines(st.u)]
    if st.book_text and not TM_EXECUTE:
        lines += ["Your rulebook:", st.book_text]
    here = [h for h in st.ledger.items if h.level == st.level]
    if here:
        lines.append("Hypotheses on this level (finish one with a line `RESULT H1: yes|no|unsure`):")
        lines += [f"- {h.line()} [{h.status}]" for h in here[-6:]]
    if st.note:
        lines.append(st.note)
        st.note = ""
    if st.mode == "test":
        if st.shown_ask != st.level:
            st.shown_ask = st.level
            lines.append(TM_HANDOFF_ASK)
        else:
            lines.append("When the rules are settled, write the Rulebook block (Tile, Controls, Objects, Win, "
                         "Traps; general rules only).")
    return lines


def _tm_stall_share(agent):
    session = agent.__dict__.get("_tm_session")
    stall = getattr(session, "__dict__", {}).get("_r4_stall") if session is not None else None
    return float(getattr(stall, "share", 0.0) or 0.0)


def tm_execute(agent, st, state_path, valid_actions, step_env):
    """Stage 4b inside analyze: one executor step as the turn, or None to
    hand back and think instead."""
    frame, _entries = _r3_load_state(state_path)
    if frame is None:
        return None
    level = int(getattr(frame, "level", 0) or 0)
    actions = tm_model_actions(valid_actions)

    def load_grid():
        after, _e = _r3_load_state(state_path)
        return [list(r) for r in after.grid] if after is not None else None

    agent._step_env_callback = step_env
    norm = getattr(_ta_tm, "_normalize_valid_actions", lambda v: list(v or []))
    agent._current_valid_actions = norm(valid_actions)
    raw, reason, verdict = tm_exec_step(agent, st.ex, st.book_text, [list(r) for r in frame.grid], level,
                                        actions, step_env, load_grid, _tm_stall_share(agent))
    if isinstance(raw, dict):
        try:
            compact = agent._compact_action_result(raw)
            guard = getattr(agent, "_noop_repeat_guard", None)
            if guard is not None:
                agent._record_guard_observations(guard, raw, compact)
            if isinstance(raw.get("valid_actions"), list):
                agent._current_valid_actions = norm(raw["valid_actions"])
            agent._last_action_call_result = dict(compact)
            if compact.get("executed"):
                agent._last_step_summary = agent._summarize_step_sequence([compact])
                updater = getattr(agent, "_update_summarized_knowledge_from_step_summary", None)
                if callable(updater):
                    updater()
        except Exception as exc:
            print(f"TM bookkeeping error ({type(exc).__name__}: {exc})", flush=True)
        if raw.get("level_completed"):
            print(f"TM executor game={_tm_game(agent)} L{level} cleared the level after {st.ex.level_steps} "
                  f"step(s) on it", flush=True)
    if reason:
        ex = st.ex
        ex.handbacks[reason] = ex.handbacks.get(reason, 0) + 1
        st.handoffs_level += 1
        st.note = tm_exec_note(ex, reason)
        st.mode, st.why = "test", f"the executor handed back on level {level}: {TM_EXEC_REASONS.get(reason, reason)}"
        st.level_turns = 0
        print(f"TM executor game={_tm_game(agent)} L{level} handback={reason} steps={ex.run_steps} "
              f"held={ex.run_held} cleared={ex.run_levels} last={verdict}", flush=True)
        ex.start()
    if isinstance(raw, dict):
        return _ta_tm.AnalyzerTurnResult(step_executed=bool(raw.get("executed")))
    return None


def tm_install(tool_agent_module, solver_module):
    """Wrap analyze, the chat call and the game loop. Returns the originals."""
    cls = tool_agent_module.ToolAgent
    for attr in ("analyze", "_chat_completion", "_compact_action_result", "_summarize_step_sequence"):
        if not callable(getattr(cls, attr, None)):
            raise RuntimeError(f"ToolAgent has no {attr}; the two-mode player cannot attach")
    analyze, chat = cls.analyze, cls._chat_completion
    if getattr(analyze, "_tm_wrapped", False):
        return analyze, chat

    def _tm_chat_completion(self, *args, **kwargs):
        if kwargs.get("enable_thinking") is not False:
            messages = kwargs.get("messages", args[0] if args else None)
            check = getattr(tool_agent_module, "_message_is_summary", None)
            try:
                summary = bool(callable(check) and messages and check(messages[-1]))
            except Exception:
                summary = False
            if not summary:
                _tm_state(self).thinking += 1
        return chat(self, *args, **kwargs)

    def _tm_analyze(self, state_path, action_num, valid_actions=None, step_env=None, *args, **kwargs):
        st = _tm_state(self)
        if not st.yielded:
            try:
                frame, entries = _r3_load_state(state_path)
                level = int(getattr(frame, "level", 0) or 0) if frame is not None else None
                if frame is not None and level != st.level:
                    tm_recognise_turn(self, st, frame, tm_model_actions(valid_actions))
                if st.mode == "test":
                    tm_judge(self, st)
                    book = tm_read_replies(self, st)
                    if book is not None:
                        tm_accept(self, st, book, "written")
                    elif st.asks_level < TM_ASK_PER_LEVEL and st.level_turns - st.last_ask >= TM_ASK_GAP and (
                            st.level_turns >= TM_ASK_AFTER
                            or (st.ledger.confirmed_here() and st.level_turns >= TM_ASK_AFTER_CONFIRMED)):
                        tm_ask(self, st)
                stop = kwargs.get("should_stop")
                if st.mode == "execute" and step_env is not None and not (callable(stop) and stop()):
                    got = tm_execute(self, st, state_path, valid_actions, step_env)
                    if got is not None:
                        return got
            except Exception as exc:
                print(f"TM error (thinking turn instead): {type(exc).__name__}: {exc}", flush=True)
                if st.mode == "execute":
                    st.mode = "test"
            st.turns += 1
            st.level_turns += 1
        result = analyze(self, state_path, action_num, valid_actions, step_env, *args, **kwargs)
        st.yielded = bool(getattr(result, "yielded_control", False))
        return result

    _tm_analyze._tm_wrapped = True
    cls.analyze, cls._chat_completion = _tm_analyze, _tm_chat_completion

    session_cls = getattr(solver_module, "_HarnessGameSession", None)
    play = getattr(session_cls, "play", None)
    if callable(play) and not getattr(play, "_tm_wrapped", False):
        def _tm_play(self, *args, **kwargs):
            agent = getattr(self, "analyzer", None)
            if agent is not None:
                agent.__dict__["_tm_game"] = str(r4_game_name(self))
                agent.__dict__["_tm_session"] = self
            try:
                return play(self, *args, **kwargs)
            finally:
                try:
                    tm_game_line(self, agent)
                except Exception as exc:
                    print(f"TM game line error ({type(exc).__name__}: {exc})", flush=True)

        _tm_play._tm_wrapped = True
        session_cls.play = _tm_play
    return analyze, chat


def tm_game_line(session, agent):
    st = agent.__dict__.get("_tm_state") if agent is not None else None
    if st is None:
        return
    actions = getattr(session, "action_count", None)
    ex = st.ex
    share = f"{round(100 * ex.steps / actions)}%" if isinstance(actions, int) and actions > 0 else "?"
    recog = ",".join(f"L{lv}:{v[0]}" for lv, v in st.recognised) or "-"
    backs = ",".join(f"{k}:{v}" for k, v in sorted(ex.handbacks.items())) or "-"
    print(f"TM game game={_tm_game(agent)} levels={r4_levels(session)} actions={actions} "
          f"executor_steps={ex.steps} executor_held={ex.held} executor_levels={ex.levels} executor_share={share} "
          f"thinking_calls={st.thinking} turns={st.turns} understands={st.understands} "
          f"handoffs={st.handoffs['accepted']}/{st.handoffs['accepted'] + st.handoffs['rejected']} "
          f"asks={st.handoffs['asked']} handbacks={backs} recognised={recog} hyps={st.ledger.summary()} "
          f"timebox={st.timebox or '-'} t={round(r4_game_seconds(session) / 60, 1)}m", flush=True)


def tm_timebox(session, stall):
    """Stage 5, as an action of the stalled-level clock."""
    agent = getattr(session, "analyzer", None)
    st = agent.__dict__.get("_tm_state") if agent is not None else None
    limit = TM_BOX_BOOK if st is not None and st.book else TM_BOX_NO_BOOK
    actions = getattr(session, "action_count", None)
    actions = actions if isinstance(actions, int) else 0
    mark = session.__dict__.setdefault("_tm_box_mark", [stall.levels, actions])
    if mark[0] != stall.levels:
        mark[:] = [stall.levels, actions]   # a clear: count actions again
    if stall.share < limit or actions - mark[1] < TM_BOX_MIN_ACTIONS:
        return None
    if not stall.stopped:
        stall.stopped = True
        if st is not None:
            st.timebox = f"{round(100 * stall.share)}%@{round(r4_game_seconds(session) / 60, 1)}m"
        print(f"TM timebox game={r4_game_name(session)} levels={stall.levels} stalled={round(100 * stall.share)}% "
              f"limit={round(100 * limit)}% rulebook={'yes' if st is not None and st.book else 'no'} "
              f"t={round(r4_game_seconds(session) / 60, 1)}m", flush=True)
    return True


r3_register("twomode", tm_section)
r4_register("twomode-box", tm_timebox)
tm_install(_ta_tm, _solver_tm)
print(f"TM two-mode player on: time box {round(100 * TM_BOX_NO_BOOK)}%/{round(100 * TM_BOX_BOOK)}% "
      f"of the game's time with no clear", flush=True)
