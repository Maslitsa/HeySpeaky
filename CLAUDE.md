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
| `heyspeaky/dictionary.py` | words this person says that the model gets wrong |
| `heyspeaky/correct.py` | Ctrl+Alt+Win: the box that asks what it should have said |
| `heyspeaky/levels.py` | making a quiet recording loud enough to transcribe |
| `heyspeaky/sound.py` | the tone at the end, built here, not shipped |
| `heyspeaky/diagnostics.py` | the problem report people send you |
| `heyspeaky/tray.py` `hotkey.py` `mic.py` `output.py` `winjob.py` | the rest |
| `install.ps1` `uninstall.ps1` | how everyone installs and removes it |
| `tools/doctor.py` | the check-up; the installer runs it with `--install` |
| `tools/ui_lab.py` | draws every state to a PNG, or `--gif` to animate it |
| `tools/benchmark.py` | measures models against real recordings |
| `tools/language_drill.py` | measures sentences that change language halfway |
| `tools/live_check.py` | shows the pill on the real screen and photographs it |
| `tools/correction_check.py` | the same, for the correction box |
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
- **The keyboard hook has a watchdog, and it must not fire on a moving
  mouse.** Windows drops a low-level hook silently - after sleep, or if the
  callback ever overruns - and the only symptom is that Ctrl+Alt stops
  working. There is no API for "is my hook alive", so `hotkey.py` compares
  when Windows last saw input against when the hook last saw a key. A moving
  mouse looks identical to a dead hook through that pair, and the first
  version believed it: the owner's log held 455 refreshes in three days, one a
  minute for as long as he used the mouse, with no dead hook behind any of
  them. Each refresh unhooks and rehooks, so each is a window where a press
  lands on nothing. `_dead_hook_reason` now asks `GetCursorPos` as well and
  stays quiet when the pointer moved, except just after a resume. That cut
  it to 36 the next day, and the log explained the rest: 16 were input older
  than the last check, which a comparison with the last check cannot see
  (`_pointer_explains` now places the input against when the pointer moved),
  and 21 were a fresh hook that heard no key at all until the next refresh -
  input that was not keys, most likely a wheel or a click. A refresh answered
  by silence now doubles the wait, up to ten minutes, and the first key heard
  brings the minute back (`_refresh_gap`). Waking from sleep never waits.
  Do not go back to injecting a key to probe: `SendInput` resets the idle
  timer, so a scheduled probe stops the laptop ever sleeping.
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
- **The order of `cloud.languages` is a priority order, not a list.** A
  language near the end of it is effectively ignored on a short stretch of
  speech. Measured over 24 recordings that change language mid-clause:
  `["en","ru","de","kk"]` got 17% of words wrong and lost 35% of the Cyrillic
  to Latin; `["kk","ru","en","de"]` got 11% and 22%, twice in a row. Kazakh
  fourth turned "Ertengh kezdesemiz" into "You think is the same"; Kazakh
  first, or `language="kk"` pinned by hand, brought it back whole - which is
  how we know the audio was never at fault. **English never goes first**: the
  model leans that way unasked, so the front of the list is worth more to
  whichever language it is most likely to mishear. A language switched on from
  the tray is inserted at the front for the same reason.
  `tools/language_drill.py` is how any of this gets re-measured.
- **A new default reaches nobody who already has a config.json.** That file
  is the user's and the installer never overwrites it, so the owner was still
  running the measured-worse language order a day after it was replaced, and
  the fix he had been told about had never applied to him. `_migrate` in
  `config.py` upgrades a stored list that exactly matches a superseded
  default, and leaves anything else alone. Put a retired default in
  `SUPERSEDED_LANGUAGES` when you replace one; do not reach further than
  that, because every other setting might be something somebody typed.
- **Write config.json and dictionary.json through `config.write_json`.** Both
  are edited by hand, and a typo makes one read as missing so dictation keeps
  going - after which the next save used to write over it. It now moves an
  unreadable file aside to `<name>.broken-<time>` first, and replaces the file
  in one step so a crash cannot leave half of it.
- **A name the model keeps mangling is fixed by `cloud.keywords`, not by the
  language order.** The owner's friend is called Magzhan and he got back
  Marzhan, Makzhan and Bagzhan. Measured on synthesised speech, four clips:
  Kazakh first on its own rescued it 0 times out of 4, the same as the old
  order; adding the name to `keywords` rescued it 2 out of 2 in a Kazakh
  sentence, plain and slurred alike. In a Russian sentence the keyword still
  moved it from "Marzhan" to "Magzhan" but the Kazakh letter did not survive
  into Russian text, so priming narrows the gap and does not always close it.
  That remainder is what a spelling fix applied after transcription is for.
- **The model cannot be taught how somebody sounds, and `dictionary.py` is
  what to do instead.** There is no fine-tuning here: the model is OpenAI's.
  What a correction can do is name the word in the request, which primes the
  decoder, and fix the spelling afterwards, which is certain. Both, together,
  is the whole feature, and it lives in `%APPDATA%\HeySpeaky\dictionary.json`
  next to the key - personal, growing, and not something to put in
  config.json. `Router.transcribe` applies it, so local transcription gets it
  too. Two things to keep: the words go out newest-first and capped, because
  the steering text has a budget; and a replacement never fires on a word
  that is itself in the dictionary as something meant, because "Marzhan" is a
  real name belonging to somebody else and eating it every time it is said
  would be worse than the mistake being fixed. That is also why only the
  owner's own corrections are ever applied, never a guess. A word is stored
  without the punctuation around it - he selected "Мағжан." with its full
  stop and it went to the model like that - but only from the ends, because
  inside a word a dot or a hyphen is part of it. The suite points
  `dictionary.PATH` at an empty file for the whole run, because that file is
  read fresh on every transcription: without it the keyword tests pass on a
  clean CI runner and fail on any machine that has actually used the feature.
- **The correction key is Ctrl+Alt+Win, not Ctrl+Alt+Space.** Space was the
  first choice, and on the owner's machine another program owns
  Ctrl+Alt+Space as a global shortcut: it gets the keys first, and a hook
  that only watches cannot take them back. Pressed on his machine, fast,
  slow and Win first, Ctrl+Alt+Win did not open the Start menu (Win alone
  did, which is how the check was checked). `_migrate` moves a stored
  "space" to the new default. The three keys are accepted in any order.
- **The correction key is the only one carved out of `cancel_on_other_key`**,
  while nothing is being recorded or within `CHORD_SLOP` of a recording the
  same chord started - Ctrl+Alt a little ahead of Win is one gesture, and it
  asked for the box. Later in a recording it cancels like any other key.
  The correction also marks the chord dirty, because two corrections in a
  row are two chords released quickly - the exact shape of the double tap
  that goes hands-free. And it is one correction at a time
  (`correct.OneAtATime`), claimed on the key press rather than when the box
  appears: the box waits for Ctrl and Alt to come up, and the key pressed
  again inside a held chord is a fresh key-down, not a repeat. The owner's
  log showed two boxes open on top of each other. A press while the box is
  open brings it forward instead.
- **A chord that has been used stays used until Ctrl and Alt come up**
  (`_spend_chord_locked`). Clearing it on a cancel let the chord re-arm the
  moment the other key was released: the owner's log has a recording
  cancelled by Win and a new one starting 0.37 s later, twice.
- **The correction box takes focus and the pill never does.** They are
  opposite windows and both are right: dictation is worthless if it steals
  the caret, and a box you cannot type into is worthless too. The box is an
  ordinary `Toplevel`, not a layered surface, so none of the pill's rules
  apply to it - `-alpha` is fine here and fatal there - but Windows 10 will
  not round a window with no frame, so it clips itself with `SetWindowRgn`.
  Look at it with `tools/correction_check.py`, which also drags it and runs
  it at several screen scales.
- **Both windows are drawn by the same code, and that is the point.**
  `glass.card` builds the box's background out of the three layers
  `glass.prepare` builds the capsule from: the tint, the bright edge
  strongest along the top, the specular just inside it. The one piece of
  colour in either window is the waveform's palette, which runs as a line
  under the field you type in. Sizes live in `theme.py` with everything else
  about the look. The box lays the same thing out twice - once as pixels in
  the picture, once as widgets over it - so every size is computed once in
  `CorrectionBox.__init__` and used by both, and the well in the picture is
  where the entry is placed. Change one without the other and the field
  floats off its own slot.
- **Reading somebody's selection means borrowing the clipboard.** There is no
  API for another program's selection. `output.copy_selection` empties the
  clipboard first - otherwise a Ctrl+C that copies nothing, because nothing
  was selected, leaves the old contents sitting there looking like a
  selection - sends Ctrl+C only once Ctrl and Alt are up, and puts back what
  was there. The same modifier wait is why `deliver` exists in that shape.
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

Every fault the owner has found in the pill was invisible to the tests and to
`ui_lab.py`, because both draw it over a backdrop that holds still. Run
`tools\live_check.py` when the look changes: it puts the real window on the
real screen and photographs it.

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
