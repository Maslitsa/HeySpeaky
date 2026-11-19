import words from "../public/vo/words.json";
import levels from "../public/levels.json";
import { FPS, Lang } from "./theme";

// When each spoken line starts, in seconds into the film.
export const VO_AT = {
  hook: 0.3,
  one: 3.0,
  mess: 5.6,
  meet: 9.3,
  hold: 11.8,
  letgo: 26.9,
  names: 30.2,
  langs: 33.8,
  logo: 38.7,
  meta: 42.6,
} as const;
export type Line = keyof typeof VO_AT;

type Timed = { seconds: number; words: { w: string; start: number; end: number }[] };
const TIMED = words as unknown as Record<Line, Timed>;

/** When word `i` of a line is heard, in seconds into the film. */
export const wordAt = (line: Line, i: number) => VO_AT[line] + TIMED[line].words[i].start;

// The demo recording: four languages in one breath, as the app heard it.
export const CLIP_AT = 15.4;
export const CLIP_SECONDS = 11.1;

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
  ["hook", 0.0, 2.9],
  ["one", 2.9, 9.0],
  ["meet", 9.0, 11.6],
  ["hold", 11.6, 15.3],
  ["demo", 15.3, 30.0],
  ["names", 30.0, 33.6],
  ["langs", 33.6, 38.4],
  ["logo", 38.4, 42.4],
  ["meta", 42.4, 47.5],
] as const;
export const DURATION = 47.5;
