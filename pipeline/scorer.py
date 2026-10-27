"""RHAE, the competition's score (docs/scoring.md, docs/requirements.md).

Relative Human Action Efficiency, as https://docs.arcprize.org/methodology.md
states it and as the arc-agi toolkit computes it (arc_agi/scorecard.py,
EnvironmentScoreCalculator):

- a completed level scores min(1.15, (human_actions / ai_actions) ** 2); an
  uncompleted level scores 0;
- a game scores the average of its level scores weighted by the 1-indexed
  level number, capped at the weight share of the levels it completed;
- the total is the plain mean over games.

Scores here are fractions (1.0 = 100%); the toolkit reports percent. Pure
standard library, so it runs on the box's python3 as well as on 3.12.

What counts as an action follows the toolkit's scorecard, so our count and
the toolkit's agree step for step (`count_actions`):

- every ACTION1-7 that returns a frame counts;
- a level RESET counts;
- a full RESET starts a new play and does not count. Competition mode allows
  one play per game, so the evaluator turns every later reset into a level
  reset (pipeline/evaluate.py);
- a step that returns no frame (anything sent after GAME_OVER or WIN except
  RESET) changed nothing and does not count.
"""
LEVEL_CAP = 1.15
RESET = 0  # GameAction.RESET's id


def upper_median(human_actions):
    """The human baseline for one level: the upper median, by fewest actions,
    of the first-time players who completed it. With four players it is the
    third best; with five it is the third best too."""
    ranked = sorted(human_actions)
    if not ranked:
        raise ValueError("no human completed this level")
    return ranked[len(ranked) // 2]


def level_score(human_actions, ai_actions):
    """One completed level: min(1.15, (human / ai) ** 2)."""
    if ai_actions <= 0:
        return 0.0  # the toolkit scores a zero-action completion as 0
    return min(LEVEL_CAP, (human_actions / ai_actions) ** 2)


def game_score(baselines, level_actions, levels_completed):
    """One game. `baselines[i]` is level i+1's human actions,
    `level_actions[i]` the agent's actions on it, and the first
    `levels_completed` levels are the completed ones. Returns
    `(score, per_level_scores)`."""
    scores = []
    for i, human in enumerate(baselines):
        done = i < levels_completed
        ai = level_actions[i] if i < len(level_actions) else 0
        scores.append(level_score(human, ai) if done else 0.0)
    weights = range(1, len(baselines) + 1)
    total_weight = sum(weights)
    if not total_weight:
        return 0.0, scores
    mean = sum(s * w for s, w in zip(scores, weights)) / total_weight
    cap = sum(w for s, w in zip(scores, weights) if s > 0) / total_weight
    return min(mean, cap), scores


def total_score(game_scores):
    """The plain mean over games; 0.0 for none."""
    game_scores = list(game_scores)
    return sum(game_scores) / len(game_scores) if game_scores else 0.0


def count_actions(steps):
    """Count one play's actions from the step trace, as the scorecard does.

    `steps` is a list of dicts with `action` (the GameAction id), `frames`
    (how many frames came back), `full_reset` and `levels_completed`.
    Returns `(total_actions, transitions)`: `transitions[k]` is the running
    action count when level k+1 was completed. A full reset starts the count
    again, so the result describes the last play."""
    total, levels, transitions = 0, 0, []
    for s in steps:
        if not s["frames"]:
            continue
        if s["action"] == RESET and s["full_reset"]:
            total, levels, transitions = 0, 0, []
        else:
            total += 1
        if s["levels_completed"] != levels:
            transitions.append(total)
            levels = s["levels_completed"]
    return total, transitions


def level_actions(total, transitions, n_levels):
    """Per-level actions from `count_actions`. The level being played when
    the run ended gets the remainder; later levels get 0."""
    out, prev = [], 0
    for i in range(n_levels):
        if i < len(transitions):
            out.append(transitions[i] - prev)
            prev = transitions[i]
        else:
            out.append(total - prev)
            prev = total
    return out


def score_play(baselines, steps):
    """Score one game's step trace against its human baselines. Returns a
    dict: score, levels_completed, actions, level_actions, level_scores."""
    total, transitions = count_actions(steps)
    per_level = level_actions(total, transitions, len(baselines))
    completed = min(len(transitions), len(baselines))
    score, scores = game_score(baselines, per_level, completed)
    return {"score": score, "levels_completed": completed, "actions": total,
            "level_actions": per_level, "level_scores": scores}
