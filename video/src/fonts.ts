import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadSerif } from "@remotion/google-fonts/InstrumentSerif";
import { loadFont as loadHeavy } from "@remotion/google-fonts/ArchivoBlack";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

// Inter carries Cyrillic and the Kazakh letters; Archivo Black is the heavy,
// wide face of the headlines, struck in metal; Instrument Serif's italic is
// the accent; JetBrains Mono is the blueprint's labels and the typing.
const inter = loadInter("normal", {
  weights: ["400", "500", "600", "700", "800", "900"],
  subsets: ["latin", "latin-ext", "cyrillic", "cyrillic-ext"],
});
const serif = loadSerif("italic", { weights: ["400"], subsets: ["latin"] });
const heavy = loadHeavy("normal", { weights: ["400"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["400", "600"], subsets: ["latin", "cyrillic"] });

export const INTER = inter.fontFamily;
export const SERIF = serif.fontFamily;
export const HEAVY = heavy.fontFamily;
export const MONO_FONT = mono.fontFamily;
export const fontsReady = Promise.all([inter.waitUntilDone(), serif.waitUntilDone(), heavy.waitUntilDone(), mono.waitUntilDone()]);
