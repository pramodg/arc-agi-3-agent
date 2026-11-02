# The stage question bank for duck/staged/cell.py (arc-agi-3 staged-questions). MIT-0.
#
# Data only: one dict and no code, so row question-learning can add, reword
# or drop a question here without touching the cell. Krishan, 2026-11-01
# (D-dcfc42): the system learns which questions to ask itself; it does not
# memorise solutions. So every entry stays general: never a game id,
# coordinates or an action sequence (RULES.md 3).
#
# stage: (title, [(key, question)]). The stages are fixed by the detector:
# opening, early-check, executing, surprised, stuck, new-level, low-budget.
# A key is one word; the model answers "Key: answer" on its own line. Started
# from the per-stage list in Krishan's direction note of 2026-11-01; improve it
# from debriefs, never from a named game. Round 1 of question-learning
# (docs/question-learning.md) rewrote the opening so it can be answered from
# the first frame, before any move, and added the questions a lost level
# showed were missing: is this progress, does the plan fit the moves left,
# what does this failure prove wrong, and how to test a new element. Round 2
# kept the opening as it was (its answers are being logged, so a new wording
# would blur that), took out three questions (Solve, and the stuck stage's
# Expected and Paying) so the bank is shorter than round 1's, and asked what
# ended a life, what else the goal could be when stuck, and what a doomed life
# can still test.
SQ_QUESTIONS = {
    "opening": ("Opening: the first moves of a level, answered from the first frame before any move", [
        ("Tile", "What is the real tile grid (size and offset)? Confirm or correct the harness measurement below."),
        ("Objects", "Which objects and colours are there, which colours link objects, and which one is most likely yours to move?"),
        ("HUD", "Is there a bar, counter or row of marks along an edge that could be a move budget or lives? Say where, or 'none seen'."),
        ("Goal", "What could the goal be, read literally from the board? Give your best two guesses."),
        ("Probe", "Which one action will you try first, and what change after it would tell you the most?"),
        ("Seen", "Have you seen a game or level like this before (the notes from other games, if any)?"),
    ]),
    "early-check": ("Early check: a few actions in", [
        ("Controls", "Did each control do what you thought it would? Which are measured, which still guessed?"),
        ("HUD", "Did the bar or counter change when you moved? How many moves does one life allow at that rate?"),
        ("Goal", "Which goal guess is most likely, and what is the cheapest move that tests it?"),
        ("Budget", "Does your plan fit in the moves this life allows?"),
    ]),
    "executing": ("Executing a plan", [
        ("OnPlan", "yes or no: is the board what your plan said it would be after the last step?"),
        ("Progress", "Did your last moves change anything besides your position and the counter? If not, why is this progress?"),
        ("Next", "Which next steps are certain? Send all of them in this one call, stopping before the first uncertain one."),
        ("Budget", "How many moves are left in this life, and does the rest of the plan fit in them?"),
    ]),
    "surprised": ("Surprised: something did not go as predicted", [
        ("Expected", "What did you expect, and what happened instead? If a life ended, what caused it?"),
        ("Wrong", "Which belief does this prove wrong: a measurement, a control, a rule or the goal? Name it, rather than nudging the same attempt."),
        ("Change", "What one thing will you change next, and what result would show the new belief holds?"),
    ]),
    "stuck": ("Stuck: many turns on this level and it is not cleared yet", [
        ("Repeat", "Is the board, apart from the counter, back to a state you already saw on this level? If so, what are you repeating?"),
        ("Goal", "Could the goal you assumed be wrong? What else on the board could be the goal, and which cheap action would tell the guesses apart?"),
        ("Rule", "Are you trying options one at a time? What rule or encoding would let you work the answer out instead, and is there a control that commits or checks it?"),
        ("Change", "What one thing will you change next, and what is the cheapest test of it?"),
    ]),
    "new-level": ("New level", [
        ("New", "What is new on this level, and has the goal changed?"),
        ("Holds", "Which rules from the last level still hold, and which familiar-looking object might follow a new rule here?"),
        ("Test", "What one action tests the new element fastest?"),
    ]),
    "low-budget": ("Running low on moves or time", [
        ("Left", "How much remains (moves in this life, time in the game), and where should it go?"),
        ("Worth", "Is this level still worth your moves and time? If this life cannot reach the goal, what one test is worth its remaining moves?"),
        ("Cheapest", "What is the cheapest way to finish? Spend no move on a key you have not seen change the board."),
    ]),
}
