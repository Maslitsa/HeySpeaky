import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import languageNames from "./languages.json";
import code from "./code.json";
import { CLIP_AT, CLIP_SECONDS, CLIP_WORDS, levelAt, SPANS, VO_AT, WHISPER_HEARD, wordAt } from "./data";
import { INTER, MONO_FONT, SERIF } from "./fonts";
import { C, clamp, hexA, LANG, Lang } from "./theme";
import {
  accent,
  blinkAt,
  bold,
  Chip,
  Confetti,
  Dark,
  easeAt,
  easeInOut,
  Keycap,
  NotesWindow,
  Paper,
  Reveal,
  Speaky,
  springAt,
  Squiggle,
  useFlow,
  useT,
} from "./ui";

type Scene = { start: number; end: number };

const place = (x: number, y: number, extra: React.CSSProperties = {}): React.CSSProperties => ({
  position: "absolute",
  left: x,
  top: y,
  transform: "translate(-50%, -50%)",
  ...extra,
});

/** A slow push in, so no shot ever stands still. */
const push = (t: number, start: number, end: number, amount = 0.045) => 1 + amount * clamp((t - start) / (end - start));

// 0.0 - 2.9 -------------------------------------------------------------------
export const Hook: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const w = (i: number) => wordAt("hook", i);
  const chips: { lang: Lang; x: number; y: number }[] = [
    { lang: "kk", x: 330, y: 250 },
    { lang: "ru", x: 1590, y: 300 },
    { lang: "en", x: 1500, y: 830 },
  ];
  return (
    <Dark>
      <AbsoluteFill style={{ transform: `scale(${push(t, start, end, 0.06)})` }}>
        <div style={place(960, 470, { textAlign: "center", width: 1700 })}>
          <div style={bold(128, "#FFFFFF")}>
            <Reveal t={t} at={w(0)}>You </Reveal>
            <Reveal t={t} at={w(1)}>think </Reveal>
            <Reveal t={t} at={w(2)}>in</Reveal>
          </div>
          <div style={{ marginTop: 6 }}>
            <Reveal t={t} at={w(3)} style={accent(200, "#FF5A5F")}>
              three{" "}
            </Reveal>
            <Reveal t={t} at={w(4)} style={bold(128, "#FFFFFF")}>
              languages.
            </Reveal>
          </div>
        </div>
        {chips.map((c, i) => {
          const p = springAt(t, w(3) + 0.12 * i, { damping: 10 });
          const float = Math.sin(t * 1.6 + i * 2) * 14;
          return (
            <div key={c.lang} style={place(c.x, c.y + float, { transform: `translate(-50%, -50%) scale(${p}) rotate(${(i - 1) * 6}deg)` })}>
              <Chip lang={c.lang} size={46} strong />
            </div>
          );
        })}
      </AbsoluteFill>
    </Dark>
  );
};

// 2.9 - 9.0 -------------------------------------------------------------------
const MIC = { x: 1600, y: 560 };

export const One: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const w = (i: number) => wordAt("one", i);
  const m = (i: number) => wordAt("mess", i);
  const spit = m(4); // "like"
  const items: { label: string; lang: Lang; at: number; y: number; chip: boolean }[] = [
    { label: LANG.kk.name, lang: "kk", at: 3.3, y: 380, chip: true },
    { label: "Ертең", lang: "kk", at: 3.6, y: 720, chip: false },
    { label: LANG.ru.name, lang: "ru", at: 3.9, y: 520, chip: true },
    { label: "клиент", lang: "ru", at: 4.2, y: 830, chip: false },
    { label: LANG.de.name, lang: "de", at: 4.5, y: 440, chip: true },
    { label: "Antwort", lang: "de", at: 4.8, y: 660, chip: false },
  ];
  const swallowed = items.filter((it) => t > it.at + 0.75).length;
  const shake = t > spit - 0.05 && t < spit + 0.4 ? Math.sin(t * 90) * 10 : 0;
  const gulp = items.reduce((acc, it) => acc + Math.max(0, 1 - Math.abs(t - (it.at + 0.75)) / 0.12) * 0.08, 0);
  const garbageAt = spit + 0.05;
  const fallAt = garbageAt + 0.95;

  return (
    <Paper>
      <AbsoluteFill style={{ transform: `scale(${push(t, start, end)})` }}>
        <div style={{ position: "absolute", left: 140, top: 110 }}>
          <div style={bold(92)}>
            <Reveal t={t} at={w(0)}>Your </Reveal>
            <Reveal t={t} at={w(1)}>dictation </Reveal>
            <Reveal t={t} at={w(2)}>hears </Reveal>
            <Reveal t={t} at={w(3)} style={accent(140)}>
              one.
            </Reveal>
          </div>
          <div style={{ ...bold(46, C.grey, 600), marginTop: 26 }}>
            <Reveal t={t} at={m(0)}>Everything </Reveal>
            <Reveal t={t} at={m(1)}>else </Reveal>
            <Reveal t={t} at={m(2)}>comes </Reveal>
            <Reveal t={t} at={m(3)}>out </Reveal>
            <Reveal t={t} at={m(4)}>like </Reveal>
            <Reveal t={t} at={m(5)}>this.</Reveal>
          </div>
        </div>

        {/* The one-language microphone. */}
        <div style={place(MIC.x + shake, MIC.y, { transform: `translate(-50%, -50%) scale(${1 + gulp})` })}>
          <div
            style={{
              width: 300,
              height: 300,
              borderRadius: 70,
              background: "linear-gradient(#EDECE8, #DEDCD6)",
              boxShadow: "0 30px 60px rgba(40,30,20,0.16)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="150" height="190" viewBox="0 0 150 190">
              <rect x="45" y="8" width="60" height="110" rx="30" fill="#9C9A93" />
              <path d="M 22 92 Q 22 150 75 150 Q 128 150 128 92" stroke="#9C9A93" strokeWidth="10" fill="none" strokeLinecap="round" />
              <line x1="75" y1="150" x2="75" y2="180" stroke="#9C9A93" strokeWidth="10" strokeLinecap="round" />
            </svg>
          </div>
          <div style={{ ...bold(28, C.grey, 600), textAlign: "center", marginTop: 22 }}>English only</div>
        </div>

        {items.map((it, i) => {
          const p = clamp((t - it.at) / 0.75);
          if (p <= 0 || p >= 1) return null;
          const e = easeInOut(p);
          const x0 = -160;
          const x = x0 + (MIC.x - x0) * e;
          const y = it.y + (MIC.y - 40 - it.y) * e - Math.sin(Math.PI * e) * 120;
          const s = 1 - 0.8 * Math.pow(e, 3);
          return (
            <div key={i} style={place(x, y, { transform: `translate(-50%, -50%) scale(${s}) rotate(${(1 - e) * (i % 2 ? 10 : -10)}deg)` })}>
              {it.chip ? (
                <Chip lang={it.lang} size={44} strong />
              ) : (
                <span style={{ ...bold(64, LANG[it.lang].ink, 700), background: hexA(LANG[it.lang].color, 0.16), padding: "4px 18px", borderRadius: 14 }}>
                  {it.label}
                </span>
              )}
            </div>
          );
        })}
        {swallowed > 0 && t < spit && (
          <div style={place(MIC.x, MIC.y + 250, { ...bold(26, C.grey, 600) })}>{swallowed} swallowed</div>
        )}

        {/* What came out: whisper-1's own answer, its letters falling apart. */}
        {t >= garbageAt &&
          WHISPER_HEARD.map((line, row) => {
            const letters = line.split("");
            const fly = easeAt(t, garbageAt + row * 0.08, 0.35);
            const baseX = 150 + (1 - fly) * 1100;
            const baseY = 600 + row * 104;
            return (
              <div key={row} style={{ position: "absolute", left: baseX, top: baseY, whiteSpace: "pre", opacity: clamp(fly * 2) }}>
                {letters.map((ch, i) => {
                  const fall = Math.max(0, t - (fallAt + ((i * 7 + row * 13) % 23) * 0.012));
                  const dy = 1600 * fall * fall;
                  const rot = fall * (((i * 37) % 11) - 5) * 90;
                  return (
                    <span key={i} style={{ display: "inline-block", ...bold(64, C.ink, 700), transform: `translateY(${dy}px) rotate(${rot}deg)` }}>
                      {ch}
                    </span>
                  );
                })}
                <div style={{ position: "absolute", left: 0, top: 78, opacity: t < fallAt ? 1 : 0 }}>
                  <Squiggle width={row === 0 ? 1000 : 1130} share={easeAt(t, garbageAt + 0.2 + row * 0.1, 0.4)} />
                </div>
              </div>
            );
          })}
        <div style={{ position: "absolute", left: 150, bottom: 54, ...bold(24, C.grey, 500), opacity: easeAt(t, garbageAt + 0.3) }}>
          Real output: OpenAI whisper-1 on the same clip you will hear next.
        </div>
      </AbsoluteFill>
    </Paper>
  );
};

// 9.0 - 11.6 ------------------------------------------------------------------
export const Meet: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const w = (i: number) => wordAt("meet", i);
  const enter = springAt(t, 9.15, { damping: 9, mass: 0.8, stiffness: 120 });
  const land = 9.42;
  const squash = Math.exp(-Math.pow((t - land) / 0.07, 2)) * 0.9 - Math.exp(-Math.pow((t - (land - 0.12)) / 0.06, 2)) * 0.5;
  return (
    <Paper glow="#FFF6F2">
      <AbsoluteFill style={{ transform: `scale(${push(t, start, end, 0.05)})` }}>
        <div style={place(960, 250, { textAlign: "center", width: 1600 })}>
          <Reveal t={t} at={w(0)} style={accent(120, C.grey)}>
            Meet{" "}
          </Reveal>
          <Reveal t={t} at={w(1)} style={bold(150, C.ink, 900)}>
            HeySpeaky.
          </Reveal>
        </div>
        <Confetti t={t} at={w(1)} x={960} y={600} count={34} />
        <div style={place(960, 640 + (1 - enter) * 640)}>
          <Speaky
            width={560}
            mood="talking"
            t={t}
            level={levelAt("meet", t - VO_AT.meet)}
            squash={squash}
            blink={blinkAt(t, 10.75)}
            look={[Math.sin(t * 1.3) * 0.25, -0.1]}
          />
        </div>
      </AbsoluteFill>
    </Paper>
  );
};

// 11.6 - 15.3 -----------------------------------------------------------------
const KEYS_BIG = [
  { label: "Ctrl", x: 470 },
  { label: "Alt", x: 760 },
];

export const Hold: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const w = (i: number) => wordAt("hold", i);
  const listening = t >= w(3) + 0.15;
  const keyAt = [w(1), w(3)];
  const hop = springAt(t, w(3) + 0.15, { damping: 8 });
  return (
    <Paper>
      <AbsoluteFill style={{ transform: `scale(${push(t, start, end)})` }}>
        <div style={{ position: "absolute", left: 150, top: 120 }}>
          <div>
            <Reveal t={t} at={w(0)} style={accent(150)}>
              Hold{" "}
            </Reveal>
            <Reveal t={t} at={w(1)} style={bold(130)}>
              Ctrl{" "}
            </Reveal>
            <Reveal t={t} at={w(2)} style={bold(130, C.grey)}>
              +{" "}
            </Reveal>
            <Reveal t={t} at={w(3)} style={bold(130)}>
              Alt
            </Reveal>
          </div>
          <div style={{ ...bold(78, C.grey, 700), marginTop: 18 }}>
            <Reveal t={t} at={w(4)}>and </Reveal>
            <Reveal t={t} at={w(5)}>just </Reveal>
            <Reveal t={t} at={w(6)} style={bold(78, C.ink, 800)}>
              talk.
            </Reveal>
          </div>
        </div>
        {KEYS_BIG.map((k, i) => {
          const fall = easeAt(t, keyAt[i] - 0.2, 0.2);
          const pressed = t > keyAt[i] + 0.02 ? 1 : 0;
          return (
            <div key={k.label} style={place(k.x, 690 - (1 - fall) * 420, { opacity: clamp(fall * 3) })}>
              <Keycap label={k.label} size={250} press={pressed} />
            </div>
          );
        })}
        <div style={place(1440, 640 - hop * 0 - Math.sin(clamp((t - w(3) - 0.15) / 0.3) * Math.PI) * 60)}>
          <Speaky
            width={460}
            mood={listening ? "listening" : "talking"}
            t={t}
            level={listening ? 0.04 : levelAt("hold", t - VO_AT.hold)}
            look={listening ? [0, 0] : [-0.9, 0.25]}
            eyeScale={listening ? 1 + 0.15 * Math.exp(-Math.pow((t - w(3) - 0.3) / 0.25, 2)) : 1}
            blink={blinkAt(t, 14.4)}
          />
        </div>
      </AbsoluteFill>
    </Paper>
  );
};

// 15.3 - 30.0: hold, talk, let go - one continuous shot. ---------------------
const SPEAKY = { x: 500, y: 600, width: 560 };
const MOUTH = { x: SPEAKY.x, y: SPEAKY.y + 30 };
const CLOUD = { x: 1010, y: 200, width: 800, size: 50, line: 74 };
const PAGE = { x: 1010, y: 662, width: 760, size: 44, line: 62 };
const WIN = { x: 960, y: 560, w: 860, h: 470 };

export const Demo: React.FC<Scene> = ({ start }) => {
  const t = useT(start);
  const at = t - CLIP_AT;
  const release = CLIP_AT + CLIP_SECONDS + 0.2;
  const land = release + 1.1;
  const cloud = useFlow(
    CLIP_WORDS.map((w) => w.said),
    `600 ${CLOUD.size}px ${INTER}`,
    CLOUD.width,
    CLOUD.line,
  );
  const page = useFlow(
    CLIP_WORDS.map((w) => w.typed),
    `500 ${PAGE.size}px ${INTER}`,
    PAGE.width,
    PAGE.line,
  );
  if (!cloud || !page) return null;

  const speaking = SPANS.findIndex(([a, b]) => at >= a && at < b);
  const mood = t < release ? "listening" : t < land ? "thinking" : "happy";
  const lw = (i: number) => wordAt("letgo", i);
  const keysUp = t >= release;
  const keysGone = easeAt(t, release + 0.25, 0.35);
  const win = springAt(t, release, { damping: 16 });
  const heads = [
    { at: CLIP_AT - 0.1, until: release - 0.1 },
    { at: lw(0), until: 99 },
  ];

  return (
    <Paper>
      <AbsoluteFill>
        {/* Headlines, as the hands change what they do. */}
        <div style={{ position: "absolute", left: 140, top: 92, opacity: t < heads[0].until ? 1 : 1 - easeAt(t, heads[0].until, 0.2) }}>
          {t < heads[0].until + 0.2 && (
            <div style={bold(56)}>
              <Reveal t={t} at={heads[0].at}>Talk. </Reveal>
              <Reveal t={t} at={heads[0].at + 0.15}>Switch languages </Reveal>
              <Reveal t={t} at={heads[0].at + 0.3} style={accent(82)}>
                whenever.
              </Reveal>
            </div>
          )}
        </div>
        {t >= lw(0) && (
          <div style={{ position: "absolute", left: 140, top: 92 }}>
            <div>
              <Reveal t={t} at={lw(0)} style={accent(96)}>
                Let go.{" "}
              </Reveal>
              <Reveal t={t} at={lw(3)} style={bold(64)}>
                It types{" "}
              </Reveal>
              <Reveal t={t} at={lw(6)} style={bold(64)}>
                where you were.
              </Reveal>
            </div>
          </div>
        )}

        {/* The window it types into, arriving as the keys come up. */}
        <NotesWindow
          x={WIN.x}
          y={WIN.y + (1 - win) * 60}
          w={WIN.w}
          h={WIN.h}
          style={{ opacity: clamp(win * 1.5) }}
        />

        {/* The languages, the one being spoken lit. */}
        <div style={{ position: "absolute", left: SPEAKY.x, top: 300, transform: "translateX(-50%)", display: "flex", gap: 14, opacity: t < release ? 1 : 1 - easeAt(t, release, 0.3) }}>
          {(["en", "de", "ru", "kk"] as Lang[]).map((lang, i) => {
            const on = i === speaking;
            return (
              <div key={lang} style={{ transform: `scale(${on ? 1.12 : 1})`, opacity: at < 0 ? 0.35 : on ? 1 : 0.3, transition: "none" }}>
                <Chip lang={lang} size={30} strong={on} />
              </div>
            );
          })}
        </div>

        <div style={place(SPEAKY.x, SPEAKY.y - (t > land ? Math.sin(clamp((t - land) / 0.35) * Math.PI) * 50 : 0))}>
          <Speaky
            width={SPEAKY.width}
            mood={mood}
            t={t}
            level={levelAt("clip", at)}
            look={mood === "thinking" ? [0.4, -0.9] : [0.55, -0.05]}
            blink={blinkAt(t, CLIP_AT + 4.1) + blinkAt(t, CLIP_AT + 9.3)}
          />
        </div>

        {/* The keys, held the whole time, then let go. */}
        {[{ label: "Ctrl", x: 150 }, { label: "Alt", x: 300 }].map((k) => (
          <div key={k.label} style={place(k.x, 930 + keysGone * 300, { opacity: 1 - keysGone })}>
            <Keycap label={k.label} size={130} press={keysUp ? 0 : 1} />
          </div>
        ))}

        {/* Each word leaves the mouth as it is said and waits in the air;
            when the keys come up they all go into the window at once. */}
        {CLIP_WORDS.map((word, i) => {
          const born = CLIP_AT + word.start;
          if (t < born) return null;
          const fly = easeAt(t, born, 0.5);
          const cx = CLOUD.x + cloud[i].x;
          const cy = CLOUD.y + cloud[i].y;
          let x = MOUTH.x + (cx - MOUTH.x) * fly;
          let y = MOUTH.y + (cy - MOUTH.y) * fly - Math.sin(Math.PI * fly) * 160;
          let scale = 0.35 + 0.65 * fly;
          let colour: string = LANG[word.lang].ink;
          let text = word.said;
          const bob = Math.sin(t * 2.2 + i) * 4 * fly;
          y += t < land ? bob : 0;
          const goAt = land + i * 0.02;
          const go = easeInOut(clamp((t - goAt) / 0.4));
          if (t >= goAt) {
            const px = PAGE.x + page[i].x;
            const py = PAGE.y + page[i].y;
            x = cx + (px - cx) * go;
            y = cy + (py - cy) * go - Math.sin(Math.PI * go) * 40;
            scale = 1 + (PAGE.size / CLOUD.size - 1) * go;
            text = go > 0.5 ? word.typed : word.said;
            if (go >= 1) colour = C.ink;
          }
          const landed = t >= goAt + 0.4;
          // While it thinks, a wave of light runs through the waiting words.
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
                background: landed ? hexA(LANG[word.lang].color, 0.2 * mark) : "transparent",
                opacity: shimmer,
                textShadow: thinking ? `0 0 ${18 * (1 - shimmer)}px ${hexA(C.blueLit, 0.6)}` : undefined,
              }}
            >
              {text}
            </div>
          );
        })}

        {/* The caret, where the typing stopped. */}
        {t > land + 0.5 && Math.floor(t * 2) % 2 === 0 && (
          <div
            style={{
              position: "absolute",
              left: PAGE.x + page[page.length - 1].x + page[page.length - 1].w + 8,
              top: PAGE.y + page[page.length - 1].y + 6,
              width: 4,
              height: PAGE.size * 1.15,
              background: C.ink,
            }}
          />
        )}
      </AbsoluteFill>
    </Paper>
  );
};

// 30.0 - 33.6 -----------------------------------------------------------------
export const Names: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const w = (i: number) => wordAt("names", i);
  const keys = [
    { label: "Ctrl", at: 31.0 },
    { label: "Alt", at: 31.12 },
    { label: "Win", at: 31.24 },
  ];
  const keysOff = easeAt(t, 31.55, 0.3);
  const box = springAt(t, 31.5, { damping: 14 });
  const boxGone = easeAt(t, 32.75, 0.25);
  const typed = "Мағжан";
  const shown = Math.floor(clamp((t - 31.75) / 0.55) * typed.length);
  const tick = springAt(t, 32.5, { damping: 8 });
  const fixedAt = 32.62;
  const fixed = t >= fixedAt;
  const scramble = t >= fixedAt - 0.25 && t < fixedAt;
  const letters = "MARZHANмағжанqwxz";
  const name = fixed
    ? typed
    : scramble
      ? "Marzhan"
          .split("")
          .map((ch, i) => letters[(i * 7 + Math.floor(t * 40)) % letters.length])
          .join("")
      : "Marzhan";
  const badge = springAt(t, 32.85, { damping: 11 });

  return (
    <Paper>
      <AbsoluteFill style={{ transform: `scale(${push(t, start, end)})` }}>
        <div style={{ position: "absolute", left: 140, top: 110 }}>
          <Reveal t={t} at={w(0)} style={bold(92)}>
            Teach{" "}
          </Reveal>
          <Reveal t={t} at={w(1)} style={bold(92)}>
            it{" "}
          </Reveal>
          <Reveal t={t} at={w(2)} style={bold(92)}>
            the{" "}
          </Reveal>
          <Reveal t={t} at={w(3)} style={accent(136)}>
            names{" "}
          </Reveal>
          <Reveal t={t} at={w(4)} style={bold(92)}>
            you{" "}
          </Reveal>
          <Reveal t={t} at={w(5)} style={bold(92)}>
            use.
          </Reveal>
        </div>

        <div style={place(900, 470, { whiteSpace: "nowrap", opacity: easeAt(t, 30.3, 0.3) })}>
          <span style={bold(88, C.ink, 600)}>See you tomorrow, </span>
          <span
            style={{
              ...bold(88, fixed ? LANG.kk.ink : C.ink, 700),
              position: "relative",
              display: "inline-block",
              padding: "0 10px",
              borderRadius: 14,
              background: fixed ? hexA(LANG.kk.color, 0.22) : "transparent",
              transform: `scale(${fixed ? 1 + 0.12 * Math.exp(-Math.pow((t - fixedAt - 0.08) / 0.12, 2)) : 1})`,
            }}
          >
            {name}!
            {!fixed && (
              <span style={{ position: "absolute", left: 10, top: 98 }}>
                <Squiggle width={330} share={easeAt(t, 30.5, 0.4)} />
              </span>
            )}
          </span>
        </div>
        {fixed && <Confetti t={t} at={fixedAt} x={1330} y={470} count={22} seed={4} />}

        {keys.map((k, i) => {
          const fall = easeAt(t, k.at - 0.16, 0.16);
          return (
            <div key={k.label} style={place(700 + i * 210, 760 - (1 - fall) * 300 + keysOff * 260, { opacity: clamp(fall * 3) * (1 - keysOff) })}>
              <Keycap label={k.label} size={150} press={t > k.at ? 1 : 0} />
            </div>
          );
        })}

        {/* The correction composer, in the Mono look. */}
        {t > 31.5 && t < 33.1 && (
          <div style={place(960, 770, { transform: `translate(-50%, -50%) scale(${box * (1 - boxGone * 0.6)})`, opacity: 1 - boxGone })}>
            <div style={{ width: 760, height: 116, borderRadius: 58, background: C.mono, display: "flex", alignItems: "center", padding: "0 18px", gap: 16, boxShadow: "0 24px 60px rgba(0,0,0,0.25)" }}>
              <div style={{ width: 80, height: 80, borderRadius: 40, background: "#343038", color: "#C8C6CE", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 40, fontFamily: INTER }}>×</div>
              <div style={{ flex: 1, height: 80, borderRadius: 40, background: "#1C1A1F", border: `3px solid ${C.blue}`, display: "flex", alignItems: "center", padding: "0 30px", ...bold(44, "#FFFFFF", 600) }}>
                {typed.slice(0, shown)}
                {Math.floor(t * 3) % 2 === 0 && <span style={{ width: 3, height: 46, background: "#FFFFFF", marginLeft: 4 }} />}
              </div>
              <div style={{ width: 80, height: 80, borderRadius: 40, background: C.blue, color: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 44, fontFamily: INTER, transform: `scale(${1 + 0.25 * Math.sin(clamp(tick) * Math.PI)})` }}>✓</div>
            </div>
          </div>
        )}

        {t > 32.85 && (
          <div style={place(1330, 590, { transform: `translate(-50%, -50%) scale(${badge})` })}>
            <Chip name="Remembered" color={C.blue} ink={C.blue} size={34} strong />
          </div>
        )}

        <div style={place(1660, 820 - (fixed ? Math.sin(clamp((t - fixedAt) / 0.3) * Math.PI) * 30 : 0))}>
          <Speaky width={280} mood={fixed ? "happy" : "idle"} t={t} look={[-0.7, -0.2]} blink={blinkAt(t, 30.9)} />
        </div>
      </AbsoluteFill>
    </Paper>
  );
};

// 33.6 - 38.4 -----------------------------------------------------------------
const YOURS: Lang[] = ["kk", "ru", "de", "en"];

export const Languages: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const w = (i: number) => wordAt("langs", i);
  const names = languageNames as string[];
  const count = Math.round(97 * easeAt(t, 33.85, 1.1));
  const yours = w(2);
  const palette = [LANG.en.color, LANG.de.color, LANG.ru.color, LANG.kk.color, "#FFFFFF"];
  return (
    <Dark from={C.nightLit} to={C.night}>
      <AbsoluteFill style={{ transform: `scale(${push(t, start, end, 0.04)})` }}>
        {names.slice(0, 72).map((n, i) => {
          const depth = 0.45 + ((i * 37) % 70) / 100;
          const speed = 300 * depth;
          const offset = ((i * 53) % 100) / 100;
          const y = ((offset * 1350 + (t - start) * speed) % 1350) - 160;
          const life = 1;
          const x = ((i * 241) % 1900) + 10;
          const dim = t > yours ? 0.25 : 0.7;
          return (
            <div
              key={n}
              style={{
                position: "absolute",
                left: x,
                top: y,
                transform: `scale(${depth}) rotate(${((i * 13) % 20) - 10}deg)`,
                opacity: Math.min(1, life * 3) * (0.35 + depth * 0.5) * dim,
                filter: depth < 0.65 ? `blur(${(0.65 - depth) * 8}px)` : undefined,
              }}
            >
              <Chip name={n} color={palette[i % palette.length]} ink="#FFFFFF" size={34} />
            </div>
          );
        })}
        <div style={{ position: "absolute", left: -200, top: 0, width: 1300, height: 1080, background: `radial-gradient(ellipse at 35% 55%, ${hexA(C.night, 0.92)} 0%, ${hexA(C.night, 0)} 65%)` }} />
        <div style={{ position: "absolute", left: 150, top: 250 }}>
          <div style={{ ...bold(300, "#FFFFFF", 900), lineHeight: 0.9 }}>{count}</div>
          <Reveal t={t} at={w(1)} style={accent(130, "#FFFFFF")}>
            languages.
          </Reveal>
        </div>
        <div style={{ position: "absolute", left: 150, top: 760 }}>
          <Reveal t={t} at={w(2)} style={accent(120, LANG.kk.color)}>
            Yours{" "}
          </Reveal>
          <Reveal t={t} at={w(3)} style={bold(100, "#FFFFFF")}>
            go{" "}
          </Reveal>
          <Reveal t={t} at={w(4)} style={bold(100, "#FFFFFF")}>
            first.
          </Reveal>
        </div>
        {YOURS.map((lang, i) => {
          const p = springAt(t, yours + 0.12 * i, { damping: 11 });
          if (p <= 0) return null;
          const fromX = 1100 + i * 180;
          const toX = 1080 + i * 0;
          const toY = 300 + i * 120;
          return (
            <div key={lang} style={place(fromX + (toX - fromX) * p, -100 + (toY + 100) * p, { transform: `translate(-50%, -50%) scale(${0.6 + 0.4 * p})` })}>
              <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
                <span style={bold(48, "rgba(255,255,255,0.5)", 800)}>{i + 1}</span>
                <Chip lang={lang} size={58} strong style={{ background: hexA(LANG[lang].color, 0.32), color: "#FFFFFF" }} />
              </div>
            </div>
          );
        })}
      </AbsoluteFill>
    </Dark>
  );
};

// 38.4 - 42.4 -----------------------------------------------------------------
export const Logo: React.FC<Scene> = ({ start, end }) => {
  const t = useT(start);
  const w = (i: number) => wordAt("logo", i);
  const icon = springAt(t, 38.42, { damping: 9, stiffness: 140 });
  const pal = springAt(t, 38.7, { damping: 10 });
  return (
    <Paper glow="#FFFFFF">
      <AbsoluteFill style={{ transform: `scale(${push(t, start, end, 0.035)})` }}>
        <div style={place(960, 300, { transform: `translate(-50%, -50%) scale(${0.3 + 0.7 * icon}) rotate(${(1 - icon) * -14}deg)`, opacity: clamp(icon * 2) })}>
          <Img src={staticFile("icon.png")} style={{ width: 230, height: 230, filter: "drop-shadow(0 24px 40px rgba(0,0,0,0.25))" }} />
        </div>
        <div style={place(960, 520, { textAlign: "center" })}>
          <Reveal t={t} at={38.5} style={bold(170, C.ink, 900)}>
            HeySpeaky
          </Reveal>
        </div>
        <div style={place(960, 690, { textAlign: "center", whiteSpace: "nowrap" })}>
          <Reveal t={t} at={w(2)} style={bold(72, C.ink, 700)}>
            Talk{" "}
          </Reveal>
          <Reveal t={t} at={w(3)} style={bold(72, C.ink, 700)}>
            the{" "}
          </Reveal>
          <Reveal t={t} at={w(4)} style={bold(72, C.ink, 700)}>
            way{" "}
          </Reveal>
          <Reveal t={t} at={w(5)} style={bold(72, C.ink, 700)}>
            you{" "}
          </Reveal>
          <Reveal t={t} at={w(6)} style={accent(110)}>
            think.
          </Reveal>
        </div>
        <div style={place(960, 880, { ...bold(32, C.grey, 500), opacity: easeAt(t, 41.0, 0.4), whiteSpace: "nowrap", letterSpacing: 0 })}>
          Free and open source · Windows · github.com/Maslitsa/HeySpeaky
        </div>
        <div style={place(1590, 470 + (1 - pal) * 400)}>
          <Speaky width={230} mood="talking" t={t} level={levelAt("logo", t - VO_AT.logo)} look={[-0.8, 0.1]} blink={blinkAt(t, 41.6)} />
        </div>
      </AbsoluteFill>
    </Paper>
  );
};

// 42.4 - 47.5 -----------------------------------------------------------------
const KEYWORDS = /\b(const|let|return|import|from|export|type|if|else|for|new|true|false|null)\b/g;

const CodeLine: React.FC<{ text: string }> = ({ text }) => {
  const parts: React.ReactNode[] = [];
  let last = 0;
  const re = /("[^"]*"|'[^']*'|`[^`]*`|\b\d+(\.\d+)?\b|\b(const|let|return|import|from|export|type|if|else|for|new|true|false|null)\b|\/\/.*$)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    parts.push(text.slice(last, m.index));
    const tok = m[0];
    const colour = tok.startsWith("//") ? "#5E6A7A" : /^["'`]/.test(tok) ? "#7FD18B" : /^\d/.test(tok) ? "#F5A65B" : KEYWORDS.test(tok) ? "#C792EA" : "#C9D1D9";
    KEYWORDS.lastIndex = 0;
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
  const w = (i: number) => wordAt("meta", i);
  const lines = code as string[];
  const scroll = (t - start) * 90;
  const first = easeAt(t, w(3) + 0.5, 0.3);
  const fade = easeAt(t, end - 0.45, 0.45);
  return (
    <Dark from="#151019" to="#050306">
      <AbsoluteFill style={{ transform: `scale(${push(t, start, end, 0.05)})` }}>
        <div style={{ position: "absolute", left: 80, top: 40 - scroll, fontFamily: MONO_FONT, fontSize: 22, opacity: 0.32 * easeAt(t, start, 0.5), width: 1800, columnCount: 2, columnGap: 60 }}>
          {lines.slice(0, 120).map((line, i) => (
            <CodeLine key={i} text={line} />
          ))}
        </div>
        <div style={place(960, 420 - first * 120, { textAlign: "center", opacity: 1 - first * 0.65, whiteSpace: "nowrap" })}>
          <Reveal t={t} at={w(0)} style={bold(110, "#FFFFFF")}>
            Oh,{" "}
          </Reveal>
          <Reveal t={t} at={w(1)} style={bold(110, "#FFFFFF")}>
            and{" "}
          </Reveal>
          <Reveal t={t} at={w(2)} style={bold(110, "#FFFFFF")}>
            this{" "}
          </Reveal>
          <Reveal t={t} at={w(3)} style={bold(110, "#FFFFFF")}>
            video?
          </Reveal>
        </div>
        <div style={place(960, 500, { textAlign: "center", whiteSpace: "nowrap" })}>
          <Reveal t={t} at={w(4)} style={bold(110, "#FFFFFF")}>
            Every{" "}
          </Reveal>
          <Reveal t={t} at={w(5)} style={bold(110, "#FFFFFF")}>
            single{" "}
          </Reveal>
          <Reveal t={t} at={w(6)} style={bold(110, "#FFFFFF")}>
            frame{" "}
          </Reveal>
          <Reveal t={t} at={w(7)} style={accent(170, "#FF5A5F")}>
            is code.
          </Reveal>
        </div>
        <div style={place(960, 720, { ...bold(34, "rgba(255,255,255,0.75)", 500), opacity: easeAt(t, 46.2, 0.4), letterSpacing: 0 })}>
          github.com/Maslitsa/HeySpeaky
        </div>
        <div style={place(960, 900 + (1 - springAt(t, 43.0, { damping: 10 })) * 300)}>
          <Speaky width={300} mood="talking" t={t} level={levelAt("meta", t - VO_AT.meta)} wink={clamp(1 - Math.abs(t - 46.35) / 0.18)} look={[0, -0.3]} />
        </div>
        <AbsoluteFill style={{ background: "#000000", opacity: fade }} />
      </AbsoluteFill>
    </Dark>
  );
};
