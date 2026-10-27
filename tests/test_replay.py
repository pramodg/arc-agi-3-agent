"""Replays: the GIF writer, the frame cap, the artifacts index, and one real
local game recorded through the evaluator."""
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

from pipeline import replay, toolchain

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAVE_PIL = importlib.util.find_spec("PIL") is not None
HAVE_NUMPY = importlib.util.find_spec("numpy") is not None
HAVE_ARC = importlib.util.find_spec("arc_agi") is not None
VENDOR = os.path.join(ROOT, "vendor", "ARC-AGI-3-Agents")
GAMES = toolchain.games_dir(ROOT)


def toy_game(n):
    """`n` distinct 64x64 grids: a background of colour 5 with one cell of
    colour 1 + (t % 15) walking along the top rows, a toy that encodes no
    public game."""
    grids = []
    for t in range(n):
        g = [[5] * 64 for _ in range(64)]
        g[t // 64][t % 64] = 1 + (t % 15)
        if g[t // 64][t % 64] == 5:
            g[t // 64][t % 64] = 0
        grids.append(g)
    return grids


def record(short, split, levels, of, rhae):
    return {"short": short, "split": split, "levels_completed": levels,
            "baseline_actions": [1] * of, "rhae": rhae}


class SampleTest(unittest.TestCase):
    def test_a_short_play_keeps_every_frame(self):
        self.assertEqual(replay.sample(5, cap=10), [0, 1, 2, 3, 4])

    def test_a_long_play_is_sampled_evenly_from_first_to_last(self):
        got = replay.sample(1001, cap=11)
        self.assertEqual(len(got), 11)
        self.assertEqual(got[0], 0)
        self.assertEqual(got[-1], 1000)
        self.assertEqual(got, sorted(set(got)))

    def test_a_cap_of_one_keeps_the_last_frame(self):
        self.assertEqual(replay.sample(9, cap=1), [8])
        self.assertEqual(replay.sample(9, cap=0), [])


@unittest.skipUnless(HAVE_PIL, "needs Pillow (arc-agi depends on it)")
class GifTest(unittest.TestCase):
    def frames_of(self, path):
        from PIL import Image
        with Image.open(path) as im:
            n = im.n_frames
            size = im.size
            palette = im.getpalette()[:48]
        return n, size, palette

    def test_a_toy_game_gives_one_frame_per_grid_in_the_arc_palette(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "toy.gif")
            wrote = replay.write_gif(path, toy_game(12))
            n, size, palette = self.frames_of(path)
        self.assertEqual(wrote, 12)
        self.assertEqual(n, 12)
        self.assertEqual(size, (256, 256))
        self.assertEqual(palette, [c for rgb in replay.PALETTE for c in rgb])

    def test_the_frame_cap_holds(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "toy.gif")
            wrote = replay.write_gif(path, toy_game(50), cap=7)
            n, _, _ = self.frames_of(path)
        self.assertEqual((wrote, n), (7, 7))

    def test_palette_colours_are_the_official_rgb(self):
        self.assertEqual(len(replay.PALETTE), 16)
        self.assertEqual(replay.PALETTE[0], (255, 255, 255))
        self.assertEqual(replay.PALETTE[5], (0, 0, 0))
        self.assertEqual(replay.PALETTE[8], (249, 60, 49))
        self.assertEqual(replay.PALETTE[9], (30, 147, 255))
        self.assertEqual(replay.PALETTE[14], (79, 204, 48))

    def test_the_last_frame_holds_for_two_seconds(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "toy.gif")
            replay.write_gif(path, toy_game(3))
            with Image.open(path) as im:
                durations = []
                for i in range(im.n_frames):
                    im.seek(i)
                    durations.append(im.info["duration"])
        self.assertEqual(durations, [100, 100, 2000])

    def test_cells_take_their_palette_colour(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "toy.gif")
            replay.write_gif(path, toy_game(1))
            with Image.open(path) as im:
                rgb = im.convert("RGB")
                self.assertEqual(rgb.getpixel((1, 1)), replay.PALETTE[1])
                self.assertEqual(rgb.getpixel((200, 200)), replay.PALETTE[5])

    def test_repeated_grids_become_one_longer_frame(self):
        a, b = toy_game(2)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "toy.gif")
            wrote = replay.write_gif(path, [a, a, a, b])
            n, _, _ = self.frames_of(path)
        self.assertEqual((wrote, n), (2, 2))

    def test_no_grids_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "toy.gif")
            self.assertEqual(replay.write_gif(path, []), 0)
            self.assertFalse(os.path.exists(path))


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class RecorderTest(unittest.TestCase):
    def test_the_recorder_keeps_a_copy_of_each_grid(self):
        grid = [[1, 2], [3, 4]]
        r = replay.Recorder()
        r.add(None, grid)
        r.add(6, grid)
        grid[0][0] = 9
        self.assertEqual([a for a, _ in r.frames], [None, 6])
        self.assertEqual(int(r.frames[0][1][0][0]), 1)


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.result = {
            "started": "2026-10-25T07:00:00+00:00", "commit": "a" * 40,
            "games": [record("aa11", "developed", 1, 7, 0.02),
                      record("bb22", "held_out", 3, 7, 0.10),
                      record("cc33", "developed", 2, 6, 0.05),
                      record("dd44", "developed", 0, 6, 0.0)]}

    def test_developed_games_are_images_and_held_out_ones_score_lines(self):
        repo = "/r"
        gifs = {"aa11": "/r/var/replays/S/aa11.gif",
                "cc33": "/r/var/replays/S/cc33.gif"}
        got = replay.index_entries(self.result, "/r/var/eval/S-x.json", gifs,
                                   repo, "S", row="gameplay-pane")
        self.assertEqual([e["id"] for e in got],
                         ["score/S/bb22", "replay/S/cc33", "replay/S/aa11"])
        held, best, _ = got
        self.assertEqual(held["kind"], "text")
        self.assertEqual(held["path"], "var/eval/S-x.json")
        self.assertNotIn(".gif", json.dumps(held))
        self.assertIn("held-out", held["title"])
        self.assertEqual(best["kind"], "image")
        self.assertEqual(best["path"], "var/replays/S/cc33.gif")
        self.assertEqual(best["title"],
                         "cc33 · developed · levels 2/6 · RHAE 5.00%")
        for e in got:
            self.assertEqual(set(e), {"id", "title", "kind", "path",
                                      "made_at", "commit", "row"})
            self.assertEqual(e["commit"], "a" * 12)
            self.assertEqual(e["row"], "gameplay-pane")
            self.assertEqual(e["made_at"], "2026-10-25T07:00:00+00:00")

    def test_a_path_outside_the_repo_stays_absolute(self):
        got = replay.index_entries(self.result, "/elsewhere/r.json", {}, "/r",
                                   "S")
        self.assertEqual(got[0]["path"], "/elsewhere/r.json")

    def test_the_index_is_replaced_whole(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "var", "artifacts.json")
            replay.write_index(path, [{"id": "old"}, {"id": "older"}])
            replay.write_index(path, [{"id": "new"}])
            with open(path) as f:
                self.assertEqual(json.load(f), [{"id": "new"}])
            self.assertEqual(os.listdir(os.path.dirname(path)),
                             ["artifacts.json"])


AGENT = '''
from arcengine import GameAction, GameState
from agents.agent import Agent

class MyAgent(Agent):
    MAX_ACTIONS = 12

    def is_done(self, frames, latest_frame):
        return False

    def choose_action(self, frames, latest_frame):
        if latest_frame.state in (GameState.NOT_PLAYED, GameState.GAME_OVER):
            return GameAction.RESET
        return GameAction.from_id(latest_frame.available_actions[0])
'''


@unittest.skipUnless(HAVE_ARC and os.path.isdir(VENDOR)
                     and os.path.isdir(os.path.join(GAMES, "ls20"))
                     and os.path.isdir(os.path.join(GAMES, "bp35")),
                     "needs the 3.12 env, the framework and the cached games")
class RecordedRunTest(unittest.TestCase):
    def run_eval(self, d, *flags):
        from pipeline import evaluate
        agent = os.path.join(d, "agent.py")
        with open(agent, "w") as f:
            f.write(AGENT)
        var = os.path.join(d, "var")
        # A recorded run plays every game, so the split is cut down to two.
        doc = evaluate.split.load()
        doc["versions"] = {k: v for k, v in doc["versions"].items()
                           if k in ("ls20", "bp35")}
        with mock.patch.dict(os.environ, {"ARC_AGI3_VAR": var}), \
                mock.patch.object(evaluate.split, "load", return_value=doc), \
                mock.patch.object(evaluate.toolchain, "games_dir",
                                  return_value=GAMES), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            evaluate.main(["run", "--agent", agent, *flags])
        return var

    def test_a_recorded_run_writes_developed_gifs_and_the_index(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            var = self.run_eval(d, "--record", "--row", "gameplay-pane")
            (stamp,) = os.listdir(os.path.join(var, "replays"))
            run_dir = os.path.join(var, "replays", stamp)
            self.assertEqual(os.listdir(run_dir), ["ls20.gif"])
            self.assertFalse(os.path.exists(
                os.path.join(var, "replays-held-out")))
            (result_name,) = os.listdir(os.path.join(var, "eval"))
            with open(os.path.join(var, "eval", result_name)) as f:
                result = json.load(f)
            steps = {g["short"]: g["steps"] for g in result["games"]}
            listed = result["replays"]
            with Image.open(os.path.join(run_dir, "ls20.gif")) as im:
                frames = im.n_frames
            with open(os.path.join(var, "artifacts.json")) as f:
                index = json.load(f)
        # the start frame plus the frame after every action, with repeats
        # merged in the GIF
        self.assertEqual(listed["ls20"]["recorded"], steps["ls20"] + 1)
        self.assertEqual(listed["ls20"]["frames"], frames)
        self.assertLessEqual(frames, steps["ls20"] + 1)
        self.assertEqual(set(listed), {"ls20"})
        by_id = {e["id"]: e for e in index}
        self.assertEqual(set(by_id), {f"replay/{stamp}/ls20",
                                      f"score/{stamp}/bp35"})
        self.assertEqual(by_id[f"replay/{stamp}/ls20"]["path"],
                         f"var/replays/{stamp}/ls20.gif")
        self.assertEqual(by_id[f"score/{stamp}/bp35"]["path"],
                         f"var/eval/{result_name}")

    def test_held_out_gifs_need_their_own_flag_and_go_elsewhere(self):
        with tempfile.TemporaryDirectory() as d:
            var = self.run_eval(d, "--record-held-out")
            (stamp,) = os.listdir(os.path.join(var, "replays-held-out"))
            self.assertEqual(os.listdir(os.path.join(
                var, "replays-held-out", stamp)), ["bp35.gif"])
            self.assertFalse(os.path.exists(os.path.join(var, "replays")))
            self.assertFalse(os.path.exists(os.path.join(var,
                                                         "artifacts.json")))

    def test_without_the_flag_nothing_is_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            var = self.run_eval(d)
            self.assertEqual(os.listdir(var), ["eval"])


if __name__ == "__main__":
    unittest.main()
