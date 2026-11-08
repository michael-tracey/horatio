import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { useSignOut } from "../offline/Offline";
import { useToast } from "./Toast";

/*
 * Light mode, for a vampire: the sun comes up over the city, the screen goes
 * white, and the person at it crumbles to ash and blows away, signed out.
 *
 * It runs at the root of the app, over everything, so it carries on while the
 * page under it changes to the sign-in page.
 */

let running = false;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

/** Let the sun rise. */
export function startSunrise() {
  if (running) return;
  running = true;
  emit();
}

function useRunning() {
  return useSyncExternalStore(
    (changed) => {
      listeners.add(changed);
      return () => listeners.delete(changed);
    },
    () => running,
    () => false,
  );
}

export function SunriseHost() {
  const on = useRunning();
  if (!on) return null;
  return (
    <Sunrise
      onDone={() => {
        running = false;
        emit();
      }}
    />
  );
}

// The timeline, in ms from the start.
const FADE_IN = 1400;
const RISE = 6800;
const WHITE_FROM = 5600;
const WHITE_TO = 7400;
/** Longest the white waits on signing out before the ash goes anyway. */
const SIGN_OUT_WAIT = 6000;
// The ash: how long the burn takes to cross the screen, and how long a fleck lives.
const SPREAD = 2000;
const LIFE_MIN = 1800;
const LIFE_MAX = 3400;

const WHITE = "#fff6e6";

type Rgb = [number, number, number];
const hex = (h: string): Rgb => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
const smooth = (t: number) => t * t * (3 - 2 * t);
const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

/** A colour along a run of stops, as "rgb(…)". */
function along(stops: [number, string][], t: number): string {
  const s = stops.map(([at, h]) => [at, hex(h)] as const);
  let i = 0;
  while (i < s.length - 2 && t > s[i + 1]![0]) i++;
  const [a, ca] = s[i]!;
  const [b, cb] = s[i + 1]!;
  const k = clamp((t - a) / (b - a || 1));
  return `rgb(${Math.round(lerp(ca[0], cb[0], k))},${Math.round(lerp(ca[1], cb[1], k))},${Math.round(lerp(ca[2], cb[2], k))})`;
}

const SKY_TOP: [number, string][] = [
  [0, "#141016"],
  [0.3, "#241a33"],
  [0.55, "#5a3560"],
  [0.78, "#c9776a"],
  [1, "#ffeccc"],
];
const SKY_MID: [number, string][] = [
  [0, "#1a1420"],
  [0.3, "#3d2140"],
  [0.55, "#a3405a"],
  [0.78, "#f0925a"],
  [1, "#fff3dc"],
];
const SKY_LOW: [number, string][] = [
  [0, "#1e1922"],
  [0.3, "#5a2a3d"],
  [0.55, "#e0623e"],
  [0.78, "#ffc26a"],
  [1, "#fff8ec"],
];

/** A small seeded random, so the city is the same city each time. */
function seeded(seed: number) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type Layer = {
  /** Height, as a share of the screen's. */
  height: number;
  /** How far it sinks as the eye follows the sun up, in px at 900 high. */
  sink: number;
  /** How far it shifts with the pointer, in px. */
  sway: number;
  colour: [number, string][];
  d: string;
  /** Lit windows, which go out as it gets light. */
  lights?: string;
  /** Strokes (a dead tree's branches), by width. */
  strokes?: [number, string][];
};

const MARGIN = 120;

/** The far mountains, with a valley in the middle for the sun to come up in. */
function mountains(w: number, h: number, rand: () => number): string {
  const n = 64;
  const ys = new Array<number>(n + 1);
  ys[0] = rand();
  ys[n] = rand();
  // Midpoint displacement: a ridge that looks like rock.
  for (let step = n; step > 1; step /= 2) {
    for (let i = step / 2; i < n; i += step) ys[i] = (ys[i - step / 2]! + ys[i + step / 2]!) / 2 + (rand() - 0.5) * (step / n) * 1.4;
  }
  let d = `M0 ${h}`;
  for (let i = 0; i <= n; i++) {
    const x = (i / n) * w;
    const valley = Math.abs(i / n - 0.5) * 2;
    const top = clamp(0.38 + valley * 0.42 + ys[i]! * 0.3, 0.3, 0.95);
    d += ` L${x.toFixed(1)} ${(h - top * h).toFixed(1)}`;
  }
  return `${d} L${w} ${h} Z`;
}

/** Rolling hills. */
function hills(w: number, h: number, rand: () => number): string {
  const a = rand() * 6;
  const b = rand() * 6;
  let d = `M0 ${h}`;
  for (let x = 0; x <= w; x += 8) {
    const top = 0.55 + 0.14 * Math.sin(x / 190 + a) + 0.08 * Math.sin(x / 71 + b);
    d += ` L${x} ${(h - top * h).toFixed(1)}`;
  }
  return `${d} L${w} ${h} Z`;
}

/** Gothic rooftops: gables, spires, battlements, and a cathedral. */
function city(w: number, h: number, rand: () => number): { d: string; lights: string } {
  const s = clamp(h / 300, 0.6, 1.3);
  let d = "";
  let lights = "";
  const cathedral = w * (0.62 + rand() * 0.1);
  let x = -10;
  while (x < w + 10) {
    const isCathedral = x < cathedral && x + 90 * s > cathedral;
    const bw = isCathedral ? 150 * s : (26 + rand() * 60) * s;
    const bh = isCathedral ? h * 0.5 : h * (0.22 + rand() * 0.36);
    const top = h - bh;
    const roof = isCathedral ? -1 : rand();
    d += `M${x} ${h} L${x} ${top}`;
    if (roof < 0) {
      // Two towers with spires, and the nave between them.
      const t = bw * 0.24;
      const spire = h * 0.42;
      d += ` L${x + t / 2} ${top - spire} L${x + t} ${top} L${x + t} ${top + h * 0.06} L${x + bw / 2} ${top - h * 0.1} L${x + bw - t} ${top + h * 0.06} L${x + bw - t} ${top} L${x + bw - t / 2} ${top - spire} L${x + bw} ${top}`;
    } else if (roof < 0.35) {
      d += ` L${x + bw / 2} ${top - bw * 0.55} L${x + bw} ${top}`;
    } else if (roof < 0.55) {
      const sw = Math.min(bw * 0.3, 14 * s);
      const sx = x + bw * (0.2 + rand() * 0.5);
      d += ` L${sx} ${top} L${sx + sw / 2} ${top - h * (0.18 + rand() * 0.2)} L${sx + sw} ${top} L${x + bw} ${top}`;
    } else if (roof < 0.75) {
      const c = Math.max(3, Math.round(bw / (8 * s)));
      const cw = bw / (c * 2 - 1);
      for (let i = 0; i < c * 2 - 1; i++) {
        const cy = i % 2 === 0 ? top - 6 * s : top;
        d += ` L${x + i * cw} ${cy} L${x + (i + 1) * cw} ${cy}`;
      }
    } else {
      d += ` L${x + bw * 0.15} ${top - 4 * s} L${x + bw * 0.85} ${top - 4 * s} L${x + bw} ${top}`;
    }
    d += ` L${x + bw} ${h} Z `;
    // A few windows still lit.
    const rows = Math.floor((bh - 14 * s) / (14 * s));
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < Math.floor(bw / (12 * s)); c++)
        if (rand() < 0.09) lights += `M${x + 5 * s + c * 12 * s} ${top + 10 * s + r * 14 * s}h${3 * s}v${5 * s}h${-3 * s}Z`;
    x += bw + (rand() < 0.3 ? rand() * 14 * s : 0);
  }
  return { d, lights };
}

/** The graveyard at the front: a mound, headstones, crosses, a dead tree. */
function graveyard(w: number, h: number, rand: () => number): { d: string; strokes: [number, string][] } {
  const s = clamp(h / 180, 0.6, 1.3);
  const ground = (x: number) => h - h * (0.3 + 0.12 * Math.sin(x / 210) + 0.05 * Math.sin(x / 53));
  let d = `M0 ${h}`;
  for (let x = 0; x <= w; x += 10) d += ` L${x} ${ground(x).toFixed(1)}`;
  d += ` L${w} ${h} Z `;
  for (let x = 30 + rand() * 60; x < w; x += (50 + rand() * 120) * s) {
    const g = ground(x) + 4;
    const kind = rand();
    if (kind < 0.45) {
      const sw = (14 + rand() * 10) * s;
      const sh = (20 + rand() * 16) * s;
      d += `M${x} ${g} L${x} ${g - sh + sw / 2} A${sw / 2} ${sw / 2} 0 0 1 ${x + sw} ${g - sh + sw / 2} L${x + sw} ${g} Z `;
    } else if (kind < 0.8) {
      const ch = (30 + rand() * 18) * s;
      const t = 4 * s;
      const arm = 9 * s;
      const at = g - ch * 0.7;
      d += `M${x} ${g} L${x} ${at} L${x - arm} ${at} L${x - arm} ${at - t} L${x} ${at - t} L${x} ${g - ch} L${x + t} ${g - ch} L${x + t} ${at - t} L${x + t + arm} ${at - t} L${x + t + arm} ${at} L${x + t} ${at} L${x + t} ${g} Z `;
    } else {
      const ow = (12 + rand() * 6) * s;
      const oh = (40 + rand() * 20) * s;
      d += `M${x} ${g} L${x + ow * 0.15} ${g - oh} L${x + ow / 2} ${g - oh - ow * 0.8} L${x + ow * 0.85} ${g - oh} L${x + ow} ${g} Z `;
    }
  }
  // The tree: each branch splits in two, thinner, until twigs.
  const byWidth = new Map<number, string>();
  const branch = (x: number, y: number, angle: number, length: number, width: number, depth: number) => {
    const x2 = x + Math.cos(angle) * length;
    const y2 = y + Math.sin(angle) * length;
    const key = Math.max(1, Math.round(width));
    byWidth.set(key, (byWidth.get(key) ?? "") + `M${x.toFixed(1)} ${y.toFixed(1)} L${x2.toFixed(1)} ${y2.toFixed(1)} `);
    if (depth === 0) return;
    branch(x2, y2, angle - 0.3 - rand() * 0.4, length * (0.66 + rand() * 0.12), width * 0.62, depth - 1);
    branch(x2, y2, angle + 0.25 + rand() * 0.4, length * (0.62 + rand() * 0.12), width * 0.62, depth - 1);
  };
  const tx = w * (0.12 + rand() * 0.08);
  branch(tx, ground(tx) + 6, -Math.PI / 2 + 0.08, h * 0.38, 12 * s, 7);
  return { d, strokes: [...byWidth.entries()] };
}

function layers(w: number, h: number): Layer[] {
  const rand = seeded(0x5ab1e);
  const lw = w + MARGIN * 2;
  const make = (share: number) => Math.round(h * share);
  const farH = make(0.5);
  const midH = make(0.34);
  const cityH = make(0.36);
  const graveH = make(0.24);
  const town = city(lw, cityH, rand);
  const grave = graveyard(lw, graveH, rand);
  return [
    {
      height: 0.5,
      sink: 24,
      sway: 6,
      d: mountains(lw, farH, rand),
      colour: [
        [0, "#2c2531"],
        [0.6, "#6a3f5c"],
        [1, "#d8a08a"],
      ],
    },
    {
      height: 0.34,
      sink: 70,
      sway: 14,
      d: hills(lw, midH, rand),
      colour: [
        [0, "#211b26"],
        [0.6, "#4e2c44"],
        [1, "#a8665e"],
      ],
    },
    {
      height: 0.36,
      sink: 150,
      sway: 26,
      d: town.d,
      lights: town.lights,
      colour: [
        [0, "#161118"],
        [0.6, "#2e1a2a"],
        [1, "#6a3a3a"],
      ],
    },
    {
      height: 0.24,
      sink: 280,
      sway: 44,
      d: grave.d,
      strokes: grave.strokes,
      colour: [
        [0, "#0a080c"],
        [0.6, "#160d14"],
        [1, "#3a1e20"],
      ],
    },
  ];
}

const BAT = "M20 9C18 5 14 4 10 6C8 3 4 3 0 7C4 7 6 9 7 13C10 10 13 11 15 14C17 11 18 11 20 13C22 11 23 11 25 14C27 11 30 10 33 13C34 9 36 7 40 7C36 3 32 3 30 6C26 4 22 5 20 9Z";

/** Bats leaving for the night: where from, which way (px per ms), when. */
function bats(w: number, h: number) {
  const rand = seeded(0xba7);
  return Array.from({ length: 7 }, (_, i) => {
    const left = i % 2 === 0;
    return {
      x: w * (0.4 + rand() * 0.2),
      y: h * (0.55 + rand() * 0.12),
      vx: (left ? -1 : 1) * (0.12 + rand() * 0.14) * (w / 1200),
      vy: -(0.05 + rand() * 0.06) * (h / 900),
      from: 500 + i * 380 + rand() * 300,
      size: 22 + rand() * 18,
      beat: 0.018 + rand() * 0.01,
    };
  });
}

function Sunrise({ onDone }: { onDone: () => void }) {
  const signOut = useSignOut();
  const toast = useToast();
  // The latest of each, for the animation, which outlives renders.
  const now = useRef(signOut.now);
  now.current = signOut.now;
  const tell = useRef(toast);
  tell.current = toast;
  const done = useRef(onDone);
  done.current = onDone;

  const [w, h] = useMemo(() => [window.innerWidth, window.innerHeight], []);
  const scene = useMemo(() => layers(w, h), [w, h]);
  const flock = useMemo(() => bats(w, h), [w, h]);
  const stars = useMemo(() => {
    const rand = seeded(0x57a5);
    return Array.from({ length: 140 }, () => ({ x: rand() * 100, y: rand() * 70, r: rand() < 0.1 ? 2 : 1, o: 0.3 + rand() * 0.7 }));
  }, []);

  const root = useRef<HTMLDivElement>(null);
  const sky = useRef<HTMLDivElement>(null);
  const skyline = useRef<HTMLDivElement>(null);
  const starField = useRef<HTMLDivElement>(null);
  const sun = useRef<HTMLDivElement>(null);
  const glow = useRef<HTMLDivElement>(null);
  const layerEls = useRef<(SVGSVGElement | null)[]>([]);
  const lightEls = useRef<(SVGPathElement | null)[]>([]);
  const batEls = useRef<(HTMLDivElement | null)[]>([]);
  const white = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  /** Once asked, the sign-out: resolves to its error, or null. */
  const signingOut = useRef<Promise<unknown> | null>(null);

  useEffect(() => {
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    let frame = 0;
    let stopped = false;
    let signedOut = false;
    let ashFrom = 0;
    let finishing = false;
    const start = performance.now();

    const pointer = { x: 0, y: 0, sx: 0, sy: 0 };
    const move = (e: PointerEvent) => {
      pointer.x = (e.clientX / w) * 2 - 1;
      pointer.y = (e.clientY / h) * 2 - 1;
    };
    window.addEventListener("pointermove", move);

    const leave = () => {
      if (stopped) return;
      stopped = true;
      done.current();
    };
    const askSignOut = () => {
      if (signingOut.current) return;
      signingOut.current = now.current().then((error) => {
        signedOut = true;
        if (error) tell.current({ message: `You weren't signed out: ${error instanceof Error ? error.message : "something went wrong"}`, duration: 12_000 });
        return error;
      });
    };

    const radius = sunR(w, h);
    const sunFrom = h * 0.8 + radius + 30;
    const sunTo = h * 0.25;
    const scale = h / 900;

    // The ash: one fleck per cell of the screen.
    let ash: ReturnType<typeof makeAsh> | null = null;
    const makeAsh = () => {
      const el = canvas.current!;
      el.width = w;
      el.height = h;
      const ctx = el.getContext("2d")!;
      const cell = Math.max(4, Math.round(Math.sqrt((w * h) / 26000)));
      const cols = Math.ceil(w / cell);
      const rows = Math.ceil(h / cell);
      const n = cols * rows;
      const ox = w / 2;
      const oy = sunTo;
      const far = Math.hypot(Math.max(ox, w - ox), Math.max(oy, h - oy));
      const rand = Math.random;
      const p1 = rand() * 6;
      const p2 = rand() * 6;
      const lit = new Float32Array(n);
      const life = new Float32Array(n);
      const phase = new Float32Array(n);
      const vx = new Float32Array(n);
      const vy = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const x = (i % cols) * cell;
        const y = Math.floor(i / cols) * cell;
        // A ragged front, burning out from where the sun was.
        const ragged = 260 * (Math.sin(x * 0.011 + p1) + Math.sin(y * 0.015 + p2) + Math.sin((x + y) * 0.031)) / 3;
        lit[i] = Math.max(0, (Math.hypot(x - ox, y - oy) / far) * SPREAD + ragged + rand() * 380);
        life[i] = LIFE_MIN + rand() * (LIFE_MAX - LIFE_MIN);
        phase[i] = rand() * Math.PI * 2;
        vx[i] = 0.02 + rand() * 0.05;
        vy[i] = -(0.015 + rand() * 0.06);
      }
      return { ctx, cell, cols, n, lit, life, phase, vx, vy };
    };

    // Ash cools from white to ember to grey: colours by age, and alpha by share of its life.
    const COOL: [number, string][] = [
      [0, WHITE],
      [140, "#ffd27a"],
      [340, "#ff7a2e"],
      [650, "#6b3a2e"],
      [1000, "#4a4446"],
      [1700, "#9a9294"],
    ];
    const HUES = 16;
    const ALPHAS = 10;
    const hues = Array.from({ length: HUES }, (_, i) => along(COOL.map(([t, c]) => [t / 1700, c] as [number, string]), i / (HUES - 1)));

    const drawAsh = (t: number) => {
      const a = ash!;
      const { ctx, cell, cols, n, lit, life, phase, vx, vy } = a;
      ctx.clearRect(0, 0, w, h);
      const whole = new Path2D();
      const buckets: (Path2D | null)[] = new Array(HUES * ALPHAS).fill(null);
      let alive = 0;
      for (let i = 0; i < n; i++) {
        const x0 = (i % cols) * cell;
        const y0 = Math.floor(i / cols) * cell;
        const age = t - lit[i]!;
        if (age <= 0) {
          whole.rect(x0, y0, cell, cell);
          alive++;
          continue;
        }
        const share = age / life[i]!;
        if (share >= 1) continue;
        alive++;
        // Rising on the heat, the wind taking it off to the right, fluttering.
        const x = x0 + vx[i]! * age + 0.00003 * age * age + Math.sin(age * 0.004 + phase[i]!) * 7;
        const y = y0 + vy[i]! * age - 0.000012 * age * age + Math.cos(age * 0.003 + phase[i]!) * 4;
        if (x > w + 20 || y < -20) continue;
        const size = cell * (1 - share * 0.6);
        const hue = Math.min(HUES - 1, Math.floor((age / 1700) * (HUES - 1)));
        const alpha = Math.min(ALPHAS - 1, Math.floor((share < 0.3 ? 1 : 1 - (share - 0.3) / 0.7) * (ALPHAS - 1)));
        const k = hue * ALPHAS + alpha;
        (buckets[k] ??= new Path2D()).rect(x, y, size, size);
      }
      ctx.globalAlpha = 1;
      ctx.fillStyle = WHITE;
      ctx.fill(whole);
      for (let k = 0; k < buckets.length; k++) {
        const path = buckets[k];
        if (!path) continue;
        ctx.globalAlpha = (k % ALPHAS) / (ALPHAS - 1);
        ctx.fillStyle = hues[Math.floor(k / ALPHAS)]!;
        ctx.fill(path);
      }
      return alive;
    };

    const tick = (stamp: number) => {
      if (stopped) return;
      const t = stamp - start;

      if (still) {
        // No motion: the light comes, then goes, and they are signed out.
        const r = root.current!;
        r.style.background = WHITE;
        skyline.current!.style.display = "none";
        if (t < 1500) r.style.opacity = String(smooth(t / 1500));
        else {
          askSignOut();
          if (!signedOut && t < 1500 + SIGN_OUT_WAIT) r.style.opacity = "1";
          else {
            ashFrom ||= t;
            const k = (t - ashFrom) / 1200;
            r.style.opacity = String(1 - smooth(clamp(k)));
            if (k >= 1) return leave();
          }
        }
        frame = requestAnimationFrame(tick);
        return;
      }

      if (!ash) {
        root.current!.style.opacity = String(smooth(clamp(t / FADE_IN)));
        const p = easeInOut(clamp(t / RISE));
        pointer.sx += (pointer.x - pointer.sx) * 0.05;
        pointer.sy += (pointer.y - pointer.sy) * 0.05;

        sky.current!.style.background = `linear-gradient(to bottom, ${along(SKY_TOP, p)} 0%, ${along(SKY_MID, p)} 55%, ${along(SKY_LOW, p)} 85%)`;
        starField.current!.style.opacity = String(clamp(1 - p * 1.8));
        starField.current!.style.transform = `translate3d(${-pointer.sx * 3}px, ${p * 10 * scale}px, 0)`;

        const sy = lerp(sunFrom, sunTo, p);
        const sx = w / 2 - pointer.sx * 4;
        sun.current!.style.transform = `translate3d(${sx - radius}px, ${sy - radius}px, 0)`;
        const g = radius * (5 + p * 12);
        glow.current!.style.width = glow.current!.style.height = `${g * 2}px`;
        glow.current!.style.transform = `translate3d(${sx - g}px, ${sy - g}px, 0)`;
        glow.current!.style.opacity = String(0.25 + p * 0.75);

        scene.forEach((layer, i) => {
          const el = layerEls.current[i];
          if (!el) return;
          el.style.transform = `translate3d(${-pointer.sx * layer.sway}px, ${p * layer.sink * scale - pointer.sy * layer.sway * 0.3}px, 0)`;
          el.style.fill = along(layer.colour, p);
          el.style.stroke = el.style.fill;
          const lights = lightEls.current[i];
          if (lights) lights.style.opacity = String(clamp(1 - p * 2.2));
        });

        flock.forEach((bat, i) => {
          const el = batEls.current[i];
          if (!el) return;
          const age = t - bat.from;
          if (age < 0 || age > 6000) {
            el.style.opacity = "0";
            return;
          }
          const flap = 0.35 + 0.65 * Math.abs(Math.sin(age * bat.beat));
          el.style.opacity = "1";
          el.style.transform = `translate3d(${bat.x + bat.vx * age}px, ${bat.y + bat.vy * age + Math.sin(age * 0.006) * 8}px, 0) scale(${bat.vx < 0 ? -1 : 1}, ${flap})`;
        });

        const k = clamp((t - WHITE_FROM) / (WHITE_TO - WHITE_FROM));
        white.current!.style.opacity = String(smooth(k));
        if (t >= WHITE_FROM) askSignOut();

        if (t >= WHITE_TO && (signedOut || t >= WHITE_TO + SIGN_OUT_WAIT)) {
          ash = makeAsh();
          ashFrom = t;
          drawAsh(0);
          // The canvas now holds the white; under it, the page (signed out, by now).
          skyline.current!.style.display = "none";
          white.current!.style.display = "none";
          root.current!.style.pointerEvents = "none";
        }
      } else {
        const alive = drawAsh(t - ashFrom);
        if (alive === 0 && !finishing) {
          finishing = true;
          return leave();
        }
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", move);
      document.body.style.overflow = overflow;
      // Strict mode runs this once before running the effect again: let it.
      stopped = true;
    };
  }, [w, h, scene, flock]);

  return (
    <>
      <div ref={root} className="fixed inset-0 z-[10000] overflow-hidden" style={{ opacity: 0 }} aria-hidden="true">
        <div ref={skyline} className="absolute inset-0">
          <div ref={sky} className="absolute inset-0" />
          <div ref={starField} className="absolute inset-0 will-change-transform">
            {stars.map((s, i) => (
              <span
                key={i}
                className="absolute rounded-full bg-parchment"
                style={{ left: `${s.x}%`, top: `${s.y}%`, width: s.r, height: s.r, opacity: s.o }}
              />
            ))}
          </div>
          <div
            ref={glow}
            className="absolute top-0 left-0 rounded-full will-change-transform"
            style={{ background: "radial-gradient(circle, rgba(255,214,140,0.85) 0%, rgba(255,160,90,0.35) 30%, rgba(255,120,80,0) 70%)" }}
          />
          <div
            ref={sun}
            className="absolute top-0 left-0 rounded-full will-change-transform"
            style={{
              width: sunR(w, h) * 2,
              height: sunR(w, h) * 2,
              background: "radial-gradient(circle, #fffdf4 0%, #fff1b8 45%, #ffc860 80%, #ff9a4a 100%)",
              boxShadow: "0 0 60px 20px rgba(255,200,110,0.6)",
            }}
          />
          {flock.map((bat, i) => (
            <div
              key={i}
              ref={(el) => {
                batEls.current[i] = el;
              }}
              className="absolute top-0 left-0 will-change-transform"
              style={{ width: bat.size, height: bat.size / 2, opacity: 0 }}
            >
              <svg viewBox="0 0 40 20" className="h-full w-full" fill="#0a080c">
                <path d={BAT} />
              </svg>
            </div>
          ))}
          {scene.map((layer, i) => {
            const lh = Math.round(h * layer.height);
            const lw = w + MARGIN * 2;
            return (
              <svg
                key={i}
                ref={(el) => {
                  layerEls.current[i] = el;
                }}
                className="absolute will-change-transform"
                style={{ left: -MARGIN, bottom: 0, width: lw, height: lh, overflow: "visible" }}
                viewBox={`0 0 ${lw} ${lh}`}
              >
                <path d={layer.d} stroke="none" />
                {/* Solid below the screen's foot, so sinking leaves no gap. */}
                <rect x={0} y={lh - 1} width={lw} height={h} stroke="none" />
                {layer.strokes?.map(([width, d]) => (
                  <path key={width} d={d} fill="none" strokeWidth={width} strokeLinecap="round" />
                ))}
                {layer.lights && (
                  <path
                    ref={(el) => {
                      lightEls.current[i] = el;
                    }}
                    d={layer.lights}
                    style={{ fill: "#e8b85a" }}
                  />
                )}
              </svg>
            );
          })}
        </div>
        <div ref={white} className="absolute inset-0" style={{ background: WHITE, opacity: 0 }} />
        <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
      </div>
      <p role="status" className="sr-only">
        The sun rises. You crumble to ash, and drift away.
      </p>
    </>
  );
}

const sunR = (w: number, h: number) => 0.08 * Math.min(w, h) + 22;
