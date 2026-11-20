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

// The demo recording: four languages in one breath, as the app heard it.
export const CLIP_SECONDS = 11.1;

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

// What was said, and when each word starts in the clip (whisper-1's word
// timestamps, 26 October 2026) - and what OpenAI typed for it, word for word.
export const SPOKEN: { lang: Lang; said: string; typed: string; starts: number[] }[] = [
  { lang: "en", said: "I already sent the invoice,", typed: "I already sent the invoice,", starts: [0.0, 0.56, 1.14, 1.6, 2.06] },
  { lang: "de", said: "aber ich warte noch auf eine Antwort,", typed: "aber ich warte noch auf eine Antwort.", starts: [2.6, 2.88, 3.1, 3.4, 3.76, 3.94, 4.2] },
  { lang: "ru", said: "но клиент до сих пор не ответил,", typed: "Но клиент до сих пор не ответил.", starts: [5.06, 5.28, 5.92, 6.58, 6.92, 7.2, 7.78] },
  { lang: "kk", said: "сондықтан ертең қоңырау шаламын.", typed: "Сондықтан ертең қоңырау шаламын.", starts: [8.74, 9.64, 10.04, 10.6] },
];
export const SPANS = [
  [0.0, 2.53],
  [2.53, 4.87],
  [4.87, 8.53],
  [8.53, 11.1],
];

/** Every word of the clip, in order, with its language and timing. */
export const CLIP_WORDS = SPOKEN.flatMap((part) => {
  const said = part.said.split(" ");
  const typed = part.typed.split(" ");
  return said.map((w, i) => ({ said: w, typed: typed[i], lang: part.lang, start: part.starts[i] }));
});

// What whisper-1 itself wrote for the clip, in that same request.
export const WHISPER_HEARD = ["No client do sikh por ni atvetil.", "Sondag dann. Yirtin kongrao shalaman."];

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
