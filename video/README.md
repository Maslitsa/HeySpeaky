# The HeySpeaky film

Every frame of the film is drawn by the code in `src/`, with
[Remotion](https://www.remotion.dev/). The character is the app's own Mono
pill with eyes, and its bars move by the same formula the app uses
(`monoHeights`, a port of `heyspeaky/glass.py`), driven by the loudness the
app's meter would read from the audio (`scripts/assets.py`).

Nothing here is downloaded art: the sound effects are arithmetic, like the
app's own sounds, and `tap` and `blip` are the app's voices from
`heyspeaky/sound.py`.

## Building it

Install the packages in a folder outside OneDrive. Remotion is tens of
thousands of small files, and OneDrive would try to sync every one of them.

```powershell
npm install
$env:HEYSPEAKY_REPO = "<path to this repository>"
python scripts\voice.py     # speaks the lines with OpenAI, times every word
python scripts\assets.py    # sound effects, mouth levels, icon, language names
python scripts\code.py      # the source the last shot scrolls through
npx remotion studio src/index.ts                                  # look at it
npx remotion render src/index.ts HeySpeaky out/HeySpeaky-16x9.mp4  # make it
```

`voice.py` uses the OpenAI key HeySpeaky itself uses and never prints it.
Run the scripts with the app's Python, which has its packages.

Generated audio, the icon and `out/` are not committed: `public/vo/words.json`
and `public/levels.json` are, so the timing can be read without speaking
the lines again.

## What is real, and what is not

- The four-language sentence is `demo/four_languages.wav`, a synthesised
  voice, and what lands in the window is what OpenAI typed for it.
- The Latin-letter mess is whisper-1's own answer for the same clip.
- The narrator's voice is OpenAI text-to-speech.
- The wait after letting go is shorter in the film than in life.
