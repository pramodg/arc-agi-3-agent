import json
import os
import tempfile
import unittest
from unittest import mock

from pipeline import toolchain


class ToolchainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.dict(os.environ, {"ARC_AGI3_VAR": self.tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)

    def test_everything_lives_under_the_shared_var(self):
        for path in (toolchain.env_dir(self.repo), toolchain.interpreter(self.repo),
                     toolchain.games_dir(self.repo),
                     toolchain.framework_dir(self.repo)):
            self.assertTrue(path.startswith(self.tmp.name + os.sep), path)
        self.assertTrue(toolchain.env_dir(self.repo).endswith("py312"))

    def test_primary_checkout_falls_back_outside_git(self):
        self.assertEqual(toolchain.primary_checkout(self.tmp.name),
                         toolchain.DEFAULT_PRIMARY)

    def test_build_installs_3_12_without_touching_path_and_every_pin(self):
        cmds = toolchain.build_commands("uv", "/e", "/e/bin/python")
        self.assertEqual(cmds[0], ["uv", "python", "install", "--no-bin", "3.12"])
        self.assertIn("3.12", cmds[1])
        for pin in toolchain.PACKAGES:
            self.assertIn(pin, cmds[2])
        self.assertTrue(all("==" in p for p in toolchain.PACKAGES))

    def test_uv_state_stays_in_the_shared_var(self):
        env = toolchain.uv_env(self.repo)
        self.assertTrue(env["UV_PYTHON_INSTALL_DIR"].startswith(self.tmp.name))
        self.assertTrue(env["UV_CACHE_DIR"].startswith(self.tmp.name))

    def fake_built(self):
        """What a finished build leaves: the stamp, the interpreter, the
        shared framework copy."""
        py = toolchain.interpreter(self.repo)
        os.makedirs(os.path.dirname(py))
        with open(py, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(py, 0o755)
        agent = os.path.join(toolchain.framework_dir(self.repo), "agents",
                             "agent.py")
        os.makedirs(os.path.dirname(agent))
        open(agent, "w").close()
        with open(os.path.join(toolchain.env_dir(self.repo), toolchain.READY),
                  "w") as f:
            json.dump({"key": toolchain.pins_key()}, f)
        return py, agent

    def test_ready_only_for_the_current_pins(self):
        self.assertFalse(toolchain.is_ready(self.repo))
        self.fake_built()
        self.assertTrue(toolchain.is_ready(self.repo))
        ready = os.path.join(toolchain.env_dir(self.repo), toolchain.READY)
        with open(ready, "w") as f:
            json.dump({"key": "stale"}, f)
        self.assertFalse(toolchain.is_ready(self.repo))

    def test_not_ready_when_the_interpreter_or_framework_is_gone(self):
        py, agent = self.fake_built()
        os.remove(py)
        self.assertFalse(toolchain.is_ready(self.repo))
        self.forget_built()
        py, agent = self.fake_built()
        os.remove(agent)
        self.assertFalse(toolchain.is_ready(self.repo))

    def forget_built(self):
        import shutil
        shutil.rmtree(toolchain.env_dir(self.repo))
        shutil.rmtree(os.path.dirname(toolchain.framework_dir(self.repo)))

    def test_ensure_rebuilds_when_the_stamp_outlives_the_interpreter(self):
        py, _ = self.fake_built()
        os.remove(py)
        ran = []
        with mock.patch.object(toolchain, "uv_bin", return_value="uv"), \
                mock.patch.object(toolchain, "fetch_framework"), \
                mock.patch.object(toolchain.subprocess, "run",
                                  side_effect=lambda cmd, **kw: ran.append(cmd)):
            toolchain.ensure(self.repo)
        self.assertEqual(ran[:3], toolchain.build_commands(
            "uv", toolchain.env_dir(self.repo), py))
        here = os.path.join(self.repo, "vendor", "ARC-AGI-3-Agents")
        self.assertEqual(os.readlink(here), toolchain.framework_dir(self.repo))

    def test_ensure_trusts_a_complete_build(self):
        self.fake_built()
        with mock.patch.object(toolchain.subprocess, "run") as run:
            toolchain.ensure(self.repo)
        run.assert_not_called()

    def test_pins_key_follows_the_pins(self):
        before = toolchain.pins_key()
        with mock.patch.object(toolchain, "PACKAGES", ("arc-agi==0.0.1",)):
            self.assertNotEqual(before, toolchain.pins_key())

    def test_link_vendor_links_and_leaves_a_real_copy_alone(self):
        self.assertEqual(toolchain.link_vendor(self.repo), "linked")
        here = os.path.join(self.repo, "vendor", "ARC-AGI-3-Agents")
        self.assertEqual(os.readlink(here), toolchain.framework_dir(self.repo))
        self.assertEqual(toolchain.link_vendor(self.repo), "linked")
        os.remove(here)
        os.makedirs(here)
        self.assertEqual(toolchain.link_vendor(self.repo), "own copy")


if __name__ == "__main__":
    unittest.main()
