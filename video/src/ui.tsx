import React, { useEffect, useState } from "react";
import { AbsoluteFill, continueRender, delayRender, spring, useCurrentFrame } from "remotion";
import { fontsReady, INTER, SERIF } from "./fonts";
import { C, clamp, FPS, hexA, LANG, Lang } from "./theme";

/** Seconds into the film, inside a scene that began at `start`. */
export const useT = (start: number) => start + useCurrentFrame() / FPS;

/** 0 before `at`, then a spring to 1. */
export const springAt = (t: number, at: number, config: { damping?: number; mass?: number; stiffness?: number } = {}) =>
  t < at ? 0 : spring({ frame: (t - at) * FPS, fps: FPS, config: { damping: 15, mass: 0.7, stiffness: 160, ...config } });

/** 0 before `at`, 1 after `at + length`, eased out in between. */
export const easeAt = (t: number, at: number, length = 0.4) => {
  const p = clamp((t - at) / length);
  return 1 - Math.pow(1 - p, 3);
};

export const easeInOut = (p: number) => {
  p = clamp(p);
  return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
};

// -- type ---------------------------------------------------------------------

export const bold = (size: number, color: string = C.ink, weight = 800): React.CSSProperties => ({
  fontFamily: INTER,
  fontWeight: weight,
  fontSize: size,
  color,
  letterSpacing: -size * 0.03,
  lineHeight: 1.05,
});

export const accent = (size: number, color: string = C.red): React.CSSProperties => ({
  fontFamily: SERIF,
  fontStyle: "italic",
  fontWeight: 400,
  fontSize: size,
  color,
  letterSpacing: -size * 0.01,
  lineHeight: 1.0,
});

/** A word that arrives when it is said: up, sharp and out of a blur. */
export const Reveal: React.FC<{ t: number; at: number; style?: React.CSSProperties; children: React.ReactNode; rise?: number }> = ({
  t,
  at,
  style,
  children,
  rise = 46,
}) => {
  const p = springAt(t, at, { damping: 13, mass: 0.6, stiffness: 190 });
  return (
    <span
      style={{
        display: "inline-block",
        opacity: clamp(p * 1.4),
        transform: `translateY(${(1 - p) * rise}px) scale(${0.9 + 0.1 * p})`,
        filter: `blur(${(1 - clamp(p)) * 10}px)`,
        whiteSpace: "pre",
        ...style,
      }}
    >
      {children}
    </span>
  );
};

// -- backgrounds --------------------------------------------------------------

// Soft colour far behind, and small glossy beads drifting nearer: depth, so
// the page never reads as a flat slide. One colour per language.
const BEADS = [
  { x: 180, y: 820, r: 26, c: LANG.kk.color, s: 0.7 },
  { x: 1760, y: 180, r: 18, c: LANG.en.color, s: 1.1 },
  { x: 1650, y: 930, r: 34, c: LANG.ru.color, s: 0.5 },
  { x: 90, y: 260, r: 14, c: LANG.de.color, s: 1.3 },
  { x: 1150, y: 980, r: 12, c: LANG.kk.color, s: 0.9 },
  { x: 860, y: 70, r: 10, c: LANG.ru.color, s: 1.2 },
];
const HAZE = [
  { x: 260, y: 300, r: 520, c: LANG.en.color },
  { x: 1700, y: 800, r: 620, c: LANG.ru.color },
  { x: 1500, y: 160, r: 420, c: LANG.kk.color },
];

export const Paper: React.FC<{ children?: React.ReactNode; glow?: string }> = ({ children, glow }) => {
  const t = useCurrentFrame() / FPS;
  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at 50% 42%, ${glow ?? "#FFFFFF"} 0%, ${C.paper} 55%, #ECEAE4 100%)`,
      }}
    >
      {HAZE.map((h, i) => (
        <div
          key={`h${i}`}
          style={{
            position: "absolute",
            left: h.x - h.r + Math.sin(t * 0.3 + i) * 40,
            top: h.y - h.r + Math.cos(t * 0.25 + i * 2) * 30,
            width: h.r * 2,
            height: h.r * 2,
            borderRadius: "50%",
            background: `radial-gradient(circle, ${hexA(h.c, 0.09)} 0%, ${hexA(h.c, 0)} 70%)`,
          }}
        />
      ))}
      {BEADS.map((b, i) => (
        <div
          key={`b${i}`}
          style={{
            position: "absolute",
            left: b.x + Math.sin(t * 0.6 * b.s + i * 1.7) * 30,
            top: b.y + Math.cos(t * 0.5 * b.s + i) * 24 - t * 12 * b.s,
            width: b.r * 2,
            height: b.r * 2,
            borderRadius: "50%",
            background: `radial-gradient(circle at 35% 30%, #FFFFFF 0%, ${hexA(b.c, 0.85)} 35%, ${b.c} 100%)`,
            boxShadow: `0 ${b.r * 0.5}px ${b.r}px ${hexA(b.c, 0.25)}`,
            filter: b.r < 16 ? "blur(1.5px)" : undefined,
            opacity: 0.8,
          }}
        />
      ))}
      {children}
    </AbsoluteFill>
  );
};

/** Each shot arrives out of a blur and a little too close, over the last. */
export const Arrive: React.FC<{ children: React.ReactNode; length?: number }> = ({ children, length = 0.3 }) => {
  const frame = useCurrentFrame();
  const p = clamp(frame / (length * FPS));
  const e = 1 - Math.pow(1 - p, 3);
  if (p >= 1) return <AbsoluteFill>{children}</AbsoluteFill>;
  return (
    <AbsoluteFill style={{ opacity: e, transform: `scale(${1.08 - 0.08 * e})`, filter: `blur(${(1 - e) * 14}px)` }}>{children}</AbsoluteFill>
  );
};

export const Dark: React.FC<{ children?: React.ReactNode; from?: string; to?: string }> = ({ children, from = "#1D1424", to = C.mono }) => (
  <AbsoluteFill style={{ background: `radial-gradient(ellipse at 50% 45%, ${from} 0%, ${to} 70%)` }}>{children}</AbsoluteFill>
);

// -- Speaky -------------------------------------------------------------------

export type Mood = "idle" | "talking" | "listening" | "thinking" | "happy";

/** heyspeaky/glass.py mono_heights, line for line: the real pill's bars. */
export const monoHeights = (state: "listening" | "thinking", level: number, now: number, count = 8) => {
  const out: number[] = [];
  level = clamp(level);
  const middle = (count - 1) / 2;
  for (let i = 0; i < count; i++) {
    let share: number;
    if (state === "listening") {
      const drift = 0.35 * Math.sin(now * 1.7 + i * 0.9);
      const bell = Math.exp(-Math.pow((i - middle - drift) / 1.9, 2));
      const pulse = 0.5 + 0.5 * Math.sin(now * (5.3 + i * 0.7) + i * 1.9);
      share = level * bell * (0.82 + 0.18 * pulse) + 0.14 * pulse * (0.35 + 0.65 * level);
    } else {
      const wave = 0.5 + 0.5 * Math.sin(now * 2 * Math.PI * 1.6 - i * 0.75);
      share = 0.3 + 0.7 * wave;
    }
    out.push(clamp(share));
  }
  return out;
};

/**
 * The Mono pill with eyes. The capsule is the app's own - 108 by 58, its
 * black, its eight bars - and the bars are its mouth: red while it listens
 * or talks, a blue wave while it thinks, grey while it waits.
 */
export const Speaky: React.FC<{
  width: number;
  mood: Mood;
  t: number;
  level?: number;
  blink?: number;
  wink?: number;
  look?: [number, number];
  squash?: number;
  eyeScale?: number;
  dark?: boolean;
  style?: React.CSSProperties;
}> = ({ width, mood, t, level = 0, blink = 0, wink = 0, look = [0, 0], squash = 0, eyeScale = 1, dark = true, style }) => {
  const w = width;
  const h = w / 1.862;
  const room = h * 0.42;
  const top = room;
  const cx = w / 2;
  const cy = top + h / 2;
  const still = mood === "idle" || mood === "happy";
  const heights = monoHeights(mood === "thinking" ? "thinking" : "listening", still ? 0.02 : level, t, 8);
  const k = h / 58;
  const barW = 4.6 * k;
  const pitch = 9.4 * k;
  const minH = 8.0 * k;
  const maxH = 26 * k;
  const barColor = mood === "thinking" ? C.blueLit : still ? "#5B5560" : C.red;
  const glow = mood === "thinking" ? C.blue : still ? "transparent" : C.red;
  const first = cx - pitch * 3.5;
  const id = `s${Math.round(w)}`;

  const r = h * 0.27 * eyeScale;
  const eyes = [cx - w * 0.2, cx + w * 0.2];
  const eyeY = top + h * 0.04;
  const blinkFor = (side: number) => clamp(blink + (side === 1 ? wink : 0));

  return (
    <svg
      width={w}
      height={h + room + h * 0.3}
      viewBox={`0 0 ${w} ${h + room + h * 0.3}`}
      style={{
        overflow: "visible",
        transform: `scale(${1 + squash * 0.14}, ${1 - squash * 0.14})`,
        transformOrigin: "50% 85%",
        ...style,
      }}
    >
      <defs>
        <filter id={`${id}glow`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation={2.6 * k} />
        </filter>
        <filter id={`${id}soft`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation={h * 0.09} />
        </filter>
        <linearGradient id={`${id}sheen`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFFFFF" stopOpacity="0.13" />
          <stop offset="0.45" stopColor="#FFFFFF" stopOpacity="0" />
        </linearGradient>
      </defs>
      {dark ? (
        // On the dark stage it stands in its own light: a red pool on the
        // floor, and a rim so the black capsule never melts into the black.
        <ellipse cx={cx} cy={top + h * 1.14} rx={w * 0.55} ry={h * 0.16} fill={mood === "thinking" ? "rgba(40,124,226,0.45)" : "rgba(255,74,43,0.42)"} filter={`url(#${id}soft)`} />
      ) : (
        <ellipse cx={cx} cy={top + h * 1.12} rx={w * 0.4} ry={h * 0.1} fill="rgba(20,10,20,0.22)" filter={`url(#${id}soft)`} />
      )}
      <rect x={0} y={top} width={w} height={h} rx={h / 2} fill={C.mono} stroke={dark ? "#3B3442" : "none"} strokeWidth={dark ? Math.max(1.5, h * 0.018) : 0} />
      <rect x={h * 0.06} y={top + h * 0.04} width={w - h * 0.12} height={h * 0.9} rx={h * 0.45} fill={`url(#${id}sheen)`} />
      <g filter={`url(#${id}glow)`} opacity={0.55}>
        {heights.map((s, i) => {
          const bh = minH + (maxH - minH) * s;
          return <rect key={i} x={first + i * pitch - barW / 2} y={cy - bh / 2} width={barW} height={bh} rx={barW / 2} fill={glow} />;
        })}
      </g>
      {heights.map((s, i) => {
        const bh = minH + (maxH - minH) * s;
        return <rect key={i} x={first + i * pitch - barW / 2} y={cy - bh / 2} width={barW} height={bh} rx={barW / 2} fill={barColor} />;
      })}
      {eyes.map((ex, side) => {
        const shut = blinkFor(side);
        if (mood === "happy" && shut < 0.5) {
          // Smiling eyes: closed arcs, the way a pleased face squints.
          return (
            <g key={side}>
              <circle cx={ex} cy={eyeY} r={r} fill="#FFFFFF" stroke={C.mono} strokeWidth={h * 0.05} />
              <path
                d={`M ${ex - r * 0.55} ${eyeY + r * 0.18} Q ${ex} ${eyeY - r * 0.6} ${ex + r * 0.55} ${eyeY + r * 0.18}`}
                stroke={C.mono}
                strokeWidth={h * 0.07}
                strokeLinecap="round"
                fill="none"
              />
            </g>
          );
        }
        const ry = r * (1 - shut * 0.92);
        return (
          <g key={side}>
            <ellipse cx={ex} cy={eyeY} rx={r} ry={ry} fill="#FFFFFF" stroke={C.mono} strokeWidth={h * 0.05} />
            {shut < 0.6 && (
              <circle
                cx={ex + look[0] * r * 0.38}
                cy={eyeY + look[1] * r * 0.38 * (1 - shut)}
                r={r * 0.46 * (1 - shut * 0.5)}
                fill={C.mono}
              />
            )}
            {shut < 0.6 && <circle cx={ex + look[0] * r * 0.38 + r * 0.16} cy={eyeY + look[1] * r * 0.3 - r * 0.16} r={r * 0.12} fill="#FFFFFF" />}
          </g>
        );
      })}
    </svg>
  );
};

/** A blink, 0 to 1 and back, around `at`. */
export const blinkAt = (t: number, at: number, length = 0.14) => {
  const d = Math.abs(t - at);
  return d > length / 2 ? 0 : 1 - d / (length / 2);
};

// -- keys -----------------------------------------------------------------------

/** A keycap seen from the front: its top drops into its lip when pressed. */
export const Keycap: React.FC<{ label: string; size: number; press: number; style?: React.CSSProperties }> = ({ label, size, press, style }) => {
  const w = size * (label.length > 3 ? 1.3 : 1.05);
  const h = size * 0.8;
  const lip = size * 0.1;
  const drop = lip * 0.8 * press;
  const radius = size * 0.17;
  return (
    <div style={{ position: "relative", width: w, height: h + lip, ...style }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          top: lip,
          width: w,
          height: h,
          borderRadius: radius,
          background: "#CBC9C2",
          boxShadow: `0 ${size * 0.14 * (1 - press * 0.6)}px ${size * 0.24}px rgba(30,20,10,${0.2 - press * 0.08})`,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 0,
          top: drop,
          width: w,
          height: h,
          borderRadius: radius,
          background: press > 0.5 ? "linear-gradient(#EDECE8, #E2E1DC)" : "linear-gradient(#FFFFFF, #F2F1ED)",
          border: `${Math.max(2, size * 0.012)}px solid #D9D7D0`,
          boxSizing: "border-box",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: INTER,
          fontWeight: 700,
          fontSize: size * 0.27,
          color: C.ink,
        }}
      >
        {label}
      </div>
    </div>
  );
};

// -- chips, windows, marks ----------------------------------------------------

export const Chip: React.FC<{ lang?: Lang; name?: string; color?: string; ink?: string; size?: number; strong?: boolean; style?: React.CSSProperties }> = ({
  lang,
  name,
  color,
  ink,
  size = 34,
  strong = false,
  style,
}) => {
  const c = lang ? LANG[lang].color : color ?? C.grey;
  const k = lang ? LANG[lang].ink : ink ?? C.ink;
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: size * 0.36,
        padding: `${size * 0.26}px ${size * 0.62}px ${size * 0.26}px ${size * 0.46}px`,
        borderRadius: 999,
        background: hexA(c, strong ? 0.24 : 0.15),
        color: k,
        fontFamily: INTER,
        fontWeight: 600,
        fontSize: size,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      <span style={{ width: size * 0.36, height: size * 0.36, borderRadius: "50%", background: c, flex: "none" }} />
      {name ?? (lang ? LANG[lang].name : "")}
    </div>
  );
};

export const NotesWindow: React.FC<{ x: number; y: number; w: number; h: number; style?: React.CSSProperties; children?: React.ReactNode }> = ({
  x,
  y,
  w,
  h,
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
      background: "#FFFFFF",
      borderRadius: 24,
      boxShadow: "0 30px 80px rgba(40,30,20,0.14), 0 2px 0 rgba(0,0,0,0.04)",
      border: "1px solid #E6E4DE",
      overflow: "hidden",
      ...style,
    }}
  >
    <div style={{ height: 64, borderBottom: "1px solid #EEEDE8", display: "flex", alignItems: "center", padding: "0 28px", justifyContent: "space-between" }}>
      <span style={{ fontFamily: INTER, fontWeight: 500, fontSize: 24, color: C.grey }}>Notes</span>
      <svg width="110" height="20" viewBox="0 0 110 20">
        <line x1="4" y1="10" x2="22" y2="10" stroke={C.grey} strokeWidth="2" />
        <rect x="48" y="2" width="16" height="16" fill="none" stroke={C.grey} strokeWidth="2" />
        <line x1="90" y1="2" x2="106" y2="18" stroke={C.grey} strokeWidth="2" />
        <line x1="90" y1="18" x2="106" y2="2" stroke={C.grey} strokeWidth="2" />
      </svg>
    </div>
    {children}
  </div>
);

/** A spelling checker's red line, drawn left to right as `share` grows. */
export const Squiggle: React.FC<{ width: number; share: number; color?: string; style?: React.CSSProperties }> = ({ width, share, color = "#E23C34", style }) => {
  const step = 9;
  let d = "M 0 6";
  for (let x = 0; x < width; x += step) d += ` Q ${x + step / 2} ${(x / step) % 2 ? 12 : 0} ${x + step} 6`;
  return (
    <svg width={width} height={14} style={{ overflow: "visible", ...style }}>
      <path d={d} stroke={color} strokeWidth={3} fill="none" strokeDasharray={width * 1.6} strokeDashoffset={width * 1.6 * (1 - clamp(share))} strokeLinecap="round" />
    </svg>
  );
};

// -- measuring words ----------------------------------------------------------

export type Placed = { x: number; y: number; w: number };

/**
 * Where each word sits when the words flow into `maxWidth`, measured with
 * the real font once it has loaded. The render waits for it.
 */
export const useFlow = (words: string[], font: string, maxWidth: number, lineHeight: number): Placed[] | null => {
  const [handle] = useState(() => delayRender("measuring words"));
  const [placed, setPlaced] = useState<Placed[] | null>(null);
  useEffect(() => {
    let alive = true;
    fontsReady.then(() => {
      const ctx = document.createElement("canvas").getContext("2d")!;
      ctx.font = font;
      const space = ctx.measureText(" ").width;
      let x = 0;
      let y = 0;
      const out: Placed[] = [];
      for (const word of words) {
        const w = ctx.measureText(word).width;
        if (x > 0 && x + w > maxWidth) {
          x = 0;
          y += lineHeight;
        }
        out.push({ x, y, w });
        x += w + space;
      }
      if (alive) setPlaced(out);
      continueRender(handle);
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return placed;
};

/** A small burst of coloured dots that fall away. */
export const Confetti: React.FC<{ t: number; at: number; x: number; y: number; count?: number; seed?: number }> = ({ t, at, x, y, count = 30, seed = 1 }) => {
  if (t < at || t > at + 1.6) return null;
  const colours = [LANG.en.color, LANG.de.color, LANG.ru.color, LANG.kk.color];
  const dt = t - at;
  const pieces = [];
  for (let i = 0; i < count; i++) {
    const a = ((i * 137.5 + seed * 31) % 360) * (Math.PI / 180);
    const speed = 520 + ((i * 53 + seed * 17) % 380);
    const px = x + Math.cos(a) * speed * dt;
    const py = y + Math.sin(a) * speed * dt * 0.8 + 900 * dt * dt;
    const size = 10 + ((i * 7) % 14);
    pieces.push(
      <div
        key={i}
        style={{
          position: "absolute",
          left: px,
          top: py,
          width: size,
          height: size * (i % 3 === 0 ? 1 : 0.45),
          borderRadius: i % 2 ? "50%" : 3,
          background: colours[i % 4],
          opacity: clamp(1.6 - dt * 1.1),
          transform: `rotate(${dt * 400 + i * 40}deg)`,
        }}
      />,
    );
  }
  return <>{pieces}</>;
};
