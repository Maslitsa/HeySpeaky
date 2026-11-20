# The HeySpeaky film

Every frame of the film is drawn by the code in `src/`, with
[Remotion](https://www.remotion.dev/) and, for the 3D world,
[three.js](https://threejs.org/) through `@remotion/three`. The character is
Speaky, the app's own Mono pill as a glossy object with two glowing eyes,
and its eight bars move by the same formula the app uses (`monoHeights`, a
port of `heyspeaky/glass.py`), driven by the loudness the app's meter would
read from the audio (`scripts/assets.py`).

The film is one 3D world the camera travels through (`src/Film3D.tsx`):
languages as glowing orbs, Speaky made from three of them, keycaps that
fall into place and glow red while held, a galaxy of all 97 languages. One
solid-red shot - what regular dictation does to the same sentence - is
flat on purpose. Type and the window are HTML over the 3D, placed on the
world by projecting through the same camera (`src/three/camera.ts`).

## Building it

Install the packages in a folder outside OneDrive. Remotion is tens of
thousands of small files, and OneDrive would try to sync every one of them.

```powershell
npm install
$env:HEYSPEAKY_REPO = "<path to this repository>"
python scripts\voice.py           # speaks the lines (OpenAI), times every word
python scripts\assets.py          # mouth levels, icon, languages, the demo clip
python scripts\soft_sfx.py        # the sound effects
python scripts\music_dark.py      # the music, written as numbers
python scripts\code.py            # the source the last shot scrolls through
npx remotion studio src/index.ts  # look at it
npx remotion render src/index.ts HeySpeaky out/HeySpeaky.mp4 --gl=angle --preferred-effect-backend=webgl2 --concurrency=2
```

Those render flags are all needed on an ordinary laptop: `--gl=angle` for
WebGL at all, `webgl2` because Remotion's WebGPU effects lost the device
next to the 3D, and two tabs because four ran a 14 GB laptop out of memory
(ffprobe failed with 0xC000012D).

The film's own narration is one ElevenLabs take (voice Laura, `eleven_v4`),
read in one go so it sounds like one person telling a story, then cut into
lines by `scripts\split_voice.py TAKE.mp3`; the four-language sentence is a
second Laura take, `takes/laura-demo.mp3`, which `assets.py` uses when it is
there. Without them, `voice.py` and the repository's
`demo/four_languages.wav` stand in, and the whole film re-times itself to
whatever voice it gets: every scene starts where its line starts
(`src/data.ts`), and every word on screen is found by what it says.

The music is code too (`scripts/music_dark.py`): D minor at 120 beats a
minute, laid on the same timeline, so the drop lands on regular
dictation's answer and the last chord under the last line. It goes down to
a bare pad under the four-language sentence, because anything with an edge
there took the end off the last Kazakh word when HeySpeaky listened to the
mix. Any other track can go in `public/`, named in `src/music.json`.

Run the scripts with the app's Python, which has its packages. Keys are read
where HeySpeaky keeps them and are never printed.

## Three things three.js does differently here

- **The camera is the canvas's own, moved in a layout effect.** Remotion
  draws a frame in an effect; a camera made default by drei's
  `PerspectiveCamera` arrives one render later, and the effects pass drew
  the first frame through the old one - squashed, shifted, from elsewhere.
- **No `ContactShadows`.** The effects pass turns the renderer's auto-clear
  off and ContactShadows never clears its buffer, so each frame's shadow
  piled onto the last and the orbs drew their path on the floor as a ring.
  `Shadow` in `World.tsx` is a soft disc instead.
- **The effects pass is sized before the first frame** (`SizedComposer`):
  it is made while the canvas is still 300 by 150.

Generated audio, the icon and `out/` are not committed: `public/vo/words.json`
and `public/levels.json` are, so the timing can be read without speaking the
lines again.

## What is real, and what is not

- The four-language sentence is a synthesised voice. What lands in the
  window is what HeySpeaky typed for it (`tools/try_demo.py --cloud`), word
  for word.
- The Latin-letter mess is whisper-1's own answer for the same take.
- The narrator's voice is synthesised.
- The wait after letting go is shorter in the film than in life.
