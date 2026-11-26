# Why the rules are what they are

[AGENTS.md](../AGENTS.md) keeps each rule to a line or two, because it is
read at the start of every session. This is the story behind each one: the
measurement, the date, what went wrong and how it was found. Read the
section before you change what a rule protects, and when something new is
learned the hard way, put the rule in `AGENTS.md` and the story here.

## Rules

### Attribution

**Never put AI attribution anywhere** - not in commits, files or pull
requests, and do not mention Claude or Anthropic in the repository. Owner's
rule. `tools\precommit.py` refuses a commit whose staged changes carry it.

### ASCII installer

**`install.ps1` and `uninstall.ps1` must stay ASCII** and must parse before
any commit: Windows PowerShell 5.1 mangles anything else, and the installer
is the only way anyone updates, so a broken one breaks every user.
`script_problems` in `tools\precommit.py` refuses a staged `.ps1` that is not
ASCII or does not parse.

### Tests

**Run the tests and the strict compile before pushing.** A `SyntaxWarning`
fails CI. `tools\precommit.py` runs both before every commit; the commands
are under [Before you push](../AGENTS.md#before-you-push).

### Private files

**Never commit a problem report, a recording or a key.** `*-report-*.zip` is
ignored for that reason. `tools\precommit.py` also refuses a staged file
whose name looks like a report, a key or the usage tally, and a diff holding
anything shaped like an OpenAI key.

### Console

**There is no console.** Under pythonw.exe `print()` goes nowhere and can
raise; use the logger.

### The look

**The look changes in `theme.py`**, and you look at the result with
`tools/ui_lab.py` before wiring it in. The pill is small and dark: cross,
waveform, tick, and nothing else. It does not repeat the transcript back,
because the transcript is already in the window you were typing in.

### Silence

**Silence is drawn as dots, not as motion.** Many thin round-capped bars,
newest on the right, scrolling left, falling to dots when nothing is heard -
which is how ChatGPT and every other voice composer worth copying does it.
An idle animation was tried and removed: it invented activity where there
was none, and a waveform that moves when the room is quiet is a lie about
what the microphone can hear.

### Layered window

**The pill is a layered window with a real alpha channel**, drawn by
`UpdateLayeredWindow`, not by Tk. Never call `root.attributes("-alpha")` on
it: that is `SetLayeredWindowAttributes`, and a window given one of those
can never be updated the other way again. The fade uses the blend function.
It used to photograph the desktop and draw the picture as its background;
that looked like glass until anything underneath moved, and then the pill
showed as a bright rectangle full of somebody else's pixels. A screenshot
from the owner is what finally proved it.

### Focus

**The pill must never take focus and never appear in Alt+Tab.** That is what
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

### Hands-free

**Hands-free is a double tap of the whole chord**, half a second apart, the
way Wispr Flow does it. The owner asked for that specifically. It works
because a single tap is shorter than the engage delay and so does nothing at
all, which is also what the start of every Ctrl+Alt+<key> shortcut looks
like. The old latch - release between 0.25s and 0.7s - is off by default
(`hotkey.tap_max: 0`) because nobody can hit a window that narrow.

### Watchdog

**The keyboard hook has a watchdog, and it must not fire on a moving
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

### Worker

**The transcription worker must die with the app** (`winjob.py`). Orphans
once wrote 8.7 GB of the same traceback.

### Black box

**A run that ends must leave a trace** (`blackbox.py`). In November 2026
HeySpeaky vanished six times, mostly overnight, and the owner found out only
when Ctrl+Alt did nothing; once it stayed gone for a whole day. Each time the
log just stopped. There was no "Shutting down", no "Fatal error", nothing in
Windows' Application log, and the computer had not restarted since 18
October. Windows did flag python's memory as growing twice (1 and 20
November), which is a lead, not an answer. The last run had been started by
the installer from a script, not from the shortcut, so the window that ran
the script may have taken it down. Nothing could tell.

Nothing could tell because nothing wrote it down. Under pythonw.exe a native
crash, a Tk callback that fails and an exception in a thread all print to
stderr, which `run.py` points at stdout.log, and the next start emptied
stdout.log. So now:

- faulthandler writes every thread's stack to `logs/crash.log` when the
  process dies in C code, one header line per start, set aside at 1 MB;
- uncaught exceptions in any thread, and failed Tk callbacks, go to the log;
- `logs/running.json` holds the pid, who started it, when it was last seen
  alive and what it held, refreshed every minute and removed by a clean
  shutdown. The next start finds it and says "ended without shutting down",
  telling a Python exit apart from a kill;
- once an hour, a line with memory, handles and GDI objects, so a leak shows
  as a slope;
- a tick five minutes late says the computer slept or the loop stood still;
- the last run's stdout.log is kept as stdout.prev.log. A rename that fails
  means another copy still has the file open, and it is appended to, never
  emptied.

All of it is numbers, times and program names, never anything dictated. The
marker is read only after the single-instance check, because a second copy
on its way out would otherwise read the running copy's marker as a death.

### Keys

**Keys live outside the project**, in `%APPDATA%\HeySpeaky\openai.key`. The
SpeakIt and VoiceType paths are read as a fallback. Never log one, never
print one, never put one in config.json.

### Quiet audio

**Quiet audio comes back as an empty string, not an error.** Measured on
the owner's machine: every recording OpenAI returned nothing for peaked
below -27 dB, and every one that worked was louder. `levels.py` boosts by up
to 24x - the old ceiling of 8 was not enough - and an empty transcript from
quiet audio says "Too quiet" rather than "Nothing heard", because the second
one sends people looking for the wrong fault.

### Language order

**The order of `cloud.languages` is a priority order, not a list.** A
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
with English third "Ертең кездесеміз" came back as "If time is thisms". A
language switched on from the tray is inserted at the front for the same
reason.
`tools/language_drill.py` is how any of this gets re-measured.
**It matters less than it did.** Re-measured on 21 November with the
model then current, asking with no languages at all got 11.6% and
13.2% of words wrong against 11.0% and 11.7% the HeySpeaky way: a
point or so, not the six it once was. The owner noticed it himself -
plain Whisper apps now cope with his Russian and English - and the
answer was [the alphabet check](#alphabet-check), below, not a better
order.

### First languages

**A new install starts with the computer's own languages**
(`languages.from_this_computer`): the language Windows's menus are in,
then every keyboard layout, English last, five at most. The defaults are
the owner's four, and on anybody else's computer the model was told to
expect Kazakh. An existing config.json keeps its list. And
`language_menu` is stored whole, never merged with the default
(`config._WHOLE`): merged, a language switched off in the tray came back
after a restart, at the front of the list - measured, "ru, en" became
"kk, de, ru, en". The owner never saw it because he keeps all four.

### New defaults

**A new default reaches nobody who already has a config.json.** That file
is the user's and the installer never overwrites it, so the owner was still
running the measured-worse language order a day after it was replaced, and
the fix he had been told about had never applied to him. `_migrate` in
`config.py` upgrades a stored list that exactly matches a superseded
default, and leaves anything else alone. Put a retired default in
`SUPERSEDED_LANGUAGES` when you replace one; do not reach further than
that, because every other setting might be something somebody typed.

### JSON files

**Write config.json and dictionary.json through `config.write_json`.** Both
are edited by hand, and a typo makes one read as missing so dictation keeps
going - after which the next save used to write over it. It now moves an
unreadable file aside to `<name>.broken-<time>` first, and replaces the file
in one step so a crash cannot leave half of it.

### Keywords

**A name the model keeps mangling is fixed by `cloud.keywords`, not by the
language order.** The owner's friend is called Magzhan and he got back
Marzhan, Makzhan and Bagzhan. Measured on synthesised speech, four clips:
Kazakh first on its own rescued it 0 times out of 4, the same as the old
order; adding the name to `keywords` rescued it 2 out of 2 in a Kazakh
sentence, plain and slurred alike. In a Russian sentence the keyword still
moved it from "Marzhan" to "Magzhan" but the Kazakh letter did not survive
into Russian text, so priming narrows the gap and does not always close it.
That remainder is what a spelling fix applied after transcription is for.

### Dictionary

**The model cannot be taught how somebody sounds, and `dictionary.py` is
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

### Hints

**One correction is a hint, not a rule.** A pair used to be replaced from
its first correction, and the owner saw where that goes: "Всем привет",
written for his own name, corrected to "Усенов Мирас", would turn every
"всем привет" he said after into his name. A correction to a different
word now only primes, and is replaced once the same correction has been
made `REPLACE_AFTER` (2) times. The same word spelled another way - a
Kazakh letter written as its Russian look-alike, "Магжан" for "Мағжан" -
is fixed at once, for every word somebody meant, corrected or declared; a
word differing only in case is left alone, because "notion" is a word.

### Alphabet check

**The alphabet check is what HeySpeaky adds that the model does not**
(`alphabet.py`). What the model still gets wrong in mixed speech is
mostly one word in the other alphabet: "Kubernetes cluster upal",
"Данке дир", "Ефтенг" for "Ертең". After the cloud, a text model is asked
to fix exactly that. Measured on 21 November, the drill's 24 recordings:
gpt-5.4-mini improved 4 and made none worse, 0.7 s median, 0.84 s worst,
and the drill went from 11.0% to 9.1% and from 11.7% to 10.2% of words
wrong. It is told reasoning "none": at "low" it was no better and took up
to 2.4 s. gpt-4o-mini fixed as much but turned "ещё не пришла" into "уже
пришла", which says the opposite, so `same_words` now reads both texts in
Latin letters and refuses any answer that is not the same words, in the
same order, in another alphabet. It runs only after the cloud, with no
language pinned, when the user's languages mix Cyrillic and Latin and the
text has Latin in it, so a purely Russian sentence never waits. Any error
or slow answer types the text as it came. Its log lines carry counts and
seconds, never the text.

**Later that day it got sharper.** The owner asked for "a model that
understands the sentence and decides which word it was, in any of the
languages". Twelve harder sentences went into the drill (48 recordings in
all), and three ideas were measured on the same drafts: a text model told
to fix words that make no sense (gpt-5.5: 7.9%, but it turned "upal" into
the English "up all"), gpt-audio-mini listening again (7.9%, 8 better and
3 worse: "half past seven" became "7:30", "10 percent" "10 процентов"),
and the alphabet check itself. The check had left "I think on Prav" and
"Prosta yazabil napisat" alone - its instruction described the job, and
the model did not go looking. Rewritten to go word by word and ask whether
a Latin word is English or German at all, with examples from outside the
drill, gpt-5.5 took the drill from 9.3% to 6.2% (11 better, none worse;
1.3 s median, 2.6 s worst), where gpt-5.4-mini reached only 8.1%. The
same model with no hints at all gets 10.8% on those 48. Eight sentences
nothing had been tuned on came back unchanged, nothing better or worse.
Runs vary by about half a point. A stored "gpt-5.4-mini" is moved forward
by `_migrate`.

**That evening it learned to look at Kazakh with no Latin in it.** The
first listening-lab run (`tools/voice_lab.py`: 80 sentences from the web,
eleven voices, eight manners, five rooms, 400 recordings) found Kazakh the
weakest - around 30% of words wrong in Kazakh mixed with Russian - and
much of it letters lost in Cyrillic: "дарылык өсүмдүк экен" for "дәрілік
өсімдік екен". The check never saw those, because it ran only on text with
Latin in it. Run anyway on the 194 answers with no Latin, it took them from
23.2% to 20.1% (45 better, 10 worse), but it would add a second and a half
to every Russian sentence, and most of the worse ones were place names
moved into Latin. So it runs when the cloud says it heard Kazakh (`heard`):
there, 71 answers went from 26.7% to 22.9%, 15 better and 1 worse, and a
sentence heard as Russian still never waits.

### Listening lab

**Measure a change to hearing in the listening lab, and decide on the
held-out quarter** (`tools/voice_lab.py`). The drill's 24 sentences in one
voice were too few and too alike to show what was wrong: the lab's first
run, on 21 November, showed in one evening that Kazakh is the weak
language, that the second-opinion line made no difference anywhere from
-0.5 to -0.1 on the sentences held out, and that the alphabet check was
missing Kazakh with no Latin in it. Its sentences come from random
Wikipedia articles, rewritten by a model into speech that changes
language, and from Russian tech news as written; a quarter are held out by
their own names. Its rooms are filters and noise built in code. Everything
it makes lives in `%LOCALAPPDATA%\HeySpeaky-lab`, never in the repository:
the sentences are other people's writing, and the clips are recordings.
It is not anyone's voice, so a real failure is still looked at with
`voice_lab.py replay` on a problem report saved right after it.

The same evening it got real voices too: `voice_lab.py people` streams the
first recordings out of Google's FLEURS (CC BY 4.0, native speakers on
their own microphones) and `run --people` hears them alone and joined in
pairs across languages. One language at a time, real people came out well
(German 3.0% of words wrong, Russian 3.7%, English 5.0%, Kazakh 11.6%). Two
joined across languages showed the fault the owner started HeySpeaky over:
the model kept to the first language and dropped the second - 18 of 120
joined recordings lost a quarter of their words or more, most of them an
English sentence after a Russian or German one, and no one-language
recording did. Hearing the recording in pieces at its pauses as well, and
taking the pieces only when they hold half as many words again, brought 5
of those back and spoiled nothing; it is measured, not yet in the app.

### The lab's bill

**The lab spends the owner's money.** On 21 November one evening of lab
runs sent six to seven hours of audio and about two thousand text
requests, and the account ran out: his next dictation got "You have no
credits remaining" and was heard by the local model. Earlier, a run
uploading six recordings at once had probably crowded out one of his own,
which timed out. So a run that would send more than half an hour of audio
refuses until it is asked for by name (`--max-minutes`), three requests go
at once rather than six, and the lab stops at the first "no credit".

The app had made it worse: it asked three more times, because "no credit"
comes back as a 429 like a rate limit, which cost the dictation 25
seconds, and then the pill said only "local (cloud error)". Now a 429 that
says `insufficient_quota` raises `NoCredit`, is never retried, and the pill
says "local (no OpenAI credit)": only the person can fix it, on OpenAI's
billing page.

On 25 November the owner offered testers on Reddit a key of his own, in a
project with a hard $5 limit. OpenAI's spend-limits guide says a spent
limit answers 429 with `project_spend_limit_exceeded` or
`organization_spend_limit_exceeded`, neither of which said
`insufficient_quota` to the old check, so a tester would have been
retried and told "cloud error". `transcribe.money_refusal` now knows all
three, most particular first. Looking at it showed the other half: a
finished pill shows no words, so the "no OpenAI credit" of 1.2.2 reached
only the problem report. `Router.last_warning` is what the pill says
instead, as a message of its own after the words land, and each one must
fit the glass pill whole (116 pixels; a test measures them).

### Asking again when unsure

The owner said "Они потребуют одинаковое количество энергий" and got
"Альбатрос бродит акварель часовой мерки". The log showed why: a 3.6 s
recording, so quiet it was boosted eight times, heard as Kazakh - the
first language in his list. No text check can fix that; the words are
gone. What can catch it is the model's own odds: asked for `logprobs`,
`gpt-transcribe` says how sure it was of every word. Synthesised speech
would not reproduce the mistake - 48 quiet, noisy short phrases came back
right, the least sure averaging -0.11 - so the line, `UNSURE_BELOW`, is
set at -0.3, below anything an ordinary recording reached, and every cloud
dictation now logs its average and its least sure word. Below the line the
audio goes out again with the next two languages first, both at once, and
the surest answer wins unless it has under 80% of the words: on the drill,
asked with Kazakh first, one sentence came back without its English half
and surer than the whole one. The next nonsense transcript in his log will
say where the line really belongs.

The listening lab's first run (400 recordings) never went below -0.35, and
moving the line made no difference that held: at -0.1 it asked again a
fifth of the time and the held-out sentences came out no better (19.6%
against 19.0% at -0.3). Its nonsense answers averaged -0.14 and the rest
-0.03, so the odds do separate them, but asking again with another
language first does not fix them: they were names and Kazakh, not the
wrong language. The line stays at -0.3, where it costs nothing, until a
real failure says otherwise.

### Your words

**Your words is a page in the panel, not a file.** The owner could not
read the JSON Notepad opened. Each word shows what it was heard as, and
two clicks forget it, as Quit takes two. The action names carry a CRC of
the entry, never the word, because action names reach the log.

### Correction key

**The correction key is Ctrl+Alt+Win, not Ctrl+Alt+Space.** Space was the
first choice, and on the owner's machine another program owns
Ctrl+Alt+Space as a global shortcut: it gets the keys first, and a hook
that only watches cannot take them back. Pressed on his machine, fast,
slow and Win first, Ctrl+Alt+Win did not open the Start menu (Win alone
did, which is how the check was checked). `_migrate` moves a stored
"space" to the new default. The three keys are accepted in any order.

### Cancelling

**The correction key is the only one carved out of `cancel_on_other_key`**,
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

### Used chords

**A chord that has been used stays used until Ctrl and Alt come up**
(`_spend_chord_locked`). Clearing it on a cancel let the chord re-arm the
moment the other key was released: the owner's log has a recording
cancelled by Win and a new one starting 0.37 s later, twice.

### Composer

**The correction composer is the pill's twin, and it is two windows.**
The owner disliked the first box (a flat card) and asked for something
from uiverse.io that looks good without being busy. It is now a capsule:
cross, a field where the waveform would be, tick. The glass (`back`) is a
layered window like the pill - `WS_EX_NOACTIVATE`, drawn with
`UpdateLayeredWindow`, never `-alpha`. The field (`top`) is an ordinary
window laid exactly over the field in the picture, because a layered
window cannot show a child widget; it takes focus, and `-alpha` is fine on
it. Clicks on the glass never move the caret out of the field.

### Shared drawing

**Both windows are drawn by the same code, and that is the point.**
`glass.composer` uses the helpers `glass.prepare` uses (`_drop_shadow`,
`_glass_body`), and the pill renders pixel-identical to before that split -
check any change there the same way. Every size comes from
`glass.composer_layout`, once, for the picture, the widget and the hit
tests alike; the widget must land on nothing but `FIELD_FILL`, and a test
says so.

### Ring

**The ring round the field is measured along its edge, not by angle.**
It is after an MIT-licensed uiverse input by Lakshay-art: two arcs of a
conic gradient chasing each other. By angle from the centre, as CSS does
it, the arcs were cut off in the middle of each long side (up to 23 levels
a pixel); along the edge the worst step is 8. It turns once as the box
opens and a little with every key. Buttons grow, the cross spins and the
tick lifts on hover, with a label after 0.35 s; an empty Enter shakes. The
animation stops scheduling frames once nothing moves. Look at all of it
with `tools/correction_check.py`, which moves the real pointer over the
buttons, drags, types, and photographs each moment.

### Tray panel

**One design, three windows: the pill, the composer and the tray panel.**
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

### Two looks

**There are two looks, and the glass stays exactly as it was.** The
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

### Mono sound

**The mono sound is rebuilt from the reel, not copied from it.** It
played twice in the reel, identically, the moment the words landed: two
notes a fourth apart, about 500 and 670 Hz, six plucks over a fifth of a
second, each gone in 5-9 ms. `sound.VOICES["blip"]` is those numbers -
every start, pitch, loudness and decay read off the recording - and its
envelope matches the original at 0.94. The end sound is "auto" by
default: blip with mono, drip with the glass; `_migrate` moves a stored
"drip", the old default, to "auto".

### Shadows

**A shadow fades to nothing before its window's edge**
(`glass._fade_at_edges`). The pill's blur reached past the 14 pixels of
room its window leaves and was cut off there: alpha 46 along the bottom
edge, a grey rectangle round the pill on a white page. The shadow and the
listening rim are eased out across that room rather than the window made
bigger, because Windows hit-tests a layered window by its alpha and a
bigger shadow would catch more clicks. Inside the capsule nothing moved
by more than 6 of 255. A test reads all four edges of every window.

### Translucent drawing

**Never draw something translucent straight onto an RGBA frame.**
`ImageDraw` on an RGBA picture replaces the pixel, alpha and all; it does
not lay one colour over another. The panel's separator was a line of
alpha 22 drawn that way, which cut a slit through the glass, and the owner
saw his desktop through it. Anything with alpha below 255 goes on its own
layer and in with `alpha_composite`. A test reads the alpha under the line.

### Quit

**Quit asks twice.** The panel opens right over the tray, so its bottom row
is the first thing the pointer meets on the way up, and that row was Quit:
the owner quit by accident again and again. One click turns it into
"Click again to quit" in red for `theme.QUIT_ARMED` seconds; Esc takes it
back.

### Pasting the key

**The key is pasted into the tray panel** (`apikey.py`). The owner
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

### Local model

**People choose the local model** (`localmodels.py`). The owner did not
want it decided for them: bigger hears better and is slower and heavier.
The panel lists tiny, base, small, medium and large-v3-turbo with their
download sizes; one not on disk is downloaded first, with a percentage
worked out by watching the files arrive, because faster-whisper reports
none. The engine then rebuilds its recorder (`engine.reload`) - RealtimeSTT
takes its model once, when it is made - and never mid-recording. Measured
on 25 September with a synthesised English sentence: base wrote it out in
Cyrillic, and after switching to small, in 8.5 s, it came back word for
word.

### Language search

**Typing in the panel is a language search.** Scrolling ninety names was
the owner's complaint. Anything typed while the panel is open goes into a
field at the top of the language list - the composer's field and ring,
after Lakshay-art's winning search bar on uiverse - and Enter ticks the top
match. A language answers to its English name, its own name, its Russian
name and a few Kazakh ones, and Kazakh letters fold to Russian ones, so
"каз", "қаз" and "kaz" all find Kazakh whichever layout is on.

### Kazakh typing

**Tk cannot type Kazakh by itself** (`keymap.py`). Tk 8.6 decodes a key
through a one-byte code page, and whichever one it last heard about: with
the Kazakh layout, "і" came into the correction box as "³", "ң", "ү" and
"қ" as "?", "й" as "é". Measured with real key presses on the owner's
laptop; Russian happened to work, Kazakh never could, because most of it
is in no one-byte code page. Every text field and the panel's search ask
Windows (`ToUnicodeEx`) what the key means in the active layout and type
that when Tk got it wrong. `tools/correction_check.py` and
`tools/panel_check.py` type Kazakh with real keys when the layout is there.

### Icon

**The shortcuts have HeySpeaky's own icon.** They start the virtual
environment's pythonw.exe, which has no icon, so the Start menu showed a
blank window. The installer draws `heyspeaky.ico` with `tools/make_icon.py`
- the waveform in its colours on a dark tile, which reads on a light Start
menu and a dark one - and falls back to a plain icon if that fails.

### Selection

**Reading somebody's selection means borrowing the clipboard.** There is no
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

### Session brief

**A session starts with a brief, not a ritual** (`tools/session_brief.py`,
a SessionStart hook in `.claude/settings.json`). Every session used to
begin by hand: tail the installed app's log and count what was unusual,
diff the installed copy file by file. It is now twenty lines computed in
under a second: repo state, which files differ from the installed copy
(line endings aside), the log's events counted by kind, which programs
selections came from, and the warning lines. It prints counts and program
names, never anything dictated. The commit check also refuses an
`install.ps1` or `uninstall.ps1` that is not ASCII or does not parse.

### Held keys

**A key the hook thinks is held is checked with Windows** before it
turns Ctrl+Alt into a shortcut (`_forget_released_keys_locked`). A
release that never reached the hook left a letter in `_pressed`, and
from 20 November every Ctrl+Alt on the owner's machine was "taken as a
shortcut": he had to start and stop dictation from the tray. Same
lesson as `wait_for_modifiers_released`: the hook's own list of held
keys goes stale, Windows' does not. The suite tells Windows to agree
with the keys it sends (`setUpModule`), since they are not real.

### Silent chord

**A Ctrl+Alt that does nothing now leaves a line.** After a restart the
owner said Ctrl+Alt did nothing, and the log could not tell that apart
from nothing being pressed. It now notes the first key the hook hears after
starting, a Ctrl+Alt ignored because the app was busy, and a Ctrl+Alt
taken as a shortcut because another key was already down (by name only
for keys like Shift - never a letter). Measured on his laptop: the app
hears the keyboard about four seconds after its shortcut is clicked, and
Ctrl+Alt worked at eight seconds and at twenty.

### OpenAI first

**OpenAI is the default and local is a fallback.** Measured on the owner's
laptop: OpenAI got a four-language clip completely right; local `base` lost
most of the Russian and Kazakh, `small` took 4-7 s, `large-v3-turbo` 17-19 s.
The installer picks `large-v3-turbo` only when a CUDA card is usable.

### Offline said

On 26 November the owner said the app had got worse, and pointed at
"дектовку" for "диктовку" and "прихня" for "брехня". The log showed that
the cloud had not written them. A 37-second dictation's connection failed
in the handshake (8.0 s, the connect timeout twice over), and the local
model wrote the text. The pill's label said "local (offline)", but a
finished pill shows no words, so he never saw it. In the week before,
10 of his 245 dictations had gone that way unseen. Now the pill says
"Offline: local model", 113 of the glass pill's 116 pixels, and a missing
key or a cloud error say so too.

### The kept connection

Every request opened its own connection, after the keys came up: the
transcription, and the alphabet check a second later. Measured that night
from his PC, a new connection cost 0.05-0.3 s more than a kept one. On
the bad line that lost the 37-second dictation, opening it was the whole
failure. So `link.py` keeps one client, and `keep_warm` opens its
connection when recording starts. It asks for the model list without a
key, and the 401 that comes back is fine: the point is the open
connection. It does this again every 25 s of a long recording. OpenAI
kept an idle connection for more than 95 s (the request count went up on
one connection), so `KEEP_OPEN` is 60 s. A connection the server has closed
is tried once more. A timeout is not, because waiting twice is worse than
the fallback.

The recording goes as FLAC, which is lossless, so OpenAI hears exactly the
same samples. On nineteen of his recordings, boosted as the app boosts
them, FLAC was 65% of the WAV size and took 5 ms to encode. Lossy Opus
would be an eighth of the size, but it changes what the model hears, so
it waits for a run in the listening lab.

Where the rest of the wait goes, from that week's log: 3.2 s median after
letting go, 6.8 s at the 90th percentile. The speech model takes 1.5 s
for under five seconds of audio and 6.3 s for over thirty. The alphabet
check ran on 83 of 232 cloud dictations, at 1.9 s each, and changed words
on 3 of them. It was left as it is: the archive will show whether those
words were worth the wait.

### The archive

A problem report holds five recordings, and only if somebody thinks to
save one. The owner asked to keep every dictation on his own PC, so a day
can be looked back on, the good next to the bad. `archive.py` keeps the
recording before the boost and a line for each dictation:

- what the cloud wrote, what asking again made of it;
- what the alphabet check and the dictionary changed;
- what was typed in the end;
- how long each step took;
- the program it went into;
- how soon after the last one it came, since a quick second try in the
  same program marks the first as wrong.

A Ctrl+Alt+Win correction gets a line of its own.

It is in `%LOCALAPPDATA%`. On his PC the Desktop and Documents are in
OneDrive, which would upload the recordings. The install folder is
replaced by an update. It is off in the defaults, and on only in his
config.json, because it holds what was said. That is everything the log
and the problem report are built to leave out. Days older than
`keep_days` (30) are deleted whole. `tools/archive_review.py` prints a day
back with the dictations worth a look flagged, so it is run when he asks,
never by the session brief.

## The name

### The way back

**The way back was the October rename undone, not a new rename.** The owner
never installed the October SpeakIt: on 19 November his PC still ran the
HeySpeaky of 26 September (`304b960`), and he asked for that to be the
version that counts. So `0187458` was reverted whole, which put every file
the app runs back to what he runs, plus the one later fix
(`3994e58`, one correction is a hint). What that commit had that was not
about the name was kept: the update check follows redirects, the suite
blanks the old dictionary paths, and the session brief and the commit check
find the app under either name.

### Used names

**Going back to a name already used is the dangerous kind of rename.** On
the owner's PC the SpeakIt folder holds a September SpeakIt, and
`%APPDATA%\SpeakIt\openai.key` is his live key - his config.json names it.
Neither may be touched, and nothing is: his HeySpeaky has its own
config.json and no note from October, so `Get-SpeakItCopy` finds nothing to
carry. A PC installed or updated between 26 October and 19 November is the
other way round: the October installer left `MOVED-TO-SPEAKIT.txt` in the
HeySpeaky folder, and the SpeakIt is the copy in use. Then, and when there
is no HeySpeaky at all, the SpeakIt is carried back: the HeySpeaky folder's
own older config.json and logs go to `HeySpeaky.old-<time>`, only if they
are older; the key is the file SpeakIt's config.json names, and a different
one in the way is renamed `.old-<time>`, never overwritten; the dictionary,
tally, update check and sounds come across the same way;
`MOVED-TO-HEYSPEAKY.txt` in the SpeakIt folder stops the next update
carrying it again. The CI install job builds that PC before it installs and
checks every piece, and another job checks the SpeakIt and VoiceType install
commands still reach an installer.
