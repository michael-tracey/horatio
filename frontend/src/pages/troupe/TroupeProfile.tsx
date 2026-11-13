import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import type { ProfilePerson, TroupeProfileOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { AtHandle } from "../../components/PersonPicker";
import { Badge, Button, Card } from "../../components/ui";
import { useDates } from "../../dates";
import { withNext } from "../../next";
import { filled, linksOf, newPlayersText, type LinkKind } from "./profile";
import { Games, Pictures, ProfilePartEditor, type ProfilePart } from "./ProfileEditor";
import { SettingDocumentFor } from "./SettingDocument";
import { WrittenRulesList } from "./WrittenRulesList";

/**
 * A troupe's profile: its portrait, links, schedule, venue, setting, new players
 * and age and content notes, each part shown only when it has something in it; and
 * its Setting Style Document and written house rules when its storytellers show them.
 * The troupe's Overview shows it to anyone signed in; the public page (/t/…) to
 * anyone at all when the troupe has made it public. `signedIn` decides whether staff
 * link to their own pages, which only people signed in can open.
 *
 * With `edit` (its storytellers, on the Overview, #781), every part shows, empty or
 * not, each with its own Edit that changes that card in place; the portrait, links
 * and new players get cards of their own.
 */
export function TroupeProfileView({ profile: p, signedIn, edit = false }: { profile: TroupeProfileOut; signedIn: boolean; edit?: boolean }) {
  const dates = useDates();
  const [next, ...later] = p.games;
  const links = linksOf(p.links);
  const newPlayers = newPlayersText(p.new_players);
  const venue = p.venue;
  const setting = p.setting;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <Avatar name={p.name} picture={p.portrait} size="lg" className="h-20 w-20 sm:h-28 sm:w-28" />
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <p className="text-sm whitespace-pre-line">{p.description || "No description yet."}</p>
          {(newPlayers || p.min_age !== null) && (
            <div className="flex flex-wrap gap-2">
              {newPlayers && <Badge tone={p.new_players === "welcoming" ? "gold" : "mist"}>{newPlayers}</Badge>}
              {p.min_age !== null && <Badge>{p.min_age}+</Badge>}
            </div>
          )}
          {next && (
            <p className="text-sm">
              <span className="text-mist">Next game:</span> <span className="font-medium text-parchment">{dates.gameStart(next.starts_at)}</span>
            </p>
          )}
          {links.length > 0 && (
            <ul className="flex flex-wrap gap-2" aria-label="Links">
              {links.map((link) => (
                <li key={link.kind}>
                  <a
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    className="inline-flex min-h-9 items-center gap-2 rounded-full border border-ash px-3 text-sm text-parchment hover:border-gold hover:text-gold"
                  >
                    <LinkIcon kind={link.kind} />
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {edit && (
          <Card title="Portrait and banner">
            <Pictures profile={p} />
          </Card>
        )}
        {edit && (
          <Part profile={p} part="links" title="Links" show={links.length > 0}>
            <ul className="flex flex-col gap-1 text-sm">
              {links.map((link) => (
                <li key={link.kind}>
                  <span className="text-mist">{link.label}:</span> <span className="break-all">{link.url}</span>
                </li>
              ))}
            </ul>
          </Part>
        )}
        <Part
          profile={p}
          part="when"
          title="When it plays"
          show={filled(p.schedule) || p.games.length > 0}
          edit={edit}
          more={<Games profile={p} />}
        >
          {p.schedule && <p className="text-sm whitespace-pre-line">{p.schedule}</p>}
          {p.games.length > 0 && (
            <ul className={`flex flex-col gap-1 text-sm ${p.schedule ? "mt-3" : ""}`} aria-label="Upcoming games">
              {[next!, ...later].map((g) => (
                <li key={g.id}>
                  <time dateTime={g.starts_at}>{dates.game(g.starts_at, g.ends_at)}</time>
                </li>
              ))}
            </ul>
          )}
        </Part>
        <Part
          profile={p}
          part="where"
          title="Where it plays"
          show={filled(venue.region, venue.name, venue.address, venue.access) || venue.address_hidden}
          edit={edit}
        >
          <dl className="flex flex-col gap-2 text-sm">
            <Entry label="City or region">{venue.region}</Entry>
            <Entry label="Venue">{venue.name}</Entry>
            <Entry label="Address">
              {venue.address ||
                (venue.address_hidden && (
                  <span className="text-mist">
                    <Link to={withNext("/sign-in", `/t/${p.id}`)} className="text-gold underline">
                      Sign in
                    </Link>{" "}
                    to see the address.
                  </span>
                ))}
            </Entry>
            <Entry label="Accessibility">{venue.access}</Entry>
          </dl>
        </Part>
        <Part profile={p} part="setting" title="The setting" show={filled(setting.chronicle, setting.city, setting.era)} edit={edit}>
          <dl className="flex flex-col gap-2 text-sm">
            <Entry label="Chronicle">{setting.chronicle}</Entry>
            <Entry label="Set in">{setting.city}</Entry>
            <Entry label="Era">{setting.era}</Entry>
          </dl>
        </Part>
        {edit && (
          <Part profile={p} part="newcomers" title="New players" show={!!newPlayers || !!p.contact}>
            <dl className="flex flex-col gap-2 text-sm">
              <Entry label="Taking new players?">{newPlayers}</Entry>
              <Entry label="Contact for new players">{p.contact && <Person person={p.contact} signedIn={signedIn} />}</Entry>
            </dl>
          </Part>
        )}
        <Card title="People">
          <dl className="flex flex-col gap-2 text-sm">
            <Entry label="Lead storyteller">
              <Person person={p.lead} signedIn={signedIn} />
            </Entry>
            <Entry label="Contact for new players">{p.contact && <Person person={p.contact} signedIn={signedIn} />}</Entry>
          </dl>
        </Card>
        {edit ? (
          <Part profile={p} part="age" title="Age and content" show={p.min_age !== null || filled(p.content_notes)}>
            <dl className="flex flex-col gap-2 text-sm">
              <Entry label="Minimum age">{p.min_age !== null && `${p.min_age}+`}</Entry>
              <Entry label="Content notes">{p.content_notes}</Entry>
            </dl>
          </Part>
        ) : (
          filled(p.content_notes) && (
            <Card title="Content notes">
              <p className="text-sm whitespace-pre-line">{p.content_notes}</p>
            </Card>
          )
        )}
        {p.setting_document && (
          <Card title="Setting Style Document" className="md:col-span-2">
            <SettingDocumentFor troupeId={p.id} />
          </Card>
        )}
        {p.written_rules.length > 0 && (
          <Card title="House rules" className="md:col-span-2">
            <WrittenRulesList rules={p.written_rules} troupeId={signedIn ? p.id : undefined} />
          </Card>
        )}
      </div>
    </div>
  );
}

/**
 * A part of the profile in its card. Read only, it shows only when it has something
 * in it. With `edit` it always shows, and its Edit turns the card into that part's
 * form (and `more`, what saves on its own, such as the games) until saved or cancelled.
 */
function Part({
  profile,
  part,
  title,
  show,
  edit = true,
  more,
  children,
}: {
  profile: TroupeProfileOut;
  part: ProfilePart;
  title: string;
  show: boolean;
  edit?: boolean;
  more?: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  if (!edit) return show ? <Card title={title}>{children}</Card> : null;
  const what = title.charAt(0).toLowerCase() + title.slice(1);
  return (
    <Card
      title={title}
      // Open, it takes the whole row: its form needs the room (the games' dates and Add game side by side).
      className={open ? "md:col-span-2" : undefined}
      actions={
        !open && (
          <Button variant="ghost" className="min-h-8 px-2" aria-label={`Edit ${what}`} onClick={() => setOpen(true)}>
            Edit
          </Button>
        )
      }
    >
      {open ? (
        <div className="flex flex-col gap-4">
          <ProfilePartEditor profile={profile} part={part} onDone={() => setOpen(false)} />
          {more && <div className="border-t border-ash pt-4">{more}</div>}
        </div>
      ) : show ? (
        children
      ) : (
        <p className="text-sm text-mist">Nothing yet.</p>
      )}
    </Card>
  );
}

/** One line of a part of the profile, left out when it has nothing in it. */
function Entry({ label, children }: { label: string; children: ReactNode }) {
  if (!children) return null;
  return (
    <div>
      <dt className="text-xs text-mist">{label}</dt>
      <dd className="whitespace-pre-line">{children}</dd>
    </div>
  );
}

/** A staff member by display name and handle; never their email. */
function Person({ person, signedIn }: { person: ProfilePerson; signedIn: boolean }) {
  const name = signedIn ? (
    <Link to={`/players/${person.id}`} className="text-gold hover:underline">
      {person.display_name}
    </Link>
  ) : (
    person.display_name
  );
  return (
    <>
      {name} <AtHandle handle={person.handle} />
    </>
  );
}

/** Each link's icon: simple shapes, in the text's own colour. */
export function LinkIcon({ kind }: { kind: LinkKind }) {
  const common = { width: 16, height: 16, viewBox: "0 0 24 24", "aria-hidden": true, className: "shrink-0" } as const;
  const line = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;
  switch (kind) {
    case "website":
      return (
        <svg {...common} {...line}>
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z" />
        </svg>
      );
    case "discord":
      return (
        <svg {...common} fill="currentColor">
          <path d="M19.3 5.3A16.6 16.6 0 0 0 15.2 4l-.5 1a15.3 15.3 0 0 0-5.4 0l-.5-1a16.6 16.6 0 0 0-4.1 1.3C2.1 9.2 1.4 13 1.8 16.8A16.7 16.7 0 0 0 6.8 19.3l1.1-1.7c-.6-.2-1.2-.5-1.7-.9l.4-.3a11.9 11.9 0 0 0 10.8 0l.4.3c-.5.4-1.1.7-1.7.9l1.1 1.7a16.7 16.7 0 0 0 5-2.5c.5-4.4-.8-8.2-2.9-11.5zM8.7 14.5c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2zm6.6 0c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2z" />
        </svg>
      );
    case "facebook":
      return (
        <svg {...common} fill="currentColor">
          <path d="M13.5 21v-7.5h2.6l.4-3h-3V8.6c0-.9.3-1.5 1.5-1.5h1.6V4.4a21 21 0 0 0-2.3-.1c-2.3 0-3.9 1.4-3.9 4v2.2H7.8v3h2.6V21h3.1z" />
        </svg>
      );
    case "instagram":
      return (
        <svg {...common} {...line}>
          <rect x="3.5" y="3.5" width="17" height="17" rx="5" />
          <circle cx="12" cy="12" r="4" />
          <circle cx="17.2" cy="6.8" r="0.6" fill="currentColor" />
        </svg>
      );
    case "join":
      return (
        <svg {...common} {...line}>
          <circle cx="9" cy="8" r="4" />
          <path d="M2 21c0-3.9 3.1-7 7-7s7 3.1 7 7M19 8v6M16 11h6" />
        </svg>
      );
  }
}
