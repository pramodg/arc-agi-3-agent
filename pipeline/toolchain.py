"""One shared Python 3.12 environment for this repository, beside the primary
checkout, reused by every worktree.

The box has Python 3.11 and the `arc-agi` package needs 3.12. uv installs a
3.12 interpreter and a virtualenv under the primary checkout's `var/`
(docs/design.md section 3): never in a worktree and never system-wide. The
same `var/` holds the ARC-AGI-3-Agents framework at a pinned commit (shared,
linked into each worktree's gitignored `vendor/`) and the cached public game
files, so after the first download local play runs offline.

This file runs under the box's python3 (3.11) and uses only the standard
library, because it is what builds the 3.12 environment.

    python3 -m pipeline.toolchain ensure       # build what is missing, print the interpreter
    python3 -m pipeline.toolchain python       # print the interpreter path only
    python3 -m pipeline.toolchain run ARGS...  # exec the 3.12 interpreter with ARGS
"""
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

PY_VERSION = "3.12"
# Pinned on 2026-10-25 from what `uv pip install arc-agi>=0.9.6 ...` resolved.
# The Kaggle notebook installs arc-agi from the competition's own wheels, so
# a version change there is checked by the submission row, not here.
PACKAGES = (
    "arc-agi==0.9.9",
    "arcengine==0.9.3",
    "kaggle==2.2.5",
    "python-dotenv==1.2.4",
    "pandas==3.1.0",
    "pyarrow==26.0.0",
    "requests==2.34.2",
    "pydantic==2.14.1",
    "numpy==2.5.4",
)
FRAMEWORK_REPO = "https://github.com/arcprize/ARC-AGI-3-Agents.git"
# ARC-AGI-3-Agents main on 2026-10-25 (committed 2026-08-03). MIT licence.
FRAMEWORK_SHA = "4743e7d0aaae0ded0d98a89a7e282e63564cd58b"
UV_URL = ("https://github.com/astral-sh/uv/releases/latest/download/"
          "uv-x86_64-unknown-linux-gnu.tar.gz")
# Where the primary checkout lives when the repository cannot be asked (a
# scratch copy without .git, such as the gate's shadow copy).
DEFAULT_PRIMARY = os.path.expanduser("~/domains/arc-agi-3")
READY = "READY"


def primary_checkout(repo):
    """The checkout every worktree of `repo` was cut from, else the default.

    It counts only if it holds this file, so an unrelated repository that
    happens to contain the tree is not taken for it."""
    found = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--path-format=absolute",
         "--git-common-dir"], capture_output=True, text=True)
    if found.returncode == 0:
        primary = os.path.dirname(found.stdout.strip())
        if os.path.isfile(os.path.join(primary, "pipeline", "toolchain.py")):
            return primary
    return DEFAULT_PRIMARY


def shared_var(repo):
    """The shared `var/`; ARC_AGI3_VAR overrides it (tests use this)."""
    return os.environ.get("ARC_AGI3_VAR") or os.path.join(
        primary_checkout(repo), "var")


def env_dir(repo):
    return os.path.join(shared_var(repo), "py312")


def interpreter(repo):
    return os.path.join(env_dir(repo), "bin", "python")


def games_dir(repo):
    """Cached public game files: arc_agi's `environments_dir`."""
    return os.path.join(shared_var(repo), "environment_files")


def framework_dir(repo):
    return os.path.join(shared_var(repo), "vendor",
                        f"ARC-AGI-3-Agents-{FRAMEWORK_SHA[:12]}")


def pins_key():
    """Changes whenever the Python version, a package pin or the framework
    commit changes, so a stale environment is rebuilt rather than trusted."""
    h = hashlib.sha256()
    for part in (PY_VERSION, FRAMEWORK_SHA, *PACKAGES):
        h.update(part.encode() + b"\0")
    return h.hexdigest()[:16]


def is_ready(repo):
    """The stamp matches the pins and what it vouches for is still there: the
    interpreter and the shared framework copy the vendor link points at."""
    try:
        with open(os.path.join(env_dir(repo), READY)) as f:
            stamped = json.load(f).get("key") == pins_key()
    except (OSError, ValueError):
        return False
    return (stamped and os.access(interpreter(repo), os.X_OK)
            and os.path.isfile(os.path.join(framework_dir(repo), "agents",
                                            "agent.py")))


def uv_bin(repo):
    """uv in the shared `var/uv/`, downloaded there on first use."""
    path = os.path.join(shared_var(repo), "uv", "uv")
    if os.access(path, os.X_OK):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with tempfile.TemporaryFile() as tmp:
        with urllib.request.urlopen(UV_URL, timeout=120) as r:
            tmp.write(r.read())
        tmp.seek(0)
        with tarfile.open(fileobj=tmp, mode="r:gz") as tar:
            for member in tar.getmembers():
                name = os.path.basename(member.name)
                if member.isfile() and name in ("uv", "uvx"):
                    member.name = name
                    tar.extract(member, os.path.dirname(path))
    return path


def uv_env(repo):
    """uv's own state kept under the shared `var/`, nothing in the home dir."""
    var = shared_var(repo)
    return dict(os.environ,
                UV_PYTHON_INSTALL_DIR=os.path.join(var, "uv-python"),
                UV_CACHE_DIR=os.path.join(var, "uv-cache"),
                UV_NO_MODIFY_PATH="1")


def build_commands(uv, env, py):
    """The uv calls that make the environment, in order."""
    return [
        [uv, "python", "install", "--no-bin", PY_VERSION],
        [uv, "venv", "--allow-existing", "--python", PY_VERSION, env],
        [uv, "pip", "install", "--python", py, *PACKAGES],
    ]


def fetch_framework(repo):
    """Clone the framework at FRAMEWORK_SHA into the shared `var/vendor/`."""
    dest = framework_dir(repo)
    if os.path.isfile(os.path.join(dest, "agents", "agent.py")):
        return dest
    tmp = dest + ".partial"
    subprocess.run(["rm", "-rf", tmp], check=True)
    os.makedirs(tmp)
    for step in (["init", "-q"],
                 ["fetch", "-q", "--depth", "1", FRAMEWORK_REPO, FRAMEWORK_SHA],
                 ["checkout", "-q", "FETCH_HEAD"]):
        subprocess.run(["git", "-C", tmp, *step], check=True)
    os.rename(tmp, dest)
    return dest


def link_vendor(repo):
    """Point `repo/vendor/ARC-AGI-3-Agents` at the shared framework copy. A
    real directory there is left alone. Returns a note."""
    target = framework_dir(repo)
    here = os.path.join(repo, "vendor", "ARC-AGI-3-Agents")
    if os.path.islink(here):
        if os.readlink(here) == target:
            return "linked"
        os.remove(here)
    elif os.path.exists(here):
        return "own copy"
    os.makedirs(os.path.dirname(here), exist_ok=True)
    os.symlink(target, here)
    return "linked"


def ensure(repo):
    """Build whatever is missing, under a lock so two worktrees do it once.
    Returns the interpreter path."""
    var = shared_var(repo)
    os.makedirs(var, exist_ok=True)
    with open(os.path.join(var, ".py312.lock"), "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        if not is_ready(repo):
            uv = uv_bin(repo)
            for cmd in build_commands(uv, env_dir(repo), interpreter(repo)):
                subprocess.run(cmd, check=True, env=uv_env(repo),
                               stdout=sys.stderr)
            fetch_framework(repo)
            slim = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "scripts", "slim_framework.py")
            subprocess.run([interpreter(repo), slim, framework_dir(repo)],
                           check=True, stdout=sys.stderr)
            with open(os.path.join(env_dir(repo), READY), "w") as f:
                json.dump({"key": pins_key(), "python": PY_VERSION,
                           "packages": list(PACKAGES),
                           "framework": FRAMEWORK_SHA}, f)
    link_vendor(repo)
    return interpreter(repo)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    repo = repo_root()
    if argv[:1] == ["ensure"]:
        print(ensure(repo))
        return 0
    if argv[:1] == ["python"]:
        print(interpreter(repo))
        return 0
    if argv[:1] == ["run"]:
        py = ensure(repo)
        os.chdir(repo)
        os.execv(py, [py, *argv[1:]])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
