#!/bin/sh
# The gate. It checks that the README still states the goal, the RHAE scorer
# reproduces the methodology page and the toolkit (tests/test_scorer.py),
# and every unit test passes on the shared Python 3.12 environment: those
# under tests/, and any test_*.py kept beside a script in scripts/. It stays
# well inside two minutes: a full evaluation over every public game is a
# background job, never the gate. Last stdout line is the JSON verdict;
# everything else goes to stderr.
cd "$(dirname "$0")/.." || exit 1
fail() {
  printf '%s\n' "$1" >&2
  printf '{"verdict": "fail", "metrics": {}, "artifacts": [], "why": "%s"}\n' "$1"
  exit 0
}
grep -q 'ARC-AGI-3' README.md 2>/dev/null || fail "README.md no longer states the goal"
n=$(find tests -name 'test_*.py' 2>/dev/null | wc -l | tr -d ' ')
# The tests run on the shared Python 3.12 environment the agent runs on.
python3 -m pipeline.toolchain ensure >&2 \
  || fail "could not build the shared Python 3.12 environment (pipeline/toolchain.py)"
py=$(python3 -m pipeline.toolchain python)
"$py" -m unittest tests.test_scorer >&2 2>&1 \
  || fail "the RHAE scorer tests failed (tests/test_scorer.py)"
"$py" -m unittest discover -s tests >&2 2>&1 || fail "unit tests under tests/ failed"
if ls scripts/test_*.py >/dev/null 2>&1; then
  "$py" -m unittest discover -s scripts -p 'test_*.py' >&2 2>&1 \
    || fail "unit tests beside scripts/ failed"
fi
printf '{"verdict": "pass", "metrics": {"test_files": %s}, "artifacts": []}\n' "$n"
