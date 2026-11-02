"""Write the Duck fork's Kaggle notebook and its kernel metadata.

The fork is Franzen's public `dfranzen/arc-agi-3-milestone-2-solution`
(Tufa Labs' Duck harness with his patch, serving Qwen3.8-Flash-Next on an
RTX Pro 6000). His notebook and metadata are kept verbatim in
`duck/upstream/`; this script makes our copy from them with only these
changes (docs/duck.md):

1. The server startup deadline goes from 12 to 40 minutes. Forum topic
   753007: the model now loads past 12 minutes, and notebooks that scored
   about 30% scored 0.00%.
2. A short commit run. Outside a competition rerun the model server, the
   precache and the demo games are skipped and a stand-in
   `submission.parquet` is written, unless the evaluation switch is on
   (`--evaluate`, or `DUCK_EVALUATE=1` in the run). The gate's source is
   `duck/gate_cell.py`; the stand-in is `duck/standin_cell.py`.
3. A new private kernel id under our account, never the explorer's.
4. The solved-level memory (`duck/solved_level_memory.py`, from the public
   notebook vickyfym/arc-agi-3-lalalia-final): each cleared level's facts
   and the model's own one-line rule are pinned at the end of the system
   prompt. It is pasted into Franzen's customization cell, so it runs only
   when the games are played.
5. The no-op repeat guard is on (`ARC3_NOOP_REPEAT_GUARD=1`, a switch in
   Franzen's harness that he ships off). The harness then refuses to repeat
   an action that changed nothing in the same board state, unless the model
   issues it twice in a row.
6. The D' priority scheduler (`duck/d_prime_scheduler.py`, from the public
   notebook yongjiehishi/arc3-duck-lab-t06): a gated cell right after the
   customization cell replaces the formula that decides which game streams
   get the model next, and stops unstarted games always going first.
7. The model is ThinkingCap (bottlecapai's fine-tune of the same
   Qwen3.8-Flash-Next, in the same Intel W4A16 AutoRound packaging, Kaggle
   model lamdang/thinkingcap-qwen3-8-flash-next-w4a16-autoround) instead of
   Franzen's Intel quantization of the base model. Only the model input and
   `MODEL_DIR` change; the drafter, the tokenizer's chat template and the
   serving settings stay. The env cell, which runs at commit too, checks the
   model's config is mounted, so a wrong path fails the short commit run.

Everything else, including the harness patch and the sglang launcher, is
Franzen's unchanged. Never edit `notebooks/duck/` by hand; rerun this.

Changes 1 to 3 are in every build. Changes 4 to 7 and the opening markdown
come from a variant file, `duck/variants/NAME.toml` (`--variant NAME`): V1 is
the plain fork and each of V2 to V5 adds one change to the one before. The
default, V5, is the submission. Any other `<family>-<name>` file whose family
is not a bet's below (`speed-*`, `explore-*`, ...) is in the same format and
builds on its `base` chain with no edit here.

The bets in the same directory keep their own formats, and `--variant` builds
them too: the fork variant they name as `base` (`--base` overrides it), plus

- framework-*: one gated cell per `[[cells]]` entry, rendered by
  duck/frameworks/library.py, after the customization cell (docs/frameworks.md);
- jev-*: the `[[cells]]` files, gated, after the customization cell, with the
  `[env]` table set in the first of them (docs/jev-in-game.md);
- worldmodel-*: the planner cell duck/world_model/build.py renders, before
  the run cell, on base v5 when the file names none (docs/world-model.md).

Franzen writes his 499 KB harness patch in one `%%writefile` cell. Ours keeps
it as pieces under `duck/harness/` (one per patched file, the long ones cut
into consecutive hunk groups, each under 50,000 characters, because Gemini
chefs read only the first 60,000 characters of a file). The notebook gets one
`%%writefile` cell per piece and a cell that joins them, checks the result is
byte-identical to Franzen's patch, and writes it where his env cell applies it.

    python3 -m pipeline.toolchain run scripts/build_duck_notebook.py [--evaluate] [--variant v3 --out DIR]
    python3 -m pipeline.toolchain run scripts/build_duck_notebook.py --variant jev-gates [--base v2] --out DIR
    python3 -m pipeline.toolchain run scripts/build_duck_notebook.py --kernel-id ID --out DIR
    python3 -m pipeline.toolchain run scripts/build_duck_notebook.py --write-harness
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DUCK = ROOT / "duck"
UPSTREAM_NOTEBOOK = DUCK / "upstream" / "arc-agi-3-milestone-2-solution.ipynb"
UPSTREAM_METADATA = DUCK / "upstream" / "kernel-metadata.json"
OUT_DIR = ROOT / "notebooks" / "duck"
HARNESS = DUCK / "harness"

EXPLORER_KERNEL = "pramodgupta15/arc-prize-2026-arc-agi-3-agent"
KERNEL_ID = "pramodgupta15/arc-agi-3-duck-fork"
TITLE = "ARC-AGI-3 Duck Fork"   # Kaggle derives the slug from the title.
CODE_FILE = "arc-agi-3-duck-fork.ipynb"

STARTUP_TIMEOUT_MIN = 40
_UPSTREAM_TIMEOUT = "SERVER_STARTUP_TIMEOUT = 12 * 60\n"
_OUR_TIMEOUT = (f"SERVER_STARTUP_TIMEOUT = {STARTUP_TIMEOUT_MIN} * 60"
                "  # duck-fork: was 12 * 60 (forum topic 753007)\n")

# Franzen's cells that serve the model or play the games, found by their
# first line so a moved cell fails the build instead of running ungated.
_GATED = (
    "import os\nimport threading",                     # precache (6.6 GB read)
    "# Paste this entire file into the launcher cell.",  # sglang server
    "# Restore the deployment target",                 # load the benchmark
    "# Make one-off changes to `bm`",                  # benchmark settings
    "# --- system census",                             # monitor thread
    "from html import escape",                         # diagnostics
)
# The run cell has a top-level `await`, which a nested run_cell cannot run,
# so it is indented under `if RUN_GAMES:` instead of taking the magic.
_RUN_CELL = "print('Starting benchmark...')"
_ENV_CELL = "import json\nimport os\nimport pickle"
# The variant files' parts, named here for the tests: the memory patch, the
# D' scheduler and the model swap (Franzen's Intel quantization of
# Qwen3.8-Flash-Next becomes the ThinkingCap fine-tune; the drafter stays).
MEMORY_PATCH = DUCK / "solved_level_memory.py"
D_PRIME = DUCK / "d_prime_scheduler.py"
UPSTREAM_MODEL = "dfranzen/intel-qwen3.8-flash-next-w4a16-autoround/Transformers/default/1"
MODEL = "lamdang/thinkingcap-qwen3-8-flash-next-w4a16-autoround/Transformers/default/1"

VARIANTS = DUCK / "variants"
DEFAULT_VARIANT = "v5"   # the submission build: every change above

# The harness patch. Gemini chefs read the first 60,000 characters of a file
# (ledger L-1695b5), so no piece and no notebook cell may be longer than that.
CELL_LIMIT = 60_000
PIECE_LIMIT = 50_000
_PATCH_CELL = "%%writefile /kaggle/harness-changes.patch\n"
_PIECE_PATH = "/kaggle/harness-part-"


def load_variant(name: str) -> dict:
    """`duck/variants/NAME.toml`, folded onto its base chain.

    A variant names its `base` and adds to it: `intro` (the opening markdown,
    whole, replacing the base's), `[[env]]` line edits to the env cell (or to
    the upstream cell whose first line an entry names as `cell`), `[[paste]]`
    files pasted after a cell's first line, `[[cells]]` new cells after a
    cell, and `[[inputs]]` kernel model inputs swapped. Lists add up base
    first, so V5 is V4 plus its own changes.
    """
    seen, chain = set(), []
    while name:
        if not OURS.fullmatch(name):
            raise SystemExit(f"{name!r} is not a fork variant (those are v1, v2, ... and <family>-<name> outside {', '.join(BETS)})")
        if name in seen:
            raise SystemExit(f"variant base loop at {name!r}")
        seen.add(name)
        path = VARIANTS / f"{name}.toml"
        if not path.is_file():
            raise SystemExit(f"no variant file {path}")
        spec = tomllib.loads(path.read_text())
        chain.append(spec)
        name = spec.get("base", "")
    out = {"intro": None, "env": [], "paste": [], "cells": [], "inputs": []}
    for spec in reversed(chain):
        if "intro" in spec:
            out["intro"] = spec["intro"]
        for key in ("env", "paste", "cells", "inputs"):
            out[key] += spec.get(key, [])
    if out["intro"] is None:
        raise SystemExit("variant chain has no intro")
    return out


# The fork's own variants are v1, v2, ... and any <family>-<name> (speed-*,
# explore-*, ...), chained by `base`. The bets keep their own formats in the
# same directory, by name prefix.
BETS = ("framework-", "jev-", "worldmodel-")
OURS = re.compile(r"v\d+|(?!" + "|".join(BETS) + r")[a-z][a-z0-9]*-[a-z0-9-]+")


def variants() -> list[str]:
    """The fork's own variants, the ones a bet may name as its base."""
    return sorted(p.stem for p in VARIANTS.glob("*.toml") if OURS.fullmatch(p.stem))


def all_variants() -> list[str]:
    """Every file in duck/variants/ that --variant builds."""
    return sorted(p.stem for p in VARIANTS.glob("*.toml")
                  if OURS.fullmatch(p.stem) or p.stem.startswith(BETS))


def _bet(name: str) -> str | None:
    """The bet family `name` belongs to, or None for a fork variant."""
    family = next((b for b in BETS if name.startswith(b)), None)
    if family is None and not OURS.fullmatch(name):
        raise SystemExit(f"{name!r} is neither a fork variant nor a bet ({', '.join(BETS)})")
    if family and not (VARIANTS / f"{name}.toml").is_file():
        raise SystemExit(f"no variant file {VARIANTS / name}.toml")
    return family


def _imports() -> None:
    """The bets' own renderers live in the duck package."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def bet_base(name: str, base: str | None = None) -> str:
    """The fork variant a bet builds on: `base`, else the file's, else (world
    model only) the default build."""
    if base:
        return base
    spec = tomllib.loads((VARIANTS / f"{name}.toml").read_text())
    if "base" not in spec and name.startswith("worldmodel-"):
        return DEFAULT_VARIANT
    return spec["base"]


def _src(cell: dict) -> str:
    s = cell["source"]
    return s if isinstance(s, str) else "".join(s)


def _code(source: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": source}


def _body(cell: dict) -> str:
    """A cell's source past any leading %%duck_games line."""
    return _src(cell).removeprefix("%%duck_games\n")


def _find(cells: list, head: str) -> int:
    hits = [i for i, c in enumerate(cells)
            if c["cell_type"] == "code" and _src(c).startswith(head)]
    if len(hits) != 1:
        raise SystemExit(f"expected one upstream cell starting {head!r}, found {len(hits)}")
    return hits[0]


def gate_source(evaluate: bool) -> str:
    text = (DUCK / "gate_cell.py").read_text()
    return text.replace("__DUCK_EVALUATE__", "True" if evaluate else "False")


def franzen_patch() -> str:
    """The file Franzen's patch cell writes. IPython ends a cell with a newline
    before running it, so `%%writefile` writes his body plus a final newline."""
    cells = json.loads(UPSTREAM_NOTEBOOK.read_text())["cells"]
    body = _src(cells[_find(cells, _PATCH_CELL)])[len(_PATCH_CELL):]
    return body if body.endswith("\n") else body + "\n"


def _lines(text: str) -> list[str]:
    return re.findall(r"[^\n]*\n|[^\n]+$", text)


def _pack(parts: list[str], limit: int) -> list[str]:
    """Consecutive parts joined greedily into groups of at most `limit`
    characters. A part over the limit is cut at line ends first."""
    units = []
    for part in parts:
        if len(part) <= limit:
            units.append(part)
        elif any(len(line) > limit for line in _lines(part)):
            raise SystemExit(f"a patch line is over {limit} characters")
        else:
            units += _pack(_lines(part), limit)
    groups = [""]
    for unit in units:
        if groups[-1] and len(groups[-1]) + len(unit) > limit:
            groups.append("")
        groups[-1] += unit
    return groups


def split_patch(text: str, limit: int = PIECE_LIMIT) -> list[tuple[str, str]]:
    """(file name, text) pieces whose concatenation is `text`: one per patched
    file, numbered in patch order, with a file over `limit` cut into
    consecutive hunk groups named -01, -02, ..."""
    files = re.split(r"(?m)^(?=diff --git )", text)
    if files[0]:
        raise SystemExit("the harness patch does not start with a diff")
    pieces = []
    for n, diff in enumerate(files[1:], 1):
        stem = f"{n:02d}-{Path(diff.split(chr(10), 1)[0].rsplit(' b/', 1)[1]).name}"
        groups = _pack(re.split(r"(?m)^(?=@@ )", diff), limit)
        if len(groups) == 1:
            pieces.append((f"{stem}.patch", groups[0]))
        else:
            pieces += [(f"{stem}-{k:02d}.patch", g) for k, g in enumerate(groups, 1)]
    return pieces


def harness_pieces() -> list[tuple[str, str]]:
    """The pieces in duck/harness/, checked to join into Franzen's patch."""
    pieces = [(p.name, p.read_text()) for p in sorted(HARNESS.glob("*.patch"))]
    if "".join(t for _, t in pieces) != franzen_patch():
        raise SystemExit("duck/harness/ does not join into Franzen's patch; "
                         "rerun with --write-harness")
    return pieces


def write_harness() -> list[Path]:
    """Rewrite duck/harness/ from Franzen's patch."""
    HARNESS.mkdir(exist_ok=True)
    for old in HARNESS.glob("*.patch"):
        old.unlink()
    paths = []
    for name, text in split_patch(franzen_patch()):
        (HARNESS / name).write_text(text)
        paths.append(HARNESS / name)
    return paths


def _blank_lines(text: str) -> dict[int, str]:
    """Line number to text of each whitespace-only line. Some IPython versions
    (9.17) empty such lines in a cell before `%%writefile` sees it."""
    return {i: line for i, line in enumerate(text.split("\n"))
            if line and not line.strip()}


def harness_cells() -> list[dict]:
    """One %%writefile cell per piece, then the cell that joins them into
    /kaggle/harness-changes.patch, which Franzen's env cell applies. The join
    puts back a whitespace-only line IPython emptied, and nothing else, then
    checks the sha256 of the whole patch against Franzen's."""
    pieces = harness_pieces()
    digest = hashlib.sha256(franzen_patch().encode()).hexdigest()
    blanks = {name: b for name, text in pieces if (b := _blank_lines(text))}
    cells = [_code(f"%%writefile {_PIECE_PATH}{name}\n{text}") for name, text in pieces]
    cells.append(_code(
        "# Join Franzen's harness patch from its pieces (duck/harness/ in our repository,\n"
        "# split by scripts/build_duck_notebook.py so no cell is over 60,000 characters).\n"
        "# The env cell below applies /kaggle/harness-changes.patch with git apply.\n"
        "import hashlib as _hp_hashlib\n"
        "from pathlib import Path as _HpPath\n"
        f"_HP_PARTS = {[name for name, _ in pieces]!r}\n"
        "# Whitespace-only lines by piece and line number: an IPython that empties\n"
        "# them before %%writefile runs gets them back here.\n"
        f"_HP_BLANKS = {blanks!r}\n"
        "def _hp_read(name):\n"
        f"    lines = _HpPath('{_PIECE_PATH}' + name).read_bytes().split(b'\\n')\n"
        "    for i, text in _HP_BLANKS.get(name, {}).items():\n"
        "        if i < len(lines) and lines[i] == b'':\n"
        "            lines[i] = text.encode()\n"
        "    return b'\\n'.join(lines)\n"
        "_hp_patch = b''.join(_hp_read(n) for n in _HP_PARTS)\n"
        f"if _hp_hashlib.sha256(_hp_patch).hexdigest() != '{digest}':\n"
        "    raise RuntimeError(\"the joined harness patch is not Franzen's\")\n"
        "_HpPath('/kaggle/harness-changes.patch').write_bytes(_hp_patch)\n"
        "print(f'harness patch joined from {len(_HP_PARTS)} pieces, {len(_hp_patch)} bytes')\n"))
    return cells


def split_harness(nb: dict) -> dict:
    """Replace Franzen's one patch cell in a built notebook with the pieces."""
    cells = nb["cells"]
    at = _find(cells, _PATCH_CELL)
    upstream = json.loads(UPSTREAM_NOTEBOOK.read_text())["cells"]
    if _src(cells[at]) != _src(upstream[_find(upstream, _PATCH_CELL)]):
        raise SystemExit("the notebook's harness patch cell is not Franzen's")
    cells[at:at + 1] = harness_cells()
    return nb


def framework_cells(nb: dict, name: str) -> dict:
    """A framework-* bet's cells, each gated, after its anchor and after any
    cells already inserted there (docs/frameworks.md)."""
    _imports()
    from duck.frameworks import library
    cells, placed = nb["cells"], {}
    for anchor, src in library.variant_cells(VARIANTS / f"{name}.toml"):
        hits = [i for i, c in enumerate(cells)
                if c["cell_type"] == "code" and _body(c).startswith(anchor)]
        if len(hits) != 1:
            raise SystemExit(f"expected one cell starting {anchor!r}, found {len(hits)}")
        cells.insert(hits[0] + placed.get(anchor, 0) + 1, _code("%%duck_games\n" + src))
        placed[anchor] = placed.get(anchor, 0) + 1
    return nb


def jev_cells(nb: dict, spec: dict) -> dict:
    """A jev-* bet's cells (docs/jev-in-game.md). Each goes straight after its
    `after` cell, which is a cell's first line or an earlier entry's `file`;
    the first sets the `[env]` table before its own code."""
    cells, placed = nb["cells"], {}
    env_lines = "".join(f"os.environ[{k!r}] = {v!r}\n" for k, v in spec.get("env", {}).items())
    for n, cell in enumerate(spec["cells"]):
        if cell["after"] in placed:
            at = placed[cell["after"]]
        else:
            hits = [i for i, c in enumerate(cells)
                    if c["cell_type"] == "code" and _body(c).startswith(cell["after"])]
            if len(hits) != 1:
                raise SystemExit(f"expected one cell starting {cell['after']!r}, found {len(hits)}")
            at = hits[0]
        src = (ROOT / cell["file"]).read_text()
        if n == 0:
            src = "import os\n" + env_lines + src
        if cell.get("gated"):
            src = "%%duck_games\n" + src
        cells.insert(at + 1, _code(src))
        placed = {k: (i + 1 if i > at else i) for k, i in placed.items()}
        placed[cell["file"]] = at + 1
    return nb


def build(evaluate: bool = False, variant: str = DEFAULT_VARIANT, split: bool = True,
          base: str | None = None) -> dict:
    """The notebook of any variant file as a dict. `split=False` keeps
    Franzen's one patch cell, which rebuilds the notebooks scored before the
    split. `base` puts a bet on another fork variant than its file names."""
    family = _bet(variant)
    if family is None:
        if base:
            raise SystemExit(f"{variant} is a fork variant; only a bet takes a base")
        return _fork(evaluate, variant, split)
    base = bet_base(variant, base)
    if family == "worldmodel-":
        _imports()
        from duck.world_model import build as wmb
        return wmb.build(wmb.load(VARIANTS / f"{variant}.toml", base), evaluate, split)
    nb = _fork(evaluate, base, split)
    if family == "framework-":
        return framework_cells(nb, variant)
    return jev_cells(nb, tomllib.loads((VARIANTS / f"{variant}.toml").read_text()))


def _fork(evaluate: bool, variant: str, split: bool) -> dict:
    """A fork variant (v*, speed-*, any non-bet family) from Franzen's notebook."""
    spec = load_variant(variant)
    nb = copy.deepcopy(json.loads(UPSTREAM_NOTEBOOK.read_text()))
    cells = nb["cells"]

    env = _find(cells, _ENV_CELL)
    if _src(cells[env]).count(_UPSTREAM_TIMEOUT) != 1:
        raise SystemExit("upstream startup timeout line not found")
    for edit in spec["env"]:
        i = _find(cells, edit.get("cell", _ENV_CELL))
        src = _src(cells[i])
        if src.count(edit["old"]) != 1 or edit.get("absent", "\0") in src:
            raise SystemExit(f"cell line not found as expected: {edit['old']!r}")
        cells[i]["source"] = src.replace(edit["old"], edit["new"])
    cells[env]["source"] = _src(cells[env]).replace(_UPSTREAM_TIMEOUT, _OUR_TIMEOUT)

    for paste in spec["paste"]:
        i = _find(cells, paste["cell"])
        first, rest = _src(cells[i]).split("\n", 1)
        cells[i]["source"] = f"{first}\n{(ROOT / paste['file']).read_text()}\n{rest}"

    for head in _GATED:
        i = _find(cells, head)
        cells[i]["source"] = "%%duck_games\n" + _src(cells[i])
    placed: dict[str, int] = {}
    for cell in spec["cells"]:
        after = cell["after"]
        try:
            i = _find(cells, after)
        except SystemExit:
            i = _find(cells, "%%duck_games\n" + after)
        i += placed.get(after, 0) + 1   # several cells after one keep their order
        placed[after] = placed.get(after, 0) + 1
        text = (ROOT / cell["file"]).read_text()
        cells.insert(i, _code(("%%duck_games\n" if cell.get("gated") else "") + text))
    run = _find(cells, _RUN_CELL)
    body = _src(cells[run])
    if '"""' in body or "'''" in body or "\n!" in body or "\n%" in body:
        raise SystemExit("the run cell cannot be indented safely any more")
    cells[run]["source"] = "if RUN_GAMES:\n" + "".join(
        ("    " + line if line.strip() else line) for line in body.splitlines(True))

    env = _find(cells, _ENV_CELL)
    cells.insert(env + 1, _code(gate_source(evaluate)))
    cells.append(_code((DUCK / "standin_cell.py").read_text()))
    cells.insert(0, {"cell_type": "markdown", "metadata": {}, "source": spec["intro"]})
    return split_harness(nb) if split else nb


def metadata(variant: str = DEFAULT_VARIANT, kernel_id: str = KERNEL_ID,
             base: str | None = None) -> dict:
    """Franzen's kernel metadata, with our id, title, code file, privacy and the
    variant's model inputs (a bet's are its base's). Another kernel id (a
    scratch kernel for a test push) takes its slug as the title, since Kaggle
    derives the slug from it."""
    if _bet(variant):
        variant = bet_base(variant, base)
    meta = json.loads(UPSTREAM_METADATA.read_text())
    meta.pop("id_no", None)
    title = TITLE if kernel_id == KERNEL_ID else kernel_id.split("/", 1)[1]
    meta.update(id=kernel_id, title=title, code_file=CODE_FILE, is_private=True)
    for swap in load_variant(variant)["inputs"]:
        models = meta["model_sources"]
        if models.count(swap["old"]) != 1:
            raise SystemExit(f"model input {swap['old']!r} not found")
        meta["model_sources"] = [swap["new"] if m == swap["old"] else m for m in models]
    return meta


def notebook_text(evaluate: bool = False, variant: str = DEFAULT_VARIANT,
                  split: bool = True, base: str | None = None) -> str:
    return json.dumps(build(evaluate, variant, split, base), indent=1, ensure_ascii=False) + "\n"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def write(out_dir: Path = OUT_DIR, evaluate: bool = False,
          variant: str = DEFAULT_VARIANT, kernel_id: str = KERNEL_ID,
          base: str | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / CODE_FILE
    path.write_text(notebook_text(evaluate, variant, base=base))
    (out_dir / "kernel-metadata.json").write_text(
        json.dumps(metadata(variant, kernel_id, base), indent=2) + "\n")
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--evaluate", action="store_true",
                   help="play the demo games in the commit run (hours of GPU quota)")
    p.add_argument("--variant", default=DEFAULT_VARIANT,
                   help=f"duck/variants/NAME.toml to build (default {DEFAULT_VARIANT}, the submission)")
    p.add_argument("--base", help="fork variant to build a bet on, overriding its file's base")
    p.add_argument("--out", type=Path, default=OUT_DIR)
    p.add_argument("--kernel-id", default=KERNEL_ID,
                   help="push target in the metadata (default: the fork kernel)")
    p.add_argument("--write-harness", action="store_true",
                   help="rewrite duck/harness/ from Franzen's patch and stop")
    a = p.parse_args()
    if a.write_harness:
        for path in write_harness():
            print(f"wrote {path.relative_to(ROOT)} ({len(path.read_text())} characters)")
        return
    if (a.variant != DEFAULT_VARIANT or a.kernel_id != KERNEL_ID or a.base) and a.out == OUT_DIR:
        p.error("only the default variant and kernel may overwrite notebooks/duck/; pass --out")
    path = write(a.out, a.evaluate, a.variant, a.kernel_id, a.base)
    print(f"wrote {path} sha256 {sha256(path.read_text())}")


if __name__ == "__main__":
    main()
