"""The random agent we compare against, with its action cap committed.

The ARC-AGI-3-Agents framework (MIT) ships a `Random` template that picks
any non-RESET action, and random click coordinates, until the game is won.
Its own cap is 80 actions a game. Our comparisons run it under the same cap
as the agent it is compared with, so the cap is set here, not by hand:

    python3 -m pipeline.toolchain run scripts/play_local.py --offline \\
        --agent scripts/random_agent.py --max-steps 10000
    python3 -m pipeline.toolchain run -m pipeline.evaluate run \\
        --agent scripts/random_agent.py

`--max-steps` / `--max-actions` can only lower RANDOM_MAX_ACTIONS. Passing
80 reproduces the framework's default run.

The framework must be importable (`make setup` links it into vendor/; both
commands above put it on sys.path before they load this file).
"""
from agents.templates.random_agent import Random

# 10,000 actions a game: the cap the first comparison with our explorer used
# (docs/baseline.md). The framework allows one action past the cap.
RANDOM_MAX_ACTIONS = 10000


class MyAgent(Random):
    """The framework's random policy under RANDOM_MAX_ACTIONS."""

    MAX_ACTIONS = RANDOM_MAX_ACTIONS
