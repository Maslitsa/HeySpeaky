# HeySpeaky, for whoever picks this up next

Hold Ctrl+Alt, talk, and the text lands in whatever window you were typing in.
Windows only. It transcribes through OpenAI by default and can fall back to a
local Whisper model. It was called VoiceType, then SpeakIt, now HeySpeaky.

The owner is Miras. He does not read code. **Answer him in Russian**, plainly,
without jargon, and say what you actually did and what you could not do.

## The map

| File | What it does |
| --- | --- |
| `run.py` | entry point, launched with pythonw.exe |
| `heyspeaky/app.py` | the controller and the state machine |
| `heyspeaky/config.py` | defaults, and config.json loading |
| `heyspeaky/theme.py` | every colour, size and timing of the pill |
| `heyspeaky/glass.py` | draws the pill: glass over a photo of the desktop |
| `heyspeaky/overlay.py` | the window: click-through, never focused |
| `heyspeaky/engine.py` | RealtimeSTT: capture and voice activity detection |
| `heyspeaky/transcribe.py` | OpenAI and local backends, the key lookup |
| `heyspeaky/languages.py` | the languages list and its tray grouping |
| `heyspeaky/diagnostics.py` | the problem report people send you |
| `heyspeaky/tray.py` `hotkey.py` `mic.py` `output.py` `winjob.py` | the rest |
| `install.ps1` `uninstall.ps1` | how everyone installs and removes it |
| `tools/doctor.py` | the check-up; the installer runs it with `--install` |
| `tools/ui_lab.py` | draws every state of the pill to a PNG |
| `tools/benchmark.py` | measures models against real recordings |
| `tools/try_demo.py` | runs a recording through both backends |

## Rules that cost something to learn

- **Never put AI attribution anywhere** - not in commits, files or pull
  requests, and do not mention Claude or Anthropic in the repository. Owner's
  rule.
- **`install.ps1` and `uninstall.ps1` must stay ASCII** and must parse before
  any commit: Windows PowerShell 5.1 mangles anything else, and the installer
  is the only way anyone updates, so a broken one breaks every user.
- **Run the tests and the strict compile before pushing.** A `SyntaxWarning`
  fails CI.
- **Never commit a problem report, a recording or a key.** `*-report-*.zip` is
  ignored for that reason.
- **There is no console.** Under pythonw.exe `print()` goes nowhere and can
  raise; use the logger.
- **The look changes in `theme.py`**, and you look at the result with
  `tools/ui_lab.py` before wiring it in.
- **The pill must never take focus, never block clicks and never appear in
  Alt+Tab.** That is what makes dictation feel invisible.
- **The transcription worker must die with the app** (`winjob.py`). Orphans
  once wrote 8.7 GB of the same traceback.
- **Keys live outside the project**, in `%APPDATA%\HeySpeaky\openai.key`. The
  SpeakIt and VoiceType paths are read as a fallback. Never log one, never
  print one, never put one in config.json.
- **OpenAI is the default and local is a fallback.** Measured on the owner's
  laptop: OpenAI got a four-language clip completely right; local `base` lost
  most of the Russian and Kazakh, `small` took 4-7 s, `large-v3-turbo` 17-19 s.
  The installer picks `large-v3-turbo` only when a CUDA card is usable.

## Before you push

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe -W error::SyntaxWarning -m compileall -q heyspeaky run.py tools
.venv\Scripts\python.exe tools\ui_lab.py --out lab.png   # if the look changed
```

And in PowerShell, for either script you touched:

```powershell
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path .\install.ps1), [ref]$null, [ref]$errors)
```

A real install is the only proof the installer works. CI does one on a clean
Windows runner for every push, including the uninstall.

## Three generations of the name

VoiceType, then SpeakIt, now HeySpeaky. Old installs are carried across, not
abandoned: `Move-FromOldNames` in `install.ps1` copies settings and the key and
removes the old shortcuts, `uninstall.ps1` knows all three names, and
`LEGACY_KEY_FILES` in `transcribe.py` still reads the old key paths.

## What the owner decided

- Quality beats cost: OpenAI stays the default, and the spending counter only
  warns, it never silently switches to the weaker local model.
- No bots in GitHub issues. He decides what gets answered.
- Private notes, money and feedback live in his Obsidian vault next to the
  project, never in this public repository.
