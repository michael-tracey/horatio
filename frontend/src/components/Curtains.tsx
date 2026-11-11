import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

/*
 * Ultra goth's entrance (#635): red velvet stage curtains close over the page,
 * the theme changes behind them, and they open on it. With "reduce motion" set,
 * a short fade to velvet and back instead.
 *
 * Like the sunrise (Sunrise.tsx) it runs at the root of the app, over everything.
 * It moves only with CSS transforms (index.css, "The curtains"), so it stays
 * smooth on a phone; the velvet is gradients and inline SVG, no pictures.
 */

type Run = { id: number; change: () => void };

let run: Run | null = null;
let runs = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

/** Close the curtains, make `change` while they are closed, and open them again. */
export function drawCurtains(change: () => void) {
  if (run) return;
  runs += 1;
  run = { id: runs, change };
  emit();
}

function useRun() {
  return useSyncExternalStore(
    (changed) => {
      listeners.add(changed);
      return () => listeners.delete(changed);
    },
    () => run,
    () => null,
  );
}

export function CurtainsHost() {
  const now = useRun();
  if (!now) return null;
  return (
    <Curtains
      key={now.id}
      change={now.change}
      onDone={() => {
        run = null;
        emit();
      }}
    />
  );
}

/** How long each part takes, in ms: closing, closed, opening (to the valance gone). */
export const MOVING = { close: 1150, hold: 650, open: 1650 };
export const STILL = { close: 250, hold: 150, open: 300 };

type Phase = "closing" | "closed" | "opening";

function useWindowSize(): [number, number] {
  const [size, setSize] = useState<[number, number]>(() => [window.innerWidth, window.innerHeight]);
  useEffect(() => {
    const resize = () => setSize([window.innerWidth, window.innerHeight]);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  return size;
}

function Curtains({ change, onDone }: { change: () => void; onDone: () => void }) {
  const still = useMemo(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false, []);
  const [phase, setPhase] = useState<Phase>("closing");
  const [w, h] = useWindowSize();
  // The latest of each, for the timeline, which outlives renders.
  const make = useRef(change);
  make.current = change;
  const done = useRef(onDone);
  done.current = onDone;
  const changed = useRef(false);

  useEffect(() => {
    const t = still ? STILL : MOVING;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const timers = [
      window.setTimeout(() => {
        // Strict mode runs this effect twice: the change is made once.
        if (!changed.current) {
          changed.current = true;
          make.current();
        }
        setPhase("closed");
      }, t.close),
      window.setTimeout(() => setPhase("opening"), t.close + t.hold),
      window.setTimeout(() => done.current(), t.close + t.hold + t.open),
    ];
    return () => {
      timers.forEach(clearTimeout);
      document.body.style.overflow = overflow;
    };
  }, [still]);

  return (
    <>
      <div className={`curtains curtains-${phase}`} data-testid="curtains" data-phase={phase} aria-hidden="true">
        {still ? (
          <div className="curtain-fade" />
        ) : (
          <>
            <div className="curtain curtain-left" />
            <div className="curtain curtain-right" />
            <div className="curtain-light" />
            <Valance w={w} h={h} />
          </>
        )}
      </div>
      <p role="status" className="sr-only">
        The curtains close, and open on Ultra goth.
      </p>
    </>
  );
}

const GOLD_DARK = "#6b4a12";

/** The valance across the top: velvet swags edged with gold rope, a tassel between each. */
function Valance({ w, h }: { w: number; h: number }) {
  const v = Math.round(Math.min(150, Math.max(56, h * 0.15)));
  const n = Math.min(7, Math.max(3, Math.round(w / 240)));
  const sw = w / n;
  const join = v * 0.58;
  const low = v * 0.92;
  const dip = 2 * low - join;
  const tassel = Math.max(26, v * 0.5);
  const rope = Math.max(3, v * 0.05);
  const pleat = Math.min(34, Math.max(16, w / 44));

  const swags = Array.from({ length: n }, (_, i) => [i * sw, (i + 1) * sw] as const);
  let body = `M0 0H${w}V${join}`;
  for (const [x0, x1] of [...swags].reverse()) body += `Q${(x0 + x1) / 2} ${dip} ${x0} ${join}`;
  body += "Z";
  const edge = `M0 ${join}` + swags.map(([x0, x1]) => `Q${(x0 + x1) / 2} ${dip} ${x1} ${join}`).join("");
  // The folds each swag falls in: curves like its edge, higher up.
  const folds = swags.flatMap(([x0, x1]) =>
    [0.32, 0.56, 0.78].map((t) => {
      const end = join * (0.12 + 0.7 * t);
      const mid = end + (low - join) * t + join * 0.22 * t;
      return `M${x0 + sw * 0.03} ${end}Q${(x0 + x1) / 2} ${2 * mid - end} ${x1 - sw * 0.03} ${end}`;
    }),
  );

  return (
    <svg className="curtain-valance" width={w} height={v + tassel} viewBox={`0 0 ${w} ${v + tassel}`}>
      <defs>
        <linearGradient id="ug-pleat" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#2b0308" />
          <stop offset="0.25" stopColor="#6a0c19" />
          <stop offset="0.5" stopColor="#b51f35" />
          <stop offset="0.72" stopColor="#7a0f1e" />
          <stop offset="1" stopColor="#2b0308" />
        </linearGradient>
        <pattern id="ug-velvet" width={pleat} height={v} patternUnits="userSpaceOnUse">
          <rect width={pleat} height={v} fill="url(#ug-pleat)" />
        </pattern>
        <linearGradient id="ug-shade" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#000" stopOpacity="0.6" />
          <stop offset="0.45" stopColor="#000" stopOpacity="0.05" />
          <stop offset="1" stopColor="#000" stopOpacity="0.35" />
        </linearGradient>
        <linearGradient id="ug-gold" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#f7e08f" />
          <stop offset="0.4" stopColor="#d4a43c" />
          <stop offset="0.75" stopColor="#8a6418" />
          <stop offset="1" stopColor="#c99a36" />
        </linearGradient>
        <linearGradient id="ug-gold-side" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#7a5514" />
          <stop offset="0.35" stopColor="#f0d27a" />
          <stop offset="0.6" stopColor="#c99a36" />
          <stop offset="1" stopColor="#5e400c" />
        </linearGradient>
        <radialGradient id="ug-gold-ball" cx="0.35" cy="0.3" r="0.75">
          <stop offset="0" stopColor="#fff2b8" />
          <stop offset="0.45" stopColor="#d4a43c" />
          <stop offset="1" stopColor="#5e400c" />
        </radialGradient>
      </defs>
      <path d={body} fill="url(#ug-velvet)" />
      <path d={body} fill="url(#ug-shade)" />
      {folds.map((d, i) => (
        <g key={i}>
          <path d={d} fill="none" stroke="#000" strokeOpacity="0.38" strokeWidth={Math.max(2, v * 0.035)} strokeLinecap="round" />
          <path d={d} fill="none" stroke="#ff7a88" strokeOpacity="0.14" strokeWidth={Math.max(1, v * 0.015)} strokeLinecap="round" transform="translate(0 -2.5)" />
        </g>
      ))}
      {/* A braid along the top and a rope along the swags, twisted. */}
      <rect y={0} width={w} height={rope * 1.6} fill="url(#ug-gold)" />
      <path d={edge} fill="none" stroke="url(#ug-gold)" strokeWidth={rope} strokeLinecap="round" />
      <path d={edge} fill="none" stroke={GOLD_DARK} strokeOpacity="0.55" strokeWidth={rope * 0.5} strokeDasharray={`${rope} ${rope}`} />
      {swags.slice(1).map(([x0], i) => (
        <g key={i} transform={`translate(${x0} ${join - rope})`}>
          <g className="curtain-tassel" style={{ animationDelay: `${(i % 3) * 90}ms` }}>
            <Tassel size={tassel} />
          </g>
        </g>
      ))}
    </svg>
  );
}

/** A gold tassel hanging from (0, 0), `size` long. */
function Tassel({ size: s }: { size: number }) {
  const strands = [-0.11, -0.055, 0, 0.055, 0.11];
  return (
    <>
      <path d={`M0 0V${s * 0.2}`} stroke="url(#ug-gold-side)" strokeWidth={Math.max(1.5, s * 0.05)} />
      <ellipse cy={s * 0.28} rx={s * 0.12} ry={s * 0.12} fill="url(#ug-gold-ball)" />
      <rect x={-s * 0.08} y={s * 0.38} width={s * 0.16} height={s * 0.07} rx={s * 0.02} fill="url(#ug-gold-side)" />
      <path d={`M${-s * 0.07} ${s * 0.45}L${-s * 0.17} ${s * 0.96}Q0 ${s * 1.03} ${s * 0.17} ${s * 0.96}L${s * 0.07} ${s * 0.45}Z`} fill="url(#ug-gold-side)" />
      {strands.map((x) => (
        <path key={x} d={`M${x * s * 0.6} ${s * 0.48}L${x * s * 1.45} ${s * 0.97}`} stroke={GOLD_DARK} strokeOpacity="0.55" strokeWidth={Math.max(0.8, s * 0.018)} />
      ))}
    </>
  );
}
