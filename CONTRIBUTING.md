# Contributing

Thank you. Small changes are the easiest to review, and every kind is
welcome: a fix, a measurement, a sentence it gets wrong.

**The single most useful thing you can send** is a sentence it gets wrong in
your languages: what you said and what it typed, with the recording if you
can. Use the [It wrote the wrong words](https://github.com/Maslitsa/HeySpeaky/issues/new?template=wrong_words.yml)
form. Everything here was tuned on Kazakh, Russian, German and English spoken
by one person into one laptop microphone, so your languages are new
information.

Never paste an API key, including inside a log excerpt.

## Setting up

```powershell
git clone https://github.com/Maslitsa/HeySpeaky.git
cd HeySpeaky
powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoStart -NoAutostart
```

That builds `.venv` in the clone without starting HeySpeaky or registering it
to start with Windows. Then run it with a console, so you can watch it:

```powershell
.venv\Scripts\python.exe run.py
```

`pythonw.exe` instead of `python.exe` runs it the way it ships, with no
window. The log is in `logs\heyspeaky.log`.

## Before a pull request

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe -W error::SyntaxWarning -m compileall -q heyspeaky run.py tools
```

About 300 tests, twenty seconds, no microphone or GPU needed: audio maths,
the shape of the OpenAI request, the alphabet check, the dictionary, the
hotkey's state machine, the settings, and every window drawn as a picture
and checked pixel by pixel. What they cannot cover is Win32 itself and a real
microphone, so "I ran it and dictated with it for a day" is a good thing to
write in a pull request. CI runs the same on Python 3.11 and 3.12, and
installs HeySpeaky on a clean Windows for every push.

If you change how anything looks, draw it first:

```powershell
.venv\Scripts\python.exe tools\ui_lab.py --out lab.png
```

## How one dictation goes through the code

1. `hotkey.py` hears Ctrl+Alt held down, or tapped twice for hands-free,
   through a low-level keyboard hook, and tells `app.py`.
2. `app.py` is the controller: one state machine, idle, recording,
   transcribing. It shows the pill, `overlay.py`, which `glass.py` draws
   with the sizes and colours in `theme.py`.
3. `engine.py` records through RealtimeSTT, which also notices when you stop
   talking. `mic.py` opens the microphone and `levels.py` makes a quiet
   recording loud enough to transcribe.
4. `transcribe.py` sends the audio to OpenAI, or to Whisper on your own
   computer when there is no key or no network. Then `alphabet.py` puts any
   word written in the wrong alphabet back in its own, and `dictionary.py`
   applies the corrections you have taught it.
5. `output.py` pastes the text into the window you were typing in, once
   Ctrl and Alt are up, and puts your clipboard back.

Around that: `tray.py` and `panel.py` are the tray icon and its panel,
`correct.py` is the Ctrl+Alt+Win box that asks what it should have said,
`config.py` holds every default with the reason for it, and
`diagnostics.py` builds the problem report. [AGENTS.md](AGENTS.md) has a
line on every file, and the rules that cost something to learn.

## Measuring

Several defaults look arbitrary and are not: each came from a measurement,
and the comment above it says which. If you change one, include a
measurement, or the next person will change it back.

- `tools/language_drill.py --tts` reads twelve sentences that change
  language halfway, twice each, and compares what each setting makes of
  them: words wrong, and how much of the Cyrillic came back in Latin
  letters. A few cents of your own key per run.
- `tools/benchmark.py` compares models on recordings you already have.
- `tools/live_check.py`, `correction_check.py` and `panel_check.py` put the
  real windows on the real screen and photograph them. They move the
  pointer, so run them when nobody is using the computer.

## House rules

- **Comments explain why, not what.** The why is what stops a measured
  value from being "tidied" back.
- **No `print()`.** The app runs under `pythonw.exe`, where print goes
  nowhere and can raise. Use the module's logger.
- **Never log what was said**, or a key. Log counts, timings and program
  names.
- **`install.ps1` and `uninstall.ps1` stay ASCII**, because Windows
  PowerShell 5.1 mangles anything else, and every update goes through them.

Match the surrounding code otherwise: 4 spaces, about 79 columns, standard
library imports first.
