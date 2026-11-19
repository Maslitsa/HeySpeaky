import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadSerif } from "@remotion/google-fonts/InstrumentSerif";

// Inter carries Cyrillic and the Kazakh letters; Instrument Serif's italic
// is the accent, as the film the owner liked set its key words.
const inter = loadInter("normal", {
  weights: ["500", "600", "700", "800", "900"],
  subsets: ["latin", "latin-ext", "cyrillic", "cyrillic-ext"],
});
const serif = loadSerif("italic", { weights: ["400"], subsets: ["latin"] });

export const INTER = inter.fontFamily;
export const SERIF = serif.fontFamily;
export const MONO_FONT = "Consolas, 'Cascadia Mono', monospace";
export const fontsReady = Promise.all([inter.waitUntilDone(), serif.waitUntilDone()]);
