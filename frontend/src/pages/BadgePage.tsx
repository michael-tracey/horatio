import { useQuery } from "@tanstack/react-query";
import { useState, type CSSProperties, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../api/client";
import type { BadgeOut, StaffBadgeOut } from "../api/types";
import { clanColour, initials } from "../components/avatar";
import { nameSize, pages, standing } from "./badgeLayout";

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
    <Sheets back={`/characters/${characterId}`} troupe={badges.data.troupe_name} items={badges.data.badges.map((b) => ({ key: b.character_id, badge: b }))} />
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
 * The badges on paper: on screen, side by side with Back, Print and the choice
 * of look above; printed, two to a US Letter page with cut marks at the corners.
 */
function Sheets({ items, back, troupe }: { items: Item[]; back: string; troupe: string | null }) {
  const [look, setLook] = useState<Look>("horatio");
  return (
    <div className="min-h-screen bg-neutral-200 py-6 text-black print:min-h-0 print:bg-white print:py-0">
      {/* Badges fill the paper themselves: no page margin, no browser header. */}
      <style>{"@page { size: letter; margin: 0; }"}</style>
      <div className="mx-auto mb-4 flex max-w-[8.5in] flex-wrap items-center justify-between gap-3 px-4 print:hidden">
        {/* A link, not history: badges open in a tab of their own. */}
        <Link to={back} className="text-sm underline">
          ← Back
        </Link>
        <span className="text-sm">
          {items.length === 1 ? "1 badge" : `${items.length} badges`} · 3 × 5 in, two to a page
        </span>
        <span className="flex items-center gap-3">
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
      {pages(items).map((page, i) => (
        <section
          key={i}
          aria-label={`Page ${i + 1}`}
          className="mx-auto mb-6 flex max-w-[8.5in] flex-wrap justify-center gap-6 px-4 print:mb-0 print:h-[11in] print:w-[8.5in] print:max-w-none print:flex-nowrap print:items-center print:gap-[0.3in] print:px-0 print:break-after-page"
        >
          {page.map((item) =>
            item.badge ? (
              <Cut key={item.key}>
                <CharacterBadge badge={item.badge} troupe={troupe} look={look} />
              </Cut>
            ) : item.staff ? (
              <Cut key={item.key}>
                <StaffBadge staff={item.staff} troupe={troupe} look={look} />
              </Cut>
            ) : null,
          )}
        </section>
      ))}
    </div>
  );
}

/** A badge with short marks just outside its corners, to cut along. */
function Cut({ children }: { children: ReactNode }) {
  const mark = "absolute hidden bg-black print:block";
  const h = `${mark} h-px w-[0.18in]`;
  const v = `${mark} w-px h-[0.18in]`;
  return (
    <div className="relative">
      {children}
      <span className={`${h} top-0 -left-[0.24in]`} />
      <span className={`${v} -top-[0.24in] left-0`} />
      <span className={`${h} top-0 -right-[0.24in]`} />
      <span className={`${v} -top-[0.24in] right-0`} />
      <span className={`${h} bottom-0 -left-[0.24in]`} />
      <span className={`${v} -bottom-[0.24in] left-0`} />
      <span className={`${h} bottom-0 -right-[0.24in]`} />
      <span className={`${v} -bottom-[0.24in] right-0`} />
    </div>
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

/** The badge's card, white, with the troupe's name small on its bottom line. */
function Card({ look, label, troupe, children }: { look: Look; label: string; troupe: string | null; children: ReactNode }) {
  return (
    <article
      aria-label={label}
      style={exact}
      className={`relative flex h-[5in] w-[3in] flex-col overflow-hidden border-[0.03in] bg-white px-[0.15in] pt-[0.15in] font-serif text-[#141016] shadow print:shadow-none ${LOOKS[look].card}`}
    >
      {children}
      <p className="h-[0.25in] shrink-0 truncate pt-[0.06in] text-center text-[7.5pt] tracking-wide">{troupe}</p>
    </article>
  );
}

/** The portrait (4:5) with the clan logo beside it; without a picture the logo,
 * larger; with neither, the initials. */
function Top({ name, picture, logo, clan, look }: { name: string; picture: string | null; logo: string | null; clan: string | null; look: Look }) {
  const frame = LOOKS[look].frame;
  if (picture) {
    return (
      <div className="flex h-[2in] shrink-0 items-start justify-center gap-[0.1in]">
        <img src={`${picture}/portrait.jpg`} alt="" className={`h-[2in] w-[1.6in] border object-cover ${frame}`} />
        {logo && <img src={`${logo}/600.webp`} alt={`${clan} logo`} className="h-[0.85in] w-[0.85in] object-contain" />}
      </div>
    );
  }
  if (logo) {
    return (
      <div className="flex h-[2in] shrink-0 justify-center">
        <img src={`${logo}/600.webp`} alt={`${clan} logo`} className="h-[1.9in] w-[1.9in] object-contain" />
      </div>
    );
  }
  return <Initials name={name} colour={look === "horatio" ? clanColour(clan) : LOOKS.plain.ink} />;
}

/** The name's initials in a ring, outlined rather than filled to spare the ink. */
function Initials({ name, colour }: { name: string; colour: string }) {
  return (
    <div className="flex h-[2in] shrink-0 justify-center">
      <span
        style={{ color: colour, borderColor: colour }}
        className="grid h-[1.9in] w-[1.9in] place-items-center rounded-full border-[0.04in] font-display text-[54pt] leading-none"
      >
        {initials(name)}
      </span>
    </div>
  );
}

function CharacterBadge({ badge, troupe, look }: { badge: BadgeOut; troupe: string | null; look: Look }) {
  const l = LOOKS[look];
  return (
    <Card look={look} label={`Badge for ${badge.name}`} troupe={troupe}>
      <Top name={badge.name} picture={badge.picture} logo={badge.logo} clan={badge.clan} look={look} />
      <h2 className="mt-[0.1in] text-center font-display leading-tight tracking-wide uppercase" style={{ fontSize: `${nameSize(badge.name)}pt` }}>
        {badge.name}
      </h2>
      <p className={`text-center text-[12.5pt] ${l.accent}`}>{standing(badge.clan, badge.social_age)}</p>
      {badge.titles.length > 0 && <p className="text-center text-[11pt] leading-snug italic">{badge.titles.join(", ")}</p>}
      <p className="mt-[0.1in] text-[10.5pt] leading-snug">
        <span className={`font-bold ${l.accent}`}>Status:</span> {badge.status.join(", ") || "—"}
      </p>
      {/* Left empty for the stickers most troupes mark status with. */}
      <div className="min-h-[0.5in] flex-1" />
      {badge.visible.length > 0 && (
        <ul
          aria-label="What others can see"
          style={exact}
          className={`-mx-[0.15in] flex min-h-[0.5in] flex-col items-center justify-center px-[0.15in] py-[0.08in] text-center text-[10pt] leading-snug font-semibold ${l.band}`}
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
function StaffBadge({ staff, troupe, look }: { staff: StaffBadgeOut; troupe: string | null; look: Look }) {
  const l = LOOKS[look];
  return (
    <Card look={look} label={`Badge for ${staff.name}`} troupe={troupe}>
      <Initials name={staff.name} colour={l.ink} />
      <h2 className="mt-[0.15in] text-center font-display leading-tight tracking-wide uppercase" style={{ fontSize: `${nameSize(staff.name)}pt` }}>
        {staff.name}
      </h2>
      <p className={`mt-[0.05in] text-center text-[15pt] ${l.accent}`}>{staff.role}</p>
      <div className={`mx-auto mt-auto mb-[0.1in] w-1/2 border-t ${l.frame}`} />
    </Card>
  );
}
