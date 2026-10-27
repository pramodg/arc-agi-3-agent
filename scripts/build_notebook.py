"""Write `notebooks/submission.ipynb`: the Kaggle notebook that plays our agent.

`make notebook` and `make submit` run this. Never edit the notebook by hand;
it is rebuilt from `agent/my_agent.py` every time.

Kaggle runs a competition notebook twice (docs/requirements.md):

- At commit ("Save & Run All") there are no games. The notebook only has to
  finish and leave a `submission.parquet`, so it writes a one-row stand-in.
- In the competition rerun, `KAGGLE_IS_COMPETITION_RERUN` is set and a
  gateway serving the hidden games runs beside the notebook at
  `gateway:8001`. The notebook copies the competition's ARC-AGI-3-Agents
  framework somewhere writable, adds our agent to it, points it at the
  gateway, and runs the framework's `main.py`. The gateway counts every
  action and writes the real `submission.parquet`.

Internet is off in both runs, so the `arc-agi` package is installed from the
wheels the competition ships as input data.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_SRC = ROOT / "agent" / "my_agent.py"
NOTEBOOK_PATH = ROOT / "notebooks" / "submission.ipynb"
METADATA_PATH = ROOT / "notebooks" / "kernel-metadata.json"

# The hardware Kaggle gives the notebook. Our agent is plain Python, so a
# CPU is enough. Each choice maps to Kaggle's accelerator name and whether
# the kernel needs a GPU.
ACCELERATOR = "cpu"
_ACCELERATORS = {
    "cpu": {"name": "none", "gpu": False},
    "t4": {"name": "nvidiaTeslaT4", "gpu": True},          # 2 x T4
    "p100": {"name": "nvidiaTeslaP100", "gpu": True},
    "rtx6000": {"name": "nvidiaRtx6000", "gpu": True},     # RTX Pro 6000
}

COMPETITION = "/kaggle/input/competitions/arc-prize-2026-arc-agi-3"
WORK = "/kaggle/working/ARC-AGI-3-Agents"
# The agent goes to /tmp, not /kaggle/working: every file in
# /kaggle/working is offered as a submission candidate beside the parquet.
AGENT_TMP = "/tmp/my_agent.py"

# The framework's agents/__init__.py imports every LLM template it ships,
# and their packages are not in the offline wheels. This replacement imports
# only what the run needs: the base classes, the random template, and ours.
REGISTRY = '''from typing import Type
from dotenv import load_dotenv
from .agent import Agent, Playback
from .swarm import Swarm
from .templates.random_agent import Random
from .templates.my_agent import MyAgent

load_dotenv()

AVAILABLE_AGENTS: dict[str, Type[Agent]] = {
    'random': Random,
    'myagent': MyAgent,
}
'''

# How the framework reaches the gateway. The gateway accepts any API key.
GATEWAY_ENV = '''SCHEME=http
HOST=gateway
PORT=8001
ARC_API_KEY=test-key-123
ARC_BASE_URL=http://gateway:8001/
OPERATION_MODE=online
ENVIRONMENTS_DIR=
RECORDINGS_DIR=/kaggle/working/server_recording
'''


def _cell(kind: str, lines: list[str]) -> dict:
    cell = {"cell_type": kind, "metadata": {}, "source": "\n".join(lines)}
    if kind == "code":
        cell.update(metadata={"trusted": True}, outputs=[],
                    execution_count=None)
    return cell


def _writer(path: str, text: str) -> list[str]:
    """Python lines, indented for an `if` body, that write `text` to `path`."""
    return [f"    with open({path!r}, 'w') as f:",
            "        f.write(" + json.dumps(text) + ")"]


def rerun_cell() -> dict:
    """The competition rerun: wait for the gateway, then play every game."""
    return _cell("code", [
        "import os",
        "",
        "if os.getenv('KAGGLE_IS_COMPETITION_RERUN'):",
        "    # The gateway may still be starting; retry for up to ten minutes.",
        "    !curl --fail --retry 999 --retry-all-errors --retry-delay 5 "
        "--retry-max-time 600 http://gateway:8001/api/games",
        f"    !cp -r {COMPETITION}/ARC-AGI-3-Agents {WORK}",
        f"    !cp {AGENT_TMP} {WORK}/agents/templates/my_agent.py",
        *_writer(f"{WORK}/agents/__init__.py", REGISTRY),
        *_writer(f"{WORK}/.env", GATEWAY_ENV),
        f"    !cd {WORK} && MPLBACKEND=agg python main.py --agent myagent",
    ])


def commit_cell() -> dict:
    """The commit run: a stand-in parquet so Kaggle accepts the version."""
    return _cell("code", [
        "import os",
        "",
        "if not os.getenv('KAGGLE_IS_COMPETITION_RERUN'):",
        "    import pandas as pd",
        "    stand_in = pd.DataFrame(",
        "        [['1_0', '1', True, 1]],",
        "        columns=['row_id', 'game_id', 'end_of_game', 'score'])",
        "    stand_in.to_parquet('/kaggle/working/submission.parquet', "
        "index=False)",
    ])


def build() -> dict:
    """The notebook as a dict, ready for json.dumps."""
    if not AGENT_SRC.exists():
        raise SystemExit(f"No agent at {AGENT_SRC}")
    if ACCELERATOR not in _ACCELERATORS:
        raise SystemExit(f"ACCELERATOR must be one of {sorted(_ACCELERATORS)},"
                         f" not {ACCELERATOR!r}")
    accel = _ACCELERATORS[ACCELERATOR]
    cells = [
        _cell("markdown", [
            "# ARC-AGI-3 agent",
            "",
            "Generated from `agent/my_agent.py` by `scripts/build_notebook.py`."
            " Edit those files, not this notebook.",
        ]),
        _cell("code", [
            f"!pip install --no-index --find-links {COMPETITION}/arc_agi_3_wheels"
            " arc-agi python-dotenv",
        ]),
        _cell("code", [f"%%writefile {AGENT_TMP}", AGENT_SRC.read_text()]),
        rerun_cell(),
        commit_cell(),
    ]
    return {
        "nbformat": 4,
        "nbformat_minor": 4,
        "metadata": {
            "kernelspec": {"name": "python3", "display_name": "Python 3",
                           "language": "python"},
            "language_info": {"name": "python", "mimetype": "text/x-python",
                              "file_extension": ".py",
                              "pygments_lexer": "ipython3"},
            "kaggle": {"accelerator": accel["name"],
                       "isGpuEnabled": accel["gpu"],
                       "isInternetEnabled": False,
                       "language": "python", "sourceType": "notebook"},
        },
        "cells": cells,
    }


def main() -> None:
    NOTEBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTEBOOK_PATH.write_text(json.dumps(build(), indent=1))
    print(f"wrote {NOTEBOOK_PATH.relative_to(ROOT)} (accelerator {ACCELERATOR})")
    # Kaggle reads the GPU switch from the kernel metadata, not the notebook,
    # so keep the two in step.
    if METADATA_PATH.exists():
        meta = json.loads(METADATA_PATH.read_text())
        if meta.get("enable_gpu") != _ACCELERATORS[ACCELERATOR]["gpu"]:
            meta["enable_gpu"] = _ACCELERATORS[ACCELERATOR]["gpu"]
            METADATA_PATH.write_text(json.dumps(meta, indent=2) + "\n")
            print(f"set enable_gpu={meta['enable_gpu']} in "
                  f"{METADATA_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
