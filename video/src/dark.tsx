import React from "react";
import { lightLeak } from "@remotion/effects/light-leak";
import { AbsoluteFill, Solid, useCurrentFrame, useVideoConfig } from "remotion";
import { useSequenceLength } from "./sequence";
import { HEAVY, INTER, MONO_FONT, SERIF } from "./fonts";
import { hexA } from "./theme";

// The dark stage, after the second film the owner sent: near black, a
// blueprint grid, a floor running away in perspective, one warm light, and
// type struck in metal. The warm light is the Mono pill's red, warmed.

export const EMBER = "#FF4A2B";

export const metal = (size: number): React.CSSProperties => ({
  fontFamily: HEAVY,
  fontSize: size,
  lineHeight: 0.92,
  letterSpacing: -size * 0.02,
  textTransform: "uppercase",
  background: "linear-gradient(180deg, #FFFFFF 0%, #ECECF1 38%, #9C9CA6 50%, #E4E4EA 62%, #FFFFFF 100%)",
  WebkitBackgroundClip: "text",
  backgroundClip: "text",
  color: "transparent",
  filter: "drop-shadow(0 6px 24px rgba(0,0,0,0.6))",
});

export const ember = (size: number, font: "heavy" | "serif" = "heavy"): React.CSSProperties => ({
  fontFamily: font === "heavy" ? HEAVY : SERIF,
  fontStyle: font === "serif" ? "italic" : "normal",
  fontSize: size,
  lineHeight: font === "heavy" ? 0.92 : 1,
  letterSpacing: font === "heavy" ? -size * 0.02 : -size * 0.01,
  textTransform: font === "heavy" ? "uppercase" : "none",
  color: "#FF5A3C",
  textShadow: `0 0 ${size * 0.12}px rgba(255,74,43,0.85), 0 0 ${size * 0.4}px rgba(255,74,43,0.45)`,
});

export const white = (size: number, weight = 700): React.CSSProperties => ({
  fontFamily: INTER,
  fontWeight: weight,
  fontSize: size,
  lineHeight: 1.05,
  letterSpacing: -size * 0.025,
  color: "#F4F2F7",
});

export const label = (size = 22, color = "rgba(255,255,255,0.55)"): React.CSSProperties => ({
  fontFamily: MONO_FONT,
  fontSize: size,
  color,
  letterSpacing: size * 0.08,
  textTransform: "uppercase",
});

const Dust: React.FC<{ t: number }> = ({ t }) => {
  const specks = [];
  for (let i = 0; i < 46; i++) {
    const x = (i * 263) % 1920;
    const speed = 8 + (i % 7) * 4;
    const y = 1080 - ((((i * 157) % 1080) + t * speed) % 1180);
    const twinkle = 0.35 + 0.65 * Math.abs(Math.sin(t * (0.6 + (i % 5) * 0.3) + i));
    const size = 1.5 + (i % 4);
    specks.push(
      <div
        key={i}
        style={{
          position: "absolute",
          left: x + Math.sin(t * 0.4 + i) * 20,
          top: y,
          width: size,
          height: size,
          borderRadius: "50%",
          background: i % 6 === 0 ? EMBER : "#FFFFFF",
          opacity: 0.28 * twinkle,
          boxShadow: i % 6 === 0 ? `0 0 8px ${EMBER}` : undefined,
        }}
      />,
    );
  }
  return <>{specks}</>;
};

/** The stage: a grid wall, a floor that slides towards us, a warm light,
 *  dust in the air. `light` is where the glow sits. */
export const Stage: React.FC<{ t: number; light?: [number, number]; heat?: number; tint?: string; floor?: number; children?: React.ReactNode }> = ({
  t,
  light = [960, 640],
  heat = 1,
  tint = EMBER,
  floor = 1,
  children,
}) => (
  <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 40%, #17121C 0%, #0A080D 55%, #030204 100%)", overflow: "hidden" }}>
    <AbsoluteFill
      style={{
        backgroundImage: "linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px)",
        backgroundSize: "96px 96px",
        backgroundPosition: `${-t * 6}px ${-t * 4}px`,
        WebkitMaskImage: "radial-gradient(ellipse at 50% 45%, black 20%, transparent 75%)",
        maskImage: "radial-gradient(ellipse at 50% 45%, black 20%, transparent 75%)",
      }}
    />
    {floor > 0 && (
      <div style={{ position: "absolute", left: 0, top: 600, width: 1920, height: 480, perspective: 640, perspectiveOrigin: "50% 0%", opacity: floor, overflow: "hidden" }}>
        <div
          style={{
            position: "absolute",
            left: -1600,
            top: 0,
            width: 5120,
            height: 1600,
            transformOrigin: "50% 0%",
            transform: "rotateX(74deg)",
            backgroundImage: `linear-gradient(${hexA(tint, 0.34)} 2px, transparent 2px), linear-gradient(90deg, ${hexA(tint, 0.24)} 2px, transparent 2px)`,
            backgroundSize: "120px 120px",
            backgroundPosition: `0px ${t * 90}px`,
            WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, black 25%, black 100%)",
            maskImage: "linear-gradient(to bottom, transparent 0%, black 25%, black 100%)",
          }}
        />
      </div>
    )}
    {floor > 0 && (
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 598,
          width: 1920,
          height: 3,
          background: `linear-gradient(90deg, transparent, ${hexA(tint, 0.9)} 30%, ${hexA(tint, 0.9)} 70%, transparent)`,
          boxShadow: `0 0 30px 6px ${hexA(tint, 0.45)}`,
          opacity: 0.45 * floor,
        }}
      />
    )}
    <div
      style={{
        position: "absolute",
        left: light[0] - 700,
        top: light[1] - 500,
        width: 1400,
        height: 1000,
        borderRadius: "50%",
        background: `radial-gradient(ellipse, ${hexA(tint, 0.2 * heat * (0.9 + 0.1 * Math.sin(t * 2.3)))} 0%, ${hexA(tint, 0)} 65%)`,
        mixBlendMode: "screen",
      }}
    />
    <Dust t={t} />
    {children}
    <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 50%, transparent 55%, rgba(0,0,0,0.65) 100%)", pointerEvents: "none" }} />
  </AbsoluteFill>
);

/** An anamorphic flare: a hot line of light that flashes and fades. */
export const Flare: React.FC<{ t: number; at: number; x: number; y: number; width?: number; color?: string; length?: number }> = ({
  t,
  at,
  x,
  y,
  width = 1400,
  color = EMBER,
  length = 0.6,
}) => {
  const d = t - at;
  if (d < 0 || d > length) return null;
  const k = d < 0.06 ? d / 0.06 : 1 - (d - 0.06) / (length - 0.06);
  const w = width * (0.6 + 0.4 * Math.min(1, d / 0.15));
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: x - w / 2,
          top: y - 2,
          width: w,
          height: 4,
          borderRadius: 4,
          background: `linear-gradient(90deg, transparent, ${color}, #FFFFFF 50%, ${color}, transparent)`,
          opacity: k,
          boxShadow: `0 0 24px 6px ${hexA(color, 0.6)}`,
          mixBlendMode: "screen",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: x - 160,
          top: y - 160,
          width: 320,
          height: 320,
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(255,255,255,${0.9 * k}) 0%, ${hexA(color, 0.5 * k)} 25%, transparent 65%)`,
          mixBlendMode: "screen",
        }}
      />
    </>
  );
};

/** A flash over everything, for the big arrivals. */
export const Flash: React.FC<{ t: number; at: number; length?: number; color?: string }> = ({ t, at, length = 0.35, color = "#FFFFFF" }) => {
  const d = t - at;
  if (d < 0 || d > length) return null;
  return <AbsoluteFill style={{ background: color, opacity: Math.pow(1 - d / length, 2) * 0.85, mixBlendMode: "screen" }} />;
};

/** Blueprint corners round a box, and a small label above it. */
export const Hud: React.FC<{ x: number; y: number; w: number; h: number; text?: string; alpha?: number; color?: string }> = ({
  x,
  y,
  w,
  h,
  text,
  alpha = 1,
  color = "rgba(255,255,255,0.5)",
}) => {
  const c = 22;
  const line = (style: React.CSSProperties, key: string) => <div key={key} style={{ position: "absolute", background: color, ...style }} />;
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, opacity: alpha }}>
      {line({ left: 0, top: 0, width: c, height: 2 }, "a")}
      {line({ left: 0, top: 0, width: 2, height: c }, "b")}
      {line({ right: 0, top: 0, width: c, height: 2 }, "c")}
      {line({ right: 0, top: 0, width: 2, height: c }, "d")}
      {line({ left: 0, bottom: 0, width: c, height: 2 }, "e")}
      {line({ left: 0, bottom: 0, width: 2, height: c }, "f")}
      {line({ right: 0, bottom: 0, width: c, height: 2 }, "g")}
      {line({ right: 0, bottom: 0, width: 2, height: c }, "h")}
      {text && <div style={{ position: "absolute", left: 0, top: -34, ...label(18, color) }}>{text}</div>}
    </div>
  );
};

/** A keycap in the dark: black, its label lit, a red glow under it pressed. */
export const DarkKey: React.FC<{ text: string; size: number; press: number; style?: React.CSSProperties }> = ({ text, size, press, style }) => {
  const w = size * (text.length > 3 ? 1.3 : 1.05);
  const h = size * 0.8;
  const lip = size * 0.1;
  const drop = lip * 0.8 * press;
  const radius = size * 0.17;
  const on = press > 0.5;
  return (
    <div style={{ position: "relative", width: w, height: h + lip, ...style }}>
      <div style={{ position: "absolute", left: -w * 0.3, top: h * 0.5, width: w * 1.6, height: h, borderRadius: "50%", background: `radial-gradient(ellipse, ${hexA(EMBER, 0.55 * press)} 0%, transparent 70%)` }} />
      <div style={{ position: "absolute", left: 0, top: lip, width: w, height: h, borderRadius: radius, background: "#050407", border: "1px solid #2A2530" }} />
      <div
        style={{
          position: "absolute",
          left: 0,
          top: drop,
          width: w,
          height: h,
          borderRadius: radius,
          background: on ? "linear-gradient(#1B1720, #141117)" : "linear-gradient(#2A2530, #18151C)",
          border: `2px solid ${on ? hexA(EMBER, 0.9) : "#3D3745"}`,
          boxShadow: on ? `0 0 ${size * 0.25}px ${hexA(EMBER, 0.55)}, inset 0 0 ${size * 0.15}px ${hexA(EMBER, 0.25)}` : "inset 0 2px 0 rgba(255,255,255,0.08)",
          boxSizing: "border-box",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: INTER,
          fontWeight: 700,
          fontSize: size * 0.27,
          color: on ? "#FFE1D9" : "#E8E6EC",
          textShadow: on ? `0 0 12px ${EMBER}` : undefined,
        }}
      >
        {text}
      </div>
    </div>
  );
};

/** A window in the dark: smoked glass, a thin rim, a title bar. */
export const DarkWindow: React.FC<{ x: number; y: number; w: number; h: number; title?: string; style?: React.CSSProperties; children?: React.ReactNode }> = ({
  x,
  y,
  w,
  h,
  title = "Notes",
  style,
  children,
}) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: w,
      height: h,
      background: "linear-gradient(180deg, rgba(32,28,38,0.94), rgba(16,13,20,0.96))",
      borderRadius: 22,
      border: "1px solid rgba(255,255,255,0.13)",
      boxShadow: `0 40px 100px rgba(0,0,0,0.6), 0 0 60px ${hexA(EMBER, 0.12)}`,
      overflow: "hidden",
      ...style,
    }}
  >
    <div style={{ height: 58, borderBottom: "1px solid rgba(255,255,255,0.08)", display: "flex", alignItems: "center", padding: "0 24px", justifyContent: "space-between" }}>
      <span style={{ fontFamily: INTER, fontWeight: 500, fontSize: 22, color: "rgba(255,255,255,0.5)" }}>{title}</span>
      <span style={{ display: "flex", gap: 10 }}>
        {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
          <span key={c} style={{ width: 13, height: 13, borderRadius: "50%", background: c, opacity: 0.8 }} />
        ))}
      </span>
    </div>
    {children}
  </div>
);

/** The red slab: a full-frame hit of colour, as the second film's "IS CRAZY". */
export const Slab: React.FC<{ children?: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ background: "radial-gradient(ellipse at 40% 40%, #FF5A36 0%, #E8392A 45%, #B8221A 100%)", overflow: "hidden" }}>
    <AbsoluteFill
      style={{
        backgroundImage: "linear-gradient(rgba(0,0,0,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.07) 1px, transparent 1px)",
        backgroundSize: "96px 96px",
      }}
    />
    {children}
  </AbsoluteFill>
);

/**
 * A light leak over a cut: warm light that blooms across the frame and
 * retracts, as on film when light gets past the gate. Remotion's own
 * lightLeak() effect (WebGL - render with --gl=angle), screened over the
 * picture so it only ever adds light.
 */
export const LightLeak: React.FC<{ seed?: number; hueShift?: number; strength?: number }> = ({ seed = 0, hueShift = 0, strength = 0.85 }) => {
  const frame = useCurrentFrame();
  const { durationInFrames, width, height } = useVideoConfig();
  const sequenceFrames = useSequenceLength(durationInFrames);
  const progress = Math.max(0, Math.min(1, frame / Math.max(1, sequenceFrames - 1)));
  // From one corner, the way light gets past a camera's gate: a wash over
  // the whole frame read as a filter, not as light.
  const corners = ["0% 0%", "100% 0%", "100% 100%", "0% 100%"];
  const corner = corners[seed % corners.length];
  const mask = `radial-gradient(ellipse 90% 110% at ${corner}, black 0%, rgba(0,0,0,0.55) 35%, transparent 75%)`;
  return (
    <AbsoluteFill style={{ mixBlendMode: "screen", opacity: strength, pointerEvents: "none", WebkitMaskImage: mask, maskImage: mask }}>
      <Solid width={width} height={height} color="black" effects={[lightLeak({ seed, hueShift, progress })]} />
    </AbsoluteFill>
  );
};
