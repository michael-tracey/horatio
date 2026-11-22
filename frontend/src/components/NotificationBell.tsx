import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { api, unwrap } from "../api/client";
import type { NotificationOut } from "../api/types";
import { useDates } from "../dates";
import { useAction, useNotifications } from "../hooks";
import { withNext } from "../next";
import { Avatar } from "./Avatar";
import { EmptyState } from "./EmptyState";
import { groupNotices, type NoticeRow } from "./noticeGroups";
import { PlayerInLine } from "./PlayerInLine";
import { PostThumb } from "./PostThumb";
import { Button, CountBubble } from "./ui";

const RELATIVE = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

/** "5 minutes ago", "yesterday", and so on. */
export function timeAgo(at: string, now = Date.now()): string {
  const seconds = Math.round((new Date(at).getTime() - now) / 1000);
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["second", 60],
    ["minute", 60],
    ["hour", 24],
    ["day", 7],
    ["week", 4.35],
    ["month", 12],
    ["year", Infinity],
  ];
  let value = seconds;
  for (const [unit, size] of steps) {
    if (Math.abs(value) < size) return RELATIVE.format(Math.round(value), unit);
    value /= size;
  }
  return RELATIVE.format(Math.round(value), "year");
}

/** The page where someone held to two-step sign-in sets it up (#1057). */
const TWO_STEP = "/two-step";

/**
 * The bell in the menu bar: work waiting on you, then messages. Each opens where to deal with it.
 * Similar unread messages gather into one row, which opens to list them and can be marked read
 * at once (#1196); the number on the bell still counts each.
 *
 * `beforeSetup`, until they set up two-step sign-in, when the bell is all that answers (#1111):
 * a notice opens in place, read in full, as its page would only send them back to set it up,
 * and a player it names is plain text; the foot has a way to the setup form instead of the
 * notification settings (#1146).
 */
export function NotificationBell({ beforeSetup = false }: { beforeSetup?: boolean }) {
  const bell = useNotifications(true);
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  // The notice opened in place, before setup.
  const [shown, setShown] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const read = useAction((ids?: string[]) => unwrap(api.POST("/api/notifications/read", { body: { ids: ids ?? null } })));

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const items = bell.data?.items ?? [];
  const tasks = items.filter((i) => i.task);
  const messages = items.filter((i) => !i.task);
  const unread = messages.filter((i) => !i.read);

  const go = (item: NotificationOut) => {
    if (!item.task && !item.read) read.mutate([item.id]);
    if (beforeSetup) return setShown(shown === item.id ? null : item.id);
    setOpen(false);
    // A link elsewhere, such as a Discord channel or invite (#855), opens in a tab of its own.
    if (/^https?:\/\//i.test(item.link)) window.open(item.link, "_blank", "noopener,noreferrer");
    else navigate(item.link);
  };

  return (
    <div ref={box} className="relative">
      <button
        aria-label={bell.data?.count ? `Notifications, ${bell.data.count} waiting` : "Notifications"}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="relative grid h-9 w-9 place-items-center rounded-full text-mist hover:bg-ash/60 hover:text-parchment"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" strokeLinejoin="round" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" strokeLinecap="round" />
        </svg>
        <span className="absolute -top-0.5 -right-0.5">
          <CountBubble count={bell.data?.count ?? 0} label="waiting" />
        </span>
      </button>
      {/* On a computer the bell sits in the top bar's nav, whose links don't wrap; its notices do (#1123). */}
      {open && (
        <div
          role="dialog"
          aria-label="Notifications"
          className="fixed inset-x-4 top-16 z-20 max-h-[70vh] overflow-y-auto rounded-lg border border-ash bg-dusk whitespace-normal shadow-xl sm:absolute sm:inset-x-auto sm:top-full sm:right-0 sm:mt-2 sm:w-96"
        >
          {items.length === 0 && (
            <div className="px-4 py-2">
              <EmptyState title="Nothing waiting.">Tasks waiting on you, and messages for you, show here as they come.</EmptyState>
            </div>
          )}
          {tasks.length > 0 && <Group title="Waiting on you" items={tasks} onOpen={go} onFollow={() => setOpen(false)} inPlace={beforeSetup} shown={shown} />}
          {messages.length > 0 && (
            <Group
              title="Messages"
              items={messages}
              onOpen={go}
              onFollow={() => setOpen(false)}
              onRead={(ids) => read.mutate(ids)}
              inPlace={beforeSetup}
              shown={shown}
              grouped
              action={
                unread.length > 0 && (
                  <button className="text-xs text-mist hover:text-parchment" onClick={() => read.mutate(undefined)}>
                    Mark all read
                  </button>
                )
              }
            />
          )}
          {beforeSetup ? (
            <div className="px-4 py-3">
              <Button
                className="w-full"
                onClick={() => {
                  setOpen(false);
                  // Back to the form from a page open before setup, such as Help, to come back there after.
                  if (location.pathname !== TWO_STEP) navigate(withNext(TWO_STEP, location.pathname + location.search + location.hash));
                }}
              >
                Set up two-step sign-in
              </Button>
            </div>
          ) : (
            <div className="px-4 py-2.5 text-right">
              <Link to="/account/notifications" onClick={() => setOpen(false)} className="text-xs text-mist underline hover:text-parchment">
                Notification settings
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Group({
  title,
  items,
  onOpen,
  onFollow,
  onRead,
  inPlace = false,
  shown = null,
  action,
  grouped = false,
}: {
  title: string;
  items: NotificationOut[];
  onOpen: (i: NotificationOut) => void;
  /** A link in a line, such as a player's name, was followed (#1131). */
  onFollow: () => void;
  /** Mark these read: a gathered row's messages (#1196). */
  onRead?: (ids: string[]) => void;
  /** Each line opens in place, `shown` the one open (#1146). */
  inPlace?: boolean;
  shown?: string | null;
  action?: React.ReactNode;
  /** Similar unread messages gather into one row, opened to list them (#1196). */
  grouped?: boolean;
}) {
  const dates = useDates();
  // The gathered rows open now, by their key.
  const [opened, setOpened] = useState<string[]>([]);
  const rows: NoticeRow[] = grouped ? groupNotices(items) : items.map((item) => ({ group: false, item }));
  const row = (item: NotificationOut) => <Notice key={item.id} item={item} onOpen={onOpen} onFollow={onFollow} inPlace={inPlace} shown={shown} />;
  return (
    <section className="border-b border-ash last:border-b-0">
      <h2 className="flex items-center justify-between px-4 pt-3 pb-1 font-sans text-xs tracking-wide text-mist uppercase">
        {title}
        {action}
      </h2>
      <ul>
        {rows.map((r) => {
          if (!r.group) return row(r.item);
          const open = opened.includes(r.key);
          const newest = r.items[0]!;
          // Their troupe, if they share one.
          const troupe = r.items.every((i) => i.troupe_name === newest.troupe_name) ? newest.troupe_name : null;
          const list = `notice-group-${r.key}`;
          return (
            <li key={r.key}>
              <div className="flex items-start hover:bg-ash/40">
                <button
                  onClick={() => setOpened(open ? opened.filter((k) => k !== r.key) : [...opened, r.key])}
                  aria-expanded={open}
                  aria-controls={list}
                  className="flex min-w-0 flex-1 gap-3 py-2.5 pl-4 text-left"
                >
                  <span aria-hidden="true" className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-gold" />
                  <span className="min-w-0">
                    <span className="block text-sm text-parchment">
                      {r.label}
                      <Chevron open={open} />
                    </span>
                    <span className="block text-xs text-mist">
                      {troupe && `${troupe} · `}
                      <time dateTime={newest.at} title={dates.dateTime(newest.at)}>
                        {timeAgo(newest.at)}
                      </time>
                    </span>
                  </span>
                </button>
                {onRead && (
                  <button onClick={() => onRead(r.items.map((i) => i.id))} aria-label={`Mark ${r.label} read`} className="shrink-0 px-4 py-2.5 text-xs text-mist hover:text-parchment">
                    Mark read
                  </button>
                )}
              </div>
              {open && (
                <ul id={list} aria-label={r.label} className="border-l border-ash/60 ml-5">
                  {r.items.map(row)}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      className={`ml-1 inline h-3.5 w-3.5 align-[-2px] text-mist transition-transform ${open ? "rotate-180" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <path d="m5 8 5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** One task or message: opens where to deal with it, or in place before setup (#1146). */
function Notice({ item, onOpen, onFollow, inPlace, shown }: { item: NotificationOut; onOpen: (i: NotificationOut) => void; onFollow: () => void; inPlace: boolean; shown: string | null }) {
  const dates = useDates();
  // A line naming a player links their name to their profile (#1131). A link can't sit
  // in a button, so its row's button lies over the row, named by the line, and the link over that.
  const named = !inPlace && Boolean(item.player_id && item.player_name);
  const line = `notice-${item.id}`;
  // In place, a line is cut to two until opened, then read in full with its date and time.
  const full = inPlace && shown === item.id;
  const inside = (
    <>
      <span aria-hidden="true" className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${item.task ? "bg-blood-bright" : item.read ? "" : "bg-gold"}`} />
      {item.picture && (item.kind === "announcement.published" ? <PostThumb picture={item.picture} className="h-9 w-9" /> : <Avatar name="" picture={item.picture} size="sm" />)}
      <span className="min-w-0">
        <span id={named ? line : undefined} className={`block text-sm ${item.read ? "text-mist" : "text-parchment"} ${inPlace && !full ? "line-clamp-2" : ""}`}>
          {named ? <PlayerInLine text={item.summary} playerId={item.player_id} playerName={item.player_name} onFollow={onFollow} className="relative z-20" /> : item.summary}
        </span>
        <span className="block text-xs text-mist">
          {item.troupe_name && `${item.troupe_name} · `}
          <time dateTime={item.at} title={dates.dateTime(item.at)}>
            {full ? dates.dateTime(item.at) : timeAgo(item.at)}
          </time>
        </span>
      </span>
    </>
  );
  return (
    <li>
      {named ? (
        <div className="relative flex w-full gap-3 px-4 py-2.5 text-left hover:bg-ash/40">
          <button onClick={() => onOpen(item)} aria-labelledby={line} className="absolute inset-0 z-10" />
          {inside}
        </div>
      ) : (
        <button onClick={() => onOpen(item)} aria-expanded={inPlace ? full : undefined} className="flex w-full gap-3 px-4 py-2.5 text-left hover:bg-ash/40">
          {inside}
        </button>
      )}
    </li>
  );
}
