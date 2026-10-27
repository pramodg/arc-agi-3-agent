# Setup -- the toolchain, the starter layout, and what each part is licensed under

Written on 2026-10-25 when the toolchain was set up; the starter-kit and
licence sections were rewritten the same day, when the ported files were
replaced with our own code.

## Quick start

```sh
make setup        # build or reuse the shared Python 3.12 env, link vendor/
make play-local   # the agent on every public game (GAME=ls20 for one)
make test         # the unit tests on that same interpreter
make notebook     # notebooks/submission.ipynb from agent/my_agent.py
make play-random  # the random agent we compare against, at its committed cap
```

`make submit` and `make status` need a Kaggle token at `.kaggle/access_token`
and your Kaggle handle in `notebooks/kernel-metadata.json` in place of
`REPLACE_WITH_YOUR_USERNAME`.

## Python 3.12: one shared environment

The box has Python 3.11. The `arc-agi` package needs 3.12.
`pipeline/toolchain.py` builds one environment for every worktree, beside the
primary checkout, at `~/domains/arc-agi-3/var/`:

| Path under `var/` | What |
|---|---|
| `uv/` | the uv binary, downloaded there. Nothing goes on PATH. |
| `uv-python/`, `uv-cache/` | uv's CPython 3.12 install and its package cache |
| `py312/` | the virtualenv. `py312/READY` records the pins it was built for. |
| `vendor/ARC-AGI-3-Agents-<sha12>/` | the agents framework at a pinned commit, slimmed |
| `environment_files/` | the cached public game files |

`python3 -m pipeline.toolchain ensure` builds whatever is missing, under a
lock, and links the worktree's gitignored `vendor/ARC-AGI-3-Agents` to the
shared framework copy. When a pin in `pipeline/toolchain.py` changes, the
`READY` stamp no longer matches and the next `ensure` reinstalls. `make test`
and the gate (`pipeline/validate.sh`) both run through it, so the tests run
on the interpreter the agent runs on.

Pinned on 2026-10-25: Python 3.12.15, arc-agi 0.9.9, arcengine 0.9.3,
kaggle 2.2.5, and ARC-AGI-3-Agents commit `4743e7d0aaae`.

## Games

With no ARC API key, arc-agi fetched an anonymous key and listed all 25 public
games. The docs said anonymous access gives 3. Every game downloaded into
`var/environment_files/`, and `scripts/play_local.py --offline` then plays
them with no network.

`pipeline/split.json` holds the held-out split: 13 developed games and 12
held out. No change may be
developed against a held-out game (RULES.md 3).

## The random agent we compare against

`scripts/random_agent.py` is the framework's `Random` template with its action
cap set in the file: `RANDOM_MAX_ACTIONS = 10000`, the cap of the first
comparison with our explorer (docs/baseline.md). `make play-random` plays it on
every public game, and `pipeline/evaluate.py run --agent
scripts/random_agent.py` scores it. `STEPS=` or `--max-actions` can only
lower the cap; 80 reproduces the framework's own default.

## Where the starter layout came from, and what is left of it

The layout follows the official ARC-AGI-3-Kaggle-Starter at commit
`eeb1535`, which declares no licence. Every file that was first ported from
it has since been rewritten as our own code under MIT-0:

| File | Status |
|---|---|
| `agent/my_agent.py` | Our own explorer. The starter's random agent was replaced, and the last ported lines were rewritten. |
| `Makefile` | Rewritten. |
| `scripts/play_local.py` | Rewritten. It also takes `--agent`, so the random agent can be played. |
| `scripts/build_notebook.py` and the notebook cells it writes | Rewritten. |
| `scripts/slim_framework.py` | Rewritten. |
| `notebooks/kernel-metadata.json` | Kept. It holds only the settings Kaggle's CLI requires (kernel id, title, notebook file, competition, internet and GPU switches). Those are facts about our kernel, not authored code. |

The notebook still does what Kaggle's rerun requires, and so does any entry:
it installs `arc-agi` from the competition's offline wheels, waits for the
gateway at `gateway:8001`, copies the competition's ARC-AGI-3-Agents
framework somewhere writable, registers `MyAgent` in place of the framework's
registry, points the framework at the gateway, and runs `main.py`. The paths,
the gateway settings and the registry it writes are the competition's and the
MIT framework's interface. The code around them is ours.

What the framework requires of an agent (subclass `Agent`, name the class
`MyAgent`, define `is_done` and `choose_action`) is the framework's MIT
contract, not starter code.

## Licences (RULES.md 5)

| Component | Where it lives | Licence |
|---|---|---|
| Our own code, including every file above | this repository | **MIT-0** (`LICENSE`) |
| ARC-AGI-3-Agents framework | `vendor/`, gitignored; on Kaggle from the competition dataset | MIT (Copyright 2025 ARC Prize) |
| `arc-agi` package | the 3.12 env; on Kaggle from the competition wheels | MIT (ARC Prize Foundation) |
| `arcengine` package | the 3.12 env | MIT (ARC Prize Foundation) |
| `kaggle` CLI | the 3.12 env, used only to push notebooks | Apache-2.0 |
| uv | `var/uv/`, a build tool only | MIT or Apache-2.0 |
| ARC-AGI-3-Kaggle-Starter | nothing of it remains in this repository | none declared |

None of the third-party parts is copied into the repository: each is
installed or fetched at setup time.
