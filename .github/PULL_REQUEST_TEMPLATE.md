## What this changes

<!-- One or two sentences. -->

## Why

<!-- What was wrong, or what it makes possible. Link the issue if there is one. -->

## How it was tested

<!-- HeySpeaky is mostly Win32 behaviour and live audio, so "I ran it and
     dictated with it for a day" is a perfectly good answer. Just say what you
     actually did. -->

- [ ] `python -m unittest discover -s tests` passes
- [ ] `python -W error::SyntaxWarning -m compileall -q heyspeaky run.py tools` passes
- [ ] I ran it and dictated with it
- [ ] If the look changed: a picture from `tools/ui_lab.py` is attached

## If this changes a default

Several defaults here were chosen by measurement, and the comment above them
says which. If you are changing one, please include the measurement that
justifies the new value (`tools/language_drill.py` and `tools/benchmark.py`
are how they were taken). Otherwise the next person will change it back.
