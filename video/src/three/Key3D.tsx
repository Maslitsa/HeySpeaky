import React, { useEffect, useState } from "react";
import * as THREE from "three";
import { RoundedBox } from "@react-three/drei";
import { continueRender, delayRender } from "remotion";
import { fontsReady, INTER } from "../fonts";

/** A key's label drawn into a texture, so it lies on the keycap in true
 *  perspective. Waits for the font: a label drawn before Inter loads comes
 *  out in a fallback face. */
const useLabel = (text: string) => {
  const [handle] = useState(() => delayRender(`key label ${text}`));
  const [texture, setTexture] = useState<THREE.CanvasTexture | null>(null);
  useEffect(() => {
    let alive = true;
    fontsReady.then(() => {
      const c = document.createElement("canvas");
      c.width = 512;
      c.height = 256;
      const g = c.getContext("2d")!;
      g.clearRect(0, 0, 512, 256);
      g.fillStyle = "#ffffff";
      g.font = `700 112px ${INTER}`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(text, 256, 132);
      const tex = new THREE.CanvasTexture(c);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 8;
      if (alive) setTexture(tex);
      continueRender(handle);
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return texture;
};

const EMBER = new THREE.Color("#ff4a2b");

/**
 * A dark glossy keycap. `drop` runs 0 to 1 as it falls into place from
 * above, `press` 0 to 1 as it goes down - and when it is down, red light
 * leaks out from under it, the way the pill glows while it listens.
 * `sink` takes it down through the floor.
 */
export const Key3D: React.FC<{ label: string; position: [number, number, number]; width?: number; drop: number; press: number; sink?: number; rotation?: number }> = ({
  label,
  position,
  width = 1,
  drop,
  press,
  sink = 0,
  rotation = 0,
}) => {
  const texture = useLabel(label);
  if (drop <= 0.001) return null;
  const depth = 0.92;
  const capH = 0.34;
  const fall = (1 - drop) * 3.2;
  const y = position[1] + fall - sink * 0.9;
  const capY = 0.1 + capH / 2 + 0.03 - press * 0.08;
  return (
    <group position={[position[0], y, position[2]]} rotation-y={rotation}>
      <RoundedBox args={[width + 0.1, 0.12, depth + 0.1]} radius={0.05} smoothness={4} position={[0, 0.06, 0]}>
        <meshStandardMaterial color="#050407" emissive={EMBER} emissiveIntensity={press * 3.2} toneMapped={false} roughness={0.6} />
      </RoundedBox>
      <RoundedBox args={[width, capH, depth]} radius={0.09} smoothness={5} position={[0, capY, 0]}>
        <meshPhysicalMaterial color="#17141c" roughness={0.32} metalness={0.2} clearcoat={0.8} clearcoatRoughness={0.2} />
      </RoundedBox>
      {texture && (
        <mesh rotation-x={-Math.PI / 2} position={[0, capY + capH / 2 + 0.003, 0.02]}>
          <planeGeometry args={[width * 0.92, width * 0.46]} />
          <meshStandardMaterial
            map={texture}
            transparent
            color={press > 0.5 ? "#ffd9cf" : "#d8d5de"}
            emissive={press > 0.5 ? "#ffb8a6" : "#ffffff"}
            emissiveMap={texture}
            emissiveIntensity={press > 0.5 ? 2.6 : 1.1}
            toneMapped={press <= 0.5}
            depthWrite={false}
          />
        </mesh>
      )}
    </group>
  );
};
