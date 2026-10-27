"""Play an agent over every public game under competition rules and score it
with RHAE (docs/scoring.md, docs/design.md section 4).

    python3 -m pipeline.toolchain run -m pipeline.evaluate run [RUN OPTIONS]

A full run over every public game takes about half an hour at 10,000
actions a game, so run it as a background job; one or two games are fine in
the foreground.

Competition rules, as docs.arcprize.org/toolkit/competition_mode.md states
them and Kaggle forces them:

- one make() per game, so one play: every RESET after make() is a level
  reset (the engine's ONLY_RESET_LEVELS switch), and the game ends at WIN;
- a wall-clock limit per game, checked before every action;
- nobody reads the score until every game has finished.

`--online` plays the same games on the official server in competition mode
(three.arcprize.org, anonymous key unless ARC_API_KEY is set) instead of
locally, and its scorecard is the official one to compare against. The
submitted agent never does this: only the harness talks to the server.

Each run writes one JSON file under the shared `var/eval/` and prints a
per-game table, split developed against / held out (pipeline/split.json),
then one line with the total RHAE. Our score (pipeline/scorer.py, from our
own step trace) sits beside the toolkit's scorecard for the same run.

`--record` also writes a GIF of each developed game's play and rewrites
`var/artifacts.json` for the project page (pipeline/replay.py). It is off
by default and needs a full run: with `--games` it is refused, because the
index it rewrites is the scoreboard of every game. The frames are kept in
memory during play and the GIFs are written after each game's clock has
stopped.
"""
import argparse
import datetime
import glob
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time

from pipeline import replay, scorer, split, toolchain

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The Kaggle notebook may run for 9 hours, and the agent stops each game at
# 75% of that (MyAgent.MAX_SECONDS). Kaggle plays the 55 private games at
# once, one thread each, so they share one interpreter's time; locally the
# games run one after another with the whole machine each. A game's local
# limit is therefore its share of the same 75% of 9 hours.
KAGGLE_RUNTIME_S = 9 * 3600
AGENT_SHARE = 0.75
PRIVATE_GAMES = 55
PER_GAME_SECONDS = int(AGENT_SHARE * KAGGLE_RUNTIME_S / PRIVATE_GAMES)
# Totals that differ by less than this (in RHAE percent) agree within rounding.
AGREE_PCT = 0.01
# The official server refused requests after ~380 in 45 s (HTTP 429) on
# 2026-10-25, below its documented 600 a minute, so online runs keep to one
# step every 0.25 s and wait out a refusal.
ONLINE_PACE_S = 0.25
RETRY_WAITS = (5, 15, 30, 60, 60)


def baselines(games_dir):
    """`{versioned game id: {"baseline_actions": [...], "source": ...}}` from
    the cached game metadata, which the toolkit downloads from
    three.arcprize.org with each game and scores against."""
    out = {}
    for path in sorted(glob.glob(os.path.join(games_dir, "*", "*",
                                              "metadata.json"))):
        with open(path) as f:
            meta = json.load(f)
        out[meta["game_id"]] = {
            "baseline_actions": meta.get("baseline_actions") or [],
            "source": f"{os.path.relpath(path, games_dir)} (downloaded "
                      f"{meta.get('date_downloaded', '?')})"}
    return out


def game_rows(versions, held_out):
    """`[(short id, versioned id, "developed"|"held_out")]` in split order."""
    return [(short, full, "held_out" if short in held_out else "developed")
            for short, full in sorted(versions.items())]


def summarise(games):
    """Totals over the per-game records, ours and the toolkit's."""
    def mean(key, rows):
        return scorer.total_score(g[key] for g in rows)
    dev = [g for g in games if g["split"] == "developed"]
    held = [g for g in games if g["split"] == "held_out"]
    out = {"rhae": mean("rhae", games), "rhae_developed": mean("rhae", dev),
           "rhae_held_out": mean("rhae", held),
           "toolkit_rhae": mean("toolkit_rhae", games),
           "levels_completed": sum(g["levels_completed"] for g in games),
           "levels": sum(len(g["baseline_actions"]) for g in games),
           "actions": sum(g["actions"] for g in games),
           "games": len(games)}
    out["agrees"] = abs(out["rhae"] - out["toolkit_rhae"]) * 100 < AGREE_PCT
    out["games_disagreeing"] = [
        g["game"] for g in games
        if abs(g["rhae"] - g["toolkit_rhae"]) * 100 >= AGREE_PCT
        or g["actions"] != g["toolkit_actions"]]
    return out


def table(result):
    """The per-game table and the one total line, as printed."""
    lines = [f"{'game':15} {'split':9} {'levels':>7} {'actions':>8} "
             f"{'RHAE%':>7} {'toolkit%':>8} {'secs':>6}  end"]
    for part in ("developed", "held_out"):
        for g in (g for g in result["games"] if g["split"] == part):
            lines.append(
                f"{g['game']:15} {part:9} "
                f"{g['levels_completed']:>3}/{len(g['baseline_actions']):<3} "
                f"{g['actions']:>8} {g['rhae'] * 100:>7.2f} "
                f"{g['toolkit_rhae'] * 100:>8.2f} {g['seconds']:>6.1f}  "
                f"{g['end']}")
    t = result["totals"]
    lines.append(
        f"RHAE {t['rhae'] * 100:.2f}% over {t['games']} games "
        f"(developed {t['rhae_developed'] * 100:.2f}%, held-out "
        f"{t['rhae_held_out'] * 100:.2f}%), levels {t['levels_completed']}/"
        f"{t['levels']}, actions {t['actions']}, toolkit "
        f"{t['toolkit_rhae'] * 100:.2f}% ({'agrees' if t['agrees'] else 'DIFFERS'}), "
        f"{result['mode']}, commit {_short(result['commit'])}, "
        f"{result['seconds']}s")
    return "\n".join(lines)


def _short(commit):
    return commit[:12] + ("-dirty" if commit.endswith("-dirty") else "")


def commit_of(repo):
    got = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                         capture_output=True, text=True)
    sha = got.stdout.strip() if got.returncode == 0 else "unknown"
    dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()
    return sha + ("-dirty" if dirty else "")


def load_agent_class(path):
    spec = importlib.util.spec_from_file_location("evaluated_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MyAgent


def competition_agent(agent_cls, deadline, max_actions, ended):
    """`agent_cls` with the competition's stopping rules on top: the game is
    over at WIN, and the wall-clock limit stops it before the next action.
    `ended` gets the reason."""
    from arcengine import GameState

    class Evaluated(agent_cls):
        def is_done(self, frames, latest_frame):
            if latest_frame.state is GameState.WIN:
                ended.append("win")
                return True
            if time.monotonic() > deadline:
                ended.append("time limit")
                return True
            if super().is_done(frames, latest_frame):
                ended.append("agent done")
                return True
            return False

    if max_actions is not None:
        Evaluated.MAX_ACTIONS = min(agent_cls.MAX_ACTIONS, max_actions)
    return Evaluated


def with_retries(call, waits, retried):
    """`call()` again after each wait in `waits` while it returns None or
    raises: the online server answers HTTP 429 when it is asked too fast,
    and the toolkit turns that into None. A refused call changed nothing,
    so it is safe to send again. `retried` counts the retries."""
    for wait in (*waits, None):
        try:
            got = call()
        except Exception:
            if wait is None:
                raise
            got = None
        if got is not None or wait is None:
            return got
        retried.append(wait)
        time.sleep(wait)


def play(arc, card, short, agent_cls, seconds_limit, max_actions, local,
         pace=0.0, recorder=None):
    """Play one game once on scorecard `card`, at most one step every `pace`
    seconds, handing the grid after every action to `recorder` if given.
    Returns `(steps, end, seconds, versioned id, retries)`."""
    retried = []
    waits = RETRY_WAITS if not local else ()
    started = time.monotonic()
    env = with_retries(lambda: arc.make(short, scorecard_id=card), waits,
                       retried)
    if env is None:
        return [], "no env", 0.0, None, len(retried)
    if env.observation_space is None:  # make()'s own reset was refused
        with_retries(env.reset, waits, retried)
    start = env.observation_space
    if recorder is not None and start is not None and start.frame:
        recorder.add(None, start.frame[-1])
    steps = []
    raw_step = env.step
    last = [0.0]

    def step(action, data=None, reasoning=None):
        def once():
            time.sleep(max(0.0, last[0] + pace - time.monotonic()))
            last[0] = time.monotonic()
            return raw_step(action, data=data, reasoning=reasoning)
        r = with_retries(once, waits, retried)
        if r is not None:
            steps.append({"action": int(action.value), "frames": len(r.frame),
                          "full_reset": bool(r.full_reset),
                          "levels_completed": r.levels_completed,
                          "state": r.state.name})
            if recorder is not None and r.frame:
                recorder.add(int(action.value), r.frame[-1])
        return r
    env.step = step
    ended = []
    agent = competition_agent(agent_cls, started + seconds_limit, max_actions,
                              ended)(
        card_id="local-eval", game_id=short, agent_name=f"eval.{short}",
        ROOT_URL="http://localhost", record=False, arc_env=env,
        tags=["eval"])
    if local:
        # make() has done the one full reset; from here resets are level
        # resets, as the competition server makes them.
        os.environ["ONLY_RESET_LEVELS"] = "true"
    try:
        agent.main()
        end = ended[-1] if ended else "max actions"
    except Exception as e:  # a crash scores what it reached, as on Kaggle
        end = f"error: {type(e).__name__}: {e}"
    finally:
        os.environ.pop("ONLY_RESET_LEVELS", None)
    return steps, end, round(time.monotonic() - started, 2), \
        env.environment_info.game_id, len(retried)


def toolkit_scores(scorecard):
    """`{versioned id: (fraction, actions, levels_completed, plays)}`."""
    out = {}
    for env in (scorecard.environments if scorecard else []):
        out[env.id] = (env.score / 100, env.actions, env.levels_completed,
                       len(env.runs))
    return out


def run(args):
    import importlib.metadata
    import logging
    import platform

    sys.path.insert(0, os.path.join(ROOT, "vendor", "ARC-AGI-3-Agents"))
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    import arc_agi
    from arc_agi import OperationMode

    quiet = logging.getLogger("pipeline.evaluate.arc")
    quiet.setLevel(logging.WARNING)
    logging.getLogger("arc_agi.scorecard").setLevel(logging.WARNING)

    # The commit is read before play, so an edit made while a long run is
    # going cannot be credited to it.
    commit = commit_of(ROOT)
    games_dir = toolchain.games_dir(ROOT)
    human = baselines(games_dir)
    doc = split.load()
    rows = game_rows(doc["versions"], set(doc["held_out"]))
    if args.games:
        want = {g.split("-")[0] for g in args.games.split(",")}
        rows = [r for r in rows if r[0] in want]
    agent_path = os.path.abspath(args.agent)
    with open(agent_path, "rb") as f:
        agent_sha = hashlib.sha256(f.read()).hexdigest()[:12]
    agent_cls = load_agent_class(agent_path)

    mode = OperationMode.COMPETITION if args.online else OperationMode.OFFLINE
    arc = arc_agi.Arcade(operation_mode=mode, environments_dir=games_dir,
                         logger=quiet)
    card = arc.open_scorecard(tags=["eval-harness"])

    started = time.time()
    stamp = time.strftime('%Y%m%dT%H%M%S', time.gmtime(started))
    var = toolchain.shared_var(ROOT)
    gifs, replays = {}, {}
    played = []
    for short, full, part in rows:
        pace = ONLINE_PACE_S if args.online else 0.0
        held = part == "held_out"
        recorder = replay.Recorder() if (
            args.record_held_out if held else args.record) else None
        steps, end, secs, got, retries = play(
            arc, card, short, agent_cls, args.seconds, args.max_actions,
            local=not args.online, pace=pace, recorder=recorder)
        played.append((short, full, part, steps, end, secs, got, retries))
        print(f"  {short}: {end}, {len(steps)} steps, {secs}s, "
              f"{retries} retries", file=sys.stderr)
        if recorder is not None and recorder.frames:
            gif = os.path.join(var, "replays-held-out" if held else "replays",
                               stamp, f"{short}.gif")
            n = replay.write_gif(gif, [g for _, g in recorder.frames])
            replays[short] = {"path": gif, "frames": n,
                              "recorded": len(recorder.frames)}
            print(f"  {short}: {n} frames of {len(recorder.frames)} -> {gif}",
                  file=sys.stderr)
            if not held:
                gifs[short] = gif
    seconds = round(time.time() - started, 1)
    # Only now, with every game finished, is the score read.
    official = toolkit_scores(with_retries(
        lambda: arc.close_scorecard(card),
        RETRY_WAITS if args.online else (), []))

    games = []
    for short, full, part, steps, end, secs, got, retries in played:
        played_id = got or full
        base = human.get(played_id) or human.get(full) or {}
        mine = scorer.score_play(base.get("baseline_actions", []), steps)
        tk = official.get(played_id) or official.get(full) or (0.0, 0, 0, 0)
        games.append({
            "game": played_id, "short": short, "split": part,
            "version_matches_split": played_id == full, "end": end,
            "seconds": secs, "steps": len(steps), "retries": retries,
            "baseline_actions": base.get("baseline_actions", []),
            "baseline_source": base.get("source", "missing"),
            "rhae": mine["score"], "levels_completed": mine["levels_completed"],
            "actions": mine["actions"], "level_actions": mine["level_actions"],
            "level_scores": mine["level_scores"],
            "toolkit_rhae": tk[0], "toolkit_actions": tk[1],
            "toolkit_levels_completed": tk[2], "toolkit_plays": tk[3]})

    result = {
        "commit": commit, "agent": os.path.relpath(agent_path, ROOT),
        "agent_sha256": agent_sha,
        "agent_max_actions": getattr(agent_cls, "MAX_ACTIONS", None),
        "max_actions": args.max_actions, "per_game_seconds": args.seconds,
        "mode": "online competition" if args.online else "local competition",
        "scorecard_id": card,
        "started": datetime.datetime.fromtimestamp(
            started, datetime.timezone.utc).isoformat(timespec="seconds"),
        "seconds": seconds,
        "versions": {"python": platform.python_version(),
                     "arc-agi": importlib.metadata.version("arc-agi"),
                     "arcengine": importlib.metadata.version("arcengine"),
                     "framework": toolchain.FRAMEWORK_SHA},
        "games": games}
    if replays:
        result["replays"] = replays
    result["totals"] = summarise(games)
    out = args.out or os.path.join(
        var, "eval",
        f"{stamp}-"
        f"{commit[:12]}-{os.path.splitext(os.path.basename(agent_path))[0]}"
        f"-{'online' if args.online else 'local'}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=1)
        f.write("\n")
    print(table(result))
    print(f"result: {out}", file=sys.stderr)
    if args.record:
        index = os.path.join(var, "artifacts.json")
        entries = replay.index_entries(result, out, gifs,
                                       os.path.dirname(var), stamp, args.row)
        replay.write_index(index, entries)
        print(f"replays: {len(gifs)} GIFs in "
              f"{os.path.join(var, 'replays', stamp)}; {index}: "
              f"{len(entries)} entries", file=sys.stderr)
    return 0


def parser():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent", default=os.path.join(ROOT, "agent", "my_agent.py"),
                   help="A file defining MyAgent. Default: agent/my_agent.py.")
    p.add_argument("--games", default=None,
                   help="Comma-separated game ids. Default: every public game.")
    p.add_argument("--seconds", type=float, default=PER_GAME_SECONDS,
                   help=f"Wall-clock limit per game (default {PER_GAME_SECONDS}"
                        ", the agent's share of the Kaggle runtime).")
    p.add_argument("--max-actions", type=int, default=None,
                   help="Lower the agent's own MAX_ACTIONS. Default: keep it, "
                        "as Kaggle does.")
    p.add_argument("--online", action="store_true",
                   help="Play on the official server in competition mode.")
    p.add_argument("--out", default=None, help="Result JSON path.")
    p.add_argument("--record", action="store_true",
                   help="Write a GIF of each developed game to var/replays/"
                        "<run stamp>/ and rewrite var/artifacts.json.")
    p.add_argument("--record-held-out", action="store_true",
                   help="Also write held-out games' GIFs, to var/replays-"
                        "held-out/<run stamp>/, which nothing lists.")
    p.add_argument("--row", default="",
                   help="The work item named in var/artifacts.json entries.")
    return p


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        p = parser()
        args = p.parse_args(argv[1:])
        if args.record and args.games:
            p.error("--record rewrites the scoreboard of every game, so it "
                    "needs a full run: drop --games")
        return run(args)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
