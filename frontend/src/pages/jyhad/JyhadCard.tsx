import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import type { components } from "../../api/schema";
import { frameSvg, svgUrl, symbolTints, tintedSymbol } from "./frame";
import {
  ART,
  CAPACITY,
  CAPACITY_BASELINE,
  CAPACITY_SIZE,
  CARD,
  CLAN,
  COLOURS,
  DISPLAY,
  DROP,
  DROP_PATH,
  DROP_VIEW,
  FACES,
  FOOTER,
  LOOKS,
  NAME,
  NAME_TEXT,
  NOTICE,
  SERIF,
  SYMBOL_SHARE,
  TEXT,
  TEXT_PAD,
  UNOFFICIAL,
  canvasMeasure,
  canvasNameMeasure,
  clanLetters,
  disciplineBox,
  layoutText,
  lookOf,
  nameFit,
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
    Promise.all(FACES.map((f) => document.fonts?.load(f))).then(
      () => live && setFonts((n) => n + 1),
      () => {},
    );
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

/** KRCG's symbols, tinted for the frame (as the image draws them): a data: URL each,
 * undefined while loading, null if it couldn't be had (then its letters show). */
function useSymbols(card: JyhadCardOut, clanTint: string, disciplineTint: string) {
  const sources = useMemo(
    () => [
      [card.clan_symbol, clanTint],
      ...card.disciplines.map((d) => [d.symbol, disciplineTint]),
    ] as [string | null, string][],
    [card.clan_symbol, card.disciplines, clanTint, disciplineTint],
  );
  const [found, setFound] = useState<(string | null | undefined)[]>([]);
  useEffect(() => {
    let live = true;
    setFound(sources.map(([src]) => (src ? undefined : null)));
    Promise.all(sources.map(([src, colour]) => (src ? tintedSymbol(src, colour) : null))).then((urls) => live && setFound(urls));
    return () => {
      live = false;
    };
  }, [sources]);
  return { clan: found[0], disciplines: found.slice(1) };
}

/**
 * A character's Jyhad card, laid out as layout.ts says, at `--mm` to the millimetre
 * (set by the page: 1mm in print): the portrait, the frame over it (frame.ts), and
 * the symbols and words over that. `text` and `flavour` are as typed, so the card
 * shows them before they're saved.
 */
export function JyhadCard({ card, clanName, text, flavour }: { card: JyhadCardOut; clanName: string | null; text: string; flavour: string }) {
  const measure = useMeasures();
  const look = lookOf(card.sect);
  const palette = LOOKS[look];
  const tints = symbolTints(look);
  const symbols = useSymbols(card, tints.clan, tints.discipline);
  const laid = useMemo(() => layoutText(card.sect_line, text, flavour, measure.text), [card.sect_line, text, flavour, measure]);
  const named = useMemo(() => nameFit(card.name, measure.name), [card.name, measure]);
  const frame = useMemo(
    () => svgUrl(frameSvg({ look, superior: card.disciplines.map((d) => d.superior), capacity: card.capacity !== null })),
    [look, card.disciplines, card.capacity],
  );
  return (
    <article
      aria-label={`Jyhad card of ${card.name}`}
      data-look={look}
      className="relative shrink-0 overflow-hidden select-none"
      style={{ ...exact, width: mm(CARD.width), height: mm(CARD.height), borderRadius: mm(CARD.radius), background: COLOURS.edge, color: COLOURS.ink }}
    >
      {card.picture && (
        <img src={`${card.picture}/portrait.webp`} alt="" className="object-cover" style={{ ...at(ART), objectPosition: "50% 30%" }} />
      )}
      <img src={frame} alt="" className="pointer-events-none absolute inset-0 h-full w-full" />
      <Symbol box={CLAN} label={clanName ? `Clan: ${clanName}` : undefined} src={symbols.clan} share={SYMBOL_SHARE.clan}>
        <span style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: mm(2.6), color: palette.name }}>{clanLetters(clanName)}</span>
      </Symbol>
      <ul aria-label="Disciplines">
        {card.disciplines.map((d, i) => (
          <li key={d.name} aria-label={`${d.name}${d.superior ? ", superior" : ""}`}>
            <Symbol box={disciplineBox(i)} src={symbols.disciplines[i]} share={d.superior ? SYMBOL_SHARE.superior : SYMBOL_SHARE.inferior}>
              <span style={{ fontFamily: SERIF, fontWeight: 700, fontSize: mm(d.superior ? 2.3 : 2.4) }}>
                {d.superior ? d.abbreviation.toUpperCase() : d.abbreviation}
              </span>
            </Symbol>
          </li>
        ))}
      </ul>
      {/* The words and the capacity, in an SVG of the card's millimetres: placed on
          their baselines, as the canvas places them, so screen, print and image match. */}
      <svg viewBox={`0 0 ${CARD.width} ${CARD.height}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
        <text
          x={NAME_TEXT.x + NAME_TEXT.w / 2}
          y={NAME.y + NAME.h / 2 + named.size * 0.36}
          textAnchor="middle"
          fontFamily={DISPLAY}
          fontWeight={700}
          fontSize={named.size}
          {...(named.squeeze !== null && { textLength: named.squeeze, lengthAdjust: "spacingAndGlyphs" })}
          fill={palette.name}
        >
          {card.name}
        </text>
        {laid.rule !== null && (
          <line x1={TEXT.x + TEXT_PAD} x2={TEXT.x + TEXT.w - TEXT_PAD} y1={laid.rule} y2={laid.rule} stroke={palette.trim} strokeWidth={0.15} />
        )}
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
            {card.capacity_symbol ? (
              <image href={card.capacity_symbol} x={CAPACITY.x} y={CAPACITY.y} width={CAPACITY.w} height={CAPACITY.h} />
            ) : (
              <path
                d={DROP_PATH}
                transform={`translate(${DROP.x} ${DROP.y}) scale(${DROP.w / DROP_VIEW.w} ${DROP.h / DROP_VIEW.h})`}
                fill={COLOURS.blood}
                stroke={palette.trim}
                strokeWidth={0.4}
              />
            )}
            <text
              x={CAPACITY.x + CAPACITY.w / 2}
              y={CAPACITY.y + CAPACITY.h * CAPACITY_BASELINE}
              textAnchor="middle"
              fontFamily={DISPLAY}
              fontWeight={700}
              fontSize={CAPACITY_SIZE}
              fill="#ffffff"
              stroke="#2a0008"
              strokeWidth={0.35}
              paintOrder="stroke"
            >
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

/** A symbol on its plate (the frame draws the plate): KRCG's, tinted, or its letters
 * without it. Nothing while it loads. */
function Symbol({ box, src, share, label, children }: { box: Box; src: string | null | undefined; share: number; label?: string; children: ReactNode }) {
  return (
    <div aria-label={label} style={{ ...at(box), ...exact }} className="flex items-center justify-center">
      {src ? (
        <img src={src} alt="" style={{ width: `${share * 100}%`, height: `${share * 100}%` }} className="object-contain" />
      ) : src === null ? (
        children
      ) : null}
    </div>
  );
}
