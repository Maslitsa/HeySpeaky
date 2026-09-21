---
name: release
description: Cut a HeySpeaky release - bump the version, tag it, watch CI, then update the owner's own machine and check it still dictates.
---

# Releasing HeySpeaky

People update by running the install command again, which pulls `main`. So a
release is really two things: making `main` good, and giving it a number that
can be talked about in an issue.

## 1. Check the tree is honest

```powershell
git status --short
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe -W error::SyntaxWarning -m compileall -q heyspeaky run.py tools
```

Both PowerShell scripts must parse and stay ASCII. Never release with a report
ZIP or a recording sitting in the tree.

## 2. Write down what changed

Move the `## Unreleased` entries in `CHANGELOG.md` under a new heading with the
version and today's date. Keep the three groups (Added, Changed, Fixed) and
write for someone who does not read code: what they will notice, not which
function moved.

Bump `__version__` in `heyspeaky/__init__.py` to match.

## 3. Tag and push

```powershell
git add -A
git commit -m "Release 1.2"
git tag v1.2
git push origin main --tags
```

The commit message carries no AI attribution. Ever.

Then publish the release itself:

```powershell
gh release create v1.2 --title "HeySpeaky 1.2" --notes-file release-notes.md
```

This step is not optional. The app asks GitHub for
`releases/latest` once a day to offer the update in the tray; a tag with no
release means nobody is ever told a fix exists.

## 4. Watch CI

```powershell
gh run list --limit 5
gh run watch <id> --exit-status
```

All four jobs must pass: the tests on 3.11 and 3.12, the installer on a clean
Windows, and the secret scan. The installer job also uninstalls, which is the
only automated proof that removal still works.

## 5. Prove it on a real machine

Update the owner's own install and check it comes back:

```powershell
irm https://raw.githubusercontent.com/Maslitsa/HeySpeaky/main/install.ps1 | iex
```

Then confirm from the log that the engine reported ready, and that both
shortcuts point at `%LOCALAPPDATA%\Programs\HeySpeaky`.

## 6. Tell him in Russian

What changed, what you checked, and anything you could not check.
