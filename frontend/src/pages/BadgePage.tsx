import { useQuery } from "@tanstack/react-query";
import { Fragment, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../api/client";
import type { BadgeOut, StaffBadgeOut } from "../api/types";
import { clanColour, initials } from "../components/avatar";
import { useClanName } from "../components/ClanNames";
import { usePreferences } from "../hooks";
import { PAPERS, pageRule } from "../paper";
import { BADGE_SIZES, grid, nameSize, pages, perPageText, SQUEEZE, standing, type BadgeSize } from "./badgeLayout";

/** White with Horatio's colours as accents, or black on white for a printer without colour. */
type Look = "horatio" | "plain";

/** Badges for characters in a troupe: those in `?characters=`, in that order, or everyone. */
export function TroupeBadgesPage() {
  const { troupeId = "" } = useParams();
  const [params] = useSearchParams();
  const ids = params.get("characters")?.split(",").filter(Boolean);
  const badges = useQuery({
    queryKey: ["badges", troupeId, ids ?? "all"],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/badges", { params: { path: { troupe_id: troupeId }, query: { characters: ids } } })),
  });
  if (badges.isPending) return <p className="p-8 text-black">Loading…</p>;
  if (badges.error) return <p className="p-8 text-black">{badges.error.message}</p>;
  return (
    <Sheets
      back={`/troupes/${troupeId}/characters`}
      troupe={badges.data.troupe_name}
      printStatus={badges.data.print_status}
      items={badges.data.badges.map((b) => ({ key: b.character_id, badge: b }))}
    />
  );
}

/** One character's badge, from its page. */
export function CharacterBadgePage() {
  const { characterId = "" } = useParams();
  const [params] = useSearchParams();
  const badges = useQuery({
    queryKey: ["badge", characterId, params.get("troupe")],
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_id}/badge", {
          params: { path: { character_id: characterId }, query: { troupe_id: params.get("troupe") ?? undefined } },
        }),
      ),
  });
  if (badges.isPending) return <p className="p-8 text-black">Loading…</p>;
  if (badges.error) return <p className="p-8 text-black">{badges.error.message}</p>;
  return (
    <Sheets
      back={`/characters/${characterId}`}
      troupe={badges.data.troupe_name}
      printStatus={badges.data.print_status}
      items={badges.data.badges.map((b) => ({ key: b.character_id, badge: b }))}
    />
  );
}

/** The troupe's storytellers' badges: name and role. */
export function StaffBadgesPage() {
  const { troupeId = "" } = useParams();
  const staff = useQuery({
    queryKey: ["staff-badges", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/staff-badges", { params: { path: { troupe_id: troupeId } } })),
  });
  if (staff.isPending) return <p className="p-8 text-black">Loading…</p>;
  if (staff.error) return <p className="p-8 text-black">{staff.error.message}</p>;
  return (
    <Sheets back={`/troupes/${troupeId}/characters`} troupe={staff.data.troupe_name} items={staff.data.staff.map((s, i) => ({ key: `${i}`, staff: s }))} />
  );
}

type Item = { key: string; badge?: BadgeOut; staff?: StaffBadgeOut };

/**
 * The badges on paper: on screen, side by side with Back, the size, the look and
 * Print above; printed, as many to a page as the person's paper holds, touching,
 * with cut marks in the margin along every cut line.
 */
function Sheets({ items, back, troupe, printStatus = "all" }: { items: Item[]; back: string; troupe: string | null; printStatus?: string }) {
  const prefs = usePreferences();
  const [look, setLook] = useState<Look>("horatio");
  // The person's badge size, unless they pick another for this print.
  const [size, setSize] = useState<BadgeSize>(prefs.badge_size);
  const paper = PAPERS[prefs.paper];
  const { columns, perPage } = grid(size, prefs.paper);
  const badge = BADGE_SIZES[size];
  return (
    <div className="min-h-screen bg-neutral-200 py-6 text-black print:min-h-0 print:bg-white print:py-0">
      {/* Badges fill the paper themselves: no page margin, no browser header. */}
      <style>{pageRule(prefs.paper, "0")}</style>
      <div className="mx-auto mb-4 flex max-w-[8.5in] flex-wrap items-center justify-between gap-3 px-4 print:hidden">
        {/* A link, not history: badges open in a tab of their own. */}
        <Link to={back} className="text-sm underline">
          ← Back
        </Link>
        <span className="text-sm">
          {items.length === 1 ? "1 badge" : `${items.length} badges`} · {perPageText(perPage, prefs.paper)}
        </span>
        <span className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm">
            Size
            <select value={size} onChange={(e) => setSize(e.target.value as BadgeSize)} className="rounded border border-neutral-400 bg-white px-1 py-0.5">
              {Object.entries(BADGE_SIZES).map(([value, { label }]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={look === "plain"} onChange={(e) => setLook(e.target.checked ? "plain" : "horatio")} />
            Black and white
          </label>
          <button onClick={() => window.print()} className="rounded bg-black px-4 py-1.5 text-sm text-white">
            Print
          </button>
        </span>
      </div>
      {items.length === 0 && <p className="text-center text-sm">No one to make a badge for.</p>}
      {pages(items, perPage).map((page, i) => {
        const across = Math.min(columns, page.length);
        return (
          <section
            key={i}
            aria-label={`Page ${i + 1}`}
            style={{ "--page-w": `${paper.width}in`, "--page-h": `${paper.height}in` } as CSSProperties}
            className="mb-6 px-4 print:mb-0 print:flex print:h-(--page-h) print:w-(--page-w) print:items-center print:justify-center print:px-0 print:break-after-page print:last:break-after-auto"
          >
            <div
              className="relative mx-auto flex max-w-[8.5in] flex-wrap justify-center gap-6 print:mx-0 print:grid print:max-w-none print:gap-0"
              style={{ gridTemplateColumns: `repeat(${across}, ${badge.width}in)` }}
            >
              {page.map((item) =>
                item.badge ? (
                  <CharacterBadge key={`${item.key}/${size}`} badge={item.badge} troupe={troupe} printStatus={printStatus} look={look} size={size} />
                ) : item.staff ? (
                  <StaffBadge key={`${item.key}/${size}`} staff={item.staff} troupe={troupe} look={look} size={size} />
                ) : null,
              )}
              <CutMarks across={across} down={Math.ceil(page.length / columns)} />
            </div>
          </section>
        );
      })}
    </div>
  );
}

/** Short marks just outside the badges, in line with every edge, to cut along. Printed only. */
function CutMarks({ across, down }: { across: number; down: number }) {
  const mark = "absolute hidden bg-black print:block";
  const at = (n: number) => Array.from({ length: n + 1 }, (_, i) => `${(i / n) * 100}%`);
  return (
    <>
      {at(across).map((x) => (
        <Fragment key={`x${x}`}>
          <span className={`${mark} -top-[0.2in] h-[0.16in] w-px -translate-x-1/2`} style={{ left: x }} />
          <span className={`${mark} -bottom-[0.2in] h-[0.16in] w-px -translate-x-1/2`} style={{ left: x }} />
        </Fragment>
      ))}
      {at(down).map((y) => (
        <Fragment key={`y${y}`}>
          <span className={`${mark} -left-[0.2in] h-px w-[0.16in] -translate-y-1/2`} style={{ top: y }} />
          <span className={`${mark} -right-[0.2in] h-px w-[0.16in] -translate-y-1/2`} style={{ top: y }} />
        </Fragment>
      ))}
    </>
  );
}

/** Both print on white, to spare the ink: colour only in the accents and the band. */
const LOOKS = {
  horatio: {
    ink: "#a3253a",
    card: "border-[#a3253a]",
    accent: "text-[#a3253a]",
    band: "bg-[#a3253a] text-white",
    frame: "border-[#c9a24a]",
  },
  plain: {
    ink: "#000000",
    card: "border-black",
    accent: "text-black",
    band: "bg-black text-white",
    frame: "border-black",
  },
} as const;

/** Keeps the band's colour when printed, which browsers drop by default. */
const exact: CSSProperties = { printColorAdjust: "exact", WebkitPrintColorAdjust: "exact" };

/** A size's lengths, from the 3 × 5 in badge's, squeezed `step`s: `inch` for the
 * picture and spacing, `pt` for the smaller text, `name` for the name. */
function scale(size: BadgeSize, step = 0) {
  const s = BADGE_SIZES[size];
  const [text, frame] = SQUEEZE[step]!;
  return {
    inch: (x: number) => `${+(x * s.frame * frame).toFixed(3)}in`,
    pt: (x: number) => `${+(x * s.text * text).toFixed(2)}pt`,
    name: (name: string) => `${+(nameSize(name, size) * frame).toFixed(1)}pt`,
  };
}

/** How far a badge is squeezed to fit its card (see SQUEEZE): after each render,
 * a step further while its contents overflow; again from the start whenever
 * fonts finish loading, since they change the text's size. */
function useSqueeze(): [RefObject<HTMLElement | null>, number] {
  const card = useRef<HTMLElement>(null);
  const [step, setStep] = useState(0);
  const [, setFonts] = useState(0);
  useLayoutEffect(() => {
    const el = card.current;
    if (el && el.scrollHeight > el.clientHeight + 1 && step < SQUEEZE.length - 1) setStep(step + 1);
  });
  useEffect(() => {
    const fonts = document.fonts;
    if (!fonts) return;
    const again = () => {
      setStep(0);
      setFonts((n) => n + 1);
    };
    fonts.addEventListener("loadingdone", again);
    return () => fonts.removeEventListener("loadingdone", again);
  }, []);
  return [card, step];
}

/** The badge's card, white, with the troupe's name small on its bottom line. */
function Card({
  look,
  label,
  troupe,
  size,
  step,
  card,
  children,
}: {
  look: Look;
  label: string;
  troupe: string | null;
  size: BadgeSize;
  step: number;
  card: RefObject<HTMLElement | null>;
  children: ReactNode;
}) {
  const { inch, pt } = scale(size, step);
  const { width, height } = BADGE_SIZES[size];
  return (
    <article
      ref={card}
      aria-label={label}
      style={{ ...exact, width: `${width}in`, height: `${height}in`, padding: `${inch(0.15)} ${inch(0.15)} 0` }}
      className={`relative flex shrink-0 flex-col overflow-hidden border-[0.03in] bg-white font-serif text-[#141016] shadow print:shadow-none ${LOOKS[look].card}`}
    >
      {children}
      <p style={{ height: inch(0.25), paddingTop: inch(0.06), fontSize: `max(${pt(7.5)}, 5.5pt)` }} className="shrink-0 truncate text-center tracking-wide">
        {troupe}
      </p>
    </article>
  );
}

/** The portrait (4:5) with the clan logo beside it; without a picture the logo,
 * larger; with neither, the initials. */
function Top({
  name,
  picture,
  logo,
  clan,
  look,
  size,
  step,
}: {
  name: string;
  picture: string | null;
  logo: string | null;
  clan: string | null;
  look: Look;
  size: BadgeSize;
  step: number;
}) {
  const { inch } = scale(size, step);
  const frame = LOOKS[look].frame;
  if (picture) {
    return (
      <div style={{ height: inch(2), gap: inch(0.1) }} className="flex shrink-0 items-start justify-center">
        <img src={`${picture}/portrait.jpg`} alt="" style={{ height: inch(2), width: inch(1.6) }} className={`border object-cover ${frame}`} />
        {logo && <img src={`${logo}/600.webp`} alt={`${clan} logo`} style={{ height: inch(0.85), width: inch(0.85) }} className="object-contain" />}
      </div>
    );
  }
  if (logo) {
    return (
      <div style={{ height: inch(2) }} className="flex shrink-0 justify-center">
        <img src={`${logo}/600.webp`} alt={`${clan} logo`} style={{ height: inch(1.9), width: inch(1.9) }} className="object-contain" />
      </div>
    );
  }
  return <Initials name={name} colour={look === "horatio" ? clanColour(clan) : LOOKS.plain.ink} size={size} step={step} />;
}

/** The name's initials in a ring, outlined rather than filled to spare the ink. */
function Initials({ name, colour, size, step }: { name: string; colour: string; size: BadgeSize; step: number }) {
  const { inch } = scale(size, step);
  return (
    <div style={{ height: inch(2) }} className="flex shrink-0 justify-center">
      <span
        style={{ color: colour, borderColor: colour, height: inch(1.9), width: inch(1.9), borderWidth: inch(0.04), fontSize: `${+(54 * BADGE_SIZES[size].frame * SQUEEZE[step]![1]).toFixed(1)}pt` }}
        className="grid place-items-center rounded-full font-display leading-none"
      >
        {initials(name)}
      </span>
    </div>
  );
}

/**
 * A character's badge. Its troupe chooses what prints (`printStatus`): all the status
 * it carries into a game, "—" for none; only negative status, and the line only
 * if it has some; or no status line. Negative status is marked out in reversed
 * text, as the visible traits are.
 */
function CharacterBadge({
  badge,
  troupe,
  printStatus,
  look,
  size,
}: {
  badge: BadgeOut;
  troupe: string | null;
  printStatus: string;
  look: Look;
  size: BadgeSize;
}) {
  const l = LOOKS[look];
  const named = useClanName();
  const anyStatus = badge.status.length + badge.negative.length > 0;
  const [card, step] = useSqueeze();
  const { inch, pt, name } = scale(size, step);
  return (
    <Card look={look} label={`Badge for ${badge.name}`} troupe={troupe} size={size} step={step} card={card}>
      <Top name={badge.name} picture={badge.picture} logo={badge.logo} clan={badge.clan} look={look} size={size} step={step} />
      <h2 className="text-center font-display leading-tight tracking-wide uppercase" style={{ marginTop: inch(0.1), fontSize: name(badge.name) }}>
        {badge.name}
      </h2>
      {badge.pronouns && (
        <p className="text-center leading-tight" style={{ fontSize: pt(11) }}>
          {badge.pronouns}
        </p>
      )}
      <p className={`text-center ${l.accent}`} style={{ fontSize: pt(12.5) }}>
        {standing(named(badge.clan), badge.social_age)}
      </p>
      {badge.titles.length > 0 && (
        <p className="text-center leading-snug italic" style={{ fontSize: pt(11) }}>
          {badge.titles.join(", ")}
        </p>
      )}
      {(printStatus === "all" || anyStatus) && (
        <p className="leading-snug" style={{ marginTop: inch(0.1), fontSize: pt(10.5) }}>
          <span className={`font-bold ${l.accent}`}>Status:</span> {badge.status.join(", ")}
          {!anyStatus && "—"}
          {badge.negative.map((n, i) => (
            <Fragment key={n}>
              {i > 0 || badge.status.length > 0 ? ", " : ""}
              <span aria-label={`Negative status: ${n}`} style={{ ...exact, paddingInline: inch(0.04) }} className={`font-semibold whitespace-nowrap ${l.band}`}>
                {n}
              </span>
            </Fragment>
          ))}
        </p>
      )}
      {/* Left empty for the stickers most troupes mark status with. */}
      <div className="flex-1" style={{ minHeight: inch(0.4) }} />
      {badge.visible.length > 0 && (
        <ul
          aria-label="What others can see"
          style={{ ...exact, marginInline: `-${inch(0.15)}`, padding: `${inch(0.08)} ${inch(0.15)}`, minHeight: inch(0.5), fontSize: pt(10) }}
          className={`flex flex-col items-center justify-center text-center leading-snug font-semibold ${l.band}`}
        >
          {badge.visible.map((v) => (
            <li key={v}>{v}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** A storyteller's badge: name and role, no status or visible traits. Initials
 * rather than Horatio's logo, whose dark shield would take a lot of ink. */
function StaffBadge({ staff, troupe, look, size }: { staff: StaffBadgeOut; troupe: string | null; look: Look; size: BadgeSize }) {
  const l = LOOKS[look];
  const [card, step] = useSqueeze();
  const { inch, pt, name } = scale(size, step);
  return (
    <Card look={look} label={`Badge for ${staff.name}`} troupe={troupe} size={size} step={step} card={card}>
      <Initials name={staff.name} colour={l.ink} size={size} step={step} />
      <h2 className="text-center font-display leading-tight tracking-wide uppercase" style={{ marginTop: inch(0.15), fontSize: name(staff.name) }}>
        {staff.name}
      </h2>
      <p className={`text-center ${l.accent}`} style={{ marginTop: inch(0.05), fontSize: pt(15) }}>
        {staff.role}
      </p>
      <div className={`mx-auto mt-auto w-1/2 border-t ${l.frame}`} style={{ marginBottom: inch(0.1) }} />
    </Card>
  );
}
