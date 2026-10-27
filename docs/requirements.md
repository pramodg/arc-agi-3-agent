# ARC-AGI-3 / ARC Prize 2026 -- what the competition needs

Researched 2026-10-25. Every fact has its source beside it. The pages were
read one by one. The Kaggle competition pages need a login, so the facts that
only live there were first marked **UNVERIFIED**. The runtime and
submission limits were read from Kaggle once an account existed
(docs/submission.md); the lines still marked UNVERIFIED have not been.

## The one-paragraph version

ARC-AGI-3 is a set of small turn-based grid games, with no instructions. An
agent has to work out what each game is for and beat its levels in as few
actions as a typical first-time human. The prize track runs on Kaggle as a code
competition. You submit a notebook. Kaggle runs it **offline**, with no API
calls to Claude, GPT or anything else, against 55 hidden games. **Final
submissions are due 2 November 2026, eight days from now.** Both milestone
prizes are already past. To be paid anything, the code must be open-sourced
under CC0 or MIT-0.

## Key dates

| Date | What | Source |
|---|---|---|
| 2026-03-25 | Competition started | [1] |
| 2026-06-30 | Milestone #1 (past) | [1][2] |
| 2026-09-30 | Milestone #2 (past) | [1][2] |
| **2026-11-02** | **Final submissions due** | [1] |
| 2026-11-08 | Papers due (Paper Prize track, via Kaggle) | [1] |
| 2026-12-04 | Results announced | [1] |
| ? | Entry deadline and team-merger deadline: **UNVERIFIED**. Kaggle usually sets them one week before the final date, which would be about 2026-10-26, i.e. tomorrow. Check the Kaggle rules page now. | [3] (login needed) |

## Prizes (ARC-AGI-3 track, $850K total) [2]

- **Grand Prize $700K**: the first eligible agent to score 100% on the ARC-AGI-3 evaluation. It rolls over if unclaimed.
- **Top Score Award $75K, guaranteed**: 1st $40K, 2nd $15K, 3rd $10K, 4th $5K, 5th $5K.
- **Milestone prizes $75K**: $25K / $10K / $2.5K per milestone. Both milestones are past, so this is gone for us.
- ARC Prize 2026 as a whole has $2M over three tracks: ARC-AGI-3, ARC-AGI-2 and a Paper Prize [1].

## The task

- **Games** [4][5]: turn-based 2D grids, at most 64x64, each cell an integer 0-15 (a colour). (0,0) is top-left. Each step returns one or more frames plus metadata: state (`NOT_PLAYED`, `NOT_FINISHED`, `WIN`, `GAME_OVER`), `levels_completed`, and `available_actions`. Game ids look like `ls20-<version>`.
- **Actions** [5]: `RESET`, `ACTION1`-`ACTION4` (semantically up/down/left/right), `ACTION5` (interact/select/rotate...), `ACTION6` (a click at x,y in 0-63; the game does not say which cells are live), and `ACTION7` (undo). Each game exposes only a subset. After `GAME_OVER` only `RESET` is valid.
- **Datasets** [6, Table 1]: 25 public demo games, 55 semi-private games (used to test frontier models behind an API) and **55 fully private games used for the competition**. The private games are "significantly more difficult" and "intentionally out-of-distribution" from the public ones. Tuning a harness to the public games is explicitly expected not to transfer.
- **The state of the art at release** [6, Table 2]: frontier LLMs scored under 1% on the semi-private set (Opus 4.6 0.50%, Gemini 3.1 Pro 0.40%, GPT 5.4 0.20%). Humans solve 100%. Handcrafted harnesses scored ~97% on one public game and 0% on another (TR87 vs BP35), which is the "bimodal" failure the report warns about.

## Scoring: RHAE (Relative Human Action Efficiency) [7]

- An **action** is any game-changing step the agent submits. Thinking, tool calls and retries that do not touch the game are free.
- **Human baseline per level**: the upper-median, by fewest actions, of first-time human players (changed from "2nd best human" on 2026-04-14 [8]).
- **Per level**: `level_score = min(1.15, (human_actions / ai_actions) ^ 2)`. 2x the human's actions scores 25%; 10x scores 1%. An uncompleted level scores 0.
- **Per game**: a weighted average of level scores, where level *n* has weight *n*. So later levels count more, and the score is capped by how far you got. Beating levels 1-4 of 5 caps the game at 10/15 = 66.7%.
- **Total**: the plain mean over all games, 0-100%.
- Practical consequence: completion matters most, then efficiency, squared. Random exploration that wins a level in 10x the human's actions earns almost nothing for it.

## How a submission works [9][10]

- **Platform**: Kaggle code competition `arc-prize-2026-arc-agi-3` [3]. You submit a notebook. Kaggle runs it twice: (A) "Save & Run All" to check it executes, then (B) "Submit to Competition", where the agent plays the hidden games through a local gateway sidecar (`http://gateway:8001`) and the notebook writes `submission.parquet`.
- **Interface**: a class `MyAgent(Agent)` from the `ARC-AGI-3-Agents` framework, with `is_done(frames, latest_frame)` and `choose_action(frames, latest_frame) -> GameAction`. The official starter kit splices `agent/my_agent.py` into the notebook and pushes it with the Kaggle CLI (`make submit`) [9].
- **Competition mode** is forced on Kaggle [11]: one `make()` per game, one scorecard, game resets turn into level resets, and no score readout mid-run.
- **No internet during evaluation**: "no API-based systems like GPT/Claude/etc." [1][2]. Packages come from the offline competition dataset (`arc_agi_3_wheels`) [12]. Any model weights must be shipped inside the notebook or as a Kaggle dataset.
- **Hardware** [9][10]: you choose the accelerator. `cpu`, `t4` (2x T4, default), `p100`, or `rtx6000` (RTX Pro 6000, `g4-standard-48`, exclusive to ARC-AGI-3, burns GPU quota faster). An official template runs GPT-OSS-120B on the RTX 6000 and warns that it is slow [13].
- **Runtime limit**: **9 hours** for a CPU or GPU notebook, internet off, read from the Kaggle competition pages on 2026-10-25 [3] (docs/submission.md). The framework plays every game at once, one thread per game. The GPT-OSS template warns that a high per-game time limit causes a "scorecard not produced in time" failure that fails the run [13].
- **Submissions per day**: **1**, read from the Kaggle rules (section 2a) and the CLI's submission limits on 2026-10-25 [3]. The starter kit's README says 5 [9]; Kaggle's own limit is the one that applies.
- **Software**: Python 3.12 is required by the `arc-agi` package [9]. `pip install arc-agi`. Local play runs offline at ~2,000 FPS after the first download of the game files [10][14]. *Checked by setup on 2026-10-25*: arc-agi 0.9.9 (arcengine 0.9.3) on Python 3.12.15 played all 25 public games from the local cache with no network, in 4.2 s for 2,025 actions (docs/setup.md). The version in Kaggle's offline competition wheels is not known until a notebook runs there.

## Eligibility and legal [1][2]

- To receive prizes, the solution must be open-sourced **before official private scores are given**.
- Code and methods we author: a permissive public-domain licence, "e.g. CC0 or MIT-0". Third-party parts need at least an open-source licence that allows public sharing (Apache-2.0, GPLv3...). Submissions must be reproducible.
- Awards are at the sole discretion of ARC Prize Inc. after technical review.
- Team size, the merger rules and any country or employer restrictions: **UNVERIFIED** (Kaggle rules page).

## Accounts and keys

- **Kaggle account** with the competition rules accepted [12], and a **Kaggle API token** (Settings -> Create New Token) for pushing notebooks. Kaggle may also need phone verification before it allows GPU notebooks (standard Kaggle policy; UNVERIFIED for this competition).
- **ARC API key** (optional): from arcprize.org/platform, log in with Google or GitHub [15]. The docs say anonymous play gets only 3 games and a key unlocks all 25 public games [16]. *Measured by setup on 2026-10-25*: with no key, arc-agi 0.9.9 fetched an anonymous key and listed, downloaded and played all 25 public games. Online play is limited to 600 requests per minute [17]. Local offline play needs no key once the game files are cached.

## What a submission needs

1. **A Kaggle account** with the competition rules accepted on it, and
   **identity verification**: Kaggle refuses a competition submission from an
   unverified account (HTTP 403), though pushing and running notebooks works.
2. **A Kaggle API token** for that account (Settings, Create New Token),
   saved as `.kaggle/access_token` in the checkout. It is gitignored.
3. **The code open-sourced** under CC0 or MIT-0 before private scores are
   given, for any prize.
4. **An ARC API key** is optional. Anonymous access gave all 25 public games
   on 2026-10-25.

Python 3.12, which `arc-agi` requires, is built by `pipeline/toolchain.py`
(docs/setup.md). No GPU is needed: the agent is plain Python.

Still **UNVERIFIED** (Kaggle rules page): the entry and team-merger
deadlines, team size, and any country or employer restrictions.

## Sources

1. ARC Prize 2026 overview -- https://arcprize.org/competitions/2026
2. ARC-AGI-3 track -- https://arcprize.org/competitions/2026/arc-agi-3
3. Kaggle competition -- https://www.kaggle.com/competitions/arc-prize-2026-arc-agi-3 (rules: /rules)
4. Game schema -- https://docs.arcprize.org/game-schema.md
5. Actions -- https://docs.arcprize.org/actions.md
6. ARC-AGI-3 Technical Report (2026-04-22) -- https://arcprize.org/media/ARC_AGI_3_Technical_Report.pdf
7. Scoring methodology -- https://docs.arcprize.org/methodology.md
8. Toolkit changelog -- https://docs.arcprize.org/changelog.md
9. Kaggle starter kit -- https://github.com/arcprize/ARC-AGI-3-Kaggle-Starter (and https://docs.arcprize.org/arc-prize-2026.md)
10. Local vs online -- https://docs.arcprize.org/local-vs-online.md
11. Competition mode -- https://docs.arcprize.org/toolkit/competition_mode.md
12. Starter `scripts/build_notebook.py` (offline wheels, gateway sidecar) -- https://github.com/arcprize/ARC-AGI-3-Kaggle-Starter/blob/main/scripts/build_notebook.py
13. GPT-OSS on Kaggle template -- https://docs.arcprize.org/partner_templates/gpt-oss-kaggle.md
14. Quickstart -- https://docs.arcprize.org/
15. API keys -- https://docs.arcprize.org/api-keys.md
16. Available games -- https://docs.arcprize.org/available-games.md
17. Rate limits -- https://docs.arcprize.org/rate_limits.md
Other: agents framework https://github.com/arcprize/ARC-AGI-3-Agents, benchmarking https://github.com/arcprize/arc-agi-3-benchmarking, engine https://github.com/arcprize/ARCEngine.
