"""The evaluator: baselines, the split, the totals, and one real local game
played under competition rules."""
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

from pipeline import evaluate, toolchain

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAVE_ARC = importlib.util.find_spec("arc_agi") is not None
VENDOR = os.path.join(ROOT, "vendor", "ARC-AGI-3-Agents")
GAMES = toolchain.games_dir(ROOT)

# An agent that resets the level every third action: under competition rules
# that must stay one play, with every reset counted as an action.
RESETTING_AGENT = '''
from arcengine import GameAction, GameState
from agents.agent import Agent

class MyAgent(Agent):
    MAX_ACTIONS = 20

    def is_done(self, frames, latest_frame):
        return False

    def choose_action(self, frames, latest_frame):
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            return GameAction.RESET
        if self.action_counter % 3 == 2:
            return GameAction.RESET
        return GameAction.from_id(latest_frame.available_actions[0])
'''

# An agent whose very first action is RESET. The engine turns a RESET sent
# with no action since the last reset (make() did one) into a full reset, a
# second play, unless the evaluator has switched resets to level resets. A
# single RESET sent later is a level reset either way, but two in a row
# later depend on the switch too (RESET_TWICE_AGENT).
RESET_FIRST_AGENT = '''
from arcengine import GameAction
from agents.agent import Agent

class MyAgent(Agent):
    MAX_ACTIONS = 10

    def is_done(self, frames, latest_frame):
        return False

    def choose_action(self, frames, latest_frame):
        if self.action_counter == 0:
            return GameAction.RESET
        return GameAction.from_id(latest_frame.available_actions[0])
'''


# An agent that plays two actions, then sends RESET twice in a row. Without
# the switch the second RESET is a full reset and the toolkit records two
# plays (checked on ls20, 2026-10-25).
RESET_TWICE_AGENT = '''
from arcengine import GameAction
from agents.agent import Agent

class MyAgent(Agent):
    MAX_ACTIONS = 10

    def is_done(self, frames, latest_frame):
        return False

    def choose_action(self, frames, latest_frame):
        if self.action_counter in (2, 3):
            return GameAction.RESET
        return GameAction.from_id(latest_frame.available_actions[0])
'''


def game(name, part, rhae, toolkit, actions=5, toolkit_actions=5):
    return {"game": name, "split": part, "rhae": rhae, "toolkit_rhae": toolkit,
            "levels_completed": 1, "baseline_actions": [1, 2],
            "actions": actions, "toolkit_actions": toolkit_actions,
            "seconds": 0.1, "end": "win"}


class PureTest(unittest.TestCase):
    def test_the_per_game_limit_is_the_agents_share_of_nine_hours(self):
        # 75% of the 9-hour notebook, shared by 55 games playing at once.
        self.assertEqual(evaluate.PER_GAME_SECONDS, 441)
        self.assertEqual(evaluate.KAGGLE_RUNTIME_S, 9 * 3600)

    def test_the_agent_stops_itself_at_the_same_share_of_nine_hours(self):
        with open(os.path.join(ROOT, "agent", "my_agent.py")) as f:
            source = f.read()
        self.assertIn("MAX_SECONDS = 0.75 * 9 * 3600", source)

    def test_baselines_and_their_source_come_from_the_game_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "ab12", "v1"))
            with open(os.path.join(d, "ab12", "v1", "metadata.json"), "w") as f:
                json.dump({"game_id": "ab12-v1", "baseline_actions": [3, 4],
                           "date_downloaded": "2026-10-25"}, f)
            got = evaluate.baselines(d)
        self.assertEqual(got["ab12-v1"]["baseline_actions"], [3, 4])
        self.assertIn("ab12/v1/metadata.json", got["ab12-v1"]["source"])
        self.assertIn("2026-10-25", got["ab12-v1"]["source"])

    def test_rows_follow_the_split(self):
        rows = evaluate.game_rows({"b": "b-2", "a": "a-1"}, {"b"})
        self.assertEqual(rows, [("a", "a-1", "developed"),
                                ("b", "b-2", "held_out")])

    def test_totals_split_and_agreement(self):
        games = [game("a", "developed", 0.5, 0.5),
                 game("b", "held_out", 0.0, 0.0),
                 game("c", "held_out", 0.25, 0.25)]
        t = evaluate.summarise(games)
        self.assertAlmostEqual(t["rhae"], 0.25)
        self.assertAlmostEqual(t["rhae_developed"], 0.5)
        self.assertAlmostEqual(t["rhae_held_out"], 0.125)
        self.assertTrue(t["agrees"])
        self.assertEqual(t["games_disagreeing"], [])

    def test_a_score_or_action_difference_is_named(self):
        games = [game("a", "developed", 0.5, 0.4),
                 game("b", "held_out", 0.0, 0.0, actions=5, toolkit_actions=6)]
        t = evaluate.summarise(games)
        self.assertFalse(t["agrees"])
        self.assertEqual(t["games_disagreeing"], ["a", "b"])

    def test_the_table_ends_with_one_total_line(self):
        result = {"games": [game("a", "developed", 0.5, 0.5)],
                  "mode": "local competition", "commit": "abc" * 10,
                  "seconds": 1.0}
        result["totals"] = evaluate.summarise(result["games"])
        lines = evaluate.table(result).splitlines()
        self.assertTrue(lines[-1].startswith("RHAE 50.00% over 1 games"))
        self.assertIn("held-out", lines[-1])
        self.assertIn("agrees", lines[-1])

    def test_a_refused_call_is_sent_again_after_a_wait(self):
        answers = iter([None, RuntimeError("429"), "frame"])

        def call():
            got = next(answers)
            if isinstance(got, Exception):
                raise got
            return got
        retried = []
        with mock.patch.object(evaluate.time, "sleep") as sleep:
            self.assertEqual(evaluate.with_retries(call, (1, 2, 3), retried),
                             "frame")
        self.assertEqual(retried, [1, 2])
        self.assertEqual(sleep.call_count, 2)

    def test_retries_give_up_after_the_last_wait(self):
        with mock.patch.object(evaluate.time, "sleep"):
            self.assertIsNone(evaluate.with_retries(lambda: None, (1,), []))
            with self.assertRaises(RuntimeError):
                evaluate.with_retries(
                    lambda: (_ for _ in ()).throw(RuntimeError("x")), (1,), [])

    def test_a_recorded_run_must_play_every_game(self):
        with mock.patch.object(evaluate, "run") as run, \
                mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                evaluate.main(["run", "--record", "--games", "ls20"])
        run.assert_not_called()

    def test_the_commit_is_read_before_any_game_is_played(self):
        with open(evaluate.__file__) as f:
            source = f.read()
        body = source[source.index("def run(args)"):]
        self.assertLess(body.index("commit_of(ROOT)"), body.index("play("))


@unittest.skipUnless(HAVE_ARC and os.path.isdir(VENDOR)
                     and os.path.isdir(os.path.join(GAMES, "ls20")),
                     "needs the 3.12 env, the framework and the cached games")
class LocalGameTest(unittest.TestCase):
    def test_one_play_with_level_resets_counted_and_the_toolkit_agreeing(self):
        with tempfile.TemporaryDirectory() as d:
            agent = os.path.join(d, "agent.py")
            with open(agent, "w") as f:
                f.write(RESETTING_AGENT)
            out = os.path.join(d, "r.json")
            with mock.patch("sys.stdout"), mock.patch("sys.stderr"):
                evaluate.main(["run", "--games", "ls20", "--agent", agent,
                               "--out", out])
            with open(out) as f:
                result = json.load(f)
        g = result["games"][0]
        self.assertEqual(g["game"], "ls20-9607627b")
        self.assertEqual(g["toolkit_plays"], 1)
        self.assertEqual(g["actions"], g["toolkit_actions"])
        self.assertEqual(g["actions"], 21)  # MAX_ACTIONS 20, the loop's <=
        self.assertTrue(result["totals"]["agrees"])
        self.assertEqual(result["mode"], "local competition")
        self.assertNotIn("ONLY_RESET_LEVELS", os.environ)

    def test_a_reset_as_the_first_action_stays_in_the_one_play(self):
        # Without competition mode the toolkit records plays [0, 10] here.
        with tempfile.TemporaryDirectory() as d:
            agent = os.path.join(d, "agent.py")
            with open(agent, "w") as f:
                f.write(RESET_FIRST_AGENT)
            out = os.path.join(d, "r.json")
            with mock.patch("sys.stdout"), mock.patch("sys.stderr"):
                evaluate.main(["run", "--games", "ls20", "--agent", agent,
                               "--out", out])
            with open(out) as f:
                g = json.load(f)["games"][0]
        self.assertEqual(g["toolkit_plays"], 1)
        self.assertEqual(g["toolkit_actions"], 11)  # the reset counts
        self.assertEqual(g["actions"], g["toolkit_actions"])

    def test_two_resets_in_a_row_later_stay_in_the_one_play(self):
        with tempfile.TemporaryDirectory() as d:
            agent = os.path.join(d, "agent.py")
            with open(agent, "w") as f:
                f.write(RESET_TWICE_AGENT)
            out = os.path.join(d, "r.json")
            with mock.patch("sys.stdout"), mock.patch("sys.stderr"):
                evaluate.main(["run", "--games", "ls20", "--agent", agent,
                               "--out", out])
            with open(out) as f:
                g = json.load(f)["games"][0]
        self.assertEqual(g["toolkit_plays"], 1)
        self.assertEqual(g["toolkit_actions"], 11)  # both resets count
        self.assertEqual(g["actions"], g["toolkit_actions"])

    def test_the_wall_clock_limit_stops_the_game(self):
        with tempfile.TemporaryDirectory() as d:
            agent = os.path.join(d, "agent.py")
            with open(agent, "w") as f:
                f.write(RESETTING_AGENT)
            out = os.path.join(d, "r.json")
            with mock.patch("sys.stdout"), mock.patch("sys.stderr"):
                evaluate.main(["run", "--games", "ls20", "--agent", agent,
                               "--seconds", "0", "--out", out])
            with open(out) as f:
                g = json.load(f)["games"][0]
        self.assertEqual(g["end"], "time limit")
        self.assertEqual(g["actions"], 0)


if __name__ == "__main__":
    unittest.main()
