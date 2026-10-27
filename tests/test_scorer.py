"""RHAE: every worked example on docs.arcprize.org/methodology.md, and our
scorer against the arc-agi toolkit's own on runs that complete levels."""
import importlib.util
import unittest

from pipeline import scorer

HAVE_ARC = importlib.util.find_spec("arc_agi") is not None


def step(action, levels, frames=1, full_reset=False):
    return {"action": action, "frames": frames, "full_reset": full_reset,
            "levels_completed": levels}


class MethodologyExamplesTest(unittest.TestCase):
    """The page's examples, in its order."""

    def test_upper_median_of_four_players_is_the_third(self):
        self.assertEqual(scorer.upper_median([40, 10, 30, 20]), 30)

    def test_upper_median_of_five_players_is_the_third(self):
        self.assertEqual(scorer.upper_median([50, 10, 40, 30, 20]), 30)

    def test_human_10_ai_10_scores_one(self):
        self.assertAlmostEqual(scorer.level_score(10, 10), 1.0)

    def test_human_10_ai_20_scores_a_quarter(self):
        self.assertAlmostEqual(scorer.level_score(10, 20), 0.25)

    def test_human_10_ai_100_scores_one_percent(self):
        self.assertAlmostEqual(scorer.level_score(10, 100), 0.01)

    def test_a_level_caps_at_1_15(self):
        self.assertAlmostEqual(scorer.level_score(10, 5), 1.15)
        self.assertAlmostEqual(scorer.level_score(10, 9), 1.15)
        self.assertAlmostEqual(scorer.level_score(100, 95), (100 / 95) ** 2)

    def test_four_of_five_levels_caps_the_game_at_two_thirds(self):
        # However efficient levels 1-4 were: here every one hit the 1.15 cap.
        score, _ = scorer.game_score([10] * 5, [1, 1, 1, 1, 50], 4)
        self.assertAlmostEqual(score, 10 / 15)

    def test_the_total_is_the_mean_over_games(self):
        self.assertAlmostEqual(scorer.total_score([1.0, 0.0, 0.5]), 0.5)
        self.assertEqual(scorer.total_score([]), 0.0)


class GameScoreTest(unittest.TestCase):
    def test_weights_are_the_level_numbers(self):
        # Level 2 only, at the human's pace: weight 2 of 1+2+3.
        score, scores = scorer.game_score([10, 10, 10], [0, 10, 0], 0)
        self.assertEqual(score, 0.0)  # nothing completed scores nothing
        score, scores = scorer.game_score([10, 10, 10], [20, 10, 99], 2)
        self.assertEqual(scores, [0.25, 1.0, 0.0])
        self.assertAlmostEqual(score, (0.25 * 1 + 1.0 * 2) / 6)

    def test_all_levels_at_the_cap_still_score_100_percent(self):
        score, _ = scorer.game_score([10, 10], [1, 1], 2)
        self.assertAlmostEqual(score, 1.0)

    def test_a_zero_action_completion_scores_zero(self):
        self.assertEqual(scorer.level_score(10, 0), 0.0)


class CountActionsTest(unittest.TestCase):
    def test_level_resets_count_and_full_resets_start_again(self):
        steps = [step(0, 0, full_reset=True), step(1, 0), step(0, 0),
                 step(2, 1), step(3, 1)]
        self.assertEqual(scorer.count_actions(steps), (4, [3]))
        steps = [step(1, 0), step(0, 0, full_reset=True), step(1, 0)]
        self.assertEqual(scorer.count_actions(steps), (1, []))

    def test_a_step_with_no_frame_does_not_count(self):
        steps = [step(1, 0), step(1, 0, frames=0), step(1, 1)]
        self.assertEqual(scorer.count_actions(steps), (2, [2]))

    def test_the_unfinished_level_gets_the_remainder(self):
        self.assertEqual(scorer.level_actions(30, [10, 25], 4), [10, 15, 5, 0])

    def test_score_play(self):
        steps = [step(1, 0)] * 9 + [step(1, 1)] + [step(1, 1)] * 5
        got = scorer.score_play([10, 10, 10], steps)
        self.assertEqual(got["levels_completed"], 1)
        self.assertEqual(got["actions"], 15)
        self.assertEqual(got["level_actions"], [10, 5, 0])
        self.assertAlmostEqual(got["score"], 1 / 6)


@unittest.skipUnless(HAVE_ARC, "arc_agi not installed (runs on the 3.12 env)")
class AgainstTheToolkitTest(unittest.TestCase):
    """The toolkit's EnvironmentScorecard.from_scorecard on the same plays."""

    CASES = [
        # (baselines, steps as (action, levels_completed) pairs)
        ([22, 123, 73], [(1, 0)] * 30 + [(1, 1)] + [(1, 1)] * 99 + [(2, 2)]),
        ([10, 10, 10, 10, 10], [(1, 0)] * 4 + [(1, 1)] + [(1, 2)] * 2
         + [(1, 3)] * 50 + [(1, 4)] + [(0, 4)] * 3),
        ([5, 40], [(1, 0)] * 7),
        ([8, 8], [(1, 0)] * 2 + [(1, 1)] + [(0, 1)] + [(1, 1)] * 3 + [(1, 2)]),
    ]

    def toolkit(self, baselines, steps):
        from arc_agi.models import EnvironmentInfo
        from arc_agi.scorecard import EnvironmentScorecard, Scorecard

        card = Scorecard(card_id="t")
        card.new_play("g-1", "guid")
        for action, levels in steps:
            if action == 0:
                card.reset("g-1", "guid")
            else:
                card.take_action("g-1", "guid")
            card.set_levels_completed("g-1", "guid", levels)
        if steps and steps[-1][1] == len(baselines):
            card.win("g-1", "guid")
        info = EnvironmentInfo(game_id="g-1", baseline_actions=baselines)
        return EnvironmentScorecard.from_scorecard(card, [info]).environments[0]

    def test_same_score_and_actions_as_the_toolkit(self):
        for baselines, pairs in self.CASES:
            with self.subTest(baselines=baselines):
                ours = scorer.score_play(
                    baselines, [step(a, lv) for a, lv in pairs])
                theirs = self.toolkit(baselines, pairs)
                self.assertAlmostEqual(ours["score"] * 100, theirs.score)
                self.assertEqual(ours["actions"], theirs.actions)
                self.assertEqual(ours["levels_completed"],
                                 theirs.levels_completed)
                self.assertEqual(ours["level_actions"],
                                 theirs.runs[0].level_actions)
                if any(lv for _, lv in pairs):  # a real, non-zero check
                    self.assertGreater(ours["score"], 0)


if __name__ == "__main__":
    unittest.main()
