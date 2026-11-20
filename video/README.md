# The HeySpeaky film

Every frame of the film is drawn by the code in `src/`, with
[Remotion](https://www.remotion.dev/). The character is Speaky, the app's own
Mono pill with eyes, and its bars move by the same formula the app uses
(`monoHeights`, a port of `heyspeaky/glass.py`), driven by the loudness the
app's meter would read from the audio (`scripts/assets.py`).

The look is a dark stage - a blueprint grid, a floor running away in
perspective, one warm light, type struck in metal - with one hit of solid
red, and a light leak over every cut (Remotion's `@remotion/effects`).

## Building it

Install the packages in a folder outside OneDrive. Remotion is tens of
thousands of small files, and OneDrive would try to sync every one of them.

```powershell
npm install
$env:HEYSPEAKY_REPO = "<path to this repository>"
python scripts\voice.py           # speaks the lines (OpenAI), times every word
python scripts\assets.py          # sound effects, mouth levels, icon, languages
python scripts\music_dark.py      # stand-in music, written as numbers
python scripts\code.py            # the source the last shot scrolls through
npx remotion studio src/index.ts  # look at it
npx remotion render src/index.ts HeySpeaky out/HeySpeaky-16x9.mp4 --gl=angle
```

`--gl=angle` is needed: the light leaks are drawn with WebGL.

The film's own narration is one ElevenLabs take (voice Laura, `eleven_v4`),
read in one go so it sounds like one person telling a story, then cut into
lines by `scripts\split_voice.py TAKE.mp3`. Its music is an ElevenLabs Music
track; put any track in `public/` and name it in `src/music.json`. Without
either, `voice.py` and `music_dark.py` make stand-ins, and the whole film
re-times itself to whatever voice it gets: every scene starts where its line
starts (`src/data.ts`), and every word on screen is found by what it says.

Run the scripts with the app's Python, which has its packages. Keys are read
where HeySpeaky keeps them and are never printed.

Generated audio, the icon and `out/` are not committed: `public/vo/words.json`
and `public/levels.json` are, so the timing can be read without speaking the
lines again.

## What is real, and what is not

- The four-language sentence is `demo/four_languages.wav`, a synthesised
  voice, and what lands in the window is what OpenAI typed for it.
- The Latin-letter mess is whisper-1's own answer for the same clip.
- The narrator's voice is synthesised.
- The wait after letting go is shorter in the film than in life.
