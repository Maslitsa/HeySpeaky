import words from "../public/vo/words.json";
import levels from "../public/levels.json";
import { FPS, Lang } from "./theme";

// The spoken lines, in order. Where each one starts is worked out from how
// long the voice took to say the ones before it, so a new voice - a new
// take, ElevenLabs instead of OpenAI - re-times the whole film by itself.
export const LINES = ["hook", "three", "this", "hold", "letgo", "regular", "names", "langs", "free", "meta", "cta"] as const;
export type Line = (typeof LINES)[number];

type Timed = { text: string; seconds: number; words: { w: string; start: number; end: number }[] };
const TIMED = words as unknown as Record<Line, Timed>;

/** How long a line takes, to its last word and a breath after. */
const spoken = (line: Line) => {
  const w = TIMED[line].words;
  return w.length ? w[w.length - 1].end + 0.1 : TIMED[line].seconds;
};

// The demo recording: Laura saying one sentence in four languages, in one
// take (ElevenLabs, eleven_v4). HeySpeaky transcribed it word for word.
export const CLIP_SECONDS = 8.72;

// After each line, how long before the next thing starts: room for what the
// picture still has to do.
const AFTER: Record<Line | "clip", number> = {
  hook: 0.15,
  three: 0.4,
  this: 0.5,
  hold: 0.25,
  clip: 0.3,
  letgo: 0.5,
  regular: 1.0,
  names: 1.25,
  langs: 0.45,
  free: 0.5,
  meta: 0.3,
  cta: 1.1,
};

const ORDER: (Line | "clip")[] = ["hook", "three", "this", "hold", "clip", "letgo", "regular", "names", "langs", "free", "meta", "cta"];

const timeline = () => {
  const at = {} as Record<Line, number>;
  let t = 0.35;
  let clip = 0;
  for (const item of ORDER) {
    if (item === "clip") {
      clip = t;
      t += CLIP_SECONDS + AFTER.clip;
    } else {
      at[item] = t;
      t += spoken(item) + AFTER[item];
    }
  }
  return { at, clip, end: t };
};
const TIMES = timeline();

export const VO_AT = TIMES.at;
export const CLIP_AT = TIMES.clip;
export const DURATION = Math.round(TIMES.end * FPS) / FPS;
export const voEnd = (line: Line) => VO_AT[line] + spoken(line);

/** When word `i` of a line is heard, in seconds into the film. */
export const wordAt = (line: Line, i: number) => {
  const w = TIMED[line].words;
  return VO_AT[line] + (w[Math.min(i, w.length - 1)]?.start ?? 0);
};

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9а-яёәғқңөұүһі]/g, "");

/**
 * When a word is heard, found by what it says rather than where it is: a
 * different voice splits "Control-Alt" or "ninety-seven" differently, and
 * counting words would then point at the wrong one. Falls back to where the
 * word sits in the line's text.
 */
export const cue = (line: Line, ...words: string[]) => {
  const said = TIMED[line].words;
  for (const word of words) {
    const key = norm(word);
    const hit = said.find((w) => norm(w.w).startsWith(key));
    if (hit) return VO_AT[line] + hit.start;
  }
  const text = TIMED[line].text.toLowerCase();
  const index = text.indexOf(words[0].toLowerCase());
  return VO_AT[line] + (index >= 0 ? index / text.length : 0) * spoken(line);
};

/** What the Mono pill would show for an audio file `at` seconds in. */
export const levelAt = (name: string, at: number) => {
  const series = (levels as unknown as Record<string, number[]>)[name];
  if (!series || at < 0) return 0;
  const i = Math.round(at * FPS);
  return i < series.length ? series[i] : 0;
};

// What was said, when each word starts in the clip (large-v3-turbo, one
// language at a time, 20 November 2026), and what HeySpeaky typed for it:
// tools/try_demo.py --cloud, word for word.
export const SPOKEN: { lang: Lang; said: string; typed: string; starts: number[] }[] = [
  { lang: "en", said: "I already sent the invoice,", typed: "I already sent the invoice,", starts: [0.0, 0.22, 0.54, 0.8, 0.96] },
  { lang: "de", said: "aber ich warte noch auf eine Antwort…", typed: "aber ich warte noch auf eine Antwort.", starts: [1.8, 2.08, 2.42, 2.7, 2.86, 3.04, 3.24] },
  { lang: "ru", said: "но клиент до сих пор не ответил,", typed: "Но клиент до сих пор не ответил,", starts: [4.36, 4.5, 4.9, 5.04, 5.24, 5.46, 5.6] },
  { lang: "kk", said: "сондықтан ертең қоңырау шаламын.", typed: "сондықтан ертең қоңырау шаламын.", starts: [6.55, 7.01, 7.51, 7.93] },
];
export const SPANS = [
  [0.0, 1.6],
  [1.6, 4.25],
  [4.25, 6.4],
  [6.4, 8.72],
];

/** Every word of the clip, in order, with its language and timing. */
export const CLIP_WORDS = SPOKEN.flatMap((part) => {
  const said = part.said.split(" ");
  const typed = part.typed.split(" ");
  return said.map((w, i) => ({ said: w, typed: typed[i], lang: part.lang, start: part.starts[i] }));
});

// What OpenAI's older whisper-1 wrote for the same clip, the same day: the
// English and German right, the Russian and Kazakh spelled out in Latin.
export const WHISPER_HEARD = ["No klient de sikhpor ne atvetil.", "Sondokhtan Yerchenkhon Raushalam."];

export const SCENES = [
  ["hook", 0, VO_AT.this - 0.12],
  ["reveal", VO_AT.this - 0.12, VO_AT.hold - 0.12],
  ["hold", VO_AT.hold - 0.12, CLIP_AT - 0.1],
  ["demo", CLIP_AT - 0.1, VO_AT.regular - 0.12],
  ["slab", VO_AT.regular - 0.12, VO_AT.names - 0.12],
  ["names", VO_AT.names - 0.12, VO_AT.langs - 0.12],
  ["langs", VO_AT.langs - 0.12, VO_AT.free - 0.12],
  ["logo", VO_AT.free - 0.12, VO_AT.meta - 0.12],
  ["meta", VO_AT.meta - 0.12, DURATION],
] as const;
export type SceneName = (typeof SCENES)[number][0];
