import React from "react";
import * as THREE from "three";

/** A language as an object: a glossy orb in its colour, glowing from inside.
 *  `life` 1 is lit, 0 is grey and dull - a language the dictation dropped. */
export const Orb: React.FC<{ color: string; position: [number, number, number]; scale: number; life: number; radius?: number }> = ({
  color,
  position,
  scale,
  life,
  radius = 0.42,
}) => {
  const lit = new THREE.Color(color);
  const grey = new THREE.Color("#5c5a61");
  const c = grey.clone().lerp(lit, life);
  if (scale <= 0.001) return null;
  return (
    <mesh position={position} scale={scale}>
      <sphereGeometry args={[radius, 64, 64]} />
      <meshPhysicalMaterial color={c} roughness={0.16 + (1 - life) * 0.4} metalness={0.05} clearcoat={1} clearcoatRoughness={0.08} emissive={lit} emissiveIntensity={0.55 * life} />
    </mesh>
  );
};

/** A flash of white light that swells and fades, for a merge. */
export const Burst: React.FC<{ t: number; at: number; position: [number, number, number] }> = ({ t, at, position }) => {
  const d = t - at;
  const length = 0.38;
  if (d < 0 || d > length) return null;
  const s = 0.15 + Math.sqrt(d / length) * 1.5;
  const o = Math.pow(1 - d / length, 2);
  return (
    <mesh position={position} scale={s}>
      <sphereGeometry args={[1, 32, 32]} />
      <meshBasicMaterial color={[4, 3.4, 3]} transparent opacity={o * 0.6} toneMapped={false} depthWrite={false} />
    </mesh>
  );
};
