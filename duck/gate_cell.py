# Our fork's run gate (arc-agi-3 duck-fork). MIT-0.
#
# Kaggle runs this notebook twice. A competition rerun sets
# KAGGLE_IS_COMPETITION_RERUN and plays the hidden games; there everything
# below runs exactly as in Franzen's notebook. A commit ("Save & Run All") is
# only a check that the notebook finishes, and playing the 25 demo games there
# would spend up to nine hours of the account's weekly GPU quota. So at commit
# the model server and the games are skipped and a stand-in submission.parquet
# is written, unless the evaluation switch is on: DUCK_EVALUATE below (set by
# scripts/build_duck_notebook.py --evaluate) or the DUCK_EVALUATE=1 variable.
from IPython.core.magic import register_cell_magic

DUCK_EVALUATE = __DUCK_EVALUATE__
DUCK_EVALUATE = DUCK_EVALUATE or os.environ.get("DUCK_EVALUATE", "").strip().lower() in {"1", "true"}
RUN_GAMES = TRUE_SUBMISSION or DUCK_EVALUATE
print(f"duck-fork: TRUE_SUBMISSION={TRUE_SUBMISSION} DUCK_EVALUATE={DUCK_EVALUATE} RUN_GAMES={RUN_GAMES}")


@register_cell_magic
def duck_games(line, cell):
    """Run the cell only when the games are played; re-raise its error."""
    if not RUN_GAMES:
        print("duck-fork: commit run, cell skipped")
        return
    get_ipython().run_cell(cell).raise_error()
