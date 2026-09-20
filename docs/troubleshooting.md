# Troubleshooting

Logs are in `logs\heyspeaky.log` (rotating). Anything a dependency printed
rather than logged lands in `logs\stdout.log`.

---

## It works worse on another PC

On the PC where it is worse, dictate a few sentences, then click the tray icon
and **Save a problem report**. A ZIP appears on the Desktop. It holds the logs,
the settings with the key removed, details of the PC and its microphone, and
the last 5 recordings with what they were transcribed as. Send it to whoever
is helping.

`report.txt` in the ZIP answers the usual questions:

- **Is it really using OpenAI?** Each dictation says `OpenAI` or `local`, and
  a fallback gives its reason in brackets: `no API key`, `offline` or
  `cloud error`.
- **Is the audio good?** `captured` well short of `held` means part of the
  recording was lost, usually to a busy CPU. `average` below about -45 dB is a
  very quiet microphone. `clipped` above 1% is distorted. Another app holding
  the microphone, like a call in WhatsApp or Teams, can also change what
  HeySpeaky hears.

To tell a microphone problem from a setup problem, run their recording through
HeySpeaky on your own PC:

```powershell
cd "$env:LOCALAPPDATA\Programs\HeySpeaky"
.venv\Scripts\python.exe tools\try_demo.py "$HOME\Downloads\recordings\1.wav" --both
```

If it comes out badly on your PC too, the audio is the problem. If it comes
out fine, the difference is in their setup.

---

## It records, but always says "Nothing heard"

The recording was captured and then thrown away by the silence guard. Run:

```powershell
cd "$env:LOCALAPPDATA\Programs\HeySpeaky"
.venv\Scripts\python.exe tools\check_mic.py
```

It records you for six seconds and reports the level, whether the speech
detector fires, and what the transcript comes back as. **Speak during those six
seconds**, because it cannot tell a silent room from a broken microphone.

Read the `quiet vs loud` number first:

| Reading | Meaning | Fix |
| --- | --- | --- |
| **below ~2** | The microphone is not picking up your voice at all. The signal never changes. | Nothing in this app will help. Check **Settings → System → Sound → Input**: right device selected, bar moves when you speak. Check the mute key and any privacy shutter. Check **Settings → Privacy → Microphone** allows desktop apps. |
| **above 2, but `longest run` below the threshold** | Your voice is there but too quiet for the detector. | Raise the level: **Sound → Input → your mic → Properties**, Volume to 100 and enable Microphone Boost. Speak closer. Or lower `recording.min_speech_run`. |
| **above 2, run above threshold** | The microphone is fine; the problem is elsewhere. | Check the log. |

### Why a real sentence can be discarded

Whisper invents plausible sentences out of silence, so every recording is
checked for real speech first. That check is WebRTC VAD, and **it gets less
sensitive the quieter the input is**. On a very quiet microphone, genuinely
spoken Russian once scored a run of 8 against a threshold of 12 and was thrown
away, while silence scored 4.

`recording.vad_aggressiveness` defaults to `1` for this reason. If you still
get false rejections, lower `recording.min_speech_run` (12 = 240 ms of
continuous speech). Raise it instead if room noise is getting through.

---

## It got slower, or the label says "local (offline)"

The status line after a dictation tells you which backend produced the text:

| Label | Meaning |
| --- | --- |
| `· cloud` | OpenAI, as configured |
| `· local (offline)` | The network was unreachable, so it fell back |
| `· local (no API key)` | No key configured |
| `· local (cloud error)` | The API returned an error |

**`local (offline)` is the one to care about**, because local is markedly
weaker on Russian and German. A sentence that was perfect yesterday can come
back mangled purely because the wifi dropped.

A failed connection also costs time. HeySpeaky bounds the connect phase at 4
seconds and then, having seen the network fail, skips the cloud for the next 20
seconds rather than stalling on every recording. Before that bound, a DNS
failure took **11.6 s** before the fallback even started.

If dictation is slow but still says `· cloud`, that is request latency, not
HeySpeaky. Measured here, the same setup ranged from 1.6 s to 7.7 s across one
evening.

---

## The hotkey stopped working

Almost certainly a lost keyboard hook. Windows removes a low-level hook
**silently**, after a sleep or if a callback ever overruns its timeout, with
no error and no crash. The app keeps running and looks perfectly healthy while
`Ctrl`+`Alt` does nothing.

A watchdog handles this. Every `hotkey.health_check_seconds` (20) it compares
when Windows last saw *any* input against when our hook last saw one. If the
system has had input we did not, the hook is refreshed, at most once per
`hotkey.min_reinstall_seconds` (60).

Nothing is injected to test it. An earlier version did inject a key, which
worked, but `SendInput` resets the system idle timer and would have quietly
stopped the laptop from ever sleeping. The passive check leaves a genuinely
idle machine reporting both as stale, so it stays quiet and the machine sleeps
normally.

Look for this in the log:

```
Keyboard hook saw nothing for 31s while Windows saw input 29s ago;
refreshing the hook (#210)
```

If it is stuck anyway, quit from the tray and start HeySpeaky again.

### It does nothing in one particular window

Windows does not deliver key events from an elevated (administrator) window to
a normal-privilege app. The hotkey will not work while such a window has focus.
Running HeySpeaky as administrator fixes it, but is not set up by default.
that is a real privilege increase for a background app that reads your
keyboard, and it should be your decision.

---

## Ctrl+Alt+key shortcuts are triggering recordings

Raise `hotkey.engage_delay` (default 0.25 s). Recording only starts once the
combo has been held that long, so a quick shortcut never reaches it.

If your keyboard layout reports right-Alt as AltGr and accented characters are
starting recordings, make sure `hotkey.accept_altgr` is `false` (the default).

---

## It pastes into the wrong place, or not at all

HeySpeaky waits for you to release Ctrl/Alt/Shift/Win before inserting
(`output.modifier_release_timeout`, 5 s), because a paste sent while Ctrl is
still down becomes a different shortcut.

If an app refuses pasted input, switch to synthesised keystrokes:

```json
{ "output": { "insert_method": "type" } }
```

Or take the text from the clipboard yourself with
`{ "output": { "insert_method": "none" } }`.

---

## Startup and processes

### It did not start when I signed in

The Startup shortcut fires before Wi-Fi is up. faster-whisper contacts Hugging
Face to check the model revision even when the weights are already cached,
which used to fail the whole load with "Server disconnected". HeySpeaky now
retries with `HF_HUB_OFFLINE=1` and uses what is on disk.

Check the log for `Models ready in …`. If the shortcut is missing entirely,
run the install command again.

### Leftover pythonw.exe processes

Should be impossible now. RealtimeSTT transcribes in a spawned child process,
and if HeySpeaky is killed without running its shutdown path (Task Manager, a
forced sign-out, a crash) that child used to be orphaned. An orphan spins on a
broken pipe, logging a traceback per iteration, and writes without limit: twelve
of them were once found on the development machine, the oldest three days old,
which had between them produced an **8.7 GB** `stdout.log`.

Two things now prevent it:

- The process joins a Windows **job object** marked kill-on-close
  ([`heyspeaky/winjob.py`](../heyspeaky/winjob.py)). Children inherit it, and
  when we die, however we die, Windows terminates everything left in it. No
  Python runs, so nothing can be skipped.
- `logs\stdout.log` is capped at 2 MB per process, so even a runaway loop
  cannot fill a disk.

`install.ps1` also clears out any orphans left by an older version.

### Only one instance runs

Enforced with a named mutex, so the Startup shortcut cannot produce duplicates.

---

## Model loading fails

### `EOFError` during startup, app never becomes ready

Do not set `silero_use_onnx` in the recorder options. Passing it **either way**
selects RealtimeSTT's legacy VAD backend, which calls `torch.hub.load()` and
asks on stdin whether you trust the repository. With no console that raises
`EOFError` and the app never finishes loading. Leaving it unset uses the
packaged ONNX model.

### "Could not initialize any automatic Silero VAD backend"

The `silero-vad` package is missing. RealtimeSTT 1.1.2 only installs it as part
of its `[default]` extra, and installs made before HeySpeaky asked for that extra
do not have it. Run the install command again.

### The installer failed

The window stays open with the reason in red, and the whole run is in
`%TEMP%\HeySpeaky-install.log`. The causes seen so far:

- **"The install folder path is too long".** Windows limits paths to 260
  characters unless long paths are turned on, and PyTorch installs files
  nearly 150 characters deep. Install somewhere short with
  `-InstallDir 'C:\HeySpeaky'`.
- **"DLL load failed" in the check at the end.** The Visual C++ runtime is
  missing and could not be added, usually because the Windows permission
  prompt was declined. Install
  [vc_redist.x64.exe](https://aka.ms/vs/17/release/vc_redist.x64.exe) and run
  the install command again.
- **"Access is denied" as soon as you press Enter.**
  Windows Defender blocks `powershell -ExecutionPolicy Bypass -c "irm ... | iex"`
  as Trojan:Win32/Commando.A!ml. That is a guess by its machine-learning
  model about the command line, not a finding in the script, and nothing is
  quarantined. An earlier version of the README gave that command. Paste the
  one in the README now, which runs in the PowerShell you already have open, or
  download the ZIP and double-click `INSTALL.bat`.
- **A download timed out.** Run the same command again. What already
  downloaded is reused.

The Python on your PATH is never the cause, because the installer does not use
it. If none of these fit, open an issue and attach the log file.

---

## Cloud transcription

### It keeps transcribing locally

`transcription.cloud.fallback_to_local` is `true`, so an unreachable API or a
missing key falls back silently rather than losing your recording. Check the
log for the reason, then confirm the key is found:

```powershell
cd "$env:LOCALAPPDATA\Programs\HeySpeaky"
.venv\Scripts\python.exe tools\check_cloud.py
```

Key lookup order is `api_key` in the config, then `OPENAI_API_KEY`, then
`%APPDATA%\HeySpeaky\openai.key`.

**An environment variable set after HeySpeaky started is invisible to it.** The
app launches from a Startup shortcut and only inherits variables that existed at
sign-in. The key file is read per request and has no such problem. Put the key
in the install command instead, as the README shows, and it is saved there.

### "not supported for this model"

`gpt-4o-transcribe` rejects `languages` and `keywords`. Use `gpt-transcribe`,
which is the default and the only model measured here that handles a sentence
that switches language.
