# Changelog

Notable changes to HeySpeaky, called VoiceType until September 2026 and then
SpeakIt. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

VoiceType became SpeakIt, and SpeakIt is now HeySpeaky. Old GitHub links still
work, a key saved under either old name is still found, settings and the key
are copied across on the first update, and the old shortcuts are removed so
only one copy starts with Windows.

### Fixed

- A fresh install could not transcribe anything. RealtimeSTT 1.1.2 moved
  faster-whisper and silero-vad into an optional extra that
  `requirements.txt` never asked for. Depending on which was missing, the app
  either had no speech model runtime, or started, looked healthy, and never
  became ready to dictate.
- Installing failed unless the Python on PATH was 3.11 or 3.12, and could
  still fail with the right one. The installer no longer uses your Python at
  all: it downloads a pinned, checksummed uv, which puts Python 3.12 inside the
  install folder. Every package is pinned in `requirements.lock`.
- Installing into any path over Windows' 260 character limit failed while
  building `halo` from source, because PyPI only has a Python 2 wheel for it. A
  Python 3 wheel now ships in `vendor/`, and nothing is built from source.
- A failed one-command install closed its own window. The installer ended with
  `exit`, which inside `irm | iex` ends the PowerShell session and takes the
  error message with it. Failures now stay on screen and are logged to
  `%TEMP%\SpeakIt-install.log`.
- Windows Defender blocked the install command itself. It started a second
  `powershell.exe` with `-ExecutionPolicy Bypass` and a download on its command
  line, which Defender's machine-learning model reports as
  Trojan:Win32/Commando.A!ml. The command is now plain `irm ... | iex`, which
  runs in the PowerShell that is already open.
- An update could end with "SpeakIt installed but did not start" while it was
  in fact starting. The installer waited 20 seconds, and the first start after
  an update, with every file new to Python and PyTorch read from a cold disk,
  took 29 on a fast laptop. It now waits two minutes, and only reports a
  failure if SpeakIt actually exited.
- The installer now checks path length, free space and the Visual C++ runtime
  up front, downloads the speech models and loads one before finishing, and
  confirms the app actually started. CI runs it on a clean Windows runner.

### Added

- A window opens during the install with a progress bar, a rough time left,
  and a dinosaur that jumps cactuses (Space) until SpeakIt is ready. It closes
  itself when the install finishes. `-NoGame` skips it.
- The install log records how long each step took.
- Any language Whisper knows can be added from the tray, under Language > Add
  or remove languages, grouped by first letter. The tray's pin list and the
  list the OpenAI model is told to expect are now one list, so they can no
  longer disagree.
- The OpenAI key can go straight into the install command:
  `$env:OPENAI_API_KEY = "sk-..."; irm .../install.ps1 | iex`. The installer
  checks it with OpenAI, saves it to the key file, and takes it back out of
  the PowerShell history file. Running the same line again changes the key.
- Without a key in the command, a fresh install asks whether to transcribe with
  OpenAI or on this computer, and recommends OpenAI. Choosing it opens the page
  where keys are created and takes a pasted key, checked the same way.
  `-Backend openai` or `-Backend local` answers in advance. Updates never ask.
- `uninstall.ps1`, one command that removes every copy of SpeakIt and
  VoiceType, their shortcuts, the saved key and the downloaded speech models.
  A git clone is never deleted.
- Tray > Save a problem report. It saves a ZIP to the Desktop with the logs,
  the settings without the key, the PC and microphone, and the last 5
  recordings with their transcripts, so a problem on someone else's PC can be
  looked at on yours. Recordings are kept in memory only until then.
- One log line per dictation: seconds held and captured, loudness, clipping,
  which backend was used and why, and how long it took. Captured audio well
  short of the time held is logged as dropped audio.
- GPU detection. `model.device` and `model.compute_type` now default to
  `"auto"`, which picks cuda/float16 when an NVIDIA card is actually usable and
  cpu/int8 otherwise. The old hardcoded cpu silently wasted a GPU on the
  machines that have one. Detecting a card is not the same as being able to use
  it, so a cuda load that fails falls back to cpu instead of refusing to start.
- A test suite, `tests/test_voicetype.py`, covering the parts that need no
  microphone: audio maths, segment merging, the cloud request ladder, config
  merging, hardware resolution and the capped log stream. 33 tests, standard
  library only, run in CI on 3.11 and 3.12.
- `tools/doctor.py` reports which device the local model will use.
- `demo/four_languages.wav`, an 11 second clip that changes language
  three times with no pause, and `tools/try_demo.py` to run it through
  either backend. `--sweep` runs any recording under a range of language
  lists, which is how the `languages` finding below was checked.

### Changed

- The installer loads the speech engine once instead of twice. It used to
  start the engine as a check and then start SpeakIt, which loaded it again;
  now it waits for SpeakIt's own engine to report ready. With `-NoStart` it
  still runs the separate check.
- Installer and uninstaller messages are always English. Errors from
  PowerShell and Windows used to come out in the Windows display language,
  mixed in with English ones.
- Uninstall is right below Install in the README.
- The `languages` list is no longer described as load-bearing.
  Rerunning that measurement, `gpt-transcribe` returns both halves of a
  switched sentence with no list at all, in both directions, and all four
  languages of the demo clip under every list. Either the model improved
  or synthesised speech is too clean to show the difference. The list is
  still sent; the claim about it is now marked as unreproduced.
- Issue templates cut from two to one. The language report asked for
  labels that do not exist in this repository.
- CI runs with `permissions: contents: read` instead of inheriting the
  repository default.
- One-command install: `irm .../install.ps1 | iex`. The same script installs a
  local copy when run from one, and bootstraps the project first when piped in.
- `transcription.cloud.timeout` lowered from 30 s to 15 s. Measured normal
  range is 1.1 to 2.6 s and the worst seen in real use was 7.7 s, so past 15 s the
  request is stuck rather than slow. Waiting half a minute before falling
  back to a local model that answers in under two seconds is a bad trade.
- Documented where the wait after you stop talking actually goes, including
  the finding that the cloud backend is not the faster option. Its median is
  comparable to local and its tail is much worse.

### Removed

- The grey live text while you speak. It came from a small model that was
  never close to the final transcript, and loading and running it cost CPU
  that a weak laptop needs for recording. The pill now shows the waveform
  until the real text arrives. `model.realtime`, `model.beam_size_realtime` and
  `overlay.show_partial_text` are gone from the settings.
- The "Clean up with AI" option. It never looked in the key file the
  installer writes, so for anyone who installed that way it did nothing. A
  `cleanup` section left in an old `config.json` is ignored.
- `install.ps1 -Uninstall`, which only removed the shortcuts. `uninstall.ps1`
  replaces it.
- `docs/accuracy.md`, `docs/architecture.md` and `docs/configuration.md`. The
  comments in `speakit/config.py` still explain every setting.

## [1.0.0] - 2026-09-08

First public release.

### Added

- Push-to-talk and hands-free dictation on `Ctrl`+`Alt`, anywhere in Windows.
- Click-through overlay above the taskbar with a live waveform and preview
  text; never takes focus, so the caret stays where it was.
- Local transcription with faster-whisper, or OpenAI `gpt-transcribe`,
  switchable from the tray without a restart.
- Mid-sentence language switching: per-segment language detection locally, and
  a `languages` list for the cloud backend.
- English, Russian and German out of the box; any Whisper language via config.
- Silence guard, so a recording with no speech in it can never produce a
  hallucinated sentence.
- Optional AI cleanup pass, with a length guard that keeps the raw transcript
  if the model rewrites too much.
- Keyboard-hook watchdog, because Windows drops low-level hooks silently after
  sleep and the only symptom is that the hotkey stops working.
- One-command install: `irm .../install.ps1 | iex`. The same script installs a
  local copy when run from one, and downloads the project first when piped in
  with nothing on disk. Re-running it updates in place and keeps `config.json`.
- `INSTALL.bat`, `UNINSTALL.bat` and `CHECKUP.bat`, for anyone who would rather
  not use a terminal at all.
- `tools/doctor.py`, a single check-up that reports what is wrong and what to
  do about it.

### Fixed

- **Orphaned transcription workers.** A force-killed parent runs no cleanup
  code, so RealtimeSTT's child process survived, spun on a broken pipe and
  logged a traceback per iteration. Twelve were found on the development
  machine, the oldest three days old, having written 8.7 GB between them. The
  process now joins a Windows job object marked kill-on-close, so the OS
  terminates children whatever happens to the parent. `logs/stdout.log` is
  also capped at 2 MB per process.
- **Slow fallback when the network is down.** Only a total timeout was set, and
  `getaddrinfo` blocks for as long as Windows wants, measured at 11.6 s before
  the local fallback even started. The connect phase is now bounded at 4 s, and
  a connection failure suppresses cloud attempts for the next 20 s. Measured
  11.6 s to 4.1 s, then 0.00 s.
- **Silent downgrade to the local model.** Falling back is right; doing it
  invisibly is not, since local is much weaker on Russian and German. The
  status line now says `local (offline)` and why.
- **Preview text looked final.** It comes from a much smaller model,
  a different system entirely on the cloud backend, so it regularly disagrees
  with the final text. It is now drawn greyed out, and can be turned off with
  `overlay.show_partial_text`.
- **Quiet microphones failed the silence guard.** WebRTC VAD gets less
  sensitive as input gets quieter; real Russian speech scored 8 against a
  threshold of 12 and was discarded as silence. Default aggressiveness lowered
  to 1, where the same speech scores 23-40 and silence still reaches only 5.
- Clipboard access violation caused by ctypes truncating 64-bit handles.
- Model load failing on a cold boot, when the Startup shortcut fires before
  Wi-Fi is up; it now retries offline against the cached weights.

[1.0.0]: https://github.com/Maslitsa/VoiceType/releases/tag/v1.0.0
