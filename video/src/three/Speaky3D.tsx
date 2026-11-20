import React from "react";
import { monoHeights } from "../ui";

const RED = "#ff2a35";
const BLUE = "#3d8bff";
const IDLE = "#6b6573";

export type Mood3D = "idle" | "talking" | "listening" | "thinking" | "happy";

// The Mono pill as an object: a glossy black capsule 108 by 58, its eight
// bars - moved by the app's own formula - lit from inside, and two soft
// glowing eyes above them, the way a small robot has a face on a screen.
const R = 0.58;
const LEN = 1.0;

export const Speaky3D: React.FC<{
  t: number;
  mood: Mood3D;
  level?: number;
  position?: [number, number, number];
  scale?: number;
  squash?: number;
  tilt?: number;
  turn?: number;
  eyes?: number;
  blink?: number;
  look?: [number, number];
}> = ({ t, mood, level = 0, position = [0, R, 0], scale = 1, squash = 0, tilt = 0, turn = 0, eyes = 1, blink = 0, look = [0, 0] }) => {
  const still = mood === "idle" || mood === "happy";
  const heights = monoHeights(mood === "thinking" ? "thinking" : "listening", still ? 0.03 : level, t, 8);
  const bar = mood === "thinking" ? BLUE : still ? IDLE : RED;
  const glow = mood === "thinking" ? 5 : still ? 0.6 : 5.5;
  const pitch = 0.112;
  const sx = scale * (1 + squash * 0.16);
  const sy = scale * (1 - squash * 0.16);
  const open = Math.max(0.06, eyes * (1 - blink));
  const happy = mood === "happy";
  return (
    <group position={position} rotation={[tilt, turn, 0]} scale={[sx, sy, scale]}>
      <mesh rotation-z={Math.PI / 2}>
        <capsuleGeometry args={[R, LEN, 24, 64]} />
        <meshPhysicalMaterial color="#0a080d" roughness={0.2} metalness={0.35} clearcoat={1} clearcoatRoughness={0.05} reflectivity={0.6} />
      </mesh>
      {heights.map((s, i) => {
        const h = 0.1 + 0.3 * s;
        return (
          <mesh key={i} position={[(i - 3.5) * pitch, -0.07, 0.578 - Math.max(0, Math.abs(-0.07) - 0) * 0]}>
            <capsuleGeometry args={[0.032, Math.max(0.001, h - 0.064), 6, 16]} />
            <meshStandardMaterial color={bar} emissive={bar} emissiveIntensity={glow} toneMapped={false} />
          </mesh>
        );
      })}
      {[-1, 1].map((side) => (
        <group key={side} position={[side * 0.27 + look[0] * 0.05, 0.27 + look[1] * 0.04, 0.522]} rotation-x={-0.48}>
          {happy ? (
            <mesh rotation-z={Math.PI} position={[0, -0.02, 0]}>
              <torusGeometry args={[0.07, 0.022, 12, 32, Math.PI]} />
              <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={2.6} toneMapped={false} />
            </mesh>
          ) : (
            <mesh scale={[1, open, 1]}>
              <capsuleGeometry args={[0.055, 0.1, 8, 24]} />
              <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={2.6} toneMapped={false} />
            </mesh>
          )}
        </group>
      ))}
    </group>
  );
};

export const PILL_RADIUS = R;
