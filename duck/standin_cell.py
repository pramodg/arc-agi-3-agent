# Our fork's commit-run output (arc-agi-3 duck-fork). MIT-0.
# When the games were skipped, Kaggle still expects a submission.parquet; the
# competition rerun writes the real one through its gateway.
if not RUN_GAMES:
    import pandas as pd

    pd.DataFrame(
        [["1_0", "1", True, 1]],
        columns=["row_id", "game_id", "end_of_game", "score"],
    ).to_parquet(WORKING_DIR / "submission.parquet", index=False)
    print("duck-fork: wrote the stand-in submission.parquet")
