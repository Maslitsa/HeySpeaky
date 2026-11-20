import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import code from "./code.json";
import music from "./music.json";
import { CLIP_AT, CLIP_SECONDS, CLIP_WORDS, cue, DURATION, LINES, levelAt, SPANS, VO_AT, voEnd, WHISPER_HEARD } from "./data";
import { DarkWindow, label, LightLeak, Slab } from "./dark";
import { HEAVY, INTER, MONO_FONT, SERIF } from "./fonts";
import { WithLength } from "./sequence";
import { clamp, FPS, hexA, LANG, Lang, sec } from "./theme";
import { springAt, Squiggle, useFlow } from "./ui";
import { big, line, Mask, Tag } from "./type";
import { cameraAt, Key, project, Shot } from "./three/camera";
import { Galaxy, GALAXY_CENTRE, makeStars, starAt } from "./three/Galaxy";
import { Key3D } from "./three/Key3D";
import { PALETTES } from "./three/look";
import { Orb } from "./three/Orb";
import { Mood3D, PILL_RADIUS, Speaky3D } from "./three/Speaky3D";
import { Pool, Shadow, World } from "./three/World";

// The film, in one 3D world the camera travels through. Every position,
// colour and word on screen is a function of the time - Remotion draws the
// frames out of order, in several browsers at once.

const P = PALETTES.dark;
// The track under the film, named in music.json: an ElevenLabs Music track
// here, or the stand-in scripts/music_dark.py writes.
const MUSIC = (music as unknown as { file: string | null }).file;

// -- when ---------------------------------------------------------------------

const T_WHAT = cue("hook", "what");
const T_YOUR = cue("hook", "your");
const T_ONE = cue("hook", "one");
const T_LANG = cue("hook", "language");
const T_AND = VO_AT.three;
const T_THREE = cue("three", "three");
const T_THIS = VO_AT.this;
const T_NAME = cue("this", "heyspeaky", "hey");
const MERGE = T_NAME - 0.08;
const T_HOLD = VO_AT.hold;
const T_CTRL = cue("hold", "ctrl", "control");
const T_ALT = Math.max(cue("hold", "alt", "-alt"), T_CTRL + 0.2);
const T_TALK = cue("hold", "talk");
const T_SWITCH = cue("hold", "switch");
const T_MID = cue("hold", "mid", "sentence");
const RELEASE = CLIP_AT + CLIP_SECONDS + 0.15;
const LAND = RELEASE + 1.0;
const T_LETGO = VO_AT.letgo;
const SLAB_IN = VO_AT.regular - 0.12;
const SLAB_OUT = VO_AT.names - 0.12;
const T_TEACH = cue("names", "teach");
const T_LANGS = VO_AT.langs;
const T_COUNTED = cue("langs", "languages");
const T_YOURS = cue("langs", "yours");
const T_FREE = VO_AT.free;
const T_META = VO_AT.meta;
const T_EVERY = cue("meta", "every");
const T_CODE = cue("meta", "code");
const T_CTA = VO_AT.cta;
const END = DURATION;

const FIX_TICK = T_TEACH + 1.25;
const FIXED = FIX_TICK + 0.12;

const easeOut = (p: number) => 1 - Math.pow(1 - clamp(p), 4);
const easeIn = (p: number) => Math.pow(clamp(p), 3);
const easeInOut = (p: number) => {
  p = clamp(p);
  return p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
};
const mix = (a: number, b: number, p: number) => a + (b - a) * p;
const pulse = (t: number, at: number, width = 0.07) => Math.exp(-Math.pow((t - at) / width, 2));

// -- the camera -------------------------------------------------------------------

const KEYS: Key[] = [
  { at: 0, angle: -16, dist: 12.2, height: 2.2, targetY: 1.85 },
  { at: T_ONE, angle: -6, dist: 10.8, height: 2.0, targetY: 1.75 },
  { at: T_THREE, angle: 5, dist: 10.4, height: 1.95, targetY: 1.7 },
  { at: MERGE, angle: 0, dist: 8.4, height: 1.7, targetY: 0.95 },
  { at: T_HOLD - 0.15, angle: 5, dist: 7.6, height: 1.5, targetY: 0.85 },
  { at: T_HOLD + 0.6, angle: -11, dist: 8.8, height: 2.2, targetY: 0.72, targetX: -0.95 },
  { at: CLIP_AT - 0.15, angle: -5, dist: 8.3, height: 2.0, targetY: 0.78, targetX: -0.8 },
  { at: CLIP_AT + 0.7, angle: 8, dist: 7.5, height: 1.65, targetY: 1.0, targetX: 1.65 },
  { at: RELEASE, angle: 4, dist: 7.3, height: 1.55, targetY: 1.0, targetX: 1.75 },
  { at: LAND + 0.5, angle: -1, dist: 7.6, height: 1.6, targetY: 1.0, targetX: 1.9 },
  { at: SLAB_IN, angle: -3, dist: 7.8, height: 1.6, targetY: 1.0, targetX: 1.9 },
  { at: SLAB_OUT, angle: -7, dist: 8.8, height: 2.0, targetY: 0.9, targetX: 0.45 },
  { at: T_LANGS - 0.35, angle: 3, dist: 8.4, height: 1.85, targetY: 0.95, targetX: 0.45 },
  { at: T_LANGS + 0.5, angle: -2, dist: 9.6, height: 2.7, targetY: 4.45 },
  { at: T_FREE - 0.25, angle: 9, dist: 9.0, height: 3.0, targetY: 4.6 },
  { at: T_FREE + 0.75, angle: 0, dist: 6.7, height: 1.35, targetY: 0.88 },
  { at: T_META - 0.1, angle: -6, dist: 6.5, height: 1.3, targetY: 0.88 },
  { at: T_META + 1.3, angle: 0, dist: 10.6, height: 3.1, targetY: 1.95 },
  { at: END, angle: 4, dist: 11.6, height: 3.4, targetY: 2.05 },
];

// -- the opening's three orbs ---------------------------------------------------

type OrbSpec = { lang: "kk" | "ru" | "en"; base: [number, number, number]; drops: boolean };
const HOOK_ORBS: OrbSpec[] = [
  { lang: "kk", base: [-2.35, 1.3, 0.25], drops: true },
  { lang: "ru", base: [0, 1.62, -0.7], drops: true },
  { lang: "en", base: [2.35, 1.3, 0.25], drops: false },
];
const ORB_R = 0.42;

const dropHeight = (dt: number, h: number) => {
  const fallT = 0.4;
  if (dt <= 0) return h;
  if (dt < fallT) return h * (1 - Math.pow(dt / fallT, 2));
  const u = dt - fallT;
  return Math.abs(Math.sin((u * Math.PI) / 0.24)) * h * 0.15 * Math.exp(-u * 5);
};

const hookOrb = (o: OrbSpec, i: number, t: number) => {
  const appear = springAt(t, 0.35 + i * 0.22, { damping: 11, stiffness: 150 });
  const float = Math.sin(t * 1.4 + i * 2.1) * 0.07;
  let [x, y, z] = o.base;
  y += float;
  let life = 1;
  let scale = appear;
  if (o.drops) {
    const dt = t - (T_ONE + i * 0.08);
    if (dt > 0) {
      life = 1 - clamp(dt / 0.25);
      y = ORB_R + dropHeight(dt, o.base[1] - ORB_R + float);
      x += (o.base[0] < 0 ? -1 : 0.4) * easeOut(dt / 1.2) * 0.35;
    }
    const back = T_THREE - 0.32 + i * 0.05;
    if (t > back) {
      const p = springAt(t, back, { damping: 12, stiffness: 170 });
      y = mix(ORB_R, o.base[1] + float, p);
      x = mix(x, o.base[0], p);
      life = clamp((t - back) / 0.3);
    }
  } else {
    const p = easeInOut((t - (T_ONE + 0.05)) / 0.6) * (1 - easeInOut((t - (T_AND - 0.1)) / 0.6));
    x = mix(x, 0, p);
    y = mix(y, 1.45 + float, p);
    z = mix(z, 0.9, p);
    scale *= 1 + 0.3 * p;
  }
  const fold = easeIn((t - (T_THIS - 0.25)) / (MERGE - (T_THIS - 0.25)));
  if (fold > 0) {
    const r = Math.hypot(x, z - 0.2);
    const a = Math.atan2(z - 0.2, x) + fold * Math.PI * 2.2;
    x = Math.cos(a) * r * (1 - fold);
    z = 0.2 + Math.sin(a) * r * (1 - fold);
    y = mix(y, 1.05, fold);
    scale *= 1 - 0.8 * fold;
    if (t >= MERGE) scale = 0;
  }
  return { pos: [x, y, z] as [number, number, number], scale, life };
};

// -- Speaky -----------------------------------------------------------------------

const HOME: [number, number] = [0, 0.2];
const NAMES_SPOT: [number, number] = [2.75, 0.55];

const speakyAt = (t: number) => {
  if (t < MERGE) return null;
  const hover = Math.sin(t * 1.8) * 0.04;
  const rest = PILL_RADIUS + 0.12 + hover;
  let [x, z] = HOME;
  let y = mix(1.15, rest, easeOut((t - MERGE) / 0.32));
  let scale = springAt(t, MERGE, { damping: 9, stiffness: 120, mass: 0.9 });
  let squash = pulse(t, MERGE + 0.32) * 0.8 - pulse(t, MERGE + 0.2, 0.06) * 0.35;
  const atNames = t >= SLAB_IN + 0.05 && t < T_LANGS + 0.6;
  if (atNames) {
    [x, z] = NAMES_SPOT;
    const drop = SLAB_OUT + 0.15;
    y = rest + Math.max(0, 1.6 * (1 - easeIn((t - drop) / 0.35)) * (t < drop + 0.35 ? 1 : 0));
    if (t < drop) y = rest + 1.6;
    scale = 0.85;
    squash = pulse(t, drop + 0.35) * 0.8 + pulse(t, FIXED + 0.05, 0.08) * -0.5;
    y += Math.max(0, Math.sin(clamp((t - FIXED) / 0.35) * Math.PI) * 0.35);
  }
  const hop = T_FREE + 0.45;
  if (t > hop - 0.4 && t < hop + 0.6) {
    y += Math.max(0, Math.sin(clamp((t - (hop - 0.35)) / 0.35) * Math.PI) * 0.45);
    squash += pulse(t, hop) * 0.7;
  }
  // What it is doing, and what it is listening to or saying.
  let mood: Mood3D = "idle";
  let level = 0;
  let look: [number, number] = [Math.sin(t * 1.1) * 0.3, 0];
  if (t >= T_NAME - 0.1 && t < voEnd("this") + 0.1) {
    mood = "talking";
    level = levelAt("this", t - VO_AT.this);
  } else if (t >= T_HOLD && t < T_ALT + 0.12) {
    mood = "talking";
    level = levelAt("hold", t - VO_AT.hold);
    look = [-0.8, 0.2];
  } else if (t >= T_ALT + 0.12 && t < CLIP_AT) {
    mood = "listening";
    level = 0.06;
    look = [0, 0];
  } else if (t >= CLIP_AT && t < RELEASE) {
    mood = "listening";
    level = levelAt("clip", t - CLIP_AT);
    look = [0.7, -0.1];
  } else if (t >= RELEASE && t < LAND) {
    mood = "thinking";
    look = [0.3, -0.9];
  } else if (t >= LAND && t < SLAB_IN) {
    mood = "happy";
  } else if (atNames) {
    mood = t >= FIXED ? "happy" : "idle";
    look = [-0.8, -0.2];
  } else if (t >= T_FREE && t < T_META) {
    mood = "talking";
    level = levelAt("free", t - VO_AT.free);
  } else if (t >= T_META) {
    mood = "talking";
    level = Math.max(levelAt("meta", t - VO_AT.meta), levelAt("cta", t - VO_AT.cta));
    look = [0, -0.2];
  }
  const eyes = clamp((t - (MERGE + 0.28)) / 0.14);
  const blink = Math.max(pulse(t, T_NAME + 0.95, 0.05), pulse(t, CLIP_AT + 3.3, 0.05), pulse(t, T_FREE + 1.6, 0.05), atNames ? pulse(t, SLAB_OUT + 1.1, 0.05) : 0);
  const wink = pulse(t, T_CTA + 0.25, 0.09);
  return { pos: [x, y, z] as [number, number, number], scale, squash, mood, level, look, eyes, blink, wink };
};

// -- the demo's four orbs, circling Speaky as it listens ----------------------------

const DEMO_LANGS: Lang[] = ["en", "de", "ru", "kk"];

const speakingAt = (t: number) => SPANS.findIndex(([a, b]) => t - CLIP_AT >= a && t - CLIP_AT < b);

const demoOrb = (i: number, t: number) => {
  const appear = springAt(t, CLIP_AT - 0.35 + i * 0.08, { damping: 11, stiffness: 160 });
  if (appear <= 0.001 || t > RELEASE + 0.65) return null;
  const active = speakingAt(t) === i;
  const glow = active ? 1 : t < CLIP_AT ? 0.85 : 0.45;
  const a = (i / 4) * Math.PI * 2 + t * 0.55;
  let r = 1.6;
  let y = 1.05 + Math.sin(a) * 0.62;
  let scale = appear * (active ? 1.55 : 0.85);
  const absorb = easeIn((t - RELEASE) / 0.6);
  r *= 1 - absorb;
  y = mix(y, 0.75, absorb);
  scale *= 1 - absorb;
  return { pos: [HOME[0] + Math.cos(a) * r, y, HOME[1] + Math.sin(a) * r * 0.5] as [number, number, number], scale, life: glow, active };
};

// -- the galaxy of languages ------------------------------------------------------

const STARS = makeStars(97, [LANG.en.color, LANG.de.color, LANG.ru.color, LANG.kk.color, "#e8e6ee"]);
const YOURS: Lang[] = ["kk", "ru", "de", "en"];
const galaxyGone = (t: number) => 1 - easeIn((t - (T_FREE - 0.35)) / 0.5);
const starShown = (t: number) => (i: number) => {
  if (t > T_FREE + 0.2) return 0;
  return springAt(t, T_LANGS + 0.15 + (i / 97) * Math.max(0.5, T_COUNTED - T_LANGS), { damping: 12, stiffness: 200 }) * galaxyGone(t);
};
const yoursOrb = (i: number, t: number) => {
  const p = springAt(t, T_YOURS + i * 0.12, { damping: 12, stiffness: 150 });
  if (p <= 0.001 || t > T_FREE + 0.2) return null;
  const from = starAt(STARS[i * 7], t);
  const to: [number, number, number] = [2.4, 5.6 - i * 0.74, 1.8];
  return { pos: [mix(from[0], to[0], p), mix(from[1], to[1], p), mix(from[2], to[2], p)] as [number, number, number], scale: p * galaxyGone(t) };
};

// -- 3D ------------------------------------------------------------------------------

const Scene3D: React.FC<{ t: number; shot: Shot }> = ({ t, shot }) => {
  const sp = speakyAt(t);
  const pressHold = (at: number) => (t >= at && t < RELEASE ? 1 : 0);
  const dropAt = (at: number) => easeOut((t - (at - 0.32)) / 0.28);
  const namesKeys: [string, number, number][] = [
    ["Ctrl", -1.5, T_TEACH],
    ["Alt", -0.38, T_TEACH + 0.12],
    ["Win", 0.74, T_TEACH + 0.24],
  ];
  const namesSink = easeIn((t - (T_TEACH + 0.55)) / 0.35);
  const showGalaxy = t > T_LANGS - 0.5 && t < T_FREE + 1.7;
  return (
    <World p={P} t={t} shot={shot} dark>
      {/* The opening: three languages, two dropped, all three back, folded into Speaky. */}
      {t < MERGE + 0.1 &&
        HOOK_ORBS.map((o, i) => {
          const s = hookOrb(o, i, t);
          return (
            <React.Fragment key={o.lang}>
              <Orb color={LANG[o.lang].color} position={s.pos} scale={s.scale} life={s.life} radius={ORB_R} />
              <Pool x={s.pos[0]} z={s.pos[2]} size={2.8 * s.scale} color={LANG[o.lang].color} strength={0.32 * s.life * clamp(1.6 - s.pos[1] / 2)} />
              <Shadow x={s.pos[0]} z={s.pos[2]} height={s.pos[1] - ORB_R * s.scale} size={1.1 * s.scale} strength={0.7} />
            </React.Fragment>
          );
        })}

      {/* Hold Ctrl + Alt: two keys fall into place and go down. */}
      {t > T_HOLD && t < SLAB_IN && (
        <>
          <Key3D label="Ctrl" position={[-2.4, 0, 1.0]} width={1.05} drop={dropAt(T_CTRL)} press={pressHold(T_CTRL)} rotation={0.12} />
          <Key3D label="Alt" position={[-1.28, 0, 1.0]} width={0.95} drop={dropAt(T_ALT)} press={pressHold(T_ALT)} rotation={0.12} />
          <Pool x={-1.85} z={1.0} size={3.2} color={P.pool} strength={0.45 * (t >= T_CTRL && t < RELEASE ? 1 : 0)} />
        </>
      )}

      {/* The demo: an orb for each language, the one being spoken lit. */}
      {t > CLIP_AT - 0.4 &&
        t < RELEASE + 0.7 &&
        DEMO_LANGS.map((lang, i) => {
          const s = demoOrb(i, t);
          if (!s) return null;
          return (
            <React.Fragment key={lang}>
              <Orb color={LANG[lang].color} position={s.pos} scale={s.scale} life={s.life} radius={0.22} />
              <Pool x={s.pos[0]} z={s.pos[2]} size={1.4 * s.scale} color={LANG[lang].color} strength={s.active ? 0.5 : 0.15} />
            </React.Fragment>
          );
        })}

      {/* Teach it your names: Ctrl + Alt + Win, then down through the floor. */}
      {t > SLAB_OUT && t < T_LANGS + 0.5 &&
        namesKeys.map(([name, x, at]) => (
          <Key3D key={name} label={name} position={[x, 0, 1.35]} width={name === "Ctrl" ? 1.05 : 0.95} drop={dropAt(at)} press={t >= at ? 1 : 0} sink={namesSink} />
        ))}

      {/* Ninety-seven languages, and yours. */}
      {showGalaxy && <Galaxy t={t} stars={STARS} shown={starShown(t)} dim={0.55 * easeOut((t - T_YOURS) / 0.5)} />}
      {showGalaxy &&
        YOURS.map((lang, i) => {
          const s = yoursOrb(i, t);
          if (!s) return null;
          return <Orb key={lang} color={LANG[lang].color} position={s.pos} scale={s.scale} life={1} radius={0.32} />;
        })}

      {/* Speaky, wherever it is. */}
      {sp && (
        <>
          <Speaky3D
            t={t}
            mood={sp.mood}
            level={sp.level}
            position={sp.pos}
            scale={sp.scale}
            squash={sp.squash}
            tilt={-0.06}
            turn={Math.sin(t * 0.9) * 0.12}
            eyes={sp.eyes}
            blink={Math.max(sp.blink, 0)}
            look={sp.look}
          />
          <Pool x={sp.pos[0]} z={sp.pos[2]} size={4.6 * sp.scale} color={sp.mood === "thinking" ? "#3d7bff" : P.pool} strength={0.38} />
          <Shadow x={sp.pos[0]} z={sp.pos[2]} height={Math.max(0, sp.pos[1] - PILL_RADIUS)} size={2.6 * sp.scale} strength={0.75} />
        </>
      )}
    </World>
  );
};

// -- type and HTML ----------------------------------------------------------------

const CLOUD = { x: 1010, y: 190, width: 800, size: 46, line: 66 };
const WIN = { x: 980, y: 520, w: 840, h: 440 };
const PAGE = { x: WIN.x + 48, y: WIN.y + 96, width: 760, size: 40, line: 58 };

const Overlay: React.FC<{ t: number; shot: Shot }> = ({ t, shot }) => {
  const cloud = useFlow(CLIP_WORDS.map((w) => w.said), `600 ${CLOUD.size}px ${INTER}`, CLOUD.width, CLOUD.line);
  const page = useFlow(CLIP_WORDS.map((w) => w.typed), `500 ${PAGE.size}px ${INTER}`, PAGE.width, PAGE.line);
  if (!cloud || !page) return null;
  const sp = speakyAt(t);
  const outA = T_AND - 0.12;
  const outB = T_THIS - 0.12;
  const speaking = speakingAt(t);

  return (
    <AbsoluteFill>
      {/* "What if I told you... your dictation speaks ONE language." */}
      {t < outA + 0.4 && (
        <div style={{ position: "absolute", top: 70, width: "100%", textAlign: "center" }}>
          <div style={{ ...line(40, P, 500), color: P.muted }}>
            <Mask t={t} at={T_WHAT} out={outA}>
              What if I told you…
            </Mask>
          </div>
          <div style={{ ...line(60, P), marginTop: 14 }}>
            <Mask t={t} at={T_YOUR} out={outA}>
              your dictation speaks
            </Mask>
          </div>
          <div style={{ marginTop: 12, whiteSpace: "nowrap" }}>
            <Mask t={t} at={T_ONE - 0.04} out={outA} style={big(172, P, "accent")}>
              One
            </Mask>
            <span style={{ display: "inline-block", width: 28 }} />
            <Mask t={t} at={T_LANG} out={outA} style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 104, color: P.ink }}>
              language.
            </Mask>
          </div>
        </div>
      )}
      {/* "And you speak THREE." */}
      {t >= T_AND - 0.1 && t < outB + 0.4 && (
        <div style={{ position: "absolute", top: 110, width: "100%", textAlign: "center" }}>
          <div style={line(60, P)}>
            <Mask t={t} at={T_AND} out={outB}>
              And you speak
            </Mask>
          </div>
          <div style={{ marginTop: 10 }}>
            <Mask t={t} at={T_THREE - 0.04} out={outB} style={big(240, P, "metal")}>
              Three.
            </Mask>
          </div>
        </div>
      )}
      {/* Each opening orb's language, under it. */}
      {t < MERGE &&
        HOOK_ORBS.map((o, i) => {
          const s = hookOrb(o, i, t);
          const at = project(shot, [s.pos[0], Math.max(0.05, s.pos[1] - ORB_R * s.scale - 0.22), s.pos[2]]);
          const alpha = clamp((t - (0.7 + i * 0.22)) / 0.3) * (0.3 + 0.7 * s.life) * clamp(s.scale);
          return <Tag key={o.lang} x={at.x} y={at.y} text={LANG[o.lang].name} color={LANG[o.lang].color} alpha={alpha} p={P} />;
        })}
      {/* The merge: a soft bloom of light. */}
      {t >= MERGE && t < MERGE + 0.6 && (() => {
        const at = project(shot, [0, 1.05, 0.2]);
        const d = (t - MERGE) / 0.6;
        const size = 300 + 900 * Math.sqrt(d);
        return (
          <div
            style={{
              position: "absolute",
              left: at.x - size / 2,
              top: at.y - size / 2,
              width: size,
              height: size,
              borderRadius: "50%",
              background: "radial-gradient(circle, rgba(255,246,238,0.95) 0%, rgba(255,140,100,0.55) 22%, rgba(255,74,43,0.18) 45%, rgba(255,74,43,0) 68%)",
              opacity: Math.pow(1 - d, 1.6),
              mixBlendMode: "screen",
            }}
          />
        );
      })()}
      {/* "This is HeySpeaky." */}
      {t >= T_THIS - 0.1 && t < T_HOLD + 0.35 && (
        <div style={{ position: "absolute", top: 120, width: "100%", textAlign: "center" }}>
          <div style={{ fontFamily: MONO_FONT, fontSize: 26, letterSpacing: 8, textTransform: "uppercase", color: P.muted }}>
            <Mask t={t} at={T_THIS} out={T_HOLD - 0.1}>
              — This is —
            </Mask>
          </div>
          <div style={{ marginTop: 18 }}>
            {"HeySpeaky".split("").map((ch, i) => (
              <Mask key={i} t={t} at={T_NAME + i * 0.035} out={T_HOLD - 0.1 + i * 0.02} style={{ ...big(176, P, "metal"), textTransform: "none", letterSpacing: -5 }}>
                {ch}
              </Mask>
            ))}
          </div>
        </div>
      )}

      {/* "Hold Ctrl + Alt and just talk. Switch languages mid-sentence." */}
      {t >= T_HOLD - 0.05 && t < CLIP_AT + 0.35 && (
        <div style={{ position: "absolute", left: 130, top: 84 }}>
          <div style={{ whiteSpace: "nowrap" }}>
            <Mask t={t} at={T_HOLD} out={CLIP_AT - 0.1} style={big(120, P, "accent")}>
              Hold
            </Mask>
            <span style={{ display: "inline-block", width: 26 }} />
            <Mask t={t} at={T_CTRL} out={CLIP_AT - 0.1} style={big(120, P, "metal")}>
              Ctrl + Alt
            </Mask>
          </div>
          <div style={{ ...line(54, P, 600), color: P.muted, marginTop: 18 }}>
            <Mask t={t} at={T_TALK - 0.25} out={CLIP_AT - 0.1}>
              and just <span style={{ color: P.ink }}>talk.</span>
            </Mask>
          </div>
          <div style={{ marginTop: 6, whiteSpace: "nowrap" }}>
            <Mask t={t} at={T_SWITCH} out={CLIP_AT - 0.1} style={line(54, P, 600)}>
              Switch languages
            </Mask>
            <span style={{ display: "inline-block", width: 16 }} />
            <Mask t={t} at={T_MID} out={CLIP_AT - 0.1} style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 76, color: P.accent, textShadow: P.accentGlow }}>
              mid-sentence.
            </Mask>
          </div>
        </div>
      )}
      {/* The keys' names while the camera is on them is on the keys themselves. */}

      {/* The demo: listening, which language, and the keys held. */}
      {t >= CLIP_AT + 0.2 && t < RELEASE + 0.3 && (
        <div style={{ position: "absolute", left: 130, top: 92, opacity: clamp((t - (CLIP_AT + 0.2)) / 0.25) * (1 - clamp((t - RELEASE) / 0.3)) }}>
          <div style={label(22, P.accent)}>
            <span style={{ opacity: Math.floor(t * 2.5) % 2 ? 0.35 : 1 }}>●</span> listening · {Math.max(0, t - CLIP_AT).toFixed(1)}s · 4 languages · 1 breath
          </div>
          <div style={{ display: "flex", gap: 12, marginTop: 18 }}>
            {DEMO_LANGS.map((lang, i) => {
              const on = i === speaking;
              return (
                <div
                  key={lang}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "8px 16px 8px 12px",
                    borderRadius: 999,
                    fontFamily: INTER,
                    fontWeight: 600,
                    fontSize: 24,
                    color: "#ffffff",
                    background: hexA(LANG[lang].color, on ? 0.38 : 0.12),
                    boxShadow: on ? `0 0 28px ${hexA(LANG[lang].color, 0.6)}` : undefined,
                    opacity: on ? 1 : 0.45,
                    transform: `scale(${on ? 1.08 : 1})`,
                  }}
                >
                  <span style={{ width: 10, height: 10, borderRadius: 5, background: LANG[lang].color }} />
                  {LANG[lang].name}
                </div>
              );
            })}
          </div>
        </div>
      )}
      {/* "Let go. It types where you were." */}
      {t >= T_LETGO - 0.05 && t < SLAB_IN + 0.1 && (
        <div style={{ position: "absolute", left: 130, top: 84, whiteSpace: "nowrap" }}>
          <Mask t={t} at={cue("letgo", "let")} style={big(112, P, "accent")}>
            Let go.
          </Mask>
          <span style={{ display: "inline-block", width: 26 }} />
          <Mask t={t} at={cue("letgo", "types", "it")} style={line(58, P)}>
            It types
          </Mask>
          <span style={{ display: "inline-block", width: 14 }} />
          <Mask t={t} at={cue("letgo", "where", "right")} style={line(58, P)}>
            where you were.
          </Mask>
        </div>
      )}
      {/* The window it types into. */}
      {t >= RELEASE && t < SLAB_IN + 0.1 && (() => {
        const win = springAt(t, RELEASE, { damping: 16 });
        return <DarkWindow x={WIN.x} y={WIN.y + (1 - win) * 70} w={WIN.w} h={WIN.h} style={{ opacity: clamp(win * 1.5) }} />;
      })()}
      {/* Each word leaves Speaky's mouth as it is said and waits in the air;
          when the keys come up they go into the window together. */}
      {t >= CLIP_AT && t < SLAB_IN + 0.1 && sp &&
        CLIP_WORDS.map((word, i) => {
          const born = CLIP_AT + word.start;
          if (t < born) return null;
          const mouth = project(shot, [sp.pos[0] + 0.3, sp.pos[1] - 0.07, sp.pos[2] + 0.62]);
          const fly = easeOut((t - born) / 0.6);
          const cx = CLOUD.x + cloud[i].x;
          const cy = CLOUD.y + cloud[i].y;
          let x = mouth.x + (cx - mouth.x) * fly;
          let y = mouth.y + (cy - mouth.y) * fly - Math.sin(Math.PI * fly) * 140;
          let scale = 0.3 + 0.7 * fly;
          let colour: string = LANG[word.lang].color;
          let text = word.said;
          if (t < LAND) y += Math.sin(t * 2.2 + i) * 4 * fly;
          const goAt = LAND + i * 0.02;
          const go = easeInOut(clamp((t - goAt) / 0.42));
          if (t >= goAt) {
            x = cx + (PAGE.x + page[i].x - cx) * go;
            y = cy + (PAGE.y + page[i].y - cy) * go - Math.sin(Math.PI * go) * 40;
            scale = 1 + (PAGE.size / CLOUD.size - 1) * go;
            text = go > 0.5 ? word.typed : word.said;
            if (go >= 1) colour = "#F4F2F7";
          }
          const landed = t >= goAt + 0.42;
          const thinking = t >= RELEASE && t < goAt;
          const shimmer = thinking ? 0.55 + 0.45 * Math.sin((t - RELEASE) * 9 - i * 0.45) : 1;
          const mark = easeOut((t - (LAND + 0.8 + DEMO_LANGS.indexOf(word.lang) * 0.25)) / 0.3);
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: x,
                top: y,
                transform: `scale(${scale})`,
                transformOrigin: "0 0",
                fontFamily: INTER,
                fontWeight: landed ? 500 : 600,
                fontSize: CLOUD.size,
                color: colour,
                whiteSpace: "pre",
                padding: "0 6px",
                margin: "0 -6px",
                borderRadius: 8,
                background: landed ? hexA(LANG[word.lang].color, 0.26 * mark) : "transparent",
                textShadow: landed ? undefined : `0 0 ${thinking ? 30 * (1 - shimmer) + 8 : 18}px ${hexA(thinking ? "#5B9BFF" : LANG[word.lang].color, 0.75)}`,
                opacity: shimmer * (1 - clamp((t - (SLAB_IN - 0.05)) / 0.1)),
              }}
            >
              {text}
            </div>
          );
        })}
      {t > LAND + 0.5 && t < SLAB_IN && Math.floor(t * 2) % 2 === 0 && (
        <div
          style={{
            position: "absolute",
            left: PAGE.x + page[page.length - 1].x + page[page.length - 1].w + 8,
            top: PAGE.y + page[page.length - 1].y + 6,
            width: 3,
            height: PAGE.size * 1.15,
            background: "#ffffff",
            boxShadow: `0 0 10px ${P.accent}`,
          }}
        />
      )}

      {/* "Gets a name wrong? Teach it your names." */}
      {t >= SLAB_OUT && t < T_LANGS + 0.3 && <Names t={t} />}

      {/* "Ninety-seven languages. Yours go first." */}
      {t >= T_LANGS + 0.1 && t < T_FREE + 0.3 && (
        <>
          <div style={{ position: "absolute", left: 140, top: 250 }}>
            <div style={{ ...big(300, P, "metal"), opacity: clamp((t - (T_LANGS + 0.1)) / 0.15) * (1 - clamp((t - (T_FREE - 0.15)) / 0.3)) }}>
              {Math.round(97 * easeOut((t - (T_LANGS + 0.1)) / Math.max(0.5, T_COUNTED - T_LANGS + 0.2)))}
            </div>
            <Mask t={t} at={T_COUNTED} out={T_FREE - 0.15} style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 118, color: P.ink }}>
              languages.
            </Mask>
          </div>
          <div style={{ position: "absolute", left: 140, top: 760, whiteSpace: "nowrap" }}>
            <Mask t={t} at={T_YOURS} out={T_FREE - 0.15} style={big(112, P, "accent")}>
              Yours
            </Mask>
            <span style={{ display: "inline-block", width: 24 }} />
            <Mask t={t} at={cue("langs", "go")} out={T_FREE - 0.15} style={big(112, P, "metal")}>
              go first.
            </Mask>
          </div>
          {YOURS.map((lang, i) => {
            const s = yoursOrb(i, t);
            if (!s) return null;
            const at = project(shot, [s.pos[0] - 0.45, s.pos[1], s.pos[2]]);
            return (
              <div key={lang} style={{ position: "absolute", left: at.x, top: at.y, transform: "translate(-100%, -50%)", opacity: clamp(s.scale) * (1 - clamp((t - (T_FREE - 0.15)) / 0.3)), display: "flex", alignItems: "center", gap: 18, whiteSpace: "nowrap" }}>
                <span style={label(30, "rgba(255,255,255,0.45)")}>0{i + 1}</span>
                <span style={{ fontFamily: INTER, fontWeight: 700, fontSize: 44, color: "#ffffff", textShadow: `0 0 24px ${hexA(LANG[lang].color, 0.6)}` }}>{LANG[lang].name}</span>
              </div>
            );
          })}
        </>
      )}

      {/* "Free. Open source. Windows." */}
      {t >= T_FREE && t < T_META + 0.35 && (
        <>
          <div style={{ position: "absolute", top: 110, width: "100%", textAlign: "center" }}>
            {"HeySpeaky".split("").map((ch, i) => (
              <Mask key={i} t={t} at={T_FREE + 0.35 + i * 0.03} out={T_META - 0.1 + i * 0.02} style={{ ...big(176, P, "metal"), textTransform: "none", letterSpacing: -5 }}>
                {ch}
              </Mask>
            ))}
          </div>
          <div style={{ position: "absolute", top: 850, width: "100%", display: "flex", justifyContent: "center", gap: 28 }}>
            {[
              ["Free", cue("free", "free")],
              ["Open source", cue("free", "open")],
              ["Windows", cue("free", "windows")],
            ].map(([text, at]) => {
              const p = springAt(t, at as number, { damping: 12, stiffness: 240 });
              const out = clamp((t - (T_META - 0.1)) / 0.25);
              return (
                <div
                  key={text as string}
                  style={{
                    ...label(30, "#ffffff"),
                    letterSpacing: 6,
                    padding: "16px 30px",
                    borderRadius: 8,
                    background: hexA(P.accent, 0.12),
                    border: `1px solid ${hexA(P.accent, 0.55)}`,
                    boxShadow: `0 0 30px ${hexA(P.accent, 0.3)}`,
                    opacity: clamp(p * 3) * (1 - out),
                    transform: `scale(${1.35 - 0.35 * p})`,
                  }}
                >
                  {text}
                </div>
              );
            })}
          </div>
          <div style={{ position: "absolute", top: 965, width: "100%", textAlign: "center", ...label(24, "rgba(255,255,255,0.6)"), textTransform: "none", letterSpacing: 3, opacity: clamp((t - (cue("free", "windows") + 0.3)) / 0.4) * (1 - clamp((t - (T_META - 0.1)) / 0.25)) }}>
            github.com/Maslitsa/HeySpeaky
          </div>
        </>
      )}

      {/* "Oh, and this video? Every single frame is code." */}
      {t >= T_META - 0.05 && <Meta t={t} />}

      {/* The red slab: what regular dictation does to the same sentence. */}
      {t >= SLAB_IN && t < SLAB_OUT && <SlabShot t={t} />}
    </AbsoluteFill>
  );
};

const Names: React.FC<{ t: number }> = ({ t }) => {
  const typed = "Мағжан";
  const shown = Math.floor(clamp((t - (T_TEACH + 0.6)) / 0.5) * typed.length);
  const fixed = t >= FIXED;
  const scramble = t >= FIXED - 0.25 && t < FIXED;
  const letters = "MARZHANмағжанqwxz";
  const name = fixed ? typed : scramble ? "Marzhan".split("").map((_, i) => letters[(i * 7 + Math.floor(t * 40)) % letters.length]).join("") : "Marzhan";
  const box = springAt(t, T_TEACH + 0.5, { damping: 14 });
  const boxGone = easeOut((t - (FIXED + 0.05)) / 0.25);
  const badge = springAt(t, FIXED + 0.15, { damping: 11 });
  const out = clamp((t - (T_LANGS - 0.45)) / 0.25);
  return (
    <AbsoluteFill style={{ opacity: 1 - out }}>
      <div style={{ position: "absolute", left: 130, top: 84 }}>
        <div style={line(60, P)}>
          <Mask t={t} at={cue("names", "gets")}>Gets a name wrong?</Mask>
        </div>
        <div style={{ marginTop: 8, whiteSpace: "nowrap" }}>
          <Mask t={t} at={T_TEACH} style={line(60, P)}>
            Teach it your
          </Mask>
          <span style={{ display: "inline-block", width: 16 }} />
          <Mask t={t} at={cue("names", "names")} style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 92, color: P.accent, textShadow: P.accentGlow }}>
            names.
          </Mask>
        </div>
      </div>
      <div style={{ position: "absolute", left: 0, width: 1540, top: 360, textAlign: "center", whiteSpace: "nowrap", opacity: clamp((t - (SLAB_OUT + 0.2)) / 0.3) }}>
        <span style={line(80, P, 500)}>See you tomorrow, </span>
        <span
          style={{
            ...line(80, P, 700),
            position: "relative",
            display: "inline-block",
            padding: "0 12px",
            borderRadius: 14,
            color: fixed ? "#FFD7A0" : P.ink,
            background: fixed ? hexA(LANG.kk.color, 0.28) : "transparent",
            boxShadow: fixed ? `0 0 46px ${hexA(LANG.kk.color, 0.5)}` : undefined,
            transform: `scale(${fixed ? 1 + 0.12 * pulse(t, FIXED + 0.08, 0.12) : 1})`,
          }}
        >
          {name}!
          {!fixed && (
            <span style={{ position: "absolute", left: 12, top: 92 }}>
              <Squiggle width={300} share={easeOut((t - (SLAB_OUT + 0.45)) / 0.4)} />
            </span>
          )}
        </span>
      </div>
      {t > T_TEACH + 0.5 && t < FIXED + 0.35 && (
        <div style={{ position: "absolute", left: 770 - 380, top: 760 - 58, transform: `scale(${box * (1 - boxGone * 0.6)})`, opacity: 1 - boxGone, transformOrigin: "50% 50%" }}>
          <div style={{ width: 760, height: 116, borderRadius: 58, background: "#0A070B", border: "1px solid #3B3442", display: "flex", alignItems: "center", padding: "0 18px", gap: 16, boxShadow: `0 24px 60px rgba(0,0,0,0.5), 0 0 40px ${hexA("#0267C5", 0.25)}` }}>
            <div style={{ width: 80, height: 80, borderRadius: 40, background: "#343038", color: "#C8C6CE", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 40, fontFamily: INTER }}>×</div>
            <div style={{ flex: 1, height: 80, borderRadius: 40, background: "#1C1A1F", border: "3px solid #0267C5", display: "flex", alignItems: "center", padding: "0 30px", ...line(44, P, 600) }}>
              {typed.slice(0, shown)}
              {Math.floor(t * 3) % 2 === 0 && <span style={{ width: 3, height: 46, background: "#FFFFFF", marginLeft: 4 }} />}
            </div>
            <div style={{ width: 80, height: 80, borderRadius: 40, background: "#0267C5", color: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 44, fontFamily: INTER, transform: `scale(${1 + 0.25 * Math.sin(clamp(springAt(t, FIX_TICK, { damping: 8 })) * Math.PI)})` }}>✓</div>
          </div>
        </div>
      )}
      {t > FIXED + 0.15 && (
        <div style={{ position: "absolute", left: 1010, top: 500, transform: `scale(${badge})`, transformOrigin: "0 50%" }}>
          <div style={{ ...label(24, "#9FC2FF"), padding: "10px 20px", border: "1px solid rgba(91,155,255,0.6)", borderRadius: 999, background: "rgba(2,103,197,0.25)" }}>✓ remembered</div>
        </div>
      )}
    </AbsoluteFill>
  );
};

const KEYWORDS = /\b(const|let|return|import|from|export|type|if|else|for|new|true|false|null)\b/;
const CodeLine: React.FC<{ text: string }> = ({ text }) => {
  const parts: React.ReactNode[] = [];
  let last = 0;
  const re = /("[^"]*"|'[^']*'|`[^`]*`|\b\d+(\.\d+)?\b|\b(const|let|return|import|from|export|type|if|else|for|new|true|false|null)\b|\/\/.*$)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    parts.push(text.slice(last, m.index));
    const tok = m[0];
    const colour = tok.startsWith("//") ? "#5E6A7A" : /^["'`]/.test(tok) ? "#7FD18B" : /^\d/.test(tok) ? "#FF8A5B" : KEYWORDS.test(tok) ? "#C792EA" : "#C9D1D9";
    parts.push(
      <span key={m.index} style={{ color: colour }}>
        {tok}
      </span>,
    );
    last = m.index + tok.length;
  }
  parts.push(text.slice(last));
  return <div style={{ whiteSpace: "pre", height: 30, color: "#8B95A3" }}>{parts}</div>;
};

const Meta: React.FC<{ t: number }> = ({ t }) => {
  const lines = code as string[];
  const first = easeOut((t - (T_EVERY - 0.15)) / 0.3);
  const fade = easeOut((t - (END - 0.6)) / 0.6);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ perspective: 1100, WebkitMaskImage: "linear-gradient(to bottom, black 0%, black 40%, transparent 72%)", maskImage: "linear-gradient(to bottom, black 0%, black 40%, transparent 72%)" }}>
        <div style={{ position: "absolute", left: 160, top: -220, width: 1600, transform: "rotateX(38deg) translateZ(-200px)", transformOrigin: "50% 100%", fontFamily: MONO_FONT, fontSize: 22, opacity: 0.4 * easeOut((t - T_META) / 0.6), columnCount: 2, columnGap: 70 }}>
          <div style={{ transform: `translateY(${-(t - T_META) * 70}px)` }}>
            {lines.slice(0, 160).map((l, i) => (
              <CodeLine key={i} text={l} />
            ))}
          </div>
        </div>
      </AbsoluteFill>
      <div style={{ position: "absolute", top: 230 - first * 130, width: "100%", textAlign: "center", opacity: 1 - first * 0.7, whiteSpace: "nowrap" }}>
        <span style={line(92, P, 800)}>
          {([["Oh,", "oh"], ["and", "and"], ["this", "this"], ["video?", "video"]] as const).map(([word, key], i) => (
            <React.Fragment key={word}>
              {i > 0 && <span style={{ display: "inline-block", width: "0.28em" }} />}
              <Mask t={t} at={cue("meta", key, key === "and" ? "in" : key)}>{word}</Mask>
            </React.Fragment>
          ))}
        </span>
      </div>
      <div style={{ position: "absolute", top: 250, width: "100%", textAlign: "center", whiteSpace: "nowrap" }}>
        <Mask t={t} at={T_EVERY} style={big(108, P, "metal")}>
          Every single frame
        </Mask>
        <div style={{ marginTop: 4 }}>
          <Mask t={t} at={T_CODE - 0.04} style={{ fontFamily: SERIF, fontStyle: "italic", fontSize: 150, color: P.accent, textShadow: P.accentGlow }}>
            is code.
          </Mask>
        </div>
      </div>
      {t >= T_CTA - 0.05 && (
        <div style={{ position: "absolute", top: 890, width: "100%", textAlign: "center" }}>
          <Mask t={t} at={T_CTA} style={line(50, P, 700)}>
            Link's in the comments ↓
          </Mask>
          <div style={{ ...label(22, "rgba(255,255,255,0.55)"), textTransform: "none", letterSpacing: 2, marginTop: 14, opacity: easeOut((t - (T_CTA + 0.4)) / 0.3) }}>github.com/Maslitsa/HeySpeaky</div>
        </div>
      )}
      <AbsoluteFill style={{ background: "#000000", opacity: fade }} />
    </AbsoluteFill>
  );
};

const SlabShot: React.FC<{ t: number }> = ({ t }) => {
  const reg = cue("regular", "regular");
  const dic = cue("regular", "dictation");
  const hit = cue("regular", "this");
  const slam = (at: number): React.CSSProperties => {
    const p = springAt(t, at, { damping: 12, mass: 0.5, stiffness: 260 });
    return { opacity: clamp(p * 3), transform: `scale(${1.5 - 0.5 * p})`, filter: `blur(${(1 - clamp(p)) * 10}px)`, transformOrigin: "0 50%" };
  };
  const tilt = clamp((t - SLAB_IN) / (SLAB_OUT - SLAB_IN));
  return (
    <AbsoluteFill>
      <Slab>
        <AbsoluteFill style={{ perspective: 1400 }}>
          <AbsoluteFill style={{ transform: `rotateX(${8 + 4 * tilt}deg) rotateY(${-10 - 4 * tilt}deg) scale(${1.02 + 0.05 * tilt})` }}>
            <div style={{ position: "absolute", left: 120, top: 110, fontFamily: HEAVY, color: "#140808", lineHeight: 0.86, textTransform: "uppercase" }}>
              <div style={{ fontSize: 220, ...slam(reg) }}>Regular</div>
              <div style={{ fontSize: 220, ...slam(dic) }}>dictation?</div>
            </div>
            {t >= hit &&
              WHISPER_HEARD.map((l, row) => {
                const p = springAt(t, hit + row * 0.1, { damping: 13, stiffness: 220 });
                return (
                  <div key={row} style={{ position: "absolute", left: 130, top: 660 + row * 110, opacity: clamp(p * 3), transform: `translateY(${(1 - p) * 30}px)` }}>
                    <span style={{ fontFamily: MONO_FONT, fontWeight: 600, fontSize: 56, color: "#FFFFFF", background: "rgba(20,6,6,0.55)", padding: "2px 16px", whiteSpace: "pre" }}>{l}</span>
                    <div style={{ marginTop: 8, marginLeft: 16 }}>
                      <Squiggle width={row === 0 ? 1090 : 1110} share={easeOut((t - (hit + 0.2 + row * 0.1)) / 0.4)} color="#FFFFFF" />
                    </div>
                  </div>
                );
              })}
            <div style={{ position: "absolute", left: 130, bottom: 50, ...label(20, "rgba(20,6,6,0.7)"), opacity: easeOut((t - (hit + 0.3)) / 0.3) }}>real output · openai whisper-1 · the same sentence</div>
          </AbsoluteFill>
        </AbsoluteFill>
      </Slab>
    </AbsoluteFill>
  );
};

// -- sound ----------------------------------------------------------------------

const SFX: [string, number, number][] = [
  ["soft-whoosh", 0.05, 0.5],
  ["soft-pop", 0.4, 0.45],
  ["soft-pop", 0.62, 0.45],
  ["soft-pop", 0.84, 0.45],
  ["soft-boom", T_ONE + 0.4, 0.3],
  ["soft-whoosh", T_AND - 0.2, 0.4],
  ["soft-pop", T_THREE - 0.2, 0.4],
  ["soft-pop", T_THREE - 0.1, 0.4],
  ["soft-swell", MERGE - 1.05, 0.45],
  ["soft-bloom", MERGE, 0.55],
  ["soft-boom", MERGE + 0.3, 0.42],
  ["soft-whoosh", T_HOLD + 0.05, 0.35],
  ["soft-boom", T_CTRL - 0.04, 0.25],
  ["soft-key", T_CTRL, 0.5],
  ["soft-boom", T_ALT - 0.04, 0.25],
  ["soft-key", T_ALT, 0.5],
  ["soft-whoosh", CLIP_AT - 0.2, 0.3],
  ["soft-pop", CLIP_AT + SPANS[1][0], 0.25],
  ["soft-pop", CLIP_AT + SPANS[2][0], 0.25],
  ["soft-pop", CLIP_AT + SPANS[3][0], 0.25],
  ["soft-key", RELEASE, 0.45],
  ["soft-swell", LAND - 0.95, 0.35],
  ["soft-bloom", LAND, 0.5],
  ["soft-boom", SLAB_IN, 0.4],
  ["soft-whoosh", SLAB_OUT - 0.1, 0.4],
  ["soft-boom", SLAB_OUT + 0.5, 0.3],
  ["soft-key", T_TEACH, 0.45],
  ["soft-key", T_TEACH + 0.12, 0.45],
  ["soft-key", T_TEACH + 0.24, 0.45],
  ["soft-pop", FIX_TICK, 0.45],
  ["soft-bloom", FIXED, 0.5],
  ["soft-whoosh", T_LANGS - 0.1, 0.45],
  ["soft-pop", T_YOURS, 0.4],
  ["soft-pop", T_YOURS + 0.12, 0.4],
  ["soft-pop", T_YOURS + 0.24, 0.4],
  ["soft-pop", T_YOURS + 0.36, 0.4],
  ["soft-whoosh", T_FREE - 0.2, 0.4],
  ["soft-boom", T_FREE + 0.45, 0.35],
  ["soft-pop", cue("free", "free"), 0.35],
  ["soft-pop", cue("free", "open"), 0.35],
  ["soft-pop", cue("free", "windows"), 0.35],
  ["soft-whoosh", T_META - 0.15, 0.4],
  ["soft-bloom", T_CODE, 0.45],
  ["soft-pop", T_CTA + 0.25, 0.4],
];

const musicVolume = (frame: number) => {
  const t = frame / FPS;
  let duck = 0;
  for (const [a, b] of LINES.map((l) => [VO_AT[l], voEnd(l)])) {
    const into = clamp((t - (a - 0.12)) / 0.12);
    const out = clamp((t - b) / 0.3);
    duck = Math.max(duck, into * (1 - out));
  }
  // Under the four-language sentence the music goes lower still: measured
  // through HeySpeaky, at the narration's level it took the end off the last
  // Kazakh word.
  const clip = clamp((t - (CLIP_AT - 0.15)) / 0.15) * (1 - clamp((t - (CLIP_AT + CLIP_SECONDS)) / 0.3));
  return Math.max(0.06, 0.42 - 0.27 * duck - 0.36 * clip) * clamp(t / 0.4) * clamp((END - t) / 1.0);
};

export const Film3D: React.FC = () => {
  const frame = useCurrentFrame();
  const t = frame / FPS;
  const shot = cameraAt(t, KEYS);
  return (
    <AbsoluteFill style={{ background: P.bg }}>
      <ThreeCanvas width={1920} height={1080} flat gl={{ preserveDrawingBuffer: true, antialias: false }}>
        <Scene3D t={t} shot={shot} />
      </ThreeCanvas>
      <Overlay t={t} shot={shot} />
      {[SLAB_IN, SLAB_OUT].map((at, i) => {
        const length = sec(0.7);
        return (
          <Sequence key={i} from={Math.max(0, sec(at) - Math.round(length * 0.45))} durationInFrames={length} name={`leak ${i}`}>
            <WithLength frames={length}>
              <LightLeak seed={i + 2} hueShift={28} strength={0.5} />
            </WithLength>
          </Sequence>
        );
      })}
      {LINES.map((l) => (
        <Sequence key={l} from={sec(VO_AT[l])} name={`vo ${l}`}>
          <Audio src={staticFile(`vo/${l}.wav`)} />
        </Sequence>
      ))}
      <Sequence from={sec(CLIP_AT)} name="clip">
        <Audio src={staticFile("clip.wav")} volume={0.95} />
      </Sequence>
      {SFX.map(([name, at, volume], i) => (
        <Sequence key={i} from={sec(Math.max(0, at))} name={name}>
          <Audio src={staticFile(`sfx/${name}.wav`)} volume={volume} />
        </Sequence>
      ))}
      {MUSIC && <Audio src={staticFile(MUSIC)} volume={musicVolume} />}
    </AbsoluteFill>
  );
};

export { GALAXY_CENTRE };
