# Security

## Reporting a vulnerability

Please report security issues privately using GitHub's
[report a vulnerability](https://github.com/Maslitsa/HeySpeaky/security/advisories/new)
form, rather than opening a public issue.

This is maintained in spare time, so no response time is promised, but
anything sent that way will be read.

## What HeySpeaky touches

Worth being explicit about, because the permissions look alarming and deserve
to be understood rather than trusted:

- **A global keyboard hook.** Required for a modifier-only chord like
  `Ctrl`+`Alt`, which `RegisterHotKey` cannot express. The hook classifies keys
  and never stores or transmits them.
- **The microphone**, opened *only* while you are recording. Windows' own "app
  is using your microphone" indicator is therefore an honest signal.
- **The clipboard**, to place the transcript.
- **Synthetic keystrokes**, to paste into the focused window.
- **The network**, only when the cloud backend is enabled, and only to
  `api.openai.com`. The default backend is local and sends nothing anywhere.

## What the installer downloads

All of it over HTTPS:

- The HeySpeaky source, as a ZIP of this repository.
- uv 0.12.13 from its GitHub release, checked against the SHA-256 published
  with it before it runs.
- Python 3.12, fetched by uv from python-build-standalone.
- Python packages from PyPI at the exact versions in `requirements.lock`, plus
  one wheel shipped in `vendor/` (see NOTICE). Nothing is compiled from source.
- The Whisper model weights from Hugging Face.
- The Microsoft Visual C++ runtime from `aka.ms`, only if the PC does not have
  it yet. That is the only step that asks for administrator rights, through the
  normal Windows prompt.

## Your API key

The key lives in `%APPDATA%\HeySpeaky\openai.key`, outside the project folder,
with ACL inheritance broken so only your account can read it.

Keeping it out of the project is deliberate: a key inside a repository is one
`git add -f`, one screenshot, or one cloud-sync client away from leaking.
`config.json` is gitignored and CI fails the build if anything key-shaped is
committed, but the file location is the real protection.

If you think a key has leaked, revoke it at
<https://platform.openai.com/api-keys>. That is always the right first move, and rotating a key costs nothing.
