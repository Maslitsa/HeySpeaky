import React, { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useThree } from "@react-three/fiber";
import { Environment, Lightformer, MeshReflectorMaterial } from "@react-three/drei";
import { Bloom, EffectComposer, Noise, ToneMapping, Vignette } from "@react-three/postprocessing";
import { BlendFunction, ToneMappingMode } from "postprocessing";
import { cameraObject, FOV, Shot } from "./camera";
import { Palette } from "./look";

/**
 * The effects pass, sized before the frame is drawn. The composer is made
 * while the canvas is still the browser's default 300 by 150, and resizes
 * itself in an effect - which runs after Remotion has already drawn the
 * frame, so every first frame came out squashed into that shape: round
 * things wide, everything shifted up. A layout effect runs first.
 */
const SizedComposer: React.FC<{ children: React.ReactElement | React.ReactElement[] }> = ({ children }) => {
  const ref = useRef<{ setSize: (w: number, h: number) => void } | null>(null);
  const { size } = useThree();
  useLayoutEffect(() => {
    ref.current?.setSize(size.width, size.height);
  });
  return (
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    <EffectComposer ref={ref as any} multisampling={4}>
      {children}
    </EffectComposer>
  );
};

/**
 * The camera: the canvas's own default camera, moved in a layout effect so
 * it is in place before Remotion asks three.js to draw the frame. A second
 * camera made default (drei's PerspectiveCamera) arrives one render late,
 * and the effects pass had already drawn the first frame through the old
 * one - wider, lower, from somewhere else.
 */
export const Camera: React.FC<{ shot: Shot }> = ({ shot }) => {
  const { camera, size } = useThree();
  useLayoutEffect(() => {
    const cam = camera as THREE.PerspectiveCamera;
    const want = cameraObject(shot);
    cam.fov = FOV;
    cam.near = 0.1;
    cam.far = 100;
    cam.aspect = size.width / size.height;
    cam.position.copy(want.position);
    cam.quaternion.copy(want.quaternion);
    cam.updateProjectionMatrix();
    cam.updateMatrixWorld(true);
  });
  return null;
};

/** Studio light that only reflections see: a soft box overhead, two strips
 *  either side, a warm card behind. Made here, nothing downloaded. */
const Studio: React.FC<{ p: Palette }> = ({ p }) => (
  <Environment resolution={256} frames={1}>
    <color attach="background" args={["#000000"]} />
    <Lightformer form="rect" intensity={1.5} position={[0, 6, -2.2]} rotation-x={Math.PI / 2} scale={[5, 1.4, 1]} color="#ffffff" />
    <Lightformer form="rect" intensity={1.1} position={[-6, 2, 1]} rotation-y={Math.PI / 2} scale={[0.8, 6, 1]} color="#ffffff" />
    <Lightformer form="rect" intensity={1.1} position={[6, 2, 1]} rotation-y={-Math.PI / 2} scale={[0.8, 6, 1]} color="#ffffff" />
    <Lightformer form="ring" intensity={1.2} position={[0, 2, -6]} scale={3} color={p.envWarm} />
    <Lightformer form="rect" intensity={0.5} position={[0, -2.5, 6]} rotation-x={-0.4} scale={[10, 1.2, 1]} color="#ffffff" />
  </Environment>
);

/** Motes in the air: depth you can feel, drifting slowly up. */
const Dust: React.FC<{ t: number; tint: string; count?: number }> = ({ t, tint, count = 220 }) => {
  const seeds = useMemo(() => {
    const out: number[][] = [];
    let s = 12345;
    const rnd = () => {
      s = (s * 16807) % 2147483647;
      return s / 2147483647;
    };
    for (let i = 0; i < count; i++) out.push([rnd() * 16 - 8, rnd() * 5, rnd() * 10 - 6, 0.05 + rnd() * 0.12, rnd() * 6.28]);
    return out;
  }, [count]);
  const positions = useMemo(() => new Float32Array(count * 3), [count]);
  for (let i = 0; i < count; i++) {
    const [x, y, z, speed, phase] = seeds[i];
    positions[i * 3] = x + Math.sin(t * 0.3 + phase) * 0.3;
    positions[i * 3 + 1] = ((y + t * speed) % 5) + 0.05;
    positions[i * 3 + 2] = z;
  }
  return (
    <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} count={count} array={positions} itemSize={3} needsUpdate />
      </bufferGeometry>
      <pointsMaterial size={0.025} color={tint} transparent opacity={0.6} sizeAttenuation depthWrite={false} />
    </points>
  );
};

const softDisc = () => {
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.45, "rgba(255,255,255,0.5)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 256);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
};

/**
 * A soft shadow under an object, darker and tighter the nearer it is to the
 * floor. drei's ContactShadows cannot be used: the effects pass turns the
 * renderer's auto-clear off and ContactShadows never clears its own buffer,
 * so every frame's shadow piled onto the last - the orbs drew their whole
 * path on the floor as a dark ring.
 */
export const Shadow: React.FC<{ x: number; z: number; height: number; size: number; strength: number }> = ({ x, z, height, size, strength }) => {
  const texture = useMemo(softDisc, []);
  const near = Math.max(0, 1 - height / 3);
  if (size <= 0.001 || strength * near <= 0.002) return null;
  const spread = size * (1 + height * 0.35);
  return (
    <mesh rotation-x={-Math.PI / 2} position={[x, 0.003, z]} scale={[spread, spread * 0.7, 1]}>
      <planeGeometry args={[1, 1]} />
      <meshBasicMaterial map={texture} color="#000000" transparent opacity={strength * near} depthWrite={false} toneMapped={false} />
    </mesh>
  );
};

/** A soft pool of coloured light on the floor, under whatever is lit. */
export const Pool: React.FC<{ x?: number; z?: number; size: number; color: string; strength: number }> = ({ x = 0, z = 0, size, color, strength }) => {
  const texture = useMemo(() => {
    const c = document.createElement("canvas");
    c.width = c.height = 256;
    const g = c.getContext("2d")!;
    const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    grad.addColorStop(0, "rgba(255,255,255,1)");
    grad.addColorStop(0.35, "rgba(255,255,255,0.45)");
    grad.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, 256, 256);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }, []);
  return (
    <mesh rotation-x={-Math.PI / 2} position={[x, 0.004, z]} scale={[size, size * 0.6, 1]}>
      <planeGeometry args={[1, 1]} />
      <meshBasicMaterial map={texture} color={color} transparent opacity={strength} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} />
    </mesh>
  );
};

export const World: React.FC<{ p: Palette; t: number; shot: Shot; dark: boolean; children: React.ReactNode }> = ({ p, t, shot, dark, children }) => (
  <>
    <Camera shot={shot} />
    <color attach="background" args={[p.bg]} />
    <fog attach="fog" args={[p.bg, p.fogNear, p.fogFar]} />
    <ambientLight intensity={p.ambient} />
    <directionalLight position={[2.5, 7, 5]} intensity={p.key} color="#ffffff" />
    <pointLight position={[-4.5, 2.2, -2.5]} intensity={dark ? 18 : 6} distance={14} decay={1.4} color={p.rim} />
    <pointLight position={[4.5, 2.4, -2.5]} intensity={dark ? 10 : 4} distance={14} decay={1.4} color={p.rim2} />
    <Studio p={p} />
    <mesh rotation-x={-Math.PI / 2} position={[0, 0, 0]}>
      <planeGeometry args={[80, 80]} />
      <MeshReflectorMaterial
        resolution={512}
        blur={[400, 120]}
        mixBlur={1}
        mixStrength={dark ? 3 : 1.4}
        mixContrast={1}
        roughness={dark ? 0.85 : 0.9}
        depthScale={1.1}
        minDepthThreshold={0.35}
        maxDepthThreshold={1.3}
        color={p.floor}
        metalness={dark ? 0.55 : 0.3}
        mirror={p.mirror}
      />
    </mesh>
    <Dust t={t} tint={dark ? "#ffd2c4" : "#ffffff"} />
    {children}
    <SizedComposer>
      <Bloom mipmapBlur intensity={p.bloom} luminanceThreshold={p.threshold} luminanceSmoothing={0.25} />
      <ToneMapping mode={ToneMappingMode.AGX} />
      <Vignette offset={0.32} darkness={p.vignette} />
      <Noise opacity={0.04} premultiply blendFunction={BlendFunction.SOFT_LIGHT} />
    </SizedComposer>
  </>
);
