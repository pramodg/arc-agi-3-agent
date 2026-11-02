# Rules, not replays, in solved-level memory (arc-agi-3 big-model-distill). MIT-0.
#
# Our own cell. It changes what duck/solved_level_memory.py (V2, lalalia9's
# memory, pasted into the customization cell) keeps for a cleared level,
# without editing that file, so every landed variant keeps its sha256. The
# builder puts it after the customization cell, gated.
#
# Why (docs/big-model-distill.md, deep-dive section 5 item 2): the memory pins
# the winning attempt's last 30 actions and 900 characters of reasoning. Those
# are a replay of a different level and cannot transfer. Every strong-model win
# kept a short structured note instead: the tile size and offset, what each
# control does, what each object or colour is, the win condition as literally
# seen, and the traps. A session that lost its context with no such note
# re-learned a level at about three and a half times the actions.
#
# How: the memory looks up `_slm_block` and `_SLM_RULE_CHARS` by name when it
# runs, so rebinding them here changes the pinned block. Its rule request is a
# fixed sentence appended to the turn message; the user-prompt builder is
# wrapped to swap that sentence for the rules-note request. The block is still
# written only when the conversation is drained anyway, so the cache is
# unchanged. Any error leaves the turn as the memory wrote it.
import inference.agent.tool_agent as _ta_rm

for _rm_name in ("_slm_block", "_slm_find_rule", "_re_slm", "_SLM_HEADER", "_SLM_FOOTER"):
    if _rm_name not in globals():
        raise RuntimeError("duck/bigmodel/rules_memory.py needs duck/solved_level_memory.py loaded first")

_SLM_RULE_CHARS = 1000      # five short labelled lines; the memory's own cap was 600
RM_OLD_ASK = ("that states the goal, what each control did and the plan that won (at most 5 lines). "
              "It is kept for the rest of the game.")
RM_NEW_ASK = ("and under it a rules note, not a replay, one short line each:\n"
              "  Tile: the tile size and offset in pixels\n"
              "  Controls: what each action did, measured\n"
              "  Objects: what each object or colour is and does\n"
              "  Win: the win condition exactly as you saw it happen\n"
              "  Traps: what cost actions or lives, and what to avoid\n"
              "It is kept for the rest of the game, and later levels start from it.")
RM_FOOTER = ("A new level usually keeps these rules and adds one new mechanic. Confirm a rule with one "
             "probe before you rely on it, and look first for what is new.")


def _rm_block(levels):
    """The solved-levels block: the rules note per level, and no replay."""
    if not levels:
        return ""
    lines = [_SLM_HEADER]
    for rec in levels:
        lines.append(f"Level {rec['level']} - cleared after {rec['n_actions']} actions.")
        rule = rec.get("rule")
        lines.append("  Rules note: " + (rule if rule else "not written"))
    lines.append(RM_FOOTER)
    lines.append(_SLM_FOOTER)
    return "\n".join(lines)


def _rm_find_rule(text, level):
    """The rules note after `Rule for level N:`: its own line plus up to five
    more, up to the first blank line. The memory's parser kept only the first
    line when it was long, which cut a note begun on the heading's line."""
    m = _re_slm.search(r"Rule for level\s*%d\s*:[ \t]*" % int(level), text or "", _re_slm.I)
    if not m:
        return None
    lines = text[m.end():].split("\n")
    out = [lines[0].strip()] if lines[0].strip() else []
    for line in lines[1:7]:
        if not line.strip():
            if out:
                break
            continue
        out.append(line.strip())
    rule = " | ".join(out)[:_SLM_RULE_CHARS]
    return rule if len(rule) >= 20 else None


_slm_block = _rm_block
_slm_find_rule = _rm_find_rule

_rm_original_user_prompt = _ta_rm.ToolAgent._build_user_prompt


def _rm_user_prompt(self, *args, **kwargs):
    prompt = _rm_original_user_prompt(self, *args, **kwargs)
    try:
        if RM_OLD_ASK in prompt:
            prompt = prompt.replace(RM_OLD_ASK, RM_NEW_ASK)
    except Exception:
        pass
    return prompt


_ta_rm.ToolAgent._build_user_prompt = _rm_user_prompt
print("RULES_MEMORY on: solved levels keep a rules note, not the last actions", flush=True)
