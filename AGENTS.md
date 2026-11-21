# HeySpeaky, for whoever picks this up next

Hold Ctrl+Alt, talk, and the text lands in whatever window you were typing in;
or tap Ctrl+Alt twice to keep recording with nothing held down.
Windows only. It transcribes through OpenAI by default and can fall back to a
local Whisper model. It was called VoiceType, then SpeakIt, then HeySpeaky,
then SpeakIt again for four weeks, and since 19 November 2026 HeySpeaky
again - the owner chose it, and said the HeySpeaky he has used every day
since 26 September is the version that counts.

The owner is Miras. He does not read code. **Answer him in Russian**, plainly,
without jargon, and say what you actually did and what you could not do.

## The map

| File | What it does |
| --- | --- |
| `run.py` | entry point, launched with pythonw.exe |
| `heyspeaky/app.py` | the controller and the state machine |
| `heyspeaky/config.py` | defaults, and config.json loading |
| `heyspeaky/theme.py` | every colour, size and timing: pill, composer, tray panel |
| `heyspeaky/glass.py` | draws the pill, the correction composer and the tray panel |
| `heyspeaky/overlay.py` | the window: never focused, and its two buttons |
| `heyspeaky/engine.py` | RealtimeSTT: capture and voice activity detection |
| `heyspeaky/transcribe.py` | OpenAI and local backends, the key lookup |
| `heyspeaky/languages.py` | the languages list and its tray grouping |
| `heyspeaky/dictionary.py` | words this person says that the model gets wrong |
| `heyspeaky/alphabet.py` | the alphabet check: a word put back in the alphabet it was spoken in |
| `heyspeaky/correct.py` | Ctrl+Alt+Win: the box that asks what it should have said |
| `heyspeaky/panel.py` | the tray panel: what a click on the tray icon opens |
| `heyspeaky/apikey.py` | the OpenAI key: pasted into the tray panel, checked, saved |
| `heyspeaky/localmodels.py` | which model transcribes on this laptop, and its download |
| `heyspeaky/keymap.py` | typing what the keyboard layout means, not what Tk decoded |
| `heyspeaky/levels.py` | making a quiet recording loud enough to transcribe |
| `heyspeaky/sound.py` | the tone at the end, built here, not shipped |
| `heyspeaky/diagnostics.py` | the problem report people send you |
| `heyspeaky/tray.py` `hotkey.py` `mic.py` `output.py` `winjob.py` | the rest |
| `install.ps1` `uninstall.ps1` | how everyone installs and removes it |
| `tools/doctor.py` | the check-up; the installer runs it with `--install` |
| `tools/ui_lab.py` | draws every state to a PNG, or `--gif` to animate it |
| `tools/readme_media.py` | the README's pictures, from the same drawing code; `--film` takes the poster and social preview from the film |
| `video/` | the film: Speaky, the Mono pill with eyes, in a 3D world drawn in code (Remotion + three.js); build it outside OneDrive (`video/README.md`) |
| `tools/benchmark.py` | measures models against real recordings |
| `tools/language_drill.py` | measures sentences that change language halfway |
| `tools/voice_lab.py` | the listening lab: web sentences, many voices and rooms, through the app's own path; lives in `%LOCALAPPDATA%\HeySpeaky-lab` |
| `tools/live_check.py` | shows the pill on the real screen and photographs it |
| `tools/correction_check.py` | the same, for the correction composer: hovers, clicks, drags |
| `tools/panel_check.py` | the same, for the tray panel, typing in Kazakh |
| `tools/make_icon.py` | draws the shortcuts' icon; the installer runs it |
| `tools/session_brief.py` | a session's starting facts; runs when a session starts |
| `tools/try_demo.py` | runs a recording through both backends |

## Rules that cost something to learn

Each rule says what to do. Its story - the measurement, the date, what broke -
is in [docs/why.md](docs/why.md): read it before you undo a rule, and add a new
rule here in a line or two, with its story there.

- **Never put AI attribution anywhere** - not in commits, files or pull
  requests, and do not mention Claude or Anthropic in the repository. Owner's
  rule. ([why](docs/why.md#attribution))
- **`install.ps1` and `uninstall.ps1` must stay ASCII and must parse** before
  any commit: the installer is how everyone updates. ([why](docs/why.md#ascii-installer))
- **Run the tests and the strict compile before pushing.** A `SyntaxWarning`
  fails CI. ([why](docs/why.md#tests))
- **Never commit a problem report, a recording or a key.**
  ([why](docs/why.md#private-files))
- **There is no console.** Under pythonw.exe `print()` goes nowhere and can
  raise; use the logger. ([why](docs/why.md#console))
- **The look changes in `theme.py`**, checked in `tools/ui_lab.py` first. The
  pill is cross, waveform, tick, and never the transcript. ([why](docs/why.md#the-look))
- **Silence is drawn as dots, not as motion**: bars scroll left, newest on the
  right, and fall to dots when nothing is heard. ([why](docs/why.md#silence))
- **The pill is a layered window** drawn by `UpdateLayeredWindow`: never
  `root.attributes("-alpha")` on it. ([why](docs/why.md#layered-window))
- **The pill must never take focus and never appear in Alt+Tab**
  (`WS_EX_NOACTIVATE`); clicks land only on the cross and the tick. ([why](docs/why.md#focus))
- **Hands-free is a double tap of the whole chord**; a single tap does nothing,
  and the old latch stays off (`hotkey.tap_max: 0`). ([why](docs/why.md#hands-free))
- **The hook watchdog must not fire on a moving mouse**, and must never probe
  by injecting a key: `SendInput` stops the laptop sleeping. ([why](docs/why.md#watchdog))
- **The transcription worker must die with the app** (`winjob.py`).
  ([why](docs/why.md#worker))
- **Keys live outside the project**, in `%APPDATA%\HeySpeaky\openai.key`. Never
  log one, print one or put one in config.json. ([why](docs/why.md#keys))
- **Quiet audio comes back as an empty string, not an error**: `levels.py`
  boosts it, and quiet audio that comes back empty says "Too quiet".
  ([why](docs/why.md#quiet-audio))
- **The order of `cloud.languages` is a priority order**: English never first,
  and last; one switched on in the tray goes to the front. ([why](docs/why.md#language-order))
- **A new install starts with the computer's own languages**, and
  `language_menu` is stored whole (`config._WHOLE`). ([why](docs/why.md#first-languages))
- **A new default reaches nobody who already has a config.json**: put the old
  one in `SUPERSEDED_LANGUAGES`; `_migrate` upgrades only an exact match. ([why](docs/why.md#new-defaults))
- **Write config.json and dictionary.json through `config.write_json`**, which
  never writes over a file it could not read. ([why](docs/why.md#json-files))
- **A name the model keeps mangling is fixed by `cloud.keywords`**, not by the
  language order. ([why](docs/why.md#keywords))
- **The model cannot be taught how somebody sounds; `dictionary.py` is what to
  do instead**: it primes the request and fixes the spelling after. ([why](docs/why.md#dictionary))
- **One correction is a hint, not a rule**: it replaces only once made
  `REPLACE_AFTER` (2) times; a Kazakh spelling is fixed at once. ([why](docs/why.md#hints))
- **The alphabet check** (`alphabet.py`) may change only the alphabet
  (`same_words`), only after the cloud, and never logs the text. It runs on
  text with Latin in it, or when the cloud heard Kazakh (`heard`). Its
  wording and model (gpt-5.5) were chosen on the drill; change either only
  with a drill run. ([why](docs/why.md#alphabet-check))
- **Measure a change to hearing in the listening lab** (`tools/voice_lab.py`)
  and decide on the held-out quarter; what it makes stays out of the
  repository. ([why](docs/why.md#listening-lab))
- **The lab spends the owner's money, the same credit his dictation runs
  on**: ask him before a run over half an hour of audio (`--max-minutes`),
  keep `--workers` low, and never run it while he is dictating.
  ([why](docs/why.md#the-labs-bill))
- **Out of credit is never retried** (`transcribe.NoCredit`), and the pill
  says "no OpenAI credit". ([why](docs/why.md#the-labs-bill))
- **When the model is unsure it is asked again** with the next languages
  first (`Router._second_opinion`, `UNSURE_BELOW`); the surest answer wins
  unless it is shorter. The lab found no better line than -0.3; move it
  only for a real failure in the owner's log ("Cloud heard … sure on
  average"). ([why](docs/why.md#asking-again-when-unsure))
- **Your words is a page in the panel, not a file**; its action names carry a
  CRC of the entry, never the word. ([why](docs/why.md#your-words))
- **The correction key is Ctrl+Alt+Win, not Ctrl+Alt+Space**, in any order.
  ([why](docs/why.md#correction-key))
- **The correction key is the only one carved out of `cancel_on_other_key`**,
  and one correction at a time (`correct.OneAtATime`). ([why](docs/why.md#cancelling))
- **A chord that has been used stays used until Ctrl and Alt come up**
  (`_spend_chord_locked`). ([why](docs/why.md#used-chords))
- **The correction composer is two windows**: layered glass (`back`, never
  `-alpha`) and an ordinary field (`top`) that takes focus. ([why](docs/why.md#composer))
- **The pill and the composer are drawn by the same code**; a change there
  must leave the pill pixel-identical. ([why](docs/why.md#shared-drawing))
- **The ring round the field is measured along its edge, not by angle.** Look
  at it with `tools/correction_check.py`. ([why](docs/why.md#ring))
- **One design, three windows: the pill, the composer and the tray panel.** A
  tray click opens `panel.py`, the one layered window that takes focus. ([why](docs/why.md#tray-panel))
- **There are two looks, and the glass stays exactly as it was**, byte for
  byte; Mono's numbers are `MONO_` in `theme.py`. ([why](docs/why.md#two-looks))
- **The mono sound is rebuilt from the reel, not copied from it**
  (`sound.VOICES["blip"]`). ([why](docs/why.md#mono-sound))
- **A shadow fades to nothing before its window's edge**
  (`glass._fade_at_edges`); the window does not grow. ([why](docs/why.md#shadows))
- **Never draw something translucent straight onto an RGBA frame**: own layer,
  then `alpha_composite`. ([why](docs/why.md#translucent-drawing))
- **Quit asks twice** (`theme.QUIT_ARMED`). ([why](docs/why.md#quit))
- **The key is pasted into the tray panel** (`apikey.py`), through
  `submit_key`, never `act`, and checked with OpenAI first. ([why](docs/why.md#pasting-the-key))
- **People choose the local model** (`localmodels.py`); `engine.reload` never
  runs mid-recording. ([why](docs/why.md#local-model))
- **Typing in the panel is a language search**; Kazakh letters fold to Russian
  ones. ([why](docs/why.md#language-search))
- **Tk cannot type Kazakh by itself** (`keymap.py`): text fields ask Windows
  (`ToUnicodeEx`) what the key means. ([why](docs/why.md#kazakh-typing))
- **The shortcuts have HeySpeaky's own icon**, drawn at install by
  `tools/make_icon.py`. ([why](docs/why.md#icon))
- **Reading somebody's selection means borrowing the clipboard**
  (`output.copy_selection`); log counts, never the text. ([why](docs/why.md#selection))
- **A session starts with a brief, not a ritual** (`tools/session_brief.py`):
  counts and program names, never anything dictated. ([why](docs/why.md#session-brief))
- **A key the hook thinks is held is checked with Windows**
  (`_forget_released_keys_locked`); the hook's own list goes stale. ([why](docs/why.md#held-keys))
- **A Ctrl+Alt that does nothing now leaves a line** in the log, never naming
  a letter. ([why](docs/why.md#silent-chord))
- **OpenAI is the default and local is a fallback.** ([why](docs/why.md#openai-first))

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

Every fault the owner has found in the pill was invisible to the tests and to
`ui_lab.py`, because both draw it over a backdrop that holds still. Run
`tools\live_check.py` when the look changes: it puts the real window on the
real screen and photographs it.

A real install is the only proof the installer works. CI does one on a clean
Windows runner for every push, including the uninstall.

## Five generations of the name

VoiceType, then SpeakIt, then HeySpeaky, then SpeakIt again from 26 October,
and HeySpeaky again since 19 November 2026. Old installs are carried across,
not abandoned: `Move-FromOldNames` in `install.ps1` copies settings and the
key and removes the old shortcuts, `uninstall.ps1` knows all three names, and
`LEGACY_KEY_FILES` in `transcribe.py` and `LEGACY_PATHS` in `dictionary.py`
still read the old paths.

- **The HeySpeaky of 26 September (`304b960`) is the version that counts**: the
  October rename (`0187458`) was reverted whole. ([why](docs/why.md#the-way-back))
- **Never touch the owner's SpeakIt folder or `%APPDATA%\SpeakIt\openai.key`**:
  that is his live key. ([why](docs/why.md#used-names))

## What the owner decided

- Quality beats cost: OpenAI stays the default, and the spending counter only
  warns, it never silently switches to the weaker local model.
- No bots in GitHub issues. He decides what gets answered.
- Private notes, money and feedback live in his Obsidian vault next to the
  project, never in this public repository.
