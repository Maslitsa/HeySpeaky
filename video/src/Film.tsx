import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { CLIP_AT, CLIP_SECONDS, SCENES, VO_AT, Line } from "./data";
import { Demo, Hold, Hook, Languages, Logo, Meet, Meta, Names, One } from "./scenes";
import { C, FPS, sec } from "./theme";
import music from "./music.json";
import { Arrive } from "./ui";

const OVERLAP = 0.22;

// Written by scripts/music.py once there is music; null until then.
const MUSIC = (music as unknown as { file: string | null }).file;

const SCENE = { hook: Hook, one: One, meet: Meet, hold: Hold, demo: Demo, names: Names, langs: Languages, logo: Logo, meta: Meta } as const;

// Every effect, where it lands, and how loud.
const EFFECTS: [string, number, number][] = [
  ["whoosh", 0.1, 0.5],
  ["pop", 1.55, 0.35],
  ["pop", 1.67, 0.35],
  ["pop", 1.79, 0.35],
  ["whoosh", 2.82, 0.55],
  ["swish", 3.3, 0.3],
  ["swish", 3.6, 0.3],
  ["swish", 3.9, 0.3],
  ["swish", 4.2, 0.3],
  ["swish", 4.5, 0.3],
  ["swish", 4.8, 0.3],
  ["glitch", 7.35, 0.45],
  ["whoosh", 8.9, 0.55],
  ["pop", 9.42, 0.5],
  ["sparkle", 10.1, 0.4],
  ["thud", 12.14, 0.8],
  ["thud", 12.84, 0.8],
  ["tap", 26.7, 0.7],
  ["blip", 27.8, 0.8],
  ["typing", 27.85, 0.35],
  ["whoosh", 29.92, 0.5],
  ["thud", 31.0, 0.55],
  ["thud", 31.12, 0.55],
  ["thud", 31.24, 0.55],
  ["typing", 31.75, 0.3],
  ["pop", 32.5, 0.5],
  ["sparkle", 32.62, 0.45],
  ["whoosh", 33.55, 0.5],
  ["pop", 36.0, 0.4],
  ["pop", 36.12, 0.4],
  ["pop", 36.24, 0.4],
  ["pop", 36.36, 0.4],
  ["riser", 37.5, 0.45],
  ["thud", 38.42, 0.7],
  ["sparkle", 38.45, 0.35],
  ["whoosh", 42.35, 0.45],
  ["sparkle", 46.35, 0.4],
];

const VO_SECONDS: Record<Line, number> = { hook: 2.45, one: 2.45, mess: 3.05, meet: 2.25, hold: 3.25, letgo: 2.9, names: 1.9, langs: 4.2, logo: 2.65, meta: 4.3 };

/** The music's level: down under every spoken line and under the clip. */
const musicVolume = (frame: number) => {
  const t = frame / FPS;
  let duck = 0;
  const spans: [number, number][] = Object.entries(VO_AT).map(([k, a]) => [a, a + VO_SECONDS[k as Line]]);
  spans.push([CLIP_AT, CLIP_AT + CLIP_SECONDS]);
  for (const [a, b] of spans) {
    const into = Math.min(1, Math.max(0, (t - (a - 0.15)) / 0.15));
    const out = Math.min(1, Math.max(0, (t - b) / 0.35));
    duck = Math.max(duck, into * (1 - out));
  }
  const fadeIn = Math.min(1, t / 0.4);
  const fadeOut = Math.min(1, Math.max(0, (47.5 - t) / 1.2));
  return (0.55 - 0.37 * duck) * fadeIn * fadeOut;
};

export const Film: React.FC = () => (
  <AbsoluteFill style={{ background: C.paper }}>
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

    {(Object.keys(VO_AT) as Line[]).map((line) => (
      <Sequence key={line} from={sec(VO_AT[line])} name={`vo ${line}`}>
        <Audio src={staticFile(`vo/${line}.wav`)} volume={1} />
      </Sequence>
    ))}
    <Sequence from={sec(CLIP_AT)} name="clip">
      <Audio src={staticFile("clip.wav")} volume={0.95} />
    </Sequence>
    {EFFECTS.map(([name, at, volume], i) => (
      <Sequence key={i} from={sec(at)} name={name}>
        <Audio src={staticFile(`sfx/${name}.wav`)} volume={volume} />
      </Sequence>
    ))}
    {MUSIC && <Audio src={staticFile(MUSIC)} volume={musicVolume} />}
  </AbsoluteFill>
);
