"""The held-out split of the public games (docs/design.md section 2).

The rule: sort the short game ids and put every second one into `held_out`,
starting with the second. No change may be developed against a held-out game
(RULES.md 3). setup writes `pipeline/split.json` once. A later row may rewrite
it once, by this same rule, when more games load, and says so.

    python3 -m pipeline.toolchain run -m pipeline.split   # rewrite split.json
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPLIT_JSON = os.path.join(HERE, "split.json")


def split(game_ids):
    """`(developed, held_out)` for these ids, by the rule above."""
    ids = sorted(set(game_ids))
    return ids[0::2], ids[1::2]


def document(full_ids, written_by, note):
    """The split.json content for these versioned ids (`ls20-9607627b`)."""
    versions = {g.split("-")[0]: g for g in full_ids}
    developed, held_out = split(versions)
    return {"rule": "sort the short game ids; every second one, starting with "
                    "the second, is held_out",
            "written_by": written_by, "note": note,
            "developed": developed, "held_out": held_out,
            "versions": dict(sorted(versions.items()))}


def load(path=SPLIT_JSON):
    with open(path) as f:
        return json.load(f)


def main(argv=None):
    """Rewrite split.json from the games arc_agi lists (needs the 3.12 env)."""
    import arc_agi
    from arc_agi import OperationMode

    from pipeline import toolchain
    repo = os.path.dirname(HERE)
    arc = arc_agi.Arcade(operation_mode=OperationMode.NORMAL,
                         environments_dir=toolchain.games_dir(repo))
    full = [e.game_id for e in arc.get_environments()]
    doc = document(full, "setup, 2026-10-25",
                   f"All {len(full)} public games, listed with anonymous "
                   f"access (no ARC API key).")
    with open(SPLIT_JSON, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print(f"{len(doc['developed'])} developed, {len(doc['held_out'])} held out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
