"""Game-play replays for the project page (docs/design.md section 6).

`pipeline/evaluate.py run --record` keeps the grid after every action of each
developed game and writes one animated GIF per game to the primary
checkout's `var/replays/<run stamp>/<game>.gif`. Held-out games get no GIF
unless `--record-held-out` is given, and then theirs go to
`var/replays-held-out/<run stamp>/`, which nothing lists (RULES.md 3).

After a recorded run, `var/artifacts.json` is rewritten as the newest run's
scoreboard: one image entry per developed game's GIF and one text entry per
held-out game, pointing at the run's result JSON, for whatever page shows
the project's outputs.

Recording never reaches the Kaggle notebook: only the harness imports this.
"""
import json
import os

# The official ARC-AGI-3 16-colour palette, index -> RGB, as the agents
# framework's multimodal template (agents/templates/multimodal.py) gives it.
PALETTE = (
    (0xFF, 0xFF, 0xFF),  # 0 white
    (0xCC, 0xCC, 0xCC),  # 1 off-white
    (0x99, 0x99, 0x99),  # 2 neutral light
    (0x66, 0x66, 0x66),  # 3 neutral
    (0x33, 0x33, 0x33),  # 4 off-black
    (0x00, 0x00, 0x00),  # 5 black
    (0xE5, 0x3A, 0xA3),  # 6 magenta
    (0xFF, 0x7B, 0xCC),  # 7 magenta light
    (0xF9, 0x3C, 0x31),  # 8 red
    (0x1E, 0x93, 0xFF),  # 9 blue
    (0x88, 0xD8, 0xF1),  # 10 blue light
    (0xFF, 0xDC, 0x00),  # 11 yellow
    (0xFF, 0x85, 0x1B),  # 12 orange
    (0x92, 0x12, 0x31),  # 13 maroon
    (0x4F, 0xCC, 0x30),  # 14 green
    (0xA3, 0x56, 0xD6),  # 15 purple
)
# A 64x64 grid becomes 256 px wide.
SCALE = 4
# At most this many frames per GIF. A longer play is sampled evenly, always
# keeping its first and last frame, so a 10,000-action game still shows its
# whole course in about 40 seconds at FRAME_MS.
MAX_FRAMES = 400
FRAME_MS = 100
# The last frame holds this long before the GIF loops.
LAST_FRAME_MS = 2000


class Recorder:
    """The grid after every action of one play, with the action taken."""

    def __init__(self):
        self.frames = []  # [(action id or None for the start, grid copy)]

    def add(self, action, grid):
        import numpy
        self.frames.append((action, numpy.array(grid, dtype=numpy.uint8)))


def sample(n, cap=MAX_FRAMES):
    """The indices of `n` frames to keep: all of them up to `cap`, else
    `cap` evenly spaced ones from the first to the last."""
    if n <= cap:
        return list(range(n))
    if cap <= 1:
        return [n - 1] if cap == 1 else []
    return [round(i * (n - 1) / (cap - 1)) for i in range(cap)]


def write_gif(path, grids, cap=MAX_FRAMES, scale=SCALE):
    """Write `grids` (2-D, values 0-15) as an animated GIF in the ARC
    palette, each cell `scale` px square, from at most `cap` sampled grids.
    A run of identical sampled grids becomes one frame shown that much
    longer (an action that changed nothing is a pause). Returns the number
    of frames written."""
    from PIL import Image
    keep = sample(len(grids), cap)
    if not keep:
        return 0
    flat = [c for rgb in PALETTE for c in rgb]
    images, durations, last = [], [], None
    for i in keep:
        g = grids[i]
        h, w = len(g), len(g[0])
        cells = bytes(int(v) & 0x0F for row in g for v in row)
        if cells == last:
            durations[-1] += FRAME_MS
            continue
        last = cells
        im = Image.frombytes("P", (w, h), cells)
        im.putpalette(flat)
        images.append(im.resize((w * scale, h * scale), Image.NEAREST))
        durations.append(FRAME_MS)
    durations[-1] += LAST_FRAME_MS - FRAME_MS
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    images[0].save(path, save_all=True, append_images=images[1:],
                   duration=durations, loop=0, optimize=False,
                   disposal=1)
    return len(images)


def title(game):
    """The scoreboard line for one game record of a result."""
    part = "held-out" if game["split"] == "held_out" else "developed"
    line = (f"{game['short']} · {part} · levels {game['levels_completed']}/"
            f"{len(game['baseline_actions'])} · RHAE {game['rhae'] * 100:.2f}%")
    return line + (" (score only, no replay)" if part == "held-out" else "")


def _listed_path(path, repo):
    """`path` relative to `repo` when it sits inside it, else absolute."""
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(repo))
    return os.path.abspath(path) if rel.startswith("..") else rel


def index_entries(result, result_path, gifs, repo, stamp, row=""):
    """The var/artifacts.json list for one run, best RHAE first.

    `gifs` maps a game's short id to its developed-game GIF. Developed games
    with a GIF are images; held-out games are text entries pointing at the
    run's result JSON, never at a GIF. A developed game without a GIF (it
    made no frame) is left out, since an entry needs a file."""
    made_at = result["started"]
    commit = result["commit"][:12]
    out = []
    games = sorted(result["games"], key=lambda g: (-g["rhae"], g["short"]))
    for g in games:
        if g["split"] == "held_out":
            out.append({"id": f"score/{stamp}/{g['short']}", "title": title(g),
                        "kind": "text", "path": _listed_path(result_path, repo),
                        "made_at": made_at, "commit": commit, "row": row})
        elif g["short"] in gifs:
            out.append({"id": f"replay/{stamp}/{g['short']}", "title": title(g),
                        "kind": "image", "path": _listed_path(gifs[g["short"]],
                                                              repo),
                        "made_at": made_at, "commit": commit, "row": row})
    return out


def write_index(path, entries):
    """Replace `path` with `entries`, atomically."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(entries, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)
