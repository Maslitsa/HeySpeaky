<div align="center">

# HeySpeaky

**Dictation software makes you pick a language before you start talking.**

HeySpeaky assumes you are going to switch, probably mid-sentence.

Hold Ctrl+Alt, talk, and the text lands in whatever window you were already
typing in. No console window, nothing in the taskbar, nothing in Alt+Tab. Just
a waveform in the tray.

Windows. Built on [RealtimeSTT](https://github.com/KoljaB/RealtimeSTT). MIT.

[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D4?logo=windows&logoColor=white)](#install)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Built on RealtimeSTT](https://img.shields.io/badge/built%20on-RealtimeSTT-8A2BE2)](https://github.com/KoljaB/RealtimeSTT)
[![Stars](https://img.shields.io/github/stars/Maslitsa/HeySpeaky?style=social)](https://github.com/Maslitsa/HeySpeaky/stargazers)

<img src="docs/img/overlay-hero.png" width="720" alt="The HeySpeaky pill above the taskbar showing a live waveform and a sentence that starts in English and continues in Russian">

</div>

---

## Install

Paste this into PowerShell:

```powershell
irm https://raw.githubusercontent.com/Maslitsa/HeySpeaky/main/install.ps1 | iex
```

It downloads about 1 GB, installs into `%LOCALAPPDATA%\Programs\HeySpeaky`,
starts HeySpeaky with Windows and launches it. Then hold Ctrl+Alt and talk.

### Your OpenAI key (recommended)

OpenAI is much more accurate than the model on your computer, and it is the
only option that keeps up when you switch language in the middle of a
sentence. Adding the key:

1. Create a key at
   [platform.openai.com/api-keys](https://platform.openai.com/api-keys) and
   copy it.
2. Click the HeySpeaky icon in the tray, then **Add your OpenAI key**.
3. Paste it into the field with Ctrl+V and press **Save**.

HeySpeaky checks the key with OpenAI, saves it to
`%APPDATA%\HeySpeaky\openai.key` where only your account can read it, and
takes it off the clipboard so it is not left there to be pasted by accident.
The field shows it masked. A row under it opens the page where keys are
made. To change the key later, do the same with the new one.

Or give it to the installer, which does the same checks: put the key between
the quotes and paste the whole line into PowerShell instead:

```powershell
$env:OPENAI_API_KEY = "PASTE-YOUR-KEY-HERE"; irm https://raw.githubusercontent.com/Maslitsa/HeySpeaky/main/install.ps1 | iex
```

Filled in, it looks like this:

<pre>$env:OPENAI_API_KEY = "<a href="docs/no-key-for-you.md">sk-proj-R4nd0m...x9Qz</a>"; irm https://raw.githubusercontent.com/Maslitsa/HeySpeaky/main/install.ps1 | iex</pre>

The installer also takes the key back out of your PowerShell history.

It is your own key on your own OpenAI account. Nothing is proxied. Cost is
about $0.006 per minute of audio, roughly $3.60 a month at 20 minutes of
dictation a day. Check [current pricing](https://openai.com/api/pricing/).

If you use the first command, the installer asks which one you want, and takes
the key there instead.

### Updating, and if it fails

Run the same command again to update. Your settings are kept.

If it fails, the window stays open with the reason, and the whole run is in
`%TEMP%\HeySpeaky-install.log`. If your antivirus blocks the command, use the ZIP
and `INSTALL.bat` described below. If you hit a problem, please
[open an issue](https://github.com/Maslitsa/HeySpeaky/issues) and attach that
log, so I can fix it.

<details>
<summary><b>Options, or a different install location</b></summary>

<br>

To pass arguments, load the script into a script block in PowerShell:

```powershell
$s = [scriptblock]::Create((irm https://raw.githubusercontent.com/Maslitsa/HeySpeaky/main/install.ps1))
& $s -InstallDir 'D:\Apps\HeySpeaky'
& $s -Backend local
& $s -NoAutostart
& $s -NoGame
```

</details>

<details>
<summary><b>Without piping a script from the internet</b></summary>

<br>

Read [install.ps1](install.ps1) first, or skip the pipe:

```powershell
git clone https://github.com/Maslitsa/HeySpeaky.git
cd HeySpeaky
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

If you would rather not use a terminal at all, download the
[ZIP](https://github.com/Maslitsa/HeySpeaky/archive/refs/heads/main.zip), unzip
it somewhere permanent and double-click `INSTALL.bat`.

</details>

## Uninstall

Paste this into PowerShell:

```powershell
irm https://raw.githubusercontent.com/Maslitsa/HeySpeaky/main/uninstall.ps1 | iex
```

It removes every copy of HeySpeaky on this PC, including old ones called
SpeakIt or VoiceType, with their shortcuts, your saved OpenAI key and the
downloaded speech models. A folder that is a git clone is left where it is.

## How you use it

| Gesture | What happens |
| --- | --- |
| Hold Ctrl+Alt | Records while held. Release to transcribe and insert. |
| Tap Ctrl+Alt twice, quickly | Hands-free: it keeps recording with nothing held down. Tap once more to finish, or stop talking and it ends after 2.5s of silence. |
| Click the tick on the pill | Finishes now. |
| Click the cross on the pill, or press any other key | Cancels. Nothing is inserted. |
| Select a word it got wrong, press Ctrl+Alt+Win | Type what you said. It remembers, and gets it right next time. |
| Click the tray icon | Status, your languages (just start typing to find one, in English, Russian, Kazakh or its own name), your OpenAI key, OpenAI or local, which model runs on your laptop, the look (glass or mono), pause the hotkey, your words, settings, a problem report. Quit asks for a second click. |

### Two looks

Click the tray icon, then **Look**:

- **Glass**: the dark glass pill above the taskbar, with a cross to cancel
  and a tick to finish.
- **Mono**: a small black pill that appears right above your mouse pointer,
  with red bars while it listens and blue while it works, a soft two-note
  sound, and gone the moment your words land.

Switching shows the new look straight away with a short pretend dictation.

### Choosing the model on your laptop

Click the tray icon, then **Model on this laptop**. Bigger models hear
better, especially with more than one language, and are slower and larger:

| Model | Download | What to expect |
| --- | --- | --- |
| Tiny | 78 MB | fastest, makes the most mistakes |
| Base | 148 MB | fast, the usual choice |
| Small | 486 MB | better, a few seconds a sentence |
| Medium | 1.5 GB | good, slow without a graphics card |
| Large v3 Turbo | 1.6 GB | the best, slow without a graphics card |

One you have not used yet is downloaded when you pick it, with the progress
shown in the panel. With OpenAI selected, the laptop's model only steps in
when OpenAI cannot be reached.

<div align="center">
<img src="docs/img/overlay-done.png" width="620" alt="Done state with a green dot and the final transcript in white"><br>
<em>Done. White text is the final transcript, already pasted and on the clipboard.</em>
</div>

## Why it exists

Whisper picks one language per utterance. Anything you said in another language
comes back translated, or it disappears. And a lot of the other tools keep a
black console window open while they run. HeySpeaky has none: it sits in the
tray, behind the little arrow next to the clock.

## Local or OpenAI

Both measured on the same machine, a Ryzen 7 7730U with no GPU, against the
same audio played through speakers into the microphone.

| | Local (default) | OpenAI |
| --- | --- | --- |
| Model | Whisper `base` on your CPU | `gpt-transcribe` |
| Wait after you stop | 1.5 to 1.9s, consistent | 1.1 to 2.6s typical, 7.7s seen |
| English | good | better |
| German | good | better |
| Russian | the weak one | much better |
| Mid-sentence switching | only across a pause | yes, with no pause |
| Cost | free | about $0.006/min |
| Privacy | nothing leaves the machine | audio is uploaded when you dictate |
| Offline | yes | no |

The cloud is not the faster option. Its median is close to local and its worst
case is much worse, because it depends on your connection. Switch to it for
Russian, German and mid-sentence switching, not for speed.

## Something wrong?

Double-click `CHECKUP.bat` in the HeySpeaky folder, or run:

```powershell
cd "$env:LOCALAPPDATA\Programs\HeySpeaky"
.venv\Scripts\python.exe tools\doctor.py
```

It checks the Python version, the dependencies, your settings, the microphone,
the API key, whether HeySpeaky is running and whether it starts with Windows.
Anything it cannot fix gets a line telling you what to do.

If it works worse on someone else's PC, have them dictate a few sentences,
then click the tray icon and **Save a problem report**, and send you the ZIP
from their Desktop.
[docs/troubleshooting.md](docs/troubleshooting.md#it-works-worse-on-another-pc)
says how to read it.

## Credits

HeySpeaky is built on [RealtimeSTT](https://github.com/KoljaB/RealtimeSTT) by
[Kolja Beigel](https://github.com/KoljaB). RealtimeSTT does the microphone
pipeline and the voice activity detection that ends a hands-free recording,
and none of that is mine. If HeySpeaky is useful to you, star
RealtimeSTT too.

Transcription is [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
running [OpenAI Whisper](https://github.com/openai/whisper), or the OpenAI API.

Full attribution in [NOTICE](NOTICE).

## License

MIT. See [LICENSE](LICENSE).
