import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { CLIP_AT, CLIP_SECONDS, cue, DURATION, LINES, SCENES, VO_AT, voEnd } from "./data";
import { Demo, Hold, Hook, Intro, Languages, Logo, Meta, Names, SlabShot } from "./scenes";
import { FPS, sec } from "./theme";
import music from "./music.json";
import { Arrive } from "./ui";
import { LightLeak } from "./dark";
import { WithLength } from "./sequence";

const OVERLAP = 0.2;

// Written by hand or by a script once there is music; null until then.
const MUSIC = (music as unknown as { file: string | null }).file;

const SCENE = { hook: Hook, reveal: Intro, hold: Hold, demo: Demo, slab: SlabShot, names: Names, langs: Languages, logo: Logo, meta: Meta } as const;

const release = CLIP_AT + CLIP_SECONDS + 0.15;
const land = release + 1.0;
const teach = cue("names", "teach");

// Every effect, where it lands - tied to the words, so a new voice moves
// them too - and how loud.
const EFFECTS: [string, number, number][] = [
  ["whoosh", 0.05, 0.45],
  ["thud", cue("hook", "one"), 0.75],
  ["whoosh", VO_AT.three - 0.1, 0.4],
  ["thud", cue("three", "three"), 0.85],
  ["pop", cue("three", "three") + 0.12, 0.35],
  ["pop", cue("three", "three") + 0.22, 0.35],
  ["pop", cue("three", "three") + 0.32, 0.35],
  ["riser", cue("this", "heyspeaky", "hey") - 0.85, 0.25],
  ["thud", cue("this", "heyspeaky", "hey"), 0.9],
  ["sparkle", cue("this", "heyspeaky", "hey") + 0.05, 0.4],
  ["thud", cue("hold", "ctrl", "control"), 0.75],
  ["thud", Math.max(cue("hold", "alt", "-alt"), cue("hold", "ctrl", "control") + 0.15), 0.75],
  ["swish", cue("hold", "switch"), 0.3],
  ["tap", release, 0.7],
  ["blip", land, 0.8],
  ["typing", land + 0.05, 0.35],
  ["glitch", VO_AT.regular - 0.35, 0.35],
  ["thud", voEnd("regular") - 0.02, 0.55],
  ["glitch", voEnd("regular") + 0.05, 0.5],
  ["whoosh", VO_AT.names - 0.15, 0.45],
  ["thud", teach, 0.5],
  ["thud", teach + 0.12, 0.5],
  ["thud", teach + 0.24, 0.5],
  ["typing", teach + 0.6, 0.3],
  ["pop", teach + 1.25, 0.5],
  ["sparkle", teach + 1.37, 0.45],
  ["whoosh", VO_AT.langs - 0.15, 0.45],
  ["pop", cue("langs", "yours"), 0.4],
  ["pop", cue("langs", "yours") + 0.12, 0.4],
  ["pop", cue("langs", "yours") + 0.24, 0.4],
  ["pop", cue("langs", "yours") + 0.36, 0.4],
  ["riser", VO_AT.free - 0.95, 0.4],
  ["thud", cue("free", "free"), 0.7],
  ["thud", cue("free", "open"), 0.6],
  ["thud", cue("free", "windows"), 0.6],
  ["whoosh", VO_AT.meta - 0.15, 0.45],
  ["thud", cue("meta", "code"), 0.7],
  ["sparkle", VO_AT.cta + 0.2, 0.4],
];

/** The music's level: down under every spoken line and under the clip. */
const musicVolume = (frame: number) => {
  const t = frame / FPS;
  let duck = 0;
  const spans: [number, number][] = LINES.map((line) => [VO_AT[line], voEnd(line)]);
  spans.push([CLIP_AT, CLIP_AT + CLIP_SECONDS]);
  for (const [a, b] of spans) {
    const into = Math.min(1, Math.max(0, (t - (a - 0.12)) / 0.12));
    const out = Math.min(1, Math.max(0, (t - b) / 0.3));
    duck = Math.max(duck, into * (1 - out));
  }
  const fadeIn = Math.min(1, t / 0.3);
  const fadeOut = Math.min(1, Math.max(0, (DURATION - t) / 1.2));
  return (0.5 - 0.36 * duck) * fadeIn * fadeOut;
};

export const Film: React.FC = () => (
  <AbsoluteFill style={{ background: "#050407" }}>
    {SCENES.map(([name, a, b], i) => {
      const Scene = SCENE[name];
      // Every shot but the first starts a moment early, arriving over the
      // one before it.
      const from = i === 0 ? a : a - OVERLAP;
      return (
        <Sequence key={name} from={sec(from)} durationInFrames={sec(b) - sec(from)} name={name}>
          <Arrive>
            <Scene start={from} end={b} />
          </Arrive>
        </Sequence>
      );
    })}

    {/* A light leak over every cut: warm on the dark shots, cooler into
        the languages, hot into the red slab. */}
    {SCENES.slice(1).map(([name, a], i) => {
      const length = sec(0.7);
      const hue = name === "langs" ? 150 : 28;
      return (
        <Sequence key={`leak-${name}`} from={Math.max(0, sec(a) - Math.round(length * 0.45))} durationInFrames={length} name={`leak ${name}`}>
          <WithLength frames={length}>
            <LightLeak seed={i} hueShift={hue} strength={name === "slab" ? 0.4 : 0.6} />
          </WithLength>
        </Sequence>
      );
    })}

    {LINES.map((line) => (
      <Sequence key={line} from={sec(VO_AT[line])} name={`vo ${line}`}>
        <Audio src={staticFile(`vo/${line}.wav`)} volume={1} />
      </Sequence>
    ))}
    <Sequence from={sec(CLIP_AT)} name="clip">
      <Audio src={staticFile("clip.wav")} volume={0.95} />
    </Sequence>
    {EFFECTS.map(([name, at, volume], i) => (
      <Sequence key={i} from={sec(Math.max(0, at))} name={name}>
        <Audio src={staticFile(`sfx/${name}.wav`)} volume={volume} />
      </Sequence>
    ))}
    {MUSIC && <Audio src={staticFile(MUSIC)} volume={musicVolume} />}
  </AbsoluteFill>
);
