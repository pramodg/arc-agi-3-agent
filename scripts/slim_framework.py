"""Cut the ARC-AGI-3-Agents framework's agent registry down to the random agent.

The framework's `agents/__init__.py` imports all of its LLM-backed templates,
and with them packages (langgraph, openai, smolagents and more) that we do not
install and the offline Kaggle run does not have. Nothing here uses them, so
this rewrites the file to import only the base classes and `Random`.
`pipeline/toolchain.py` runs it once on the shared framework copy. The Kaggle
notebook does the same in place at run time (scripts/build_notebook.py).

    python scripts/slim_framework.py [FRAMEWORK_DIR]
"""
from __future__ import annotations

import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "vendor" / "ARC-AGI-3-Agents"

REGISTRY = '''\
"""Rewritten by scripts/slim_framework.py: the random agent only."""
from typing import Type
from dotenv import load_dotenv
from .agent import Agent, Playback
from .swarm import Swarm
from .templates.random_agent import Random

load_dotenv()

AVAILABLE_AGENTS: dict[str, Type[Agent]] = {"random": Random}
'''


def slim(framework: Path) -> Path:
    """Rewrite `framework`'s registry. Returns the file written."""
    registry = framework / "agents" / "__init__.py"
    if not registry.is_file():
        raise SystemExit(f"No framework registry at {registry}: run `make setup`.")
    registry.write_text(REGISTRY)
    return registry


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    print(f"slimmed {slim(Path(args[0]) if args else DEFAULT)}")


if __name__ == "__main__":
    main()
