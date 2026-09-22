# HeySpeaky, for whoever picks this up next

Hold Ctrl+Alt, talk, and the text lands in whatever window you were typing in;
or tap Ctrl+Alt twice to keep recording with nothing held down.
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
| `heyspeaky/overlay.py` | the window: never focused, and its two buttons |
| `heyspeaky/engine.py` | RealtimeSTT: capture and voice activity detection |
| `heyspeaky/transcribe.py` | OpenAI and local backends, the key lookup |
| `heyspeaky/languages.py` | the languages list and its tray grouping |
| `heyspeaky/levels.py` | making a quiet recording loud enough to transcribe |
| `heyspeaky/sound.py` | the tone at the end, built here, not shipped |
| `heyspeaky/diagnostics.py` | the problem report people send you |
| `heyspeaky/tray.py` `hotkey.py` `mic.py` `output.py` `winjob.py` | the rest |
| `install.ps1` `uninstall.ps1` | how everyone installs and removes it |
| `tools/doctor.py` | the check-up; the installer runs it with `--install` |
| `tools/ui_lab.py` | draws every state to a PNG, or `--gif` to animate it |
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
  `tools/ui_lab.py` before wiring it in. The pill is small and dark: cross,
  waveform, tick, and nothing else. It does not repeat the transcript back,
  because the transcript is already in the window you were typing in.
- **Silence is drawn as dots, not as motion.** Many thin round-capped bars,
  newest on the right, scrolling left, falling to dots when nothing is heard -
  which is how ChatGPT and every other voice composer worth copying does it.
  An idle animation was tried and removed: it invented activity where there
  was none, and a waveform that moves when the room is quiet is a lie about
  what the microphone can hear.
- **The pill is a layered window with a real alpha channel**, drawn by
  `UpdateLayeredWindow`, not by Tk. Never call `root.attributes("-alpha")` on
  it: that is `SetLayeredWindowAttributes`, and a window given one of those
  can never be updated the other way again. The fade uses the blend function.
  It used to photograph the desktop and draw the picture as its background;
  that looked like glass until anything underneath moved, and then the pill
  showed as a bright rectangle full of somebody else's pixels. A screenshot
  from the owner is what finally proved it.
- **The pill must never take focus and never appear in Alt+Tab.** That is what
  makes dictation feel invisible. Clicks land on its own pixels - the cross
  and the tick are real buttons - and pass straight through everywhere else,
  because Windows hit-tests a layered window through its alpha.
  `overlay.buttons_clickable: false` makes the whole thing click-through
  again. WS_EX_NOACTIVATE stays either way, so a click never moves the caret
  out of the window you were typing in.
- **Hands-free is a double tap of the whole chord**, half a second apart, the
  way Wispr Flow does it. The owner asked for that specifically. It works
  because a single tap is shorter than the engage delay and so does nothing at
  all, which is also what the start of every Ctrl+Alt+<key> shortcut looks
  like. The old latch - release between 0.25s and 0.7s - is off by default
  (`hotkey.tap_max: 0`) because nobody can hit a window that narrow.
- **The transcription worker must die with the app** (`winjob.py`). Orphans
  once wrote 8.7 GB of the same traceback.
- **Keys live outside the project**, in `%APPDATA%\HeySpeaky\openai.key`. The
  SpeakIt and VoiceType paths are read as a fallback. Never log one, never
  print one, never put one in config.json.
- **Quiet audio comes back as an empty string, not an error.** Measured on
  the owner's machine: every recording OpenAI returned nothing for peaked
  below -27 dB, and every one that worked was louder. `levels.py` boosts by up
  to 24x - the old ceiling of 8 was not enough - and an empty transcript from
  quiet audio says "Too quiet" rather than "Nothing heard", because the second
  one sends people looking for the wrong fault.
- **OpenAI is the default and local is a fallback.** Measured on the owner's
  laptop: OpenAI got a four-language clip completely right; local `base` lost
  most of the Russian and Kazakh, `small` took 4-7 s, `large-v3-turbo` 17-19 s.
  The installer picks `large-v3-turbo` only when a CUDA card is usable.

## Before you push

The first two of these run by themselves: `tools\precommit.py` is wired into
`.claude\settings.json` as a check before every commit, and it also refuses a
commit that carries a key, a recording or AI attribution. It takes about six
seconds and it is the reason none of that reaches GitHub by accident.

Running them by hand needs an interpreter that has the app's packages. **This
working copy has no `.venv`** - the owner runs the installed app - so use the
one the installer built, or set `HEYSPEAKY_PYTHON` to any environment that has
them:

```powershell
$py = "$env:LOCALAPPDATA\Programs\HeySpeaky\.venv\Scripts\python.exe"
& $py -m unittest discover -s tests
& $py -W error::SyntaxWarning -m compileall -q heyspeaky run.py tools
& $py tools\ui_lab.py --out lab.png   # if the look changed
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
