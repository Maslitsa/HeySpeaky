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
| `heyspeaky/theme.py` | every colour, size and timing: pill, composer, tray panel |
| `heyspeaky/glass.py` | draws the pill, the correction composer and the tray panel |
| `heyspeaky/overlay.py` | the window: never focused, and its two buttons |
| `heyspeaky/engine.py` | RealtimeSTT: capture and voice activity detection |
| `heyspeaky/transcribe.py` | OpenAI and local backends, the key lookup |
| `heyspeaky/languages.py` | the languages list and its tray grouping |
| `heyspeaky/dictionary.py` | words this person says that the model gets wrong |
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
| `tools/benchmark.py` | measures models against real recordings |
| `tools/language_drill.py` | measures sentences that change language halfway |
| `tools/live_check.py` | shows the pill on the real screen and photographs it |
| `tools/correction_check.py` | the same, for the correction composer: hovers, clicks, drags |
| `tools/panel_check.py` | the same, for the tray panel, typing in Kazakh |
| `tools/make_icon.py` | draws the shortcuts' icon; the installer runs it |
| `tools/session_brief.py` | a session's starting facts; runs when a session starts |
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
  out of the window you were typing in. The buttons answer the pointer as
  the composer's do - grow, the cross spins, the tick lifts - and only
  while they can be used; at rest the pill is pixel for pixel what it was
  before hover existed, and `tools/live_check.py` puts the real pointer on
  the cross and checks the window in front stayed in front.
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
  whichever language it is most likely to mishear. **And it goes last**:
  on 26 September, three runs of the same 24 clips, `["kk","ru","de","en"]`
  got 10.0% of words wrong against 12.7% with English third, every run -
  with English third "Ертең кездесеміз" came back as "If time is thisms". A language switched on from
  the tray is inserted at the front for the same reason.
  `tools/language_drill.py` is how any of this gets re-measured.
- **A new install starts with the computer's own languages**
  (`languages.from_this_computer`): the language Windows's menus are in,
  then every keyboard layout, English last, five at most. The defaults are
  the owner's four, and on anybody else's computer the model was told to
  expect Kazakh. An existing config.json keeps its list. And
  `language_menu` is stored whole, never merged with the default
  (`config._WHOLE`): merged, a language switched off in the tray came back
  after a restart, at the front of the list - measured, "ru, en" became
  "kk, de, ru, en". The owner never saw it because he keeps all four.
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
- **The correction composer is the pill's twin, and it is two windows.**
  The owner disliked the first box (a flat card) and asked for something
  from uiverse.io that looks good without being busy. It is now a capsule:
  cross, a field where the waveform would be, tick. The glass (`back`) is a
  layered window like the pill - `WS_EX_NOACTIVATE`, drawn with
  `UpdateLayeredWindow`, never `-alpha`. The field (`top`) is an ordinary
  window laid exactly over the field in the picture, because a layered
  window cannot show a child widget; it takes focus, and `-alpha` is fine on
  it. Clicks on the glass never move the caret out of the field.
- **Both windows are drawn by the same code, and that is the point.**
  `glass.composer` uses the helpers `glass.prepare` uses (`_drop_shadow`,
  `_glass_body`), and the pill renders pixel-identical to before that split -
  check any change there the same way. Every size comes from
  `glass.composer_layout`, once, for the picture, the widget and the hit
  tests alike; the widget must land on nothing but `FIELD_FILL`, and a test
  says so.
- **The ring round the field is measured along its edge, not by angle.**
  It is after an MIT-licensed uiverse input by Lakshay-art: two arcs of a
  conic gradient chasing each other. By angle from the centre, as CSS does
  it, the arcs were cut off in the middle of each long side (up to 23 levels
  a pixel); along the edge the worst step is 8. It turns once as the box
  opens and a little with every key. Buttons grow, the cross spins and the
  tick lifts on hover, with a label after 0.35 s; an empty Enter shakes. The
  animation stops scheduling frames once nothing moves. Look at all of it
  with `tools/correction_check.py`, which moves the real pointer over the
  buttons, drags, types, and photographs each moment.
- **One design, three windows: the pill, the composer and the tray panel.**
  The owner asked for the tray to match. The Windows menu cannot be
  restyled - Windows draws it - so a click on the icon (either button) now
  opens `panel.py`, a card of the same glass: the chosen thing white with
  dark ink like the tick, the rest the cross's grey, and the only colour the
  waveform's gradient on a switch that is on. `Tray._wire_panel` swaps
  pystray's notification handler for one that opens it and falls back to
  the menu if that fails; pystray is pinned, so that table is where the code
  expects it. `tray.panel: false` brings the menu back. The panel is the one
  layered window that takes focus - a menu has to hear Escape and notice a
  click elsewhere. Tk hands out a new window handle once the window is
  really made, so the layered style is applied to the handle each frame is
  presented to, not the one seen at creation: styled on the first, the
  panel drew nothing at all, and only `tools/panel_check.py` showed it. The
  tray icon is the waveform: white, the gradient while recording, grey dots
  while paused.
- **There are two looks, and the glass stays exactly as it was.** The
  owner sent a reel of a macOS dictation app, liked its pill, and asked for
  it as a second look to try - "keep the current one too". Mono
  (`overlay.style: "mono"`, switched in the tray panel under Look) is a
  black capsule with eight bars and nothing to click: red while listening,
  blue with a travelling wave while thinking, shrinking away when the words
  land, and it appears just above the mouse pointer and stays there. All of
  it was measured off the reel's frames, not guessed: the macOS window
  buttons (12 points, 20 apart) made 3.0 pixels of the video a point, which
  put the pill at 108 x 58 - the same height as the glass, and less than
  half its length, which is what the owner meant by ours being "too big".
  Its colours are the medians of its pixels, and the pointer offset (25
  right, 12 above) comes from the frames where the pointer shows. The
  numbers are in `theme.py` under `MONO_`. Every click passes through it,
  since it has no buttons. `tools/live_check.py --style mono` puts it on
  the real screen and checks focus, click-through and the pointer.
  The owner then asked for everything to change with the look, so the tray
  panel and the correction composer do too (`panel_card`, `panel_frame`
  and `composer` take `mono`): the capsule's black, solid, a white
  hairline for an edge, and the thinking blue for whatever is on, chosen
  or ready - an iPhone's switch, a Mac's focus ring round a field. The
  popular switches on uiverse were a rocker, a day and night and a
  download button, which is why none of them is here. Switching the look
  turns an open panel there and then. Every glass render stayed byte for
  byte what it was - a sha1 of 34 renders before and after - and
  `tools/panel_check.py` and `tools/correction_check.py` take `--style
  mono`.
- **The mono sound is rebuilt from the reel, not copied from it.** It
  played twice in the reel, identically, the moment the words landed: two
  notes a fourth apart, about 500 and 670 Hz, six plucks over a fifth of a
  second, each gone in 5-9 ms. `sound.VOICES["blip"]` is those numbers -
  every start, pitch, loudness and decay read off the recording - and its
  envelope matches the original at 0.94. The end sound is "auto" by
  default: blip with mono, drip with the glass; `_migrate` moves a stored
  "drip", the old default, to "auto".
- **Never draw something translucent straight onto an RGBA frame.**
  `ImageDraw` on an RGBA picture replaces the pixel, alpha and all; it does
  not lay one colour over another. The panel's separator was a line of
  alpha 22 drawn that way, which cut a slit through the glass, and the owner
  saw his desktop through it. Anything with alpha below 255 goes on its own
  layer and in with `alpha_composite`. A test reads the alpha under the line.
- **Quit asks twice.** The panel opens right over the tray, so its bottom row
  is the first thing the pointer meets on the way up, and that row was Quit:
  the owner quit by accident again and again. One click turns it into
  "Click again to quit" in red for `theme.QUIT_ARMED` seconds; Esc takes it
  back.
- **The key is pasted into the tray panel** (`apikey.py`). The owner
  described the steps himself: click the icon, "Add your OpenAI key", a
  field appears, paste, Save. The only way before was rerunning the
  installer with the key in a PowerShell line. The row is first in the
  panel, in the accent colour, until there is a key. Ctrl+V is caught by
  the key, not the letter, because on a Russian layout the same key is
  "м". The field shows the key masked, the panel drops it the moment Save
  hands it over - through `submit_key`, never through `act`, whose action
  names reach the log - and it is checked with OpenAI before it replaces
  anything: a key OpenAI refuses never overwrites a working one. If the
  clipboard still holds that key afterwards, it is emptied. Saving one
  switches a laptop set to local over to OpenAI, and a start with no key
  says so once, in a notification.
- **People choose the local model** (`localmodels.py`). The owner did not
  want it decided for them: bigger hears better and is slower and heavier.
  The panel lists tiny, base, small, medium and large-v3-turbo with their
  download sizes; one not on disk is downloaded first, with a percentage
  worked out by watching the files arrive, because faster-whisper reports
  none. The engine then rebuilds its recorder (`engine.reload`) - RealtimeSTT
  takes its model once, when it is made - and never mid-recording. Measured
  on 25 September with a synthesised English sentence: base wrote it out in
  Cyrillic, and after switching to small, in 8.5 s, it came back word for
  word.
- **Typing in the panel is a language search.** Scrolling ninety names was
  the owner's complaint. Anything typed while the panel is open goes into a
  field at the top of the language list - the composer's field and ring,
  after Lakshay-art's winning search bar on uiverse - and Enter ticks the top
  match. A language answers to its English name, its own name, its Russian
  name and a few Kazakh ones, and Kazakh letters fold to Russian ones, so
  "каз", "қаз" and "kaz" all find Kazakh whichever layout is on.
- **Tk cannot type Kazakh by itself** (`keymap.py`). Tk 8.6 decodes a key
  through a one-byte code page, and whichever one it last heard about: with
  the Kazakh layout, "і" came into the correction box as "³", "ң", "ү" and
  "қ" as "?", "й" as "é". Measured with real key presses on the owner's
  laptop; Russian happened to work, Kazakh never could, because most of it
  is in no one-byte code page. Every text field and the panel's search ask
  Windows (`ToUnicodeEx`) what the key means in the active layout and type
  that when Tk got it wrong. `tools/correction_check.py` and
  `tools/panel_check.py` type Kazakh with real keys when the layout is there.
- **The shortcuts have HeySpeaky's own icon.** They start the virtual
  environment's pythonw.exe, which has no icon, so the Start menu showed a
  blank window. The installer draws `heyspeaky.ico` with `tools/make_icon.py`
  - the waveform in its colours on a dark tile, which reads on a light Start
  menu and a dark one - and falls back to a plain icon if that fails.
- **Reading somebody's selection means borrowing the clipboard.** There is no
  API for another program's selection. `output.copy_selection` empties the
  clipboard first - otherwise a Ctrl+C that copies nothing, because nothing
  was selected, leaves the old contents sitting there looking like a
  selection - sends Ctrl+C only once Ctrl and Alt are up, and puts back what
  was there. The same modifier wait is why `deliver` exists in that shape.
  "Up" means what Windows says (`GetAsyncKeyState`), not the keyboard
  library's list of held keys, which goes stale when a release never reaches
  its hook. Ctrl+C goes by key code, a step at a time, and is tried once more
  if the clipboard's sequence number never moved. Every read logs a line -
  how many characters, from which program and what class of window, whether
  the clipboard changed - and never the text. An unchanged clipboard does
  not prove the keys went missing: Chrome writes nothing at all when nothing
  is selected. On 23 September the owner's log still showed empty reads from
  Chrome-class windows, and the same code, driven through his running app
  with the chord pressed fast and slow and let go in every order, read a
  Chrome selection every time. The cause is not known yet; the program name
  in that line is what will say where to look.
- **A session starts with a brief, not a ritual** (`tools/session_brief.py`,
  a SessionStart hook in `.claude/settings.json`). Every session used to
  begin by hand: tail the installed app's log and count what was unusual,
  diff the installed copy file by file. It is now twenty lines computed in
  under a second: repo state, which files differ from the installed copy
  (line endings aside), the log's events counted by kind, which programs
  selections came from, and the warning lines. It prints counts and program
  names, never anything dictated. The commit check also refuses an
  `install.ps1` or `uninstall.ps1` that is not ASCII or does not parse.
- **A Ctrl+Alt that does nothing now leaves a line.** After a restart the
  owner said Ctrl+Alt did nothing, and the log could not tell that apart
  from nothing being pressed. It now notes the first key the hook hears after
  starting, a Ctrl+Alt ignored because the app was busy, and a Ctrl+Alt
  taken as a shortcut because another key was already down (by name only
  for keys like Shift - never a letter). Measured on his laptop: the app
  hears the keyboard about four seconds after its shortcut is clicked, and
  Ctrl+Alt worked at eight seconds and at twenty.
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
