import React from "react";
import { HEAVY, INTER } from "./fonts";
import { Palette } from "./three/look";
import { clamp } from "./theme";

/** A line revealed through a mask: it rises into place from behind an edge
 *  and leaves the same way. The edge has room for descenders - a y or a ң
 *  must not be clipped. */
export const Mask: React.FC<{ t: number; at: number; out?: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ t, at, out, children, style }) => {
  const pIn = 1 - Math.pow(1 - clamp((t - at) / 0.55), 5);
  const pOut = out === undefined ? 0 : Math.pow(clamp((t - out) / 0.32), 3);
  if (t < at - 0.02) return <span style={{ display: "inline-block", ...style, visibility: "hidden" }}>{children}</span>;
  return (
    <span style={{ display: "inline-block", overflow: "hidden", verticalAlign: "bottom", paddingBottom: "0.24em", marginBottom: "-0.24em", paddingTop: "0.06em", marginTop: "-0.06em" }}>
      <span style={{ display: "inline-block", transform: `translateY(${(1 - pIn) * 105 - pOut * 105}%)`, ...style }}>{children}</span>
    </span>
  );
};

/** The heavy headline face: in the accent, in metal, or in ink. */
export const big = (size: number, p: Palette, kind: "accent" | "metal" | "ink"): React.CSSProperties => {
  const base: React.CSSProperties = { fontFamily: HEAVY, fontSize: size, lineHeight: 0.9, letterSpacing: -size * 0.025, textTransform: "uppercase" };
  if (kind === "accent") return { ...base, color: p.accent, textShadow: p.accentGlow };
  if (kind === "metal")
    return {
      ...base,
      background: "linear-gradient(180deg, #FFFFFF 0%, #ECECF1 38%, #9C9CA6 50%, #E4E4EA 62%, #FFFFFF 100%)",
      WebkitBackgroundClip: "text",
      backgroundClip: "text",
      color: "transparent",
      filter: "drop-shadow(0 8px 30px rgba(0,0,0,0.6))",
    };
  return { ...base, color: p.ink };
};

export const line = (size: number, p: Palette, weight = 700): React.CSSProperties => ({
  fontFamily: INTER,
  fontWeight: weight,
  fontSize: size,
  color: p.ink,
  letterSpacing: -size * 0.02,
  lineHeight: 1.1,
});

/** A small label with a coloured dot, placed on a point of the 3D world. */
export const Tag: React.FC<{ x: number; y: number; text: string; color: string; alpha: number; p: Palette; size?: number; align?: "center" | "right" }> = ({
  x,
  y,
  text,
  color,
  alpha,
  p,
  size = 26,
  align = "center",
}) =>
  alpha <= 0.01 ? null : (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: align === "center" ? "translate(-50%, 0)" : "translate(-100%, -50%)",
        opacity: alpha,
        display: "flex",
        alignItems: "center",
        gap: size * 0.4,
        fontFamily: INTER,
        fontWeight: 600,
        fontSize: size,
        color: p.ink,
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ width: size * 0.38, height: size * 0.38, borderRadius: "50%", background: color, boxShadow: `0 0 ${size * 0.6}px ${color}` }} />
      {text}
    </div>
  );
