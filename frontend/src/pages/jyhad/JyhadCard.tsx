import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import type { components } from "../../api/schema";
import {
  ART,
  CARD,
  CLAN,
  COLOURS,
  DISPLAY,
  DROP,
  DROP_PATH,
  DROP_VIEW,
  FOOTER,
  NAME,
  NOTICE,
  SERIF,
  TEXT,
  UNOFFICIAL,
  CAPACITY_BASELINE,
  CAPACITY_SIZE,
  canvasMeasure,
  canvasNameMeasure,
  clanLetters,
  disciplineBox,
  layoutText,
  nameSize,
  type Box,
  type Measure,
} from "./layout";

export type JyhadCardOut = components["schemas"]["JyhadCardOut"];

/** A length in the card's millimetres: real size printed, larger on screen. */
const mm = (n: number) => `calc(${+n.toFixed(3)} * var(--mm))`;
const at = (b: Box): CSSProperties => ({ position: "absolute", left: mm(b.x), top: mm(b.y), width: mm(b.w), height: mm(b.h) });
const exact: CSSProperties = { printColorAdjust: "exact", WebkitPrintColorAdjust: "exact" };

/** A rough measure where there's no canvas (tests): wide enough never to overflow. */
const rough: Measure = (text, size) => text.length * size * 0.55;

/** Measures text as the canvas draws it, once the card's fonts have loaded. */
function useMeasures(): { text: Measure; name: Measure } {
  const [fonts, setFonts] = useState(0);
  useEffect(() => {
    let live = true;
    document.fonts?.load(`700 20px ${DISPLAY}`).then(() => live && setFonts((n) => n + 1), () => {});
    return () => {
      live = false;
    };
  }, []);
  return useMemo(() => {
    void fonts;
    const ctx = typeof document !== "undefined" ? document.createElement("canvas").getContext?.("2d") : null;
    return ctx ? { text: canvasMeasure(ctx), name: canvasNameMeasure(ctx) } : { text: rough, name: rough };
  }, [fonts]);
}

/**
 * A character's Jyhad card, laid out as layout.ts says, at `--mm` to the millimetre
 * (set by the page: 1mm in print). `text` and `flavour` are as typed, so the card
 * shows them before they're saved.
 */
export function JyhadCard({ card, clanName, text, flavour }: { card: JyhadCardOut; clanName: string | null; text: string; flavour: string }) {
  const measure = useMeasures();
  const laid = useMemo(() => layoutText(card.sect_line, text, flavour, measure.text), [card.sect_line, text, flavour, measure]);
  const named = useMemo(() => nameSize(card.name, measure.name), [card.name, measure]);
  return (
    <article
      aria-label={`Jyhad card of ${card.name}`}
      className="relative shrink-0 overflow-hidden select-none"
      style={{ ...exact, width: mm(CARD.width), height: mm(CARD.height), borderRadius: mm(CARD.radius), background: COLOURS.frame, color: COLOURS.ink }}
    >
      {card.picture && (
        <img
          src={`${card.picture}/portrait.webp`}
          alt=""
          className="object-cover"
          style={{ ...at(ART), objectPosition: "50% 30%", borderRadius: mm(1.5) }}
        />
      )}
      <Plate box={CLAN} round label={clanName ? `Clan: ${clanName}` : undefined}>
        {card.clan_symbol ? (
          <img src={card.clan_symbol} alt="" style={{ width: "72%", height: "72%" }} className="object-contain" />
        ) : (
          <span style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: mm(2.6) }}>{clanLetters(clanName)}</span>
        )}
      </Plate>
      <ul aria-label="Disciplines">
        {card.disciplines.map((d, i) => (
          <li key={d.name} aria-label={`${d.name}${d.superior ? ", superior" : ""}`}>
            <Plate box={disciplineBox(i)} round={!d.superior} ring={d.superior ? COLOURS.gold : COLOURS.ink}>
              {d.symbol ? (
                <img src={d.symbol} alt="" style={{ width: "74%", height: "74%" }} className="object-contain" />
              ) : (
                <span style={{ fontFamily: SERIF, fontWeight: 700, fontSize: mm(d.superior ? 2.3 : 2.1) }}>
                  {d.superior ? d.abbreviation.toUpperCase() : d.abbreviation}
                </span>
              )}
            </Plate>
          </li>
        ))}
      </ul>
      {/* The words, in an SVG of the card's millimetres: placed on their baselines,
          as the canvas places them, so screen, print and image match. */}
      <svg viewBox={`0 0 ${CARD.width} ${CARD.height}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
        <rect x={NAME.x} y={NAME.y} width={NAME.w} height={NAME.h} rx={1} fill={COLOURS.plate} stroke={COLOURS.gold} strokeWidth={0.3} />
        <text x={NAME.x + NAME.w / 2} y={NAME.y + NAME.h / 2 + named * 0.36} textAnchor="middle" fontFamily={DISPLAY} fontWeight={700} fontSize={named} fill={COLOURS.ink}>
          {card.name}
        </text>
        <rect x={TEXT.x} y={TEXT.y} width={TEXT.w} height={TEXT.h} rx={1} fill={COLOURS.parchment} />
        {laid.lines.map((l, i) => (
          <text
            key={i}
            x={l.x}
            y={l.y}
            fontFamily={SERIF}
            fontSize={laid.size}
            fontWeight={l.style === "bold" ? 700 : 400}
            fontStyle={l.style === "italic" ? "italic" : "normal"}
            fill={COLOURS.ink}
          >
            {l.text}
          </text>
        ))}
        {card.capacity !== null && (
          <g>
            <path d={DROP_PATH} transform={`translate(${DROP.x} ${DROP.y}) scale(${DROP.w / DROP_VIEW.w} ${DROP.h / DROP_VIEW.h})`} fill={COLOURS.blood} stroke={COLOURS.ink} strokeWidth={0.4} />
            <text x={DROP.x + DROP.w / 2} y={DROP.y + DROP.h * CAPACITY_BASELINE} textAnchor="middle" fontFamily={DISPLAY} fontWeight={700} fontSize={CAPACITY_SIZE} fill="#ffffff">
              {card.capacity}
            </text>
          </g>
        )}
        {[
          [UNOFFICIAL, FOOTER.y1],
          [NOTICE, FOOTER.y2],
        ].map(([line, y]) => (
          <text key={line} x={CARD.width / 2} y={y} textAnchor="middle" fontFamily={SERIF} fontSize={FOOTER.size} fill={COLOURS.footer}>
            {line}
          </text>
        ))}
      </svg>
      {/* For screen readers, what the drawing says. */}
      <p className="sr-only">
        {card.sect_line ? `${card.sect_line}. ` : ""}
        {card.capacity !== null ? `Capacity ${card.capacity}. ` : ""}
        {text} {flavour}
      </p>
    </article>
  );
}

/** A parchment plate for a symbol: round, or square for a superior discipline. */
function Plate({ box, round, ring = COLOURS.gold, label, children }: { box: Box; round?: boolean; ring?: string; label?: string; children: ReactNode }) {
  return (
    <div
      aria-label={label}
      style={{ ...at(box), ...exact, background: COLOURS.parchment, borderRadius: round ? "50%" : mm(1.2), boxShadow: `0 0 0 ${mm(0.35)} ${ring}` }}
      className="flex items-center justify-center overflow-hidden"
    >
      {children}
    </div>
  );
}
