import React, { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

export const GALAXY_CENTRE: [number, number, number] = [0, 4.6, -0.6];

type Star = { r: number; a: number; h: number; colour: THREE.Color; size: number };

/** Where orb `i` of the galaxy is at time `t`: a slow, tilted ring. */
export const starAt = (star: Star, t: number): [number, number, number] => {
  const a = star.a + t * 0.22;
  const x = Math.cos(a) * star.r;
  const z = Math.sin(a) * star.r;
  const tilt = 0.38;
  const y = star.h + z * Math.sin(tilt);
  return [GALAXY_CENTRE[0] + x, GALAXY_CENTRE[1] + y, GALAXY_CENTRE[2] + z * Math.cos(tilt)];
};

export const makeStars = (count: number, palette: string[]): Star[] => {
  let s = 4242;
  const rnd = () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
  const out: Star[] = [];
  for (let i = 0; i < count; i++) {
    out.push({ r: 2.2 + rnd() * 2.6, a: rnd() * Math.PI * 2, h: (rnd() - 0.5) * 1.5, colour: new THREE.Color(palette[i % palette.length]), size: 0.1 + rnd() * 0.09 });
  }
  return out;
};

/**
 * Every language the app knows, one glossy orb each, drawn as one
 * instanced mesh. `shown(i)` is how far orb i has appeared, 0 to 1, so the
 * galaxy can fill as the counter climbs.
 */
export const Galaxy: React.FC<{ t: number; stars: Star[]; shown: (i: number) => number; dim: number }> = ({ t, stars, shown, dim }) => {
  const ref = useRef<THREE.InstancedMesh>(null);
  const temp = useMemo(() => new THREE.Object3D(), []);
  const grey = useMemo(() => new THREE.Color("#3a3840"), []);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    stars.forEach((star, i) => {
      const p = starAt(star, t);
      const s = Math.max(0.0001, star.size * shown(i));
      temp.position.set(p[0], p[1], p[2]);
      temp.scale.setScalar(s);
      temp.updateMatrix();
      mesh.setMatrixAt(i, temp.matrix);
      mesh.setColorAt(i, star.colour.clone().lerp(grey, dim));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  });
  return (
    <instancedMesh ref={ref} args={[undefined, undefined, stars.length]} frustumCulled={false}>
      <sphereGeometry args={[1, 24, 24]} />
      <meshPhysicalMaterial roughness={0.2} metalness={0.05} clearcoat={1} clearcoatRoughness={0.1} emissive="#ffffff" emissiveIntensity={0.08} />
    </instancedMesh>
  );
};
