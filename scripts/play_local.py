"""Play an agent on the public ARC-AGI-3 games, here, with no Kaggle involved.

The `arc-agi` package runs the games inside this process, and the agent is
driven by the framework's own `Agent.main()` loop, the loop Kaggle uses.
Game files come from the shared cache (`pipeline/toolchain.py`), so once
they are downloaded `--offline` needs no network.

It reports levels cleared and actions spent per game. It does not score:
RHAE comes from `pipeline/evaluate.py` (docs/scoring.md).

    make play-local GAME=ls20 STEPS=200
    python3 -m pipeline.toolchain run scripts/play_local.py --list
    python3 -m pipeline.toolchain run scripts/play_local.py --offline --json var/play.json
    python3 -m pipeline.toolchain run scripts/play_local.py --agent scripts/random_agent.py
"""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import logging
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import toolchain  # noqa: E402

FRAMEWORK = ROOT / "vendor" / "ARC-AGI-3-Agents"
DEFAULT_AGENT = ROOT / "agent" / "my_agent.py"


def short_id(game_id: str) -> str:
    """The game's name without its version: `ls20-9607627b` is `ls20`."""
    return game_id.split("-", 1)[0]


def resolve_games(all_ids: list[str], wanted: str | None) -> list[str]:
    """Short ids to play, in the order the arcade lists them.

    `wanted` is a comma-separated list, with or without versions. None plays
    every game, as the Kaggle rerun does. An id the arcade lacks is an error.
    """
    available = [short_id(g) for g in all_ids]
    if not wanted:
        return available
    asked = {short_id(w.strip()) for w in wanted.split(",") if w.strip()}
    unknown = sorted(asked.difference(available))
    if unknown:
        raise SystemExit(f"No such game: {', '.join(unknown)}. "
                         "See the ids with --list.")
    return [g for g in available if g in asked]


def agent_class(path: Path):
    """The `MyAgent` class that the file at `path` defines."""
    spec = importlib.util.spec_from_file_location("played_agent", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, "MyAgent", None)
    if cls is None:
        raise SystemExit(f"{path} defines no class MyAgent")
    return cls


def play_one(arc, short: str, cls, render: str | None) -> dict:
    """One game from make() to the agent's stop. Returns its result line."""
    env = arc.make(short, render_mode=render)
    if env is None:
        return {"error": "no env"}
    agent = cls(card_id="local", game_id=short, agent_name=f"local.{short}",
                ROOT_URL="http://localhost", record=False, arc_env=env,
                tags=["local"])
    agent.main()
    last = agent.frames[-1]
    return {"state": last.state.name, "levels_completed": last.levels_completed,
            "win_levels": last.win_levels, "actions": agent.action_counter}


def report(results: list[dict], asked: int, seconds: float) -> None:
    print("\nper game:")
    for r in results:
        if "error" in r:
            print(f"  {r['game']:15} {r['error']}")
        else:
            print(f"  {r['game']:15} levels {r['levels_completed']:>2}/"
                  f"{r['win_levels']:<2}  actions {r['actions']:>6}  "
                  f"{r['state']}")
    ok = [r for r in results if "error" not in r]
    print(f"\ngames played: {len(ok)} of {asked}, levels completed: "
          f"{sum(r['levels_completed'] for r in ok)}, actions: "
          f"{sum(r['actions'] for r in ok)}, wall-clock: {seconds}s")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", type=Path, default=DEFAULT_AGENT,
                    help="File defining MyAgent (default agent/my_agent.py).")
    ap.add_argument("--game", help="Comma-separated game ids (default: all).")
    ap.add_argument("--max-steps", type=int, default=None,
                    help="Lower the agent's MAX_ACTIONS to this per game "
                         "(default: keep the agent's own cap).")
    ap.add_argument("--list", action="store_true", help="List the games.")
    ap.add_argument("--offline", action="store_true",
                    help="Use only the cached game files.")
    ap.add_argument("--json", type=Path, help="Also write the results here.")
    ap.add_argument("--render", choices=["terminal"],
                    help="Draw each step in the terminal.")
    args = ap.parse_args(argv)

    if not FRAMEWORK.exists():
        raise SystemExit(f"No framework at {FRAMEWORK}: run `make setup`.")
    sys.path.insert(0, str(FRAMEWORK))
    import arc_agi
    from arc_agi import OperationMode

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    versions = {"python": platform.python_version(),
                "arc-agi": importlib.metadata.version("arc-agi"),
                "arcengine": importlib.metadata.version("arcengine"),
                "framework": toolchain.FRAMEWORK_SHA}
    print("versions: " + ", ".join(f"{k} {v}" for k, v in versions.items()))

    arc = arc_agi.Arcade(
        operation_mode=OperationMode.OFFLINE if args.offline else OperationMode.NORMAL,
        environments_dir=toolchain.games_dir(str(ROOT)),
        recordings_dir=str(ROOT / "recordings"))
    envs = arc.get_environments()
    if args.list:
        print(f"{len(envs)} games:")
        for e in envs:
            print(f"  {e.game_id}  {getattr(e, 'title', '')}")
        return

    versioned = {short_id(e.game_id): e.game_id for e in envs}
    games = resolve_games(list(versioned.values()), args.game)
    cls = agent_class(args.agent)
    if args.max_steps is not None and hasattr(cls, "MAX_ACTIONS"):
        cls.MAX_ACTIONS = min(cls.MAX_ACTIONS, args.max_steps)
    print(f"MyAgent from {args.agent}, cap "
          f"{getattr(cls, 'MAX_ACTIONS', None)} actions, "
          f"{len(games)} of {len(envs)} games\n")

    results = []
    t0 = time.time()
    for n, short in enumerate(games, 1):
        print(f"--- {n}/{len(games)} {short}")
        r = {"game": versioned[short], **play_one(arc, short, cls, args.render)}
        results.append(r)
        if "error" not in r:
            print(f"    {r['state']}, levels {r['levels_completed']}/"
                  f"{r['win_levels']}, actions {r['actions']}")
    seconds = round(time.time() - t0, 1)

    report(results, len(games), seconds)
    card = arc.get_scorecard()
    print(f"arc-agi scorecard score: {getattr(card, 'score', card)}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(
            {"versions": versions, "agent": str(args.agent),
             "max_steps": args.max_steps, "seconds": seconds,
             "games": results}, indent=1) + "\n")


if __name__ == "__main__":
    main()
