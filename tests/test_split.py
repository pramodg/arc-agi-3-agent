import glob
import json
import os
import unittest

from pipeline import split, toolchain

GAMES = toolchain.games_dir(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SplitTest(unittest.TestCase):
    def test_every_second_sorted_id_starting_with_the_second_is_held_out(self):
        developed, held_out = split.split(["d", "b", "a", "c", "e"])
        self.assertEqual(developed, ["a", "c", "e"])
        self.assertEqual(held_out, ["b", "d"])

    def test_document_uses_short_ids(self):
        doc = split.document(["ls20-1", "vc33-2", "ft09-3"], "t", "n")
        self.assertEqual(doc["developed"], ["ft09", "vc33"])
        self.assertEqual(doc["held_out"], ["ls20"])
        self.assertEqual(doc["versions"]["ls20"], "ls20-1")

    def test_split_json_follows_the_rule(self):
        doc = split.load()
        developed, held_out = split.split(doc["versions"])
        self.assertEqual(doc["developed"], developed)
        self.assertEqual(doc["held_out"], held_out)
        self.assertFalse(set(developed) & set(held_out))
        self.assertTrue(doc["note"])

    def test_split_json_lists_every_public_game_once(self):
        # The evaluator reports by the split, so a public game missing from
        # it would drop out of both halves. The 25 public games, as arc_agi
        # listed them on 2026-10-25 (docs/setup.md).
        public = {"ar25", "bp35", "cd82", "cn04", "dc22", "ft09", "g50t",
                  "ka59", "lf52", "lp85", "ls20", "m0r0", "r11l", "re86",
                  "s5i5", "sb26", "sc25", "sk48", "sp80", "su15", "tn36",
                  "tr87", "tu93", "vc33", "wa30"}
        doc = split.load()
        self.assertEqual(set(doc["versions"]), public)
        self.assertEqual(sorted(doc["developed"] + doc["held_out"]),
                         sorted(public))

    @unittest.skipUnless(os.path.isdir(GAMES), "no cached games")
    def test_split_json_covers_every_cached_game(self):
        cached = set()
        for path in glob.glob(os.path.join(GAMES, "*", "*", "metadata.json")):
            with open(path) as f:
                cached.add(json.load(f)["game_id"].split("-")[0])
        doc = split.load()
        self.assertLessEqual(cached, set(doc["versions"]))


if __name__ == "__main__":
    unittest.main()
