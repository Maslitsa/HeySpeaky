import * as THREE from "three";

// Two looks for the same 3D world, so the owner can choose by seeing: a dark
// studio lit by the pill's own red, and a pale one like a product shot. The
// objects, the camera and the timing are the same in both.
export type Look = "dark" | "light";

export type Palette = {
  bg: string;
  fogNear: number;
  fogFar: number;
  floor: string;
  mirror: number;
  ink: string;
  muted: string;
  accent: string;
  accentGlow: string;
  bloom: number;
  threshold: number;
  vignette: number;
  shadow: number;
  ambient: number;
  key: number;
  rim: string;
  rim2: string;
  envWarm: string;
  pool: string;
};

export const PALETTES: Record<Look, Palette> = {
  dark: {
    bg: "#07060a",
    fogNear: 9,
    fogFar: 24,
    floor: "#0d0b11",
    mirror: 0.75,
    ink: "#F4F2F7",
    muted: "rgba(244,242,247,0.62)",
    accent: "#FF5A3C",
    accentGlow: "0 0 24px rgba(255,74,43,0.85), 0 0 80px rgba(255,74,43,0.45)",
    bloom: 1.15,
    threshold: 0.6,
    vignette: 0.75,
    shadow: 0.9,
    ambient: 0.12,
    key: 1.6,
    rim: "#ff4a2b",
    rim2: "#3d6bff",
    envWarm: "#ff7a50",
    pool: "#ff3b2a",
  },
  light: {
    bg: "#e8e5ec",
    fogNear: 10,
    fogFar: 28,
    floor: "#dedae4",
    mirror: 0.45,
    ink: "#141216",
    muted: "rgba(20,18,22,0.56)",
    accent: "#F0432A",
    accentGlow: "0 10px 30px rgba(240,67,42,0.25)",
    bloom: 0.75,
    threshold: 0.93,
    vignette: 0.28,
    shadow: 0.5,
    ambient: 0.6,
    key: 1.3,
    rim: "#ff8a6a",
    rim2: "#8fb0ff",
    envWarm: "#ffd6c4",
    pool: "#ff6a50",
  },
};

export const color = (hex: string) => new THREE.Color(hex);
