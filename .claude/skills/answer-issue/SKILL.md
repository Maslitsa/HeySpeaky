---
name: answer-issue
description: Work out what is wrong on someone else's PC from a HeySpeaky problem report, and draft an answer for the owner to send.
---

# Answering an issue

**No bot posts in issues.** The owner decides what gets answered and posts it
himself. Your job is to work out the cause and hand him a short answer.

## 1. Ask for the report

Everything needed is in one file. They dictate three or four sentences, click
the tray icon, then **Save a problem report**, and send the ZIP from their
Desktop. It holds the logs, the settings with the key removed, the PC and its
microphones, and the last five recordings with what they were transcribed as.

## 2. Read `report.txt` in this order

1. **Which engine actually ran.** Each dictation says `OpenAI` or `local`, and
   a fallback gives its reason: `no API key`, `offline`, `cloud error`. Most
   "it got worse" reports are this.
2. **`captured` against `held`.** Much shorter means audio was lost, usually a
   busy processor. The log says so in as many words.
3. **Loudness.** `average` below about -45 dB is a very quiet microphone;
   `clipped` above 1% is distortion.
4. **Which microphone.** Windows often records from something other than the
   one they think, and the report lists every input.
5. **Settings.** Languages, pinned language, local model, and whether a key
   was found at all.

## 3. Listen to the recording

The ZIP has the wav files. Run one through both backends on your machine:

```powershell
cd "$env:LOCALAPPDATA\Programs\HeySpeaky"
.venv\Scripts\python.exe tools\try_demo.py "path\to\1.wav" --both
```

Bad here too means the problem is their audio. Fine here means it is their
setup, and the report says which part.

## 4. Draft the reply

Short, plain, no jargon, and one thing to try. If it is a bug, say so plainly
and open a note in the changelog rather than promising a date.
