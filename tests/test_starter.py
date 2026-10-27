"""The ported starter layout: local play, the notebook, the agent."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import build_notebook  # noqa: E402
import play_local  # noqa: E402
from pipeline import split  # noqa: E402



class PlayLocalTest(unittest.TestCase):
    IDS = ["ls20-9607627b", "vc33-5430563c", "ft09-0d8bbf25"]

    def test_all_games_by_default(self):
        self.assertEqual(play_local.resolve_games(self.IDS, None),
                         ["ls20", "vc33", "ft09"])

    def test_named_games_accept_versioned_ids(self):
        self.assertEqual(play_local.resolve_games(self.IDS, "vc33-x, ls20"),
                         ["ls20", "vc33"])

    def test_unknown_game_is_refused(self):
        with self.assertRaises(SystemExit):
            play_local.resolve_games(self.IDS, "zz99")


class NotebookTest(unittest.TestCase):
    def test_notebook_carries_the_agent_and_runs_offline(self):
        nb = build_notebook.build()
        with open(os.path.join(ROOT, "agent", "my_agent.py")) as f:
            agent = f.read()
        sources = [c["source"] for c in nb["cells"]]
        self.assertTrue(any(agent in s for s in sources))
        self.assertFalse(nb["metadata"]["kaggle"]["isInternetEnabled"])
        self.assertIn(build_notebook.ACCELERATOR, build_notebook._ACCELERATORS)

    def test_kernel_metadata_is_offline_and_unclaimed(self):
        with open(os.path.join(ROOT, "notebooks", "kernel-metadata.json")) as f:
            meta = json.load(f)
        self.assertFalse(meta["enable_internet"])
        self.assertIn("arc-prize-2026-arc-agi-3", meta["competition_sources"])
        self.assertTrue(meta["id"].startswith("REPLACE_WITH_YOUR_USERNAME/"))


class AgentTest(unittest.TestCase):
    def test_agent_names_no_public_game(self):
        # RULES.md 3: nothing in the submitted agent encodes a public game.
        with open(os.path.join(ROOT, "agent", "my_agent.py")) as f:
            words = set(re.findall(r"[a-z0-9]+", f.read().lower()))
        self.assertFalse(words & set(split.load()["versions"]))
    # The agent's behaviour is tested in tests/test_agent.py.

if __name__ == "__main__":
    unittest.main()
