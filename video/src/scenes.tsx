import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import code from "./code.json";
import languageNames from "./languages.json";
import { CLIP_AT, CLIP_SECONDS, CLIP_WORDS, cue, levelAt, SPANS, VO_AT, WHISPER_HEARD } from "./data";
import { DarkKey, DarkWindow, EMBER, ember, Flare, Flash, Hud, label, metal, Slab, Stage, white } from "./dark";
import { HEAVY, INTER, MONO_FONT } from "./fonts";
import { clamp, hexA, LANG, Lang } from "./theme";
import { blinkAt, Chip, Confetti, easeAt, easeInOut, Reveal, Speaky, springAt, Squiggle, useFlow, useT } from "./ui";

type Scene = { start: number; end: number };

const place = (x: number, y: number, extra: React.CSSProperties = {}): React.CSSProperties => ({
  position: "absolute",
  left: x,
  top: y,
  transform: "translate(-50%, -50%)",
  ...extra,
});

/** A camera that drifts through the scene: a slow dolly and a slight turn,
 *  so nothing ever sits still and the flat layers read as space. */
const Camera: React.FC<{ t: number; start: number; end: number; from?: number[]; to?: number[]; children: React.ReactNode }> = ({
  t,
  start,
  end,
  from = [1.0, 2, -1.5],
  to = [1.06, -2, 1.5],
  children,
}) => {
  const p = easeInOut(clamp((t - start) / Math.max(0.1, end - start)));
  const s = from[0] + (to[0] - from[0]) * p;
  const ry = from[1] + (to[1] - from[1]) * p;
  const rx = from[2] + (to[2] - from[2]) * p;
  return (
    <AbsoluteFill style={{ perspective: 1600 }}>
      <AbsoluteFill style={{ transform: `scale(${s}) rotateY(${ry}deg) rotateX(${rx}deg)` }}>{children}</AbsoluteFill>
    </AbsoluteFill>
  );
};

/** A slam: a word that lands too big and settles, out of a blur. */
const slam = (t: number, at: number): React.CSSProperties => {
  const p = springAt(t, at, { damping: 12, mass: 0.5, stiffness: 260 });
  return { opacity: clamp(p * 3), transform: `scale(${1.6 - 0.6 * p})`, filter: `blur(${(1 - clamp(p)) * 12}px)` };
};

// ---------------------------------------------------------------------------
// "What if I told you... your dictation only speaks one language?"
// "And you speak three."
export const Hook: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const three = VO_AT.three;
  const back = easeAt(t, three - 0.05, 0.4);
  const one = cue("hook", "one");
  const threeWord = cue("three", "three");
  const chips: { lang: Lang; x: number; y: number; r: number }[] = [
    { lang: "kk", x: 470, y: 840, r: -8 },
    { lang: "ru", x: 960, y: 900, r: 3 },
    { lang: "en", x: 1450, y: 840, r: 8 },
  ];
  return (
    <Stage t={t} light={[960, 560]} heat={1 + back * 0.5}>
      <Camera t={t} start={start} end={end} from={[0.94, 5, -2]} to={[1.04, -3, 1]}>
        <div
          style={{
            ...place(960, 470, { width: 1800, textAlign: "center" }),
            transform: `translate(-50%, -50%) translateY(${-back * 340}px) scale(${1 - back * 0.5})`,
            opacity: 1 - back * 0.9,
            filter: `blur(${back * 5}px)`,
          }}
        >
          <div style={{ ...white(66, 400), color: "rgba(255,255,255,0.86)" }}>
            <Reveal t={t} at={cue("hook", "what")}>What </Reveal>
            <Reveal t={t} at={cue("hook", "if")}>if </Reveal>
            <Reveal t={t} at={cue("hook", "i")}>I </Reveal>
            <Reveal t={t} at={cue("hook", "told")}>told </Reveal>
            <Reveal t={t} at={cue("hook", "you")}>you…</Reveal>
          </div>
          <div style={{ margin: "14px auto 0", height: 3, width: 560 * easeAt(t, cue("hook", "told"), 0.5), background: EMBER, boxShadow: `0 0 18px ${EMBER}` }} />
          <div style={{ ...white(74, 700), marginTop: 46 }}>
            <Reveal t={t} at={cue("hook", "your")}>your </Reveal>
            <Reveal t={t} at={cue("hook", "dictation")}>dictation </Reveal>
            <Reveal t={t} at={cue("hook", "only")}>only </Reveal>
            <Reveal t={t} at={cue("hook", "speaks")}>speaks</Reveal>
          </div>
          <div style={{ marginTop: 26, whiteSpace: "nowrap" }}>
            <span style={{ display: "inline-block", ...ember(210), ...slam(t, one), marginRight: "0.22em" }}>One</span>
            <Reveal t={t} at={cue("hook", "language")} style={metal(170)}>
              language?
            </Reveal>
          </div>
        </div>

        {t >= three - 0.1 && (
          <div style={place(960, 520, { width: 1800, textAlign: "center" })}>
            <div style={white(84, 800)}>
              <Reveal t={t} at={cue("three", "and")}>And </Reveal>
              <Reveal t={t} at={cue("three", "you")}>you </Reveal>
              <Reveal t={t} at={cue("three", "speak")}>speak</Reveal>
            </div>
            <div style={{ display: "inline-block", marginTop: 10, ...metal(300), ...slam(t, threeWord) }}>three.</div>
          </div>
        )}
        {chips.map((c, i) => {
          const p = springAt(t, threeWord + 0.12 + 0.1 * i, { damping: 11, stiffness: 200 });
          if (p <= 0) return null;
          const float = Math.sin(t * 1.7 + i * 2) * 10;
          return (
            <div key={c.lang} style={place(c.x, c.y + float, { transform: `translate(-50%, -50%) perspective(800px) rotateY(${(1 - p) * 90}deg) rotate(${c.r}deg) scale(${0.6 + 0.4 * p})` })}>
              <Chip lang={c.lang} size={56} strong style={{ background: hexA(LANG[c.lang].color, 0.28), color: "#FFFFFF", boxShadow: `0 0 40px ${hexA(LANG[c.lang].color, 0.45)}` }} />
            </div>
          );
        })}
      </Camera>
      <Flare t={t} at={one} x={760} y={700} />
      <Flare t={t} at={threeWord} x={960} y={640} width={1700} />
    </Stage>
  );
};

// ---------------------------------------------------------------------------
// "This is HeySpeaky."
export const Intro: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const name = cue("this", "heyspeaky", "hey");
  const rise = springAt(t, VO_AT.this - 0.05, { damping: 10, mass: 0.8, stiffness: 120 });
  const beam = clamp(1 - Math.abs(t - (VO_AT.this + 0.3)) / 0.6);
  return (
    <Stage t={t} light={[960, 620]} heat={1.3}>
      <Camera t={t} start={start} end={end} from={[1.08, -4, 2]} to={[1.0, 3, -1]}>
        <div style={{ position: "absolute", left: 960 - 160, top: 0, width: 320, height: 1080, background: `linear-gradient(90deg, transparent, ${hexA(EMBER, 0.35 * beam)}, transparent)`, filter: "blur(12px)" }} />
        <div style={place(960, 170, { ...label(30, "rgba(255,255,255,0.7)"), opacity: easeAt(t, cue("this", "this"), 0.25) })}>— This is —</div>
        <div style={place(960, 290, { whiteSpace: "nowrap" })}>
          <span style={{ display: "inline-block", ...metal(196), ...slam(t, name) }}>HeySpeaky</span>
        </div>
        <Confetti t={t} at={name} x={960} y={660} count={40} seed={7} />
        <div style={place(960, 690 + (1 - rise) * 520)}>
          <Speaky width={540} mood="talking" t={t} level={levelAt("this", t - VO_AT.this)} blink={blinkAt(t, name + 0.7)} look={[Math.sin(t * 1.2) * 0.2, -0.15]} />
        </div>
        <Hud x={640} y={500} w={640} h={420} text="speaky · mono · 108×58 pt" alpha={easeAt(t, name + 0.2, 0.3) * 0.8} />
        <div style={{ position: "absolute", left: 1300, top: 900, ...label(16, "rgba(255,255,255,0.4)"), opacity: easeAt(t, name + 0.3, 0.3) }}>
          x 960 · y 640 · t {(t - start).toFixed(2)}s
        </div>
      </Camera>
      <Flash t={t} at={name} length={0.3} />
      <Flare t={t} at={name} x={960} y={360} width={1800} />
    </Stage>
  );
};

// ---------------------------------------------------------------------------
// "Hold Control-Alt and just talk. Switch languages mid-sentence."
export const Hold: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const ctrl = cue("hold", "ctrl", "control");
  const alt = Math.max(cue("hold", "alt", "-alt"), ctrl + 0.15);
  const listening = t >= alt + 0.12;
  const keys = [
    { text: "Ctrl", x: 440, at: ctrl },
    { text: "Alt", x: 730, at: alt },
  ];
  return (
    <Stage t={t} light={[600, 700]}>
      <Camera t={t} start={start} end={end} from={[1.0, 4, 0]} to={[1.05, -2, 1]}>
        <div style={{ position: "absolute", left: 140, top: 110, whiteSpace: "nowrap" }}>
          <span style={{ display: "inline-block", ...ember(130), ...slam(t, VO_AT.hold), marginRight: "0.22em" }}>Hold</span>
          <Reveal t={t} at={ctrl} style={metal(130)}>
            Ctrl + Alt
          </Reveal>
        </div>
        <div style={{ position: "absolute", left: 140, top: 270, ...white(62, 600), color: "rgba(255,255,255,0.75)" }}>
          <Reveal t={t} at={cue("hold", "and")}>and </Reveal>
          <Reveal t={t} at={cue("hold", "just")}>just </Reveal>
          <Reveal t={t} at={cue("hold", "talk")} style={{ color: "#FFFFFF" }}>
            talk.
          </Reveal>
        </div>
        <div style={{ position: "absolute", left: 140, top: 360, whiteSpace: "nowrap" }}>
          <Reveal t={t} at={cue("hold", "switch")} style={white(62, 600)}>
            Switch languages{" "}
          </Reveal>
          <Reveal t={t} at={cue("hold", "mid", "sentence")} style={ember(96, "serif")}>
            mid-sentence.
          </Reveal>
        </div>
        {keys.map((k) => {
          const fall = easeAt(t, k.at - 0.18, 0.18);
          return (
            <div key={k.text} style={place(k.x, 760 - (1 - fall) * 420, { opacity: clamp(fall * 3) })}>
              <DarkKey text={k.text} size={250} press={t > k.at + 0.02 ? 1 : 0} />
            </div>
          );
        })}
        <div style={place(1450, 690 - Math.sin(clamp((t - alt - 0.12) / 0.3) * Math.PI) * 60)}>
          <Speaky
            width={470}
            mood={listening ? "listening" : "talking"}
            t={t}
            level={listening ? 0.05 : levelAt("hold", t - VO_AT.hold)}
            look={listening ? [0, 0] : [-0.9, 0.3]}
            eyeScale={listening ? 1 + 0.15 * Math.exp(-Math.pow((t - alt - 0.3) / 0.25, 2)) : 1}
            blink={blinkAt(t, end - 0.4)}
          />
        </div>
        {listening && <div style={{ position: "absolute", left: 1290, top: 470, ...label(20, EMBER), opacity: 0.6 + 0.4 * Math.sin(t * 8) }}>● listening</div>}
      </Camera>
      {keys.map((k) => (
        <Flare key={k.text} t={t} at={k.at} x={k.x} y={820} width={700} />
      ))}
    </Stage>
  );
};

// ---------------------------------------------------------------------------
// The clip, four languages in one breath; then "Let go, and it types right
// where you were." One continuous shot.
const SPEAKY = { x: 470, y: 640, width: 520 };
const MOUTH = { x: SPEAKY.x, y: SPEAKY.y + 40 };
const CLOUD = { x: 960, y: 190, width: 840, size: 50, line: 74 };
const WIN = { x: 930, y: 560, w: 880, h: 470 };
const PAGE = { x: WIN.x + 50, y: WIN.y + 100, width: 780, size: 44, line: 62 };

export const Demo: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const at = t - CLIP_AT;
  const release = CLIP_AT + CLIP_SECONDS + 0.15;
  const land = release + 1.0;
  const cloud = useFlow(CLIP_WORDS.map((w) => w.said), `600 ${CLOUD.size}px ${INTER}`, CLOUD.width, CLOUD.line);
  const page = useFlow(CLIP_WORDS.map((w) => w.typed), `500 ${PAGE.size}px ${INTER}`, PAGE.width, PAGE.line);
  if (!cloud || !page) return null;

  const speaking = SPANS.findIndex(([a, b]) => at >= a && at < b);
  const mood = t < release ? "listening" : t < land ? "thinking" : "happy";
  const keysGone = easeAt(t, release + 0.2, 0.35);
  const win = springAt(t, release, { damping: 16 });

  return (
    <Stage t={t} light={[t < release ? 520 : 1300, 640]} tint={t >= release && t < land ? "#3D7BFF" : EMBER}>
      <Camera t={t} start={start} end={end} from={[1.0, 3, 0]} to={[1.04, -3, 1]}>
        {t < release && (
          <div style={{ position: "absolute", left: 140, top: 96, ...label(24, EMBER) }}>
            <span style={{ opacity: Math.floor(t * 2.5) % 2 ? 0.35 : 1 }}>●</span> listening · {Math.max(0, at).toFixed(1)}s · 4 languages · 1 breath
          </div>
        )}
        {t >= VO_AT.letgo - 0.05 && (
          <div style={{ position: "absolute", left: 140, top: 80, whiteSpace: "nowrap" }}>
            <span style={{ display: "inline-block", ...ember(112), ...slam(t, cue("letgo", "let")), marginRight: "0.3em" }}>Let go.</span>
            <Reveal t={t} at={cue("letgo", "types", "it")} style={white(60, 700)}>
              It types{" "}
            </Reveal>
            <Reveal t={t} at={cue("letgo", "where", "right")} style={white(60, 700)}>
              where you were.
            </Reveal>
          </div>
        )}

        <div
          style={{
            position: "absolute",
            left: SPEAKY.x,
            top: 340,
            transform: "translateX(-50%)",
            display: "flex",
            gap: 12,
            opacity: t < release ? easeAt(t, CLIP_AT - 0.1, 0.3) : 1 - easeAt(t, release, 0.3),
          }}
        >
          {(["en", "de", "ru", "kk"] as Lang[]).map((lang, i) => {
            const on = i === speaking;
            return (
              <div key={lang} style={{ transform: `scale(${on ? 1.14 : 1})`, opacity: on ? 1 : 0.35 }}>
                <Chip lang={lang} size={28} strong={on} style={{ color: "#FFFFFF", background: hexA(LANG[lang].color, on ? 0.4 : 0.18), boxShadow: on ? `0 0 26px ${hexA(LANG[lang].color, 0.6)}` : undefined }} />
              </div>
            );
          })}
        </div>

        <DarkWindow x={WIN.x} y={WIN.y + (1 - win) * 70} w={WIN.w} h={WIN.h} style={{ opacity: clamp(win * 1.5) }} />

        <div style={place(SPEAKY.x, SPEAKY.y - (t > land ? Math.sin(clamp((t - land) / 0.35) * Math.PI) * 50 : 0))}>
          <Speaky
            width={SPEAKY.width}
            mood={mood}
            t={t}
            level={levelAt("clip", at)}
            look={mood === "thinking" ? [0.4, -0.9] : [0.6, -0.1]}
            blink={blinkAt(t, CLIP_AT + 4.1) + blinkAt(t, CLIP_AT + 9.3)}
          />
        </div>

        {[
          { text: "Ctrl", x: 150 },
          { text: "Alt", x: 290 },
        ].map((k) => (
          <div key={k.text} style={place(k.x, 960 + keysGone * 300, { opacity: 1 - keysGone })}>
            <DarkKey text={k.text} size={110} press={t < release ? 1 : 0} />
          </div>
        ))}

        {CLIP_WORDS.map((word, i) => {
          const born = CLIP_AT + word.start;
          if (t < born) return null;
          const fly = easeAt(t, born, 0.5);
          const cx = CLOUD.x + cloud[i].x;
          const cy = CLOUD.y + cloud[i].y;
          let x = MOUTH.x + (cx - MOUTH.x) * fly;
          let y = MOUTH.y + (cy - MOUTH.y) * fly - Math.sin(Math.PI * fly) * 170;
          let scale = 0.35 + 0.65 * fly;
          let colour: string = LANG[word.lang].color;
          let text = word.said;
          if (t < land) y += Math.sin(t * 2.2 + i) * 4 * fly;
          const goAt = land + i * 0.02;
          const go = easeInOut(clamp((t - goAt) / 0.4));
          if (t >= goAt) {
            x = cx + (PAGE.x + page[i].x - cx) * go;
            y = cy + (PAGE.y + page[i].y - cy) * go - Math.sin(Math.PI * go) * 40;
            scale = 1 + (PAGE.size / CLOUD.size - 1) * go;
            text = go > 0.5 ? word.typed : word.said;
            if (go >= 1) colour = "#F4F2F7";
          }
          const landed = t >= goAt + 0.4;
          const thinking = t >= release && t < goAt;
          const shimmer = thinking ? 0.55 + 0.45 * Math.sin((t - release) * 9 - i * 0.45) : 1;
          const mark = easeAt(t, land + 0.75 + ["en", "de", "ru", "kk"].indexOf(word.lang) * 0.25, 0.3);
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
                padding: "0 7px",
                margin: "0 -7px",
                borderRadius: 8,
                background: landed ? hexA(LANG[word.lang].color, 0.26 * mark) : "transparent",
                textShadow: landed ? undefined : `0 0 ${thinking ? 30 * (1 - shimmer) + 8 : 16}px ${hexA(thinking ? "#5B9BFF" : LANG[word.lang].color, 0.7)}`,
                opacity: shimmer,
              }}
            >
              {text}
            </div>
          );
        })}
        {t > land + 0.5 && Math.floor(t * 2) % 2 === 0 && (
          <div
            style={{
              position: "absolute",
              left: PAGE.x + page[page.length - 1].x + page[page.length - 1].w + 8,
              top: PAGE.y + page[page.length - 1].y + 6,
              width: 4,
              height: PAGE.size * 1.15,
              background: "#FFFFFF",
              boxShadow: `0 0 10px ${EMBER}`,
            }}
          />
        )}
        <div style={{ position: "absolute", left: WIN.x, top: WIN.y + WIN.h + 24, ...label(18, "rgba(255,255,255,0.5)"), opacity: easeAt(t, land + 0.6, 0.3) }}>
          typed at your cursor · any window
        </div>
      </Camera>
      <Flare t={t} at={release} x={300} y={960} width={900} color="#5B9BFF" />
      <Flare t={t} at={land} x={WIN.x + WIN.w / 2} y={WIN.y + 60} width={1200} />
    </Stage>
  );
};

// ---------------------------------------------------------------------------
// "Regular dictation? This."
export const SlabShot: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const reg = cue("regular", "regular");
  const dic = cue("regular", "dictation");
  const hit = cue("regular", "this");
  const shake = t > hit && t < hit + 0.35 ? Math.sin(t * 95) * 14 * (1 - (t - hit) / 0.35) : 0;
  const tilt = 1 + 0.08 * clamp((t - start) / (end - start));
  return (
    <Slab>
      <AbsoluteFill style={{ perspective: 1400 }}>
        <AbsoluteFill style={{ transform: `translateX(${shake}px) rotateX(${10 * tilt}deg) rotateY(${-12 * tilt}deg) scale(${1.02 + 0.04 * tilt})` }}>
          <div style={{ position: "absolute", left: 120, top: 110, fontFamily: HEAVY, color: "#140808", lineHeight: 0.86, textTransform: "uppercase" }}>
            <div style={{ fontSize: 220, transformOrigin: "0 50%", ...slam(t, reg) }}>Regular</div>
            <div style={{ fontSize: 220, transformOrigin: "0 50%", ...slam(t, dic) }}>dictation?</div>
          </div>
          {t >= hit &&
            WHISPER_HEARD.map((line, row) => {
              const p = springAt(t, hit + row * 0.08, { damping: 12, stiffness: 260 });
              const glitch = Math.sin(t * 60 + row * 3) > 0.7 ? Math.sin(t * 173) * 18 : 0;
              return (
                <div key={row} style={{ position: "absolute", left: 130 + glitch, top: 660 + row * 110, opacity: clamp(p * 3), transform: `scale(${1.3 - 0.3 * p})`, transformOrigin: "0 50%" }}>
                  <span
                    style={{
                      fontFamily: MONO_FONT,
                      fontWeight: 600,
                      fontSize: 58,
                      color: "#FFFFFF",
                      textShadow: "-4px 0 rgba(0,255,240,0.65), 4px 0 rgba(20,0,0,0.6)",
                      background: "rgba(20,6,6,0.55)",
                      padding: "2px 16px",
                      whiteSpace: "pre",
                    }}
                  >
                    {line}
                  </span>
                  <div style={{ marginTop: 8, marginLeft: 16 }}>
                    <Squiggle width={row === 0 ? 1150 : 1290} share={easeAt(t, hit + 0.15 + row * 0.1, 0.35)} color="#FFFFFF" />
                  </div>
                </div>
              );
            })}
          <div style={{ position: "absolute", left: 130, bottom: 50, ...label(20, "rgba(20,6,6,0.7)"), opacity: easeAt(t, hit + 0.3, 0.3) }}>
            real output · openai whisper-1 · the same clip
          </div>
        </AbsoluteFill>
      </AbsoluteFill>
    </Slab>
  );
};

// ---------------------------------------------------------------------------
// "Gets a name wrong? Teach it your names."
export const Names: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const k = cue("names", "teach");
  const keys = [
    { text: "Ctrl", at: k },
    { text: "Alt", at: k + 0.12 },
    { text: "Win", at: k + 0.24 },
  ];
  const keysOff = easeAt(t, k + 0.5, 0.3);
  const box = springAt(t, k + 0.45, { damping: 14 });
  const tickAt = k + 1.25;
  const fixedAt = tickAt + 0.12;
  const boxGone = easeAt(t, fixedAt + 0.05, 0.25);
  const typed = "Мағжан";
  const shown = Math.floor(clamp((t - (k + 0.6)) / 0.5) * typed.length);
  const fixed = t >= fixedAt;
  const scramble = t >= fixedAt - 0.25 && t < fixedAt;
  const letters = "MARZHANмағжанqwxz";
  const name = fixed
    ? typed
    : scramble
      ? "Marzhan"
          .split("")
          .map((_, i) => letters[(i * 7 + Math.floor(t * 40)) % letters.length])
          .join("")
      : "Marzhan";
  const badge = springAt(t, fixedAt + 0.15, { damping: 11 });
  return (
    <Stage t={t} light={[1100, 480]}>
      <Camera t={t} start={start} end={end} from={[1.0, -3, 0]} to={[1.05, 3, 1]}>
        <div style={{ position: "absolute", left: 140, top: 100 }}>
          <div style={white(66, 700)}>
            <Reveal t={t} at={cue("names", "gets")}>Gets </Reveal>
            <Reveal t={t} at={cue("names", "a")}>a </Reveal>
            <Reveal t={t} at={cue("names", "name")}>name </Reveal>
            <Reveal t={t} at={cue("names", "wrong")}>wrong?</Reveal>
          </div>
          <div style={{ marginTop: 10, whiteSpace: "nowrap" }}>
            <Reveal t={t} at={k} style={white(66, 700)}>
              Teach it your{" "}
            </Reveal>
            <Reveal t={t} at={cue("names", "names")} style={ember(104, "serif")}>
              names.
            </Reveal>
          </div>
        </div>
        <div style={place(900, 500, { whiteSpace: "nowrap", opacity: easeAt(t, VO_AT.names + 0.1, 0.3) })}>
          <span style={white(88, 500)}>See you tomorrow, </span>
          <span
            style={{
              ...white(88, 700),
              position: "relative",
              display: "inline-block",
              padding: "0 12px",
              borderRadius: 14,
              color: fixed ? "#FFD7A0" : "#F4F2F7",
              background: fixed ? hexA(LANG.kk.color, 0.28) : "transparent",
              boxShadow: fixed ? `0 0 40px ${hexA(LANG.kk.color, 0.45)}` : undefined,
              transform: `scale(${fixed ? 1 + 0.12 * Math.exp(-Math.pow((t - fixedAt - 0.08) / 0.12, 2)) : 1})`,
            }}
          >
            {name}!
            {!fixed && (
              <span style={{ position: "absolute", left: 12, top: 100 }}>
                <Squiggle width={330} share={easeAt(t, VO_AT.names + 0.4, 0.4)} />
              </span>
            )}
          </span>
        </div>
        {fixed && <Confetti t={t} at={fixedAt} x={1330} y={500} count={24} seed={4} />}
        {keys.map((key, i) => {
          const fall = easeAt(t, key.at - 0.16, 0.16);
          return (
            <div key={key.text} style={place(700 + i * 210, 790 - (1 - fall) * 300 + keysOff * 260, { opacity: clamp(fall * 3) * (1 - keysOff) })}>
              <DarkKey text={key.text} size={150} press={t > key.at ? 1 : 0} />
            </div>
          );
        })}
        {t > k + 0.45 && t < fixedAt + 0.35 && (
          <div style={place(960, 790, { transform: `translate(-50%, -50%) scale(${box * (1 - boxGone * 0.6)})`, opacity: 1 - boxGone })}>
            <div style={{ width: 760, height: 116, borderRadius: 58, background: "#0A070B", border: "1px solid #3B3442", display: "flex", alignItems: "center", padding: "0 18px", gap: 16, boxShadow: `0 24px 60px rgba(0,0,0,0.5), 0 0 40px ${hexA("#0267C5", 0.25)}` }}>
              <div style={{ width: 80, height: 80, borderRadius: 40, background: "#343038", color: "#C8C6CE", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 40, fontFamily: INTER }}>×</div>
              <div style={{ flex: 1, height: 80, borderRadius: 40, background: "#1C1A1F", border: "3px solid #0267C5", display: "flex", alignItems: "center", padding: "0 30px", ...white(44, 600) }}>
                {typed.slice(0, shown)}
                {Math.floor(t * 3) % 2 === 0 && <span style={{ width: 3, height: 46, background: "#FFFFFF", marginLeft: 4 }} />}
              </div>
              <div style={{ width: 80, height: 80, borderRadius: 40, background: "#0267C5", color: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 44, fontFamily: INTER, transform: `scale(${1 + 0.25 * Math.sin(clamp(springAt(t, tickAt, { damping: 8 })) * Math.PI)})` }}>✓</div>
            </div>
          </div>
        )}
        {t > fixedAt + 0.15 && (
          <div style={place(1330, 620, { transform: `translate(-50%, -50%) scale(${badge})` })}>
            <div style={{ ...label(24, "#9FC2FF"), padding: "10px 20px", border: "1px solid rgba(91,155,255,0.6)", borderRadius: 999, background: "rgba(2,103,197,0.25)" }}>✓ remembered</div>
          </div>
        )}
        <div style={place(1680, 860 - (fixed ? Math.sin(clamp((t - fixedAt) / 0.3) * Math.PI) * 30 : 0))}>
          <Speaky width={260} mood={fixed ? "happy" : "idle"} t={t} look={[-0.7, -0.3]} blink={blinkAt(t, VO_AT.names + 0.9)} />
        </div>
      </Camera>
      <Flare t={t} at={fixedAt} x={1330} y={500} width={900} color={LANG.kk.color} />
    </Stage>
  );
};

// ---------------------------------------------------------------------------
// "Ninety-seven languages. Yours go first."
const YOURS: Lang[] = ["kk", "ru", "de", "en"];

export const Languages: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const names = languageNames as string[];
  const counted = cue("langs", "languages");
  const count = Math.round(97 * easeAt(t, VO_AT.langs, Math.max(0.4, counted - VO_AT.langs)));
  const yours = cue("langs", "yours");
  const palette = [LANG.en.color, LANG.de.color, LANG.ru.color, LANG.kk.color, "#FFFFFF"];
  return (
    <Stage t={t} light={[700, 480]} tint="#3D6BFF">
      <Camera t={t} start={start} end={end} from={[1.0, 4, -1]} to={[1.05, -2, 1]}>
        {names.slice(0, 72).map((n, i) => {
          const depth = 0.45 + ((i * 37) % 70) / 100;
          const speed = 280 * depth;
          const offset = ((i * 53) % 100) / 100;
          const y = ((offset * 1350 + (t - start) * speed) % 1350) - 160;
          const x = ((i * 241) % 1900) + 10;
          const dim = t > yours ? 0.22 : 0.6;
          return (
            <div
              key={n}
              style={{
                position: "absolute",
                left: x,
                top: y,
                transform: `scale(${depth}) rotate(${((i * 13) % 20) - 10}deg)`,
                opacity: (0.35 + depth * 0.5) * dim,
                filter: depth < 0.65 ? `blur(${(0.65 - depth) * 8}px)` : undefined,
              }}
            >
              <Chip name={n} color={palette[i % palette.length]} ink="#FFFFFF" size={34} />
            </div>
          );
        })}
        <div style={{ position: "absolute", left: -200, top: 0, width: 1300, height: 1080, background: "radial-gradient(ellipse at 35% 50%, rgba(5,4,10,0.9) 0%, rgba(5,4,10,0) 65%)" }} />
        <div style={{ position: "absolute", left: 150, top: 220 }}>
          <div style={metal(320)}>{count}</div>
          <Reveal t={t} at={counted} style={ember(124, "serif")}>
            languages.
          </Reveal>
        </div>
        <div style={{ position: "absolute", left: 150, top: 760, whiteSpace: "nowrap" }}>
          <span style={{ display: "inline-block", ...ember(120), ...slam(t, yours), marginRight: "0.22em" }}>Yours</span>
          <Reveal t={t} at={cue("langs", "go")} style={metal(120)}>
            go first.
          </Reveal>
        </div>
        {YOURS.map((lang, i) => {
          const p = springAt(t, yours + 0.12 * i, { damping: 11 });
          if (p <= 0) return null;
          return (
            <div key={lang} style={place(1180 + (1 - p) * 400, 300 + i * 130, { transform: `translate(-50%, -50%) scale(${0.6 + 0.4 * p})`, opacity: clamp(p * 2) })}>
              <div style={{ display: "flex", alignItems: "center", gap: 26 }}>
                <span style={label(40, "rgba(255,255,255,0.45)")}>0{i + 1}</span>
                <Chip lang={lang} size={60} strong style={{ background: hexA(LANG[lang].color, 0.34), color: "#FFFFFF", boxShadow: `0 0 40px ${hexA(LANG[lang].color, 0.5)}` }} />
              </div>
            </div>
          );
        })}
      </Camera>
      <Flare t={t} at={yours} x={600} y={830} width={1100} />
    </Stage>
  );
};

// ---------------------------------------------------------------------------
// "Free. Open source. Windows."
export const Logo: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const tags = [
    { text: "Free", at: cue("free", "free"), x: 560 },
    { text: "Open source", at: cue("free", "open"), x: 960 },
    { text: "Windows", at: cue("free", "windows"), x: 1360 },
  ];
  const icon = springAt(t, start + 0.05, { damping: 9, stiffness: 140 });
  const pal = springAt(t, start + 0.4, { damping: 10 });
  return (
    <Stage t={t} light={[960, 360]} heat={1.2} floor={0.6}>
      <Camera t={t} start={start} end={end} from={[1.06, -3, 2]} to={[1.0, 2, 0]}>
        <div style={place(960, 250, { transform: `translate(-50%, -50%) scale(${0.3 + 0.7 * icon}) rotate(${(1 - icon) * -14}deg)`, opacity: clamp(icon * 2) })}>
          <div style={{ position: "absolute", inset: -60, borderRadius: "50%", background: `radial-gradient(circle, ${hexA(EMBER, 0.45)} 0%, transparent 65%)` }} />
          <Img src={staticFile("icon.png")} style={{ position: "relative", width: 230, height: 230, filter: "drop-shadow(0 24px 40px rgba(0,0,0,0.6))" }} />
        </div>
        <div style={place(960, 500, { whiteSpace: "nowrap" })}>
          <Reveal t={t} at={start + 0.15} style={metal(176)}>
            HeySpeaky
          </Reveal>
        </div>
        {tags.map((tag) => {
          const p = springAt(t, tag.at, { damping: 12, stiffness: 240 });
          if (p <= 0) return null;
          return (
            <div key={tag.text} style={place(tag.x, 720, { transform: `translate(-50%, -50%) scale(${1.4 - 0.4 * p})`, opacity: clamp(p * 3) })}>
              <div style={{ position: "relative", padding: "18px 34px", ...label(34, "#FFFFFF"), letterSpacing: 6, background: hexA(EMBER, 0.12), border: `1px solid ${hexA(EMBER, 0.55)}`, borderRadius: 8, boxShadow: `0 0 30px ${hexA(EMBER, 0.3)}` }}>{tag.text}</div>
            </div>
          );
        })}
        <div style={place(960, 880, { ...label(26, "rgba(255,255,255,0.6)"), opacity: easeAt(t, tags[2].at + 0.3, 0.4), letterSpacing: 3, textTransform: "none" })}>github.com/Maslitsa/HeySpeaky</div>
        <div style={place(1700, 560 + (1 - pal) * 400)}>
          <Speaky width={230} mood="talking" t={t} level={levelAt("free", t - VO_AT.free)} look={[-0.8, 0.1]} blink={blinkAt(t, end - 0.5)} />
        </div>
      </Camera>
      {tags.map((tag) => (
        <Flare key={tag.text} t={t} at={tag.at} x={tag.x} y={720} width={600} />
      ))}
    </Stage>
  );
};

// ---------------------------------------------------------------------------
// "Oh, and this video? Every single frame is code."  "Link's in the comments."
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

export const Meta: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const lines = code as string[];
  const every = cue("meta", "every");
  const codeWord = cue("meta", "code");
  const first = easeAt(t, every - 0.15, 0.3);
  const cta = VO_AT.cta;
  const fade = easeAt(t, end - 0.5, 0.5);
  const wink = clamp(1 - Math.abs(t - (cta + 0.2)) / 0.18);
  return (
    <Stage t={t} light={[960, 520]} heat={0.9} floor={0}>
      <AbsoluteFill style={{ perspective: 1100 }}>
        <div
          style={{
            position: "absolute",
            left: 160,
            top: -200,
            width: 1600,
            transform: "rotateX(38deg) translateZ(-200px)",
            transformOrigin: "50% 100%",
            fontFamily: MONO_FONT,
            fontSize: 22,
            opacity: 0.45 * easeAt(t, start, 0.5),
            columnCount: 2,
            columnGap: 70,
          }}
        >
          <div style={{ transform: `translateY(${-(t - start) * 70}px)` }}>
            {lines.slice(0, 160).map((line, i) => (
              <CodeLine key={i} text={line} />
            ))}
          </div>
        </div>
      </AbsoluteFill>
      <Camera t={t} start={start} end={end} from={[1.0, 0, 0]} to={[1.06, 0, 0]}>
        <div style={place(960, 380 - first * 170, { textAlign: "center", opacity: 1 - first * 0.7, whiteSpace: "nowrap" })}>
          <span style={white(104, 800)}>
            <Reveal t={t} at={cue("meta", "oh")}>Oh, </Reveal>
            <Reveal t={t} at={cue("meta", "and", "in")}>and </Reveal>
            <Reveal t={t} at={cue("meta", "this")}>this </Reveal>
            <Reveal t={t} at={cue("meta", "video")}>video?</Reveal>
          </span>
        </div>
        <div style={place(960, 470, { textAlign: "center", whiteSpace: "nowrap" })}>
          <Reveal t={t} at={every} style={metal(112)}>
            Every single frame
          </Reveal>
          <div style={{ marginTop: 6 }}>
            <span style={{ display: "inline-block", ...ember(150, "serif"), ...slam(t, codeWord) }}>is code.</span>
          </div>
        </div>
        {t >= cta - 0.05 && (
          <div style={place(960, 800, { textAlign: "center" })}>
            <Reveal t={t} at={cta} style={white(58, 700)}>
              Link's in the comments
            </Reveal>
            <div style={{ ...ember(70), marginTop: 6, transform: `translateY(${Math.abs(Math.sin(t * 5)) * 16}px)`, opacity: easeAt(t, cta + 0.2, 0.3) }}>↓</div>
            <div style={{ ...label(22, "rgba(255,255,255,0.55)"), textTransform: "none", letterSpacing: 2, opacity: easeAt(t, cta + 0.4, 0.3) }}>github.com/Maslitsa/HeySpeaky</div>
          </div>
        )}
        <div style={place(1620, 860 + (1 - springAt(t, start + 0.3, { damping: 10 })) * 300)}>
          <Speaky width={260} mood="talking" t={t} level={levelAt("meta", t - VO_AT.meta) + levelAt("cta", t - VO_AT.cta)} wink={wink} look={[-0.6, -0.3]} />
        </div>
      </Camera>
      <Flare t={t} at={codeWord} x={1300} y={520} width={1300} />
      <AbsoluteFill style={{ background: "#000000", opacity: fade }} />
    </Stage>
  );
};
