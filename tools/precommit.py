r"""Stops a commit that would embarrass us later.

Claude Code runs this before every Bash call (see .claude/settings.json). It
gets the command on standard input as JSON, ignores everything that is not a
git commit, and for a commit it checks the three things this project has
actually got wrong before:

  1. a key or a recording being committed
  2. a test suite that no longer passes
  3. a syntax warning, which fails CI on the next push

Exit code 2 tells Claude Code to block the command and read the reason.

    python tools\precommit.py            # check as if committing
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL = os.environ.get("LOCALAPPDATA", "")

KEY = re.compile(r"sk-(proj-)?[A-Za-z0-9_-]{20,}")
FORBIDDEN_NAMES = ("-report-", "openai.key", "usage.json")
# Attribution the owner has asked never to appear in this repository.
ATTRIBUTION = re.compile(r"(?i)co-authored-by:\s*claude|generated with \[claude")


def staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=str(ROOT), capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def staged_text():
    result = subprocess.run(["git", "diff", "--cached"], cwd=str(ROOT),
                            capture_output=True, text=True, errors="replace")
    return result.stdout


def run(command):
    return subprocess.run(command, cwd=str(ROOT), capture_output=True,
                          text=True, errors="replace")


def candidates():
    """Interpreters that might have the packages the app needs, best first.

    The Python that starts this check is whichever one Claude Code found on
    the path, and that one usually has nothing installed. The tests import
    the app, so they need the environment the app itself runs in.
    """
    chosen = os.environ.get("HEYSPEAKY_PYTHON")
    if chosen:
        yield Path(chosen)
    yield ROOT / ".venv" / "Scripts" / "python.exe"
    yield ROOT / ".venv" / "bin" / "python"
    if LOCAL:
        yield Path(LOCAL) / "Programs" / "HeySpeaky" / ".venv" / "Scripts" / "python.exe"
    yield Path(sys.executable)


def interpreter():
    """The first interpreter that can import the app, or None."""
    for path in candidates():
        if not path.exists():
            continue
        proof = run([str(path), "-c", "import heyspeaky.transcribe"])
        if proof.returncode == 0:
            return str(path)
    return None


def problems():
    found = []

    for name in staged():
        if any(part in name.lower() for part in FORBIDDEN_NAMES):
            found.append("{} looks like a key, a recording or a private tally"
                         .format(name))

    diff = staged_text()
    if KEY.search(diff):
        found.append("the staged changes contain something shaped like an "
                     "OpenAI key")
    if ATTRIBUTION.search(diff):
        found.append("the staged changes carry AI attribution, which this "
                     "repository does not use")

    python = interpreter()
    if python is None:
        found.append("the tests could not run: no Python here has the app's "
                     "packages. Install the app, or point HEYSPEAKY_PYTHON at "
                     "an environment that has them")
        python = sys.executable
    else:
        tests = run([python, "-m", "unittest", "discover", "-s", "tests"])
        if tests.returncode != 0:
            tail = (tests.stderr or tests.stdout).strip().splitlines()[-3:]
            found.append("the tests fail: " + " / ".join(tail))

    compiled = run([python, "-W", "error::SyntaxWarning", "-m", "compileall",
                    "-q", "heyspeaky", "run.py", "tools"])
    if compiled.returncode != 0:
        tail = (compiled.stderr or compiled.stdout).strip().splitlines()[-3:]
        found.append("a file does not compile cleanly: " + " / ".join(tail))

    return found


def main():
    command = ""
    if not sys.stdin.isatty():
        try:
            payload = json.load(sys.stdin)
            command = (payload.get("tool_input") or {}).get("command", "")
        except (ValueError, AttributeError):
            command = ""
    if command and "git commit" not in command:
        return 0

    found = problems()
    if not found:
        return 0
    sys.stderr.write("This commit was stopped:\n")
    for problem in found:
        sys.stderr.write("  - {}\n".format(problem))
    sys.stderr.write("Fix those, then commit again.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
