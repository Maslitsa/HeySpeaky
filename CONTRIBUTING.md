# Contributing

Small changes are easiest to review.

The single most useful thing you can send is a recording where it gets your
language wrong, with what you said and what came out. Everything here was
tuned against English, Russian and German spoken by one person into one quiet
laptop microphone, so anything outside that is new information.

Never paste an API key, including inside a log excerpt.

## Development setup

```powershell
git clone https://github.com/Maslitsa/HeySpeaky.git
cd HeySpeaky
powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoStart -NoAutostart
```

`-NoStart -NoAutostart` builds the environment without registering HeySpeaky to
run at sign-in, which is usually what you want while working on it.

Run it with a console so you can watch it:

```powershell
.venv\Scripts\python.exe run.py
```

Run it the way it ships, with no window:

```powershell
.venv\Scripts\pythonw.exe run.py
```

Logs are in `logs\heyspeaky.log`.

## Before opening a pull request

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe -m compileall -q heyspeaky run.py tools
```

The tests are stdlib `unittest` plus numpy and run in about two seconds. They
cover the parts that do not need hardware: audio maths, segment merging, the
shape of the cloud request, config merging, hardware resolution and the log
capping. Anything involving Win32 or a live microphone is not covered, and
"I ran it and dictated with it for a day" is a reasonable thing to write in a
pull request.

CI runs the same two commands on Python 3.11 and 3.12, runs the installer on
a clean Windows runner, and scans for committed API keys.

## Two house rules

**Comments explain why, not what.** Several defaults here look arbitrary and
are not. They came from a measurement, and the comment saying which one is the
reason nobody undoes it later. `heyspeaky/config.py` is the clearest example.

**If you change a default that was chosen by measurement, include a
measurement.** Otherwise the next person will change it back.

Match the surrounding code otherwise: 4 spaces, about 79 columns, standard
library imports first.
