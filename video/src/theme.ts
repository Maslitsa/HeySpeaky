// Every colour comes from the app (heyspeaky/theme.py): the Mono pill's
// black, its listening red and thinking blue, and the four rim colours,
// one per language as the old film had them.
export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

export const C = {
  paper: "#F7F6F3",
  ink: "#141414",
  grey: "#77766F",
  faint: "#C9C8C3",
  mono: "#0A070B",
  red: "#D92D34",
  blue: "#0267C5",
  blueLit: "#287CE2",
  night: "#0B1026",
  nightLit: "#1E2A5E",
};

export const LANG = {
  en: { name: "English", color: "#0A84FF", ink: "#0657B0" },
  de: { name: "Deutsch", color: "#BF5AF2", ink: "#7E2FA8" },
  ru: { name: "Русский", color: "#FF375F", ink: "#B8173A" },
  kk: { name: "Қазақша", color: "#FF9F0A", ink: "#A55F00" },
} as const;
export type Lang = keyof typeof LANG;

export const sec = (seconds: number) => Math.round(seconds * FPS);

export const clamp = (v: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));

export const hexA = (hex: string, alpha: number) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};
