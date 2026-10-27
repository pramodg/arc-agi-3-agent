# Submitting to Kaggle -- the exact steps, and what happened the first time

Written by the first-submission row on 2026-10-25.

## The limits, read from the competition pages on 2026-10-25

Read with `kaggle competitions pages list --content arc-prize-2026-arc-agi-3`
and `kaggle competitions submission-limits arc-prize-2026-arc-agi-3`:

- **Runtime: 9 hours** for a CPU or a GPU notebook, internet off. This
  replaces the 12-hour assumption in docs/design.md section 5,
  `KAGGLE_RUNTIME_S_ASSUMED` in `pipeline/evaluate.py` and `MAX_SECONDS` in
  `agent/my_agent.py`.
- **Submissions: 1 a day** (rules section 2a; the CLI reported "Remaining
  today: 1"). Not 5, as docs/requirements.md had it. Every submission is
  precious: test locally first.
- **The framework plays every game at once**, one thread per game
  (`agents/swarm.py` in ARC-AGI-3-Agents). So the per-game wall-clock cap is
  also, roughly, the whole run's length. All games share the CPU and the GIL,
  so a per-game cap of S seconds gives each game far less than S seconds of
  compute. With 9 hours, a per-game cap up to about 0.8 x 9 h = 25,920 s still
  finishes in time; the current 628 s finishes in about 11 minutes.
- **Kaggle's image** runs Python 3.13 and installs arc-agi 0.9.8 and
  arcengine 0.9.3 from the competition wheels. Locally we pin Python 3.12 and
  arc-agi 0.9.9 (docs/setup.md).

## The account

- Kaggle user `pramodgupta15`. The token is `.kaggle/access_token` in the
  primary checkout (gitignored, never printed). The Makefile passes it to the
  CLI as `KAGGLE_API_TOKEN`.
- The account must be **identity-verified** (kaggle.com/settings) before
  Kaggle accepts a competition submission. Pushing and running notebooks
  works without it; only the submit step is refused, with HTTP 403
  "You must Identity Verify your account to perform this action".

## The steps

From a checkout that has the agent and the Makefile, with the token at
`.kaggle/access_token`:

1. Put the account in the kernel id. In `notebooks/kernel-metadata.json`,
   `"id"` is `pramodgupta15/arc-prize-2026-arc-agi-3-agent` (the committed
   file still says `REPLACE_WITH_YOUR_USERNAME`; `make submit` refuses until
   it is replaced).
2. Check the agent: `make test` and
   `python3 -m pipeline.toolchain run scripts/play_local.py --offline --game ls20,vc33 --max-steps 300`.
3. Build and push: `make submit`. It builds `notebooks/submission.ipynb` from
   `agent/my_agent.py` and runs `kaggle kernels push -p notebooks/`. Kaggle
   starts Save & Run All at once. Note the version number it prints.
4. Wait for the run: `make status` until it says
   `KernelWorkerStatus.COMPLETE`. In this commit-time run the notebook only
   installs the wheels and writes a placeholder `submission.parquet`; it takes
   about 30 seconds. The real games are played later, in the competition
   rerun.
5. Submit that version:

   ```sh
   KAGGLE_API_TOKEN=$(cat .kaggle/access_token) \
     $(python3 -m pipeline.toolchain python | xargs dirname)/kaggle \
     competitions submit arc-prize-2026-arc-agi-3 \
     -k pramodgupta15/arc-prize-2026-arc-agi-3-agent -v <VERSION> \
     -f submission.parquet -m "<what this is, and the commit>"
   ```

6. Read the result: `kaggle competitions submissions arc-prize-2026-arc-agi-3`
   until the submission has a public score. The rerun plays the hidden games
   with internet off, so it takes as long as the agent's time cap plus setup.

## The first submission, 2026-10-25

| What | Value |
|---|---|
| Built from | commit `ae82887` (the baseline-agent branch tip; main did not yet hold the agent) |
| Kernel id | `pramodgupta15/arc-prize-2026-arc-agi-3-agent`, version 1 |
| Pushed | 2026-10-25T06:32:06Z |
| Save & Run All | `KernelWorkerStatus.COMPLETE`, about 29 s (log ends at 28.6 s) |
| Accelerator | none (CPU), internet off |
| First submit | refused, 403 IdentityVerificationRequired, 2026-10-25T06:32:56Z. The account was then identity-verified. |
| Submitted | 2026-10-25T06:40:26Z, kernel version 1, unchanged |
| Submission id | **57620094** |
| Status | `SubmissionStatus.COMPLETE` |
| Public leaderboard score | **0.09** (rank 4118 of 4790 teams, as `pramod gupta`) |
| Rerun time | about 14.5 minutes from submit to scored (still pending at 06:50:30, complete by 06:55:20) |

## The interim resubmission, 2026-10-26

Run by the resubmit row as one domain job (`arc-agi-3/20261025T180426-f8984e09`).
The job waited for the first free day, built from main as it stood then, ran
the unit tests (110, OK) and the offline smoke run, pushed, submitted and
waited for the score.

| What | Value |
|---|---|
| Built from | main `ee81908` (`ee8190811d5511677fc9ed000f5272b8dbac5181`), which carries iterate-4-levels on top of iterate-3 |
| Kernel id | `pramodgupta15/arc-prize-2026-arc-agi-3-agent`, version 2 |
| Pushed | 2026-10-26T00:10:41Z |
| Save & Run All | `KernelWorkerStatus.COMPLETE`, seen at the first check, 2 minutes after the push |
| Accelerator | none (CPU), internet off |
| Submitted | 2026-10-26T00:12:44Z, kernel version 2 |
| Submission id | **57646882** |
| Status | `SubmissionStatus.COMPLETE` |
| Public leaderboard score | **0.16** (the baseline scored 0.09) |
| Rerun time | about 5 hours from submit to scored (still pending at 00:13:45, complete by 05:14:23; the job checked every 5 minutes) |
| Rank | not read: the CLI leaderboard only lists the top 20 |

## The final submission, 2026-10-26

**The entry Kaggle scores is 57646882 (public score 0.16).** No new
submission was made, because the agent at the main tip is the agent that
entry already ran.

- **How final entries are picked.** The rules say: "You may select up to two
  (2) Final Submissions for judging" (rules section 2b), and a Final
  Submission "is the Submission selected by the user, or automatically
  selected by Kaggle in the event not selected by the user" (rules,
  definitions c). Winners are ranked on the private leaderboard only.
  The Kaggle CLI (2.2.5) has no command to mark a selection; that is a
  button on the competition's "My Submissions" page.
- **The selection.** 57646882 is our best public score (0.16, against 0.09
  for 57620094), so Kaggle's automatic choice picks it if nobody selects.
  Selecting it by hand on the website gives the same result.
- **Why the main tip is the scored agent.** Main moved from `ee81908`
  (what 57646882 was built from) to `e03be97`. That move touched only
  this file and a private build log that is not part of the agent. `git diff --stat ee81908..e03be97 -- agent
  notebooks scripts/build_notebook.py` prints nothing.
- **Kaggle slots left.** 2026-10-27 to 2026-11-01 are unused. A better agent
  can still be submitted on any of them.

### Local score of the same agent

One local competition run of `pipeline/evaluate.py` at main `e03be97`
(job `20261026T053005-5a9f590a`, 10,000 actions a game, 1,179.9 s):

| What | Value |
|---|---|
| RHAE over all 25 public games | **0.4637%** (the toolkit's own score agrees) |
| Developed games (13) | 0.7876% |
| Held-out games (12) | 0.1127% |
| Levels completed | 24 of 183 |
| Actions | 250,025 |
| Agent | `agent/my_agent.py`, sha256 `5ec383140ab4` |

### The public release

**Public URL: https://github.com/pramodg/arc-agi-3-agent** (MIT-0).

It was published on 2026-10-27 as one commit with a fresh history. It was
built from this branch's commit carrying this section, whose agent is
byte-identical to `ee81908`, the commit submission 57646882 ran. The build
and the push:

```sh
python3 scripts/build_public_tree.py --ref <commit> --out ../arc-agi-3-public
cd ../arc-agi-3-public
git remote add origin https://github.com/pramodg/arc-agi-3-agent.git
git push -u origin main
```

The build refuses to commit if any public file names the private tooling.
A later release rebuilds from the new main tip the same way.
