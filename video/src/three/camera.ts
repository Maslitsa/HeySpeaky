import * as THREE from "three";
import { clamp } from "../theme";

export const FOV = 30;
export const ASPECT = 1920 / 1080;

export type Shot = { pos: [number, number, number]; target: [number, number, number] };

const easeInOut = (p: number) => {
  p = clamp(p);
  return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
};

export type Key = { at: number; angle: number; dist: number; height: number; targetY: number; targetX?: number };

/** A camera that glides between keys: an orbit angle in degrees, a distance,
 *  a height and where it looks. Pure function of time. */
export const cameraAt = (t: number, keys: Key[]): Shot => {
  let a = keys[0];
  let b = keys[keys.length - 1];
  for (let i = 0; i < keys.length - 1; i++) {
    if (t >= keys[i].at && t <= keys[i + 1].at) {
      a = keys[i];
      b = keys[i + 1];
      break;
    }
  }
  const span = Math.max(0.001, b.at - a.at);
  const p = t <= keys[0].at ? 0 : t >= keys[keys.length - 1].at ? 1 : easeInOut((t - a.at) / span);
  const mix = (x: number, y: number) => x + (y - x) * p;
  const angle = (mix(a.angle, b.angle) * Math.PI) / 180;
  const dist = mix(a.dist, b.dist);
  const tx = mix(a.targetX ?? 0, b.targetX ?? 0);
  const ty = mix(a.targetY, b.targetY);
  return {
    pos: [tx + Math.sin(angle) * dist, mix(a.height, b.height), Math.cos(angle) * dist],
    target: [tx, ty, 0],
  };
};

/** The camera as three.js sees it, for rotation and for projecting 3D
 *  points to the screen so HTML can sit on them. */
export const cameraObject = (shot: Shot) => {
  const cam = new THREE.PerspectiveCamera(FOV, ASPECT, 0.1, 100);
  cam.position.set(...shot.pos);
  cam.lookAt(new THREE.Vector3(...shot.target));
  cam.updateMatrixWorld(true);
  cam.updateProjectionMatrix();
  return cam;
};

export const project = (shot: Shot, point: [number, number, number], width = 1920, height = 1080) => {
  const cam = cameraObject(shot);
  const v = new THREE.Vector3(...point).project(cam);
  return { x: ((v.x + 1) / 2) * width, y: ((1 - v.y) / 2) * height, depth: v.z };
};
